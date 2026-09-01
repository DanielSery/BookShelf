"""Book shelf, with a Claude session behind it.

Serves index.html and the book-*.json(l) files, and drives the /book-log,
/book-screen and /book-suggest skills through the Claude Agent SDK. The page
never writes data: it sends prompts, the skills write files, a PostToolUse hook
tells the page which file moved, and the page reloads it.

Runs on the Claude subscription via the CLI's stored login. Loopback only.

    python serve.py [--port 8777]
"""
from __future__ import annotations

import argparse
import asyncio
import contextlib
import json
import os
import sys
import time
import uuid
from pathlib import Path
from typing import Any

from claude_agent_sdk import (
    AssistantMessage,
    ClaudeAgentOptions,
    ClaudeSDKClient,
    HookMatcher,
    RateLimitEvent,
    ResultMessage,
    SystemMessage,
    TextBlock,
    ThinkingBlock,
    ToolUseBlock,
    list_sessions,
    query,
)
from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, StreamingResponse
from starlette.routing import Mount, Route
from starlette.staticfiles import StaticFiles

REPO = Path(__file__).resolve().parent
# Resolved, because TEMP on Windows is the 8.3 short form (DANIEL~2) while a
# resolved candidate path is the long one — an unresolved prefix never matches.
SCRATCH = (Path(os.environ.get("TEMP", "/tmp")) / "book-shelf-scratch").resolve()
SESSION_FILE = REPO / ".web-session.json"
READING_FILE = REPO / "book-reading.json"

# The skills own these files; nothing else in the repo may be written by a
# session started from the page. Keep in sync with the ownership table in
# .claude/skills/book-suggest/SKILL.md.
WRITABLE = {
    "book-cache.json", "book-estimates.jsonl", "book-rejects.jsonl",
    "book-revs.json", "book-media.json", "book-recommendations.md",
    "books-read.md", "book-triage.jsonl", "book-ai-rank.jsonl",
    "book-origin.json",
}

# book-reading.json is deliberately absent from WRITABLE: the page owns it and
# writes it through /api/reading while you type. An agent rewriting the whole
# file would clobber an in-flight note.

IDLE_TIMEOUT_S = 600
MAX_TURNS_CHAT = 40
MAX_TURNS_JOB = 300


# ---------------------------------------------------------------- event bus

class Bus:
    def __init__(self) -> None:
        self._subs: set[asyncio.Queue[str]] = set()

    def subscribe(self) -> asyncio.Queue[str]:
        q: asyncio.Queue[str] = asyncio.Queue(maxsize=1000)
        self._subs.add(q)
        return q

    def unsubscribe(self, q: asyncio.Queue[str]) -> None:
        self._subs.discard(q)

    def send(self, event: dict[str, Any]) -> None:
        payload = json.dumps(event, ensure_ascii=False)
        for q in list(self._subs):
            try:
                q.put_nowait(payload)
            except asyncio.QueueFull:
                self._subs.discard(q)


BUS = Bus()


# -------------------------------------------------------------------- hooks

def _resolve(raw: str) -> Path | None:
    if not raw:
        return None
    try:
        return Path(raw).expanduser().resolve()
    except OSError:
        return None


def _write_allowed(path: Path | None) -> bool:
    if path is None:
        return False
    if path.is_relative_to(SCRATCH):
        return True
    return path.parent == REPO and path.name in WRITABLE


async def guard_writes(input_data, tool_use_id, context):
    path = _resolve(input_data.get("tool_input", {}).get("file_path", ""))
    if _write_allowed(path):
        return {}
    shown = path.name if path else "(no path)"
    return {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": (
                f"{shown} is not a shelf data file. This session may only write the "
                f"book-* data files in {REPO} or scratch files under {SCRATCH}."
            ),
        }
    }


async def announce_writes(input_data, tool_use_id, context):
    path = _resolve(input_data.get("tool_input", {}).get("file_path", ""))
    if path is not None and path.parent == REPO and path.name in WRITABLE:
        BUS.send({"type": "changed", "file": path.name})
    return {}


