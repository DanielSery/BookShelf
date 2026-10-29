"""The full bibliography behind a series or shared world, drawn by the Map tab's series map.

book-series.json groups the shelf's own volumes; book-worlds.json lists everything the
world contains, including volumes no library holds, and how its series connect. A series
with no record here is drawn from book-series.json alone, with its missing volumes as
untitled gaps.

    python tools/worlds.py check [file]     # dangling ids, stale shelf links, shelf volumes left out
    python tools/worlds.py merge <files...> # add or replace the `worlds` / `reading` of research output files
"""
import io
import json
import sys

import readlog

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8")
    except AttributeError:
        pass

CACHE, READ, REJ, SERIES, OUT = ("book-cache.json", "books-read.md", "book-rejects.jsonl",
                                 "book-series.json", "book-worlds.json")
LINKS = {"then", "prequel", "crossover"}


def reading_problems(wid, w, books):
    r, out = w.get("reading"), []
    if not r:
        return out
    edges = [(c[i], c[i + 1]) for c in r.get("chains", []) for i in range(len(c) - 1)] + [tuple(p) for p in r.get("after", [])]
    for i in set(r.get("starts", [])) | {x for e in edges for x in e}:
        if i not in books:
            out.append(f"{wid}: reading order names unknown book {i!r}")
    reached = set(r.get("starts", [])) | {b for _, b in edges}
    out += [f"{wid}: {i} is neither a start nor reached by the reading order" for i in books if i not in reached]
    succ = {}
    for a, b in edges:
        succ.setdefault(a, []).append(b)
    state = {}

    def cyclic(n):
        state[n] = 1
        for m in succ.get(n, []):
            if state.get(m) == 1 or (m not in state and cyclic(m)):
                return True
        state[n] = 2
        return False
    if any(n not in state and cyclic(n) for n in list(succ)):
        out.append(f"{wid}: the reading order has a cycle")
    return out


def check(path=OUT):
    keys = {b["key"] for b in json.load(io.open(CACHE, encoding="utf-8"))["books"]}
    titles = {r["title"] for r in readlog.rows(READ)}
    rejected = {json.loads(l).get("entity") for l in io.open(REJ, encoding="utf-8") if l.startswith('{"entity')}
    series = json.load(io.open(SERIES, encoding="utf-8"))["series"]
    data = json.load(io.open(path, encoding="utf-8"))
    # A research file may carry only `reading` blocks for worlds already in book-worlds.json.
    worlds = data.get("worlds") or json.load(io.open(OUT, encoding="utf-8"))["worlds"]
    for wid, r in data.get("reading", {}).items():
        worlds[wid] = {**worlds[wid], "reading": r}
    problems, owner = [], {}
    for wid, w in worlds.items():
        lines = {l["id"] for l in w["lines"]}
        for l in lines:
            if l in owner:
                problems.append(f"{wid}: line {l} is already in {owner[l]}")
            owner[l] = wid
        books = {b["id"]: b for b in w["books"]}
        if len(books) != len(w["books"]):
            problems.append(f"{wid}: duplicate book ids")
        for b in w["books"]:
            where = f"{wid}/{b['id']}"
            if b["line"] not in lines:
                problems.append(f"{where}: line {b['line']} is not one of the world's lines")
            if b.get("key") and b["key"] not in keys:
                problems.append(f"{where}: key {b['key']} is not on the shelf (logged or rejected since?)")
            if b.get("read") and b["read"] not in titles:
                problems.append(f"{where}: read {b['read']!r} is not a books-read.md row")
            if b.get("rejected") and b["rejected"] not in rejected:
                problems.append(f"{where}: rejected {b['rejected']!r} is not a book-rejects.jsonl entity")
            if bool(b.get("lib")) != bool(b.get("recordUrl")):
                problems.append(f"{where}: lib and recordUrl go together")
            if not all(isinstance(b.get(f), (int, type(None))) for f in ("n", "year")):
                problems.append(f"{where}: n and year are whole numbers or null")
        for k in w.get("links", []):
            if k["kind"] not in LINKS:
                problems.append(f"{wid}: link kind {k['kind']!r}")
            for end in (k["from"], k["to"]):
                if end not in books and not (k["kind"] == "crossover" and end in lines):
                    problems.append(f"{wid}: link end {end!r} is no book{' or line' if k['kind'] == 'crossover' else ''}")
        for i in w.get("story", []):
            if i not in books:
                problems.append(f"{wid}: story lists unknown book {i!r}")
        if w.get("story") and len(set(w["story"])) != len(books):
            problems.append(f"{wid}: story order covers {len(set(w['story']))} of {len(books)} books")
        for a in w.get("arcs", []):
            if a["line"] not in lines:
                problems.append(f"{wid}: arc {a['name']!r} on unknown line {a['line']}")
        # A world record replaces its series' book-series.json view on the map, so a shelf
        # volume or read row it leaves out would vanish from the series map.
        linked = {f: {b.get(f) for b in w["books"]} for f in ("key", "read", "rejected")}
        for l in lines & series.keys():
            s = series[l]
            problems += [f"{wid}: shelf volume {m['key']} of {l} is not in the world" for m in s["members"]
                         if m["key"] not in linked["key"]]
            problems += [f"{wid}: read row {t!r} of {l} is not in the world" for t in s.get("read", [])
                         if t not in linked["read"]]
            problems += [f"{wid}: rejected {t!r} of {l} is not in the world" for t in s.get("rejected", [])
                         if t not in linked["rejected"]]
        problems += reading_problems(wid, w, books)
    print(f"{len(worlds)} worlds, {sum(len(w['books']) for w in worlds.values())} books, {len(problems)} problems")
    for p in problems:
        print("  !", p)
    sys.exit(1 if problems else 0)


def merge(paths):
    doc = json.load(io.open(OUT, encoding="utf-8"))
    for path in paths:
        data = json.load(io.open(path, encoding="utf-8"))
        for wid, w in data.get("worlds", {}).items():
            print(("replaced " if wid in doc["worlds"] else "added ") + wid, len(w["books"]), "books")
            doc["worlds"][wid] = w
        for wid, r in data.get("reading", {}).items():
            print("reading order for " + wid)
            doc["worlds"][wid]["reading"] = r
    doc["worlds"] = dict(sorted(doc["worlds"].items()))
    io.open(OUT, "w", encoding="utf-8", newline="\n").write(json.dumps(doc, ensure_ascii=False, indent=1) + "\n")
    check()


if __name__ == "__main__":
    cmd, args = sys.argv[1:2], sys.argv[2:]
    if cmd == ["check"] and len(args) <= 1:
        check(*args)
    elif cmd == ["merge"] and args:
        merge(args)
    else:
        sys.exit(__doc__)
