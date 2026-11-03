"""Two one-sentence lines per card: the treasure (why this book is worth reading) and how to read it.

The reader asked on 2026-11-03, after finding that Výdech wants one story per sitting and a
pause, while Stín věcí ztracených wants immersion: "for each book, even the read ones", and
"do not just copy it, analyze it and propose your own style". The writer analyses how each
book is built and derives the reading style from that; only the resulting sentence is kept.
The same day he asked for a second line of the same size, the treasure: "why this book is
special, what is the best thing on it, why it should be read".

Both are presentation, like a pitch, so they live in book-media.json as `treasure` and
`howto`: `media` for a candidate, `readMedia` for a read book, `seriesMedia` for a series
card, keyed the way the viewer keys the card. A series is one card, so it gets one pair and
its volumes get none.

    python tools/tips.py status [--min 60]
    python tools/tips.py batches <outdir> [--min 60] [--size 60] [--only read|book|series]
        -> one Sonnet agent per batch file, each following tools/tips-prompt.md
    python tools/tips.py merge <files...> [--force]

Read books and series with a read volume are always wanted; a candidate card only when its
predicted floor is at least --min. A batch row's `want` names the lines that card still
lacks, so a card that has one line is only asked for the other. `merge` refuses a line that
leaks scoring machinery or runs past one sentence, and both commands list phrases shared by
many cards, which is what copying a template looks like. `--force` overwrites existing
lines, which are otherwise kept.
"""
import argparse
import collections
import io
import json
import re
import sys
import unicodedata

sys.path.insert(0, "tools")
import readlog

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8")
    except AttributeError:
        pass

EST, CACHE, MEDIA, SERIES, FACETS = ("book-estimates.jsonl", "book-cache.json", "book-media.json",
                                     "book-series.json", "book-read-facets.json")
FIELDS = ("treasure", "howto")
MIN_LEN, MAX_LEN = 50, 220
VOLUME_NOTES, SHINGLE, REPEAT_CARDS = 1500, 5, 4
BUCKET = {"book": "media", "read": "readMedia", "series": "seriesMedia"}
SCORE_LIKE = re.compile(r"(?<!\d)(?:[3-9]\d|100)(?!\d)|\d+\s*[-–]\s*\d+")
MACHINERY = re.compile(r"\b(?:scored?|scores|deduct\w*|axis|axes|filters?|estimated?|predict\w*|rating|tier|"
                       r"leaned|the reader|rootable|legible|interiority|declared|single[- ]POV|"
                       r"concrete (?:situation|want|problem)|clear want|second-order|premise|in the shape of)\b", re.I)
SECOND_SENTENCE = re.compile(r"(?<!\b[A-Z])[.!?]\s+\S")  # an initial ("O. Henry") is not a sentence end