def _tool_detail(name: str, args: dict[str, Any]) -> str:
    for key in ("file_path", "pattern", "command", "url", "skill", "description"):
        if args.get(key):
            return str(args[key])[:160]
    return ""


UI_STATE: dict[str, Any] = {}


async def inject_context(input_data, tool_use_id, context):
    lines = [
        f"Today is {time.strftime('%Y-%m-%d')}.",
        f"This prompt came from the book shelf web app. The shelf repo is {REPO} and it is "
        f"your working directory, so the book-* data files are in the current directory.",
        f"Use scratch directory {SCRATCH} for any working files; you may not write anywhere "
        f"else except the book-* data files.",
    ]
    now_reading = read_reading()["reading"]
    if now_reading:
        titles = ", ".join(f"{e.get('title')} ({e.get('author') or 'author unknown'})"
                           for e in now_reading.values())
        lines.append(
            f"Books on the reading shelf right now: {titles}. Their in-progress notes are in "
            f"book-reading.json, which you may read but not write — the web page owns it."
        )
    if UI_STATE:
        lines.append("Current view in the app: " + json.dumps(UI_STATE, ensure_ascii=False))
    return {
        "hookSpecificOutput": {
            "hookEventName": "UserPromptSubmit",
            "additionalContext": "\n".join(lines),
        }
    }


def build_options(*, resume: str | None, max_turns: int, shell: bool) -> ClaudeAgentOptions:
    # An ANTHROPIC_API_KEY inherited from any other project would silently switch
    # this from the subscription to pay-as-you-go API billing, with no error.
    env = {k: v for k, v in os.environ.items() if k != "ANTHROPIC_API_KEY"}
    tools = ["Read", "Grep", "Glob", "Edit", "Write", "Skill", "WebFetch", "WebSearch"]
    # allowed_tools pre-approves, it does not restrict — Bash stays reachable
    # unless it is denied outright, and Bash can write any file the guard_writes
    # hook is there to protect. Only the job lane, which runs tools/*.py, gets it.
    return ClaudeAgentOptions(
        cwd=str(REPO),
        env=env,
        setting_sources=["user", "project"],
        skills="all",
        allowed_tools=tools + (["Bash"] if shell else []),
        disallowed_tools=[] if shell else ["Bash"],
        permission_mode="default",
        max_turns=max_turns,
        resume=resume,
        add_dirs=[str(SCRATCH)],
        hooks={
            "PreToolUse": [HookMatcher(matcher="Write|Edit", hooks=[guard_writes])],
            "PostToolUse": [HookMatcher(matcher="Write|Edit", hooks=[announce_writes])],
            "UserPromptSubmit": [HookMatcher(hooks=[inject_context])],
        },
    )


# ---------------------------------------------------------------- reading shelf

READING_FIELDS = {"key", "title", "altTitle", "author", "cover",
                  "started", "progress", "notes", "sent"}


def read_reading() -> dict[str, Any]:
    try:
        doc = json.loads(READING_FILE.read_text("utf-8"))
    except (OSError, ValueError):
        return {"reading": {}}
    return doc if isinstance(doc.get("reading"), dict) else {"reading": {}}


def _write_reading(doc: dict[str, Any]) -> None:
    tmp = READING_FILE.with_name(READING_FILE.name + ".tmp")
    tmp.write_text(json.dumps(doc, ensure_ascii=False, indent=2), "utf-8")
    tmp.replace(READING_FILE)


# --------------------------------------------------------------- lane plumbing

