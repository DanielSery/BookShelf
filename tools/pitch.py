"""Reader-facing pitches: the few sentences the viewer shows instead of the scoring notes.

The reader asked on 2026-10-24 for "why I could be interested", not why a book scored
what it did. A pitch lives in book-media.json next to the blurb, because it is
presentation, not judgement: re-deriving an estimate does not touch it.

    python tools/pitch.py status [--min 60]
    python tools/pitch.py batches <outdir> [--min 60] [--size 100]
        -> one Sonnet agent per batch file, each following tools/pitch-prompt.md
    python tools/pitch.py merge <files...> [--force]

`merge` refuses a pitch that leaks scoring machinery; `--force` overwrites pitches
that already exist, which are otherwise kept.
"""
import argparse
import io
import json
import re
import sys

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8")
    except AttributeError:
        pass

EST, CACHE, MEDIA = "book-estimates.jsonl", "book-cache.json", "book-media.json"
MIN_LEN, MAX_LEN = 150, 600
SCORE_LIKE = re.compile(r"(?<!\d)(?:[3-9]\d|100)(?!\d)|\d+\s*[-–]\s*\d+")
MACHINERY = re.compile(r"\b(?:scored?|scores|points?|deduct\w*|axis|axes|filters?|estimated?|predict\w*|"
                       r"rating|tier|leaned|the reader|rootable|legible|interiority|declared|single[- ]POV|"
                       r"concrete (?:situation|want|problem)|clear want|second-order|premise|in the shape of)\b", re.I)


def problems(pitch, own_titles=()):
    """Why a pitch would be refused, or an empty list."""
    out = []
    if not isinstance(pitch, str) or not pitch.strip():
        return ["empty pitch"]
    if not MIN_LEN <= len(pitch) <= MAX_LEN:
        out.append(f"length {len(pitch)} outside {MIN_LEN}-{MAX_LEN}")
    text = pitch
    for t in own_titles:
        if t:
            text = text.replace(t, "")
    if SCORE_LIKE.search(text):
        out.append(f"score-like number {SCORE_LIKE.search(text).group(0)!r}")
    if MACHINERY.search(text):
        out.append(f"scoring word {MACHINERY.search(text).group(0)!r}")
    return out


def load():
    est = [json.loads(l) for l in io.open(EST, encoding="utf-8") if l.startswith('{"key"')]
    cache = {b["key"]: b for b in json.load(io.open(CACHE, encoding="utf-8"))["books"]}
    raw = io.open(MEDIA, encoding="utf-8", newline="").read()
    return est, cache, json.loads(raw), raw


def wanted(est, media, minimum):
    mm = media.get("media", {})
    return [e for e in est if e.get("est") and e["est"][0] >= minimum and not mm.get(e["key"], {}).get("pitch")]


def status(a):
    est, _, media, _ = load()
    live = [e for e in est if e.get("est")]
    have = sum(1 for e in live if media.get("media", {}).get(e["key"], {}).get("pitch"))
    print(f"{have} of {len(live)} live candidates have a pitch; "
          f"{len(wanted(est, media, a.min))} without one at est[0] >= {a.min}")


def batches(a):
    est, cache, media, _ = load()
    todo = sorted(wanted(est, media, a.min), key=lambda e: -sum(e["est"]))
    mm = media.get("media", {})
    for n in range(0, len(todo), a.size):
        path = f"{a.outdir}/pitch_{n // a.size:03d}.jsonl"
        with io.open(path, "w", encoding="utf-8", newline="\n") as f:
            for e in todo[n:n + a.size]:
                b = cache.get(e["key"], {})
                f.write(json.dumps({
                    "key": e["key"], "title": b.get("czTitle") or b.get("title"), "author": b.get("author"),
                    "genre": b.get("genre"), "tags": b.get("tags") or [],
                    "blurb": mm.get(e["key"], {}).get("blurb"), "notes": e["why"],
                }, ensure_ascii=False) + "\n")
        print(path, min(a.size, len(todo) - n))


def merge(a):
    est, cache, media, raw = load()
    live = {e["key"] for e in est if e.get("est")}
    mm = media.setdefault("media", {})
    ok, refused, kept = 0, [], 0
    for path in a.files:
        for line in io.open(path, encoding="utf-8"):
            if not line.strip():
                continue
            d = json.loads(line)
            k, p = d.get("key"), (d.get("pitch") or "").strip()
            if k not in live:
                refused.append(f"{k}: not a live candidate")
                continue
            b = cache.get(k, {})
            bad = problems(p, (b.get("czTitle"), b.get("title")))
            if bad:
                refused.append(f"{k}: {'; '.join(bad)}")
                continue
            if mm.get(k, {}).get("pitch") and not a.force:
                kept += 1
                continue
            mm.setdefault(k, {})["pitch"] = p
            ok += 1
    nl = "\r\n" if "\r\n" in raw else "\n"
    io.open(MEDIA, "w", encoding="utf-8", newline="").write(
        json.dumps(media, ensure_ascii=False, indent=1).replace("\n", nl) + nl)
    print(f"merged {ok}, kept existing {kept}, refused {len(refused)}")
    for r in refused:
        print("  !", r)


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("status")
    s.add_argument("--min", type=int, default=60)
    s = sub.add_parser("batches")
    s.add_argument("outdir"), s.add_argument("--min", type=int, default=60), s.add_argument("--size", type=int, default=100)
    s = sub.add_parser("merge")
    s.add_argument("files", nargs="+"), s.add_argument("--force", action="store_true")
    a = ap.parse_args()
    {"status": status, "batches": batches, "merge": merge}[a.cmd](a)


if __name__ == "__main__":
    main()