def slug(s):
    s = "".join(c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")[:60]


def problems(field, text, own_titles=()):
    if not isinstance(text, str) or not text.strip():
        return [f"empty {field}"]
    out = [] if MIN_LEN <= len(text) <= MAX_LEN else [f"{field} length {len(text)} outside {MIN_LEN}-{MAX_LEN}"]
    if SECOND_SENTENCE.search(text.strip()):
        out.append(f"{field}: more than one sentence")
    for t in own_titles:
        if t:
            text = text.replace(t, "")
    if SCORE_LIKE.search(text):
        out.append(f"{field}: score-like number {SCORE_LIKE.search(text).group(0)!r}")
    if MACHINERY.search(text):
        out.append(f"{field}: scoring word {MACHINERY.search(text).group(0)!r}")
    return out


def load():
    est = [json.loads(l) for l in io.open(EST, encoding="utf-8") if l.startswith('{"key"')]
    cache = {b["key"]: b for b in json.load(io.open(CACHE, encoding="utf-8"))["books"]}
    series = json.load(io.open(SERIES, encoding="utf-8"))["series"]
    facets = json.load(io.open(FACETS, encoding="utf-8")).get("facets", {})
    raw = io.open(MEDIA, encoding="utf-8", newline="").read()
    return est, cache, series, facets, json.loads(raw), raw


def ten(score):
    return None if score is None else score / 10


def units(est, cache, series, facets, media):
    """Every card the viewer draws outside the Rejected tab, grouped into series as it groups them."""
    by_key = {e["key"]: e for e in est}
    reads = {r["title"]: r for r in readlog.rows()}
    m = media.get("media", {})
    in_series, read_in_series, out = set(), set(), []

    def title_of(key):
        b = cache.get(key, {})
        return b.get("czTitle") or b.get("title") or by_key[key].get("t")

    for sid, s in series.items():
        if s.get("kind") != "series":
            continue
        members = [x for x in s.get("members", []) if x["key"] in by_key]
        done = [reads[t] for t in s.get("read", []) if t in reads]
        if not members and not done:
            continue
        in_series.update(x["key"] for x in members)
        read_in_series.update(r["title"] for r in done)
        vols = [by_key[x["key"]] for x in members]
        scored = [e for e in vols if e.get("est")]
        floor = (None if any(e.get("blocked") for e in vols) or not scored
                 else round(sum(e["est"][0] for e in scored) / len(scored)))
        first = cache.get(members[0]["key"], {}) if members else {}
        out.append({
            "id": "s:" + sid, "kind": "series", "slot": sid, "floor": floor, "hasRead": bool(done),
            "titles": [s.get("name"), s.get("nameEn")],
            "row": {"title": s.get("name"), "alt": s.get("nameEn"),
                    "author": first.get("author") or (done[0]["author"] if done else None),
                    "volumes": [{"title": r["title"], "read": True, "score": ten(r["score"]), "notes": r["notes"]}
                                for r in done]
                               + [{"n": x.get("n"), "title": title_of(x["key"]),
                                   "notes": (by_key[x["key"]].get("why") or "")[:VOLUME_NOTES]} for x in members]},
        })

    for e in est:
        if e["key"] in in_series or not e.get("est"):
            continue
        b, mk = cache.get(e["key"], {}), m.get(e["key"], {})
        czt, en = b.get("czTitle"), b.get("title")
        out.append({
            "id": "c:" + e["key"], "kind": "book", "slot": e["key"], "floor": e["est"][0], "hasRead": False,
            "titles": [czt, en],
            "row": {"title": czt or en, "alt": en if czt and en and czt != en else None, "author": b.get("author"),
                    "genre": b.get("genre"), "form": b.get("form"), "tags": b.get("tags") or [],
                    "pitch": mk.get("pitch") or mk.get("blurb"), "notes": e.get("why")},
        })

    for r in reads.values():
        if r["title"] in read_in_series:
            continue
        k, f = slug(r["title"]), facets.get(slug(r["title"]), {})
        out.append({
            "id": "r:" + k, "kind": "read", "slot": k, "floor": None, "hasRead": True, "titles": [r["title"]],
            "row": {"title": r["title"], "author": r["author"], "genre": f.get("genre"), "form": f.get("form"),
                    "score": ten(r["score"]), "notes": r["notes"]},
        })

    for u in out:
        rec = media.get(BUCKET[u["kind"]], {}).get(u["slot"], {})
        u["have"] = {f: rec.get(f) for f in FIELDS if rec.get(f)}
    return out


def missing(u):
    return [f for f in FIELDS if f not in u["have"]]


def wanted(us, minimum, only=None):
    """--only read means every card with something read on it, series included."""
    return [u for u in us if missing(u)
            and (not only or (u["hasRead"] if only == "read" else u["kind"] == only))
            and (u["hasRead"] or (u["floor"] is not None and u["floor"] >= minimum))]


def repeats(us):
    """Phrases of SHINGLE words that recur in one field on REPEAT_CARDS or more cards, most widespread first."""
    seen = collections.defaultdict(set)
    for u in us:
        for f, text in u["have"].items():
            words = re.findall(r"[a-z']+", text.lower())
            for i in range(len(words) - SHINGLE + 1):
                seen[(f, " ".join(words[i:i + SHINGLE]))].add(u["id"])
    hits = [(k, ids) for k, ids in seen.items() if len(ids) >= REPEAT_CARDS]
    return sorted(hits, key=lambda x: -len(x[1]))


def report_repeats(us):
    hits = repeats(us)
    if hits:
        print(f"{len(hits)} phrases recur on {REPEAT_CARDS}+ cards; check whether the rest of each line is "
              f"still specific, and rewrite templated cards with --force:")
        for (f, p), ids in hits[:15]:
            print(f"  {len(ids):3}  {f}: \"{p}\"  e.g. {', '.join(sorted(ids)[:3])}")


def status(a):
    est, cache, series, facets, media, _ = load()
    us = units(est, cache, series, facets, media)
    todo = wanted(us, a.min)
    for kind in BUCKET:
        k = [u for u in us if u["kind"] == kind]
        t = [u for u in todo if u["kind"] == kind]
        have = ", ".join(f"{sum(1 for u in k if f in u['have'])} {f}" for f in FIELDS)
        print(f"{kind:6} {len(k):5} cards ({have}); {len(t)} wanted at --min {a.min}, "
              f"{sum(len(json.dumps(u['row'], ensure_ascii=False)) for u in t):,} chars of input")
    report_repeats(us)


def batches(a):
    est, cache, series, facets, media, _ = load()
    todo = wanted(units(est, cache, series, facets, media), a.min, a.only)
    todo.sort(key=lambda u: (not u["hasRead"], -(u["floor"] or 0)))
    for n in range(0, len(todo), a.size):
        path = f"{a.outdir}/tips_{n // a.size:03d}.jsonl"
        with io.open(path, "w", encoding="utf-8", newline="\n") as f:
            for u in todo[n:n + a.size]:
                f.write(json.dumps({"id": u["id"], "kind": u["kind"], "want": missing(u), **u["row"],
                                    **{f"has_{k}": v for k, v in u["have"].items()}}, ensure_ascii=False) + "\n")
        print(path, min(a.size, len(todo) - n))


def merge(a):
    est, cache, series, facets, media, raw = load()
    us = units(est, cache, series, facets, media)
    by_id = {u["id"]: u for u in us}
    ok, refused, kept, empty = 0, [], 0, 0
    for path in a.files:
        for line in io.open(path, encoding="utf-8"):
            if not line.strip():
                continue
            d = json.loads(line)
            u = by_id.get(d.get("id"))
            if not u:
                refused.append(f"{d.get('id')}: not a card")
                continue
            for f in FIELDS:
                text = (d.get(f) or "").strip()
                if not text:
                    empty += f in missing(u)
                    continue
                bad = problems(f, text, u["titles"])
                if bad:
                    refused.append(f"{u['id']}: {'; '.join(bad)}")
                    continue
                if f in u["have"] and not a.force:
                    kept += 1
                    continue
                media.setdefault(BUCKET[u["kind"]], {}).setdefault(u["slot"], {})[f] = text
                u["have"][f] = text
                ok += 1
    nl = "\r\n" if "\r\n" in raw else "\n"
    io.open(MEDIA, "w", encoding="utf-8", newline="").write(
        json.dumps(media, ensure_ascii=False, indent=1).replace("\n", nl) + nl)
    print(f"merged {ok} lines, kept existing {kept}, left empty by the writer {empty}, refused {len(refused)}")
    for r in refused:
        print("  !", r)
    report_repeats(us)


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("status")
    s.add_argument("--min", type=int, default=60)
    s = sub.add_parser("batches")
    s.add_argument("outdir"), s.add_argument("--min", type=int, default=60), s.add_argument("--size", type=int, default=60)
    s.add_argument("--only", choices=list(BUCKET))
    s = sub.add_parser("merge")
    s.add_argument("files", nargs="+"), s.add_argument("--force", action="store_true")
    a = ap.parse_args()
    {"status": status, "batches": batches, "merge": merge}[a.cmd](a)


if __name__ == "__main__":
    main()