def emit_message(msg: Any, lane: str) -> None:
    if isinstance(msg, AssistantMessage):
        for block in msg.content:
            if isinstance(block, TextBlock) and block.text.strip():
                BUS.send({"type": "text", "lane": lane, "text": block.text})
            elif isinstance(block, ThinkingBlock):
                BUS.send({"type": "thinking", "lane": lane})
            elif isinstance(block, ToolUseBlock):
                BUS.send({"type": "tool", "lane": lane, "name": block.name,
                          "detail": _tool_detail(block.name, block.input or {})})
    elif isinstance(msg, SystemMessage):
        if msg.subtype == "init":
            BUS.send({"type": "init", "lane": lane,
                      "session_id": msg.data.get("session_id"),
                      "skills": msg.data.get("skills", []),
                      "commands": msg.data.get("slash_commands", [])})
    elif isinstance(msg, RateLimitEvent):
        info = msg.rate_limit_info
        BUS.send({"type": "ratelimit", "lane": lane, "status": info.status,
                  "resets_at": info.resets_at, "utilization": info.utilization,
                  "limit_type": info.rate_limit_type})
    elif isinstance(msg, ResultMessage):
        BUS.send({"type": "result", "lane": lane, "subtype": msg.subtype,
                  "is_error": msg.is_error, "session_id": msg.session_id,
                  "turns": msg.num_turns, "ms": msg.duration_ms,
                  "text": msg.result, "errors": msg.errors})


# ------------------------------------------------------------------ chat lane

class ChatLane:
    """One Claude session, spawned on demand and hung up when idle.

    The CLI process is disposable; the conversation is not. Session state lives
    on disk, so disconnecting costs nothing as long as the id is kept and passed
    back as `resume`.
    """

    def __init__(self) -> None:
        self.client: ClaudeSDKClient | None = None
        self.session_id: str | None = _load_session_id()
        self.last_used = 0.0
        self.busy = False
        self._lock = asyncio.Lock()

    async def _ensure(self) -> ClaudeSDKClient:
        if self.client is None:
            BUS.send({"type": "status", "lane": "chat", "state": "starting"})
            client = ClaudeSDKClient(options=build_options(
                resume=self.session_id, max_turns=MAX_TURNS_CHAT, shell=False))
            try:
                await client.connect()
            except Exception:
                # A stored id whose transcript is gone makes resume fail; a clean
                # session is better than a dead panel.
                if self.session_id is None:
                    raise
                self.session_id = None
                _save_session_id(None)
                client = ClaudeSDKClient(options=build_options(
                    resume=None, max_turns=MAX_TURNS_CHAT, shell=False))
                await client.connect()
            self.client = client
        self.last_used = time.monotonic()
        return self.client

    async def ask(self, text: str) -> None:
        async with self._lock:
            self.busy = True
            BUS.send({"type": "status", "lane": "chat", "state": "busy"})
            try:
                client = await self._ensure()
                await client.query(text)
                async for msg in client.receive_response():
                    emit_message(msg, "chat")
                    if isinstance(msg, ResultMessage) and msg.session_id:
                        if msg.session_id != self.session_id:
                            self.session_id = msg.session_id
                            _save_session_id(msg.session_id)
            except Exception as exc:
                BUS.send({"type": "error", "lane": "chat", "text": f"{type(exc).__name__}: {exc}"})
                await self.close()
            finally:
                self.busy = False
                self.last_used = time.monotonic()
                BUS.send({"type": "status", "lane": "chat", "state": "idle",
                          "session_id": self.session_id})

    async def interrupt(self) -> None:
        if self.client is not None and self.busy:
            with contextlib.suppress(Exception):
                await self.client.interrupt()

    async def close(self) -> None:
        client, self.client = self.client, None
        if client is not None:
            with contextlib.suppress(Exception):
                await client.disconnect()
            BUS.send({"type": "status", "lane": "chat", "state": "closed"})

    async def reap_loop(self) -> None:
        while True:
            await asyncio.sleep(30)
            if (self.client is not None and not self.busy
                    and time.monotonic() - self.last_used > IDLE_TIMEOUT_S):
                await self.close()


def _load_session_id() -> str | None:
    try:
        return json.loads(SESSION_FILE.read_text("utf-8")).get("session_id")
    except (OSError, ValueError):
        return None


