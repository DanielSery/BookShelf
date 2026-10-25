"""Series membership for the shelf: which candidates the viewer and /book-suggest
propose as one entry.

The reader reads a series whole and never picks single titles out of one (2026-10-25),
so a series is one decision. book-series.json holds the grouping; book-cache.json's
`series` field is only the raw catalogue value, which is often a publisher's line.

    python tools/series.py batches <outdir> [--size 170]
        -> one Sonnet agent per batch file, each following tools/series-prompt.md
    python tools/series.py merge <files...>       # rewrites book-series.json
    python tools/series.py check                  # stale or duplicate members
"""
import argparse
import collections
import glob
import io
import json
import re
import sys
import unicodedata

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8")
    except AttributeError:
        pass

CACHE, EST, READ, REJ, OUT = ("book-cache.json", "book-estimates.jsonl", "books-read.md",
                              "book-rejects.jsonl", "book-series.json")
KINDS = {"series", "universe"}


def norm(s):
    s = "".join(c for c in unicodedata.normalize("NFKD", s or "") if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")


def surname(a):
    a = re.split(r",| a | and |&|;", a or "")[0]
    parts = norm(a).split("-")
    return re.sub(r"ova$", "", parts[-1]) if parts and parts[-1] else ""


def read_rows():
    out = []
    for line in io.open(READ, encoding="utf-8"):
        c = [x.strip() for x in line.strip().strip("|").split("|")]
        if len(c) == 5 and c[2].isdigit():
            out.append({"title": c[0], "author": c[1], "score": int(c[2])})
    return out


def batches(a):
    books = json.load(io.open(CACHE, encoding="utf-8"))["books"]
    by = collections.defaultdict(list)
    for b in books:
        by[surname(b.get("author"))].append({k: b.get(k) for k in ("key", "title", "czTitle", "author", "series")}
                                             | {"year": (b.get("cz") or {}).get("year")})
    reads = collections.defaultdict(list)
    for r in read_rows():
        for au in re.split(r",| a | and |&", r["author"]):
            reads[surname(au)].append(r)
    rejs = collections.defaultdict(list)
    for line in io.open(REJ, encoding="utf-8"):
        if line.startswith('{"entity'):
            r = json.loads(line)
            for au in re.split(r",| a | and |&", r.get("author") or ""):
                rejs[surname(au)].append({k: r.get(k) for k in ("entity", "author", "filter")})
    groups = [{"author": s, "shelf": v, "read": reads.get(s, []), "rejected": rejs.get(s, [])[:40]}
              for s, v in sorted(by.items())]
    chunk, size, n = [], 0, 0
    for g in groups + [None]:
        if g is None or (size + len(g["shelf"]) > a.size and chunk):
            path = f"{a.outdir}/series_{n:02d}.jsonl"
            io.open(path, "w", encoding="utf-8", newline="\n").write(
                "".join(json.dumps(x, ensure_ascii=False) + "\n" for x in chunk))
            print(path, size, "books")
            chunk, size, n = [], 0, n + 1
        if g:
            chunk.append(g)
            size += len(g["shelf"])


def merge(a):
    keys = {b["key"] for b in json.load(io.open(CACHE, encoding="utf-8"))["books"]}
    out, owner, bad = {}, {}, []
    for path in [p for f in a.files for p in sorted(glob.glob(f))]:
        for line in io.open(path, encoding="utf-8"):
            if not line.strip():
                continue
            d = json.loads(line)
            sid = d.get("id")
            if not sid or d.get("kind") not in KINDS:
                bad.append(f"{path}: bad id/kind {sid!r} {d.get('kind')!r}")
                continue
            members = []
            for m in d.get("members") or []:
                k = m.get("key")
                if k not in keys:
                    bad.append(f"{sid}: unknown key {k!r}")
                elif k in owner and owner[k] != sid:
                    bad.append(f"{sid}: {k} already in {owner[k]}")
                else:
                    owner[k] = sid
                    members.append({"key": k, "n": m.get("n")})
            if sid in out:
                if out[sid]["kind"] != "universe" or d["kind"] != "universe":
                    bad.append(f"{sid}: duplicate id across batches, members merged")
                out[sid]["members"] += members
                out[sid]["read"] += d.get("read") or []
                out[sid]["rejected"] += d.get("rejected") or []
                continue
            out[sid] = {"name": d.get("name") or d.get("nameEn") or sid, "nameEn": d.get("nameEn") or "",
                        "kind": d["kind"], "members": members, "read": d.get("read") or [],
                        "rejected": d.get("rejected") or [], "volumes": d.get("volumes"),
                        "note": d.get("note") or ""}
    # Read-only records (a series read whole, no volume left on the shelf) and `read` lists
    # were written by hand or by /book-log; a re-merge from agent output must not drop them.
    try:
        prev = json.load(io.open(OUT, encoding="utf-8"))["series"]
    except FileNotFoundError:
        prev = {}
    for sid, p in prev.items():
        if sid in out:
            out[sid]["read"] += [t for t in p.get("read", []) if t not in out[sid]["read"]]
        elif p.get("read"):
            out[sid] = {**p, "members": [m for m in p.get("members", []) if m["key"] in keys and m["key"] not in owner]}
    for s in out.values():
        s["members"].sort(key=lambda m: (m["n"] is None, m["n"] or 0))
    doc = {
        "_readme": "Which shelf candidates belong to one series, written by tools/series.py from agents following "
                   "tools/series-prompt.md. The reader reads a series whole (2026-10-25), so the viewer and "
                   "/book-suggest propose a `series` as ONE entry; a `universe` (shared world, standalone novels) "
                   "is not grouped. book-cache.json `series` is only the raw catalogue value and is often a "
                   "publisher's line. /book-screen adds a new volume here; /book-log moves a logged volume from "
                   "`members` to `read`.",
        "schema": 1,
        "series": dict(sorted(out.items())),
    }
    io.open(OUT, "w", encoding="utf-8", newline="\n").write(json.dumps(doc, ensure_ascii=False, indent=1) + "\n")
    n_series = sum(s["kind"] == "series" for s in out.values())
    grouped = sum(len(s["members"]) for s in out.values() if s["kind"] == "series")
    print(f"{n_series} series ({grouped} shelf books), {len(out) - n_series} universes -> {OUT}")
    for b in bad:
        print("  !", b)


def check(_):
    keys = {b["key"] for b in json.load(io.open(CACHE, encoding="utf-8"))["books"]}
    titles = {r["title"] for r in read_rows()}
    doc = json.load(io.open(OUT, encoding="utf-8"))
    seen, problems = {}, []
    for sid, s in doc["series"].items():
        problems += [f"{sid}: read title {t!r} is not a books-read.md row" for t in s.get("read", []) if t not in titles]
        for m in s["members"]:
            if m["key"] not in keys:
                problems.append(f"{sid}: {m['key']} is not on the shelf (logged or rejected? move it to read/rejected)")
            if m["key"] in seen:
                problems.append(f"{m['key']} in both {seen[m['key']]} and {sid}")
            seen[m["key"]] = sid
    print(f"{len(doc['series'])} records, {len(seen)} members, {len(problems)} problems")
    for p in problems:
        print("  !", p)
    sys.exit(1 if problems else 0)


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("batches")
    s.add_argument("outdir"), s.add_argument("--size", type=int, default=170)
    s = sub.add_parser("merge")
    s.add_argument("files", nargs="+")
    sub.add_parser("check")
    a = ap.parse_args()
    {"batches": batches, "merge": merge, "check": check}[a.cmd](a)


if __name__ == "__main__":
    main()