def _save_session_id(sid: str | None) -> None:
    with contextlib.suppress(OSError):
        if sid is None:
            SESSION_FILE.unlink(missing_ok=True)
        else:
            SESSION_FILE.write_text(json.dumps({"session_id": sid}), "utf-8")


CHAT = ChatLane()
JOBS: dict[str, asyncio.Task] = {}


# ------------------------------------------------------------------- job lane

async def run_job(job_id: str, text: str) -> None:
    BUS.send({"type": "job", "id": job_id, "state": "running", "prompt": text})
    try:
        async for msg in query(prompt=text, options=build_options(
                resume=None, max_turns=MAX_TURNS_JOB, shell=True)):
            emit_message(msg, f"job:{job_id}")
    except asyncio.CancelledError:
        BUS.send({"type": "job", "id": job_id, "state": "cancelled"})
        raise
    except Exception as exc:
        BUS.send({"type": "error", "lane": f"job:{job_id}",
                  "text": f"{type(exc).__name__}: {exc}"})
    finally:
        JOBS.pop(job_id, None)
        BUS.send({"type": "job", "id": job_id, "state": "done"})


# ------------------------------------------------------------------- routes

async def sse(request: Request):
    q = BUS.subscribe()

    async def stream():
        yield b": connected\n\n"
        try:
            while True:
                try:
                    payload = await asyncio.wait_for(q.get(), timeout=20)
                except asyncio.TimeoutError:
                    yield b": ping\n\n"
                    continue
                yield f"data: {payload}\n\n".encode("utf-8")
        finally:
            BUS.unsubscribe(q)

    return StreamingResponse(stream(), media_type="text/event-stream", headers={
        "Cache-Control": "no-store", "X-Accel-Buffering": "no",
    })


async def post_prompt(request: Request):
    body = await request.json()
    text = (body.get("text") or "").strip()
    if not text:
        return JSONResponse({"error": "empty prompt"}, status_code=400)
    if body.get("ui"):
        UI_STATE.clear()
        UI_STATE.update(body["ui"])
    if CHAT.busy:
        return JSONResponse({"error": "busy"}, status_code=409)
    asyncio.create_task(CHAT.ask(text))
    return JSONResponse({"ok": True})


async def post_job(request: Request):
    body = await request.json()
    text = (body.get("text") or "").strip()
    if not text:
        return JSONResponse({"error": "empty prompt"}, status_code=400)
    job_id = uuid.uuid4().hex[:8]
    JOBS[job_id] = asyncio.create_task(run_job(job_id, text))
    return JSONResponse({"ok": True, "id": job_id})


async def post_cancel(request: Request):
    job_id = request.path_params["job_id"]
    task = JOBS.get(job_id)
    if task is None:
        return JSONResponse({"error": "no such job"}, status_code=404)
    task.cancel()
    return JSONResponse({"ok": True})


async def post_interrupt(request: Request):
    await CHAT.interrupt()
    return JSONResponse({"ok": True})


async def post_new_session(request: Request):
    await CHAT.close()
    CHAT.session_id = None
    _save_session_id(None)
    return JSONResponse({"ok": True})


async def post_resume(request: Request):
    body = await request.json()
    sid = (body.get("session_id") or "").strip()
    if not sid:
        return JSONResponse({"error": "session_id required"}, status_code=400)
    await CHAT.close()
    CHAT.session_id = sid
    _save_session_id(sid)
    return JSONResponse({"ok": True})


async def get_reading(request: Request):
    return JSONResponse(read_reading())


async def put_reading(request: Request):
    try:
        body = await request.json()
    except (ValueError, UnicodeDecodeError):
        return JSONResponse({"error": "body must be UTF-8 JSON"}, status_code=400)
    patch = {k: v for k, v in body.items() if k in READING_FIELDS}
    doc = read_reading()
    entry = doc["reading"].get(request.path_params["slug"], {})
    entry.update(patch)
    if not (entry.get("title") or "").strip():
        return JSONResponse({"error": "title required"}, status_code=400)
    entry["updated"] = time.strftime("%Y-%m-%d %H:%M")
    doc["reading"][request.path_params["slug"]] = entry
    _write_reading(doc)
    return JSONResponse({"ok": True, "entry": entry})


async def delete_reading(request: Request):
    doc = read_reading()
    if doc["reading"].pop(request.path_params["slug"], None) is None:
        return JSONResponse({"error": "no such entry"}, status_code=404)
    _write_reading(doc)
    return JSONResponse({"ok": True})


async def get_state(request: Request):
    try:
        sessions = [
            {"session_id": s.session_id, "summary": s.custom_title or s.summary,
             "last_modified": s.last_modified, "tag": s.tag}
            for s in list_sessions(directory=str(REPO), limit=25)
        ]
    except Exception:
        sessions = []
    return JSONResponse({
        "session_id": CHAT.session_id,
        "busy": CHAT.busy,
        "connected": CHAT.client is not None,
        "jobs": list(JOBS),
        "sessions": sessions,
    })


class LocalOnly(BaseHTTPMiddleware):
    """Loopback bind stops the network; this stops another page in your browser
    from POSTing prompts at an agent that can write files."""

    async def dispatch(self, request: Request, call_next):
        if request.url.path.startswith("/api/"):
            origin = request.headers.get("origin")
            if origin and origin not in ALLOWED_ORIGINS:
                return JSONResponse({"error": "bad origin"}, status_code=403)
            host = (request.headers.get("host") or "").split(":")[0]
            if host not in ("localhost", "127.0.0.1", "[::1]", "::1"):
                return JSONResponse({"error": "bad host"}, status_code=403)
        return await call_next(request)


ALLOWED_ORIGINS: set[str] = set()


@contextlib.asynccontextmanager
async def lifespan(app):
    SCRATCH.mkdir(parents=True, exist_ok=True)
    reaper = asyncio.create_task(CHAT.reap_loop())
    try:
        yield
    finally:
        reaper.cancel()
        for task in list(JOBS.values()):
            task.cancel()
        await CHAT.close()


app = Starlette(
    routes=[
        Route("/api/events", sse),
        Route("/api/prompt", post_prompt, methods=["POST"]),
        Route("/api/job", post_job, methods=["POST"]),
        Route("/api/job/{job_id}/cancel", post_cancel, methods=["POST"]),
        Route("/api/interrupt", post_interrupt, methods=["POST"]),
        Route("/api/session/new", post_new_session, methods=["POST"]),
        Route("/api/session/resume", post_resume, methods=["POST"]),
        Route("/api/state", get_state),
        Route("/api/reading", get_reading),
        Route("/api/reading/{slug}", put_reading, methods=["PUT"]),
        Route("/api/reading/{slug}", delete_reading, methods=["DELETE"]),
        Mount("/", app=StaticFiles(directory=str(REPO), html=True)),
    ],
    middleware=[Middleware(LocalOnly)],
    lifespan=lifespan,
)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8777)
    args = ap.parse_args()

    for host in ("localhost", "127.0.0.1"):
        ALLOWED_ORIGINS.add(f"http://{host}:{args.port}")

    # Windows lets a 0.0.0.0 listener and a 127.0.0.1 listener hold the same port,
    # so binding succeeding does not mean this process is the one the browser
    # reaches. A stale `python -m http.server` serves the page with no API behind
    # it, and the assistant panel just reports itself unreachable.
    import socket
    with socket.socket() as probe:
        probe.settimeout(0.5)
        if probe.connect_ex(("127.0.0.1", args.port)) == 0:
            print(f"warning: something is already listening on port {args.port}. "
                  f"If the assistant panel says it cannot reach serve.py, stop that "
                  f"process (likely an old 'python -m http.server') and start again.",
                  file=sys.stderr)

    if "ANTHROPIC_API_KEY" in os.environ:
        print("note: ANTHROPIC_API_KEY is set in this shell; it is stripped from the "
              "agent environment so sessions run on your Claude subscription.",
              file=sys.stderr)

    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=args.port, log_level="warning")


if __name__ == "__main__":
    main()
