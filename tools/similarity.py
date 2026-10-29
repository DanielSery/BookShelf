"""Book and author similarity for the viewer's map tab.

A profile says what a book IS - world, kind, themes, tone, telling, lead - in the
controlled vocabulary of tools/similarity-prompt.md. `build` turns the profiles into
book-similarity.json: a 2-D map position per book and per author, plus a sparse content
vector per book that the page compares live, so "most similar" can honour whatever
filters are set instead of a precomputed top-N that the filters would empty.

Presentation only, like a pitch. An estimate must never argue from a neighbour on this
map - a candidate calibrated against another candidate is what tools/crossrefs.py fails.

    python tools/similarity.py status
    python tools/similarity.py batches <outdir> [--size 150] [--redo] [--compact]
        -> one agent per batch file, each following tools/similarity-prompt.md
    python tools/similarity.py merge <files...> [--add]
    python tools/similarity.py build
"""
import argparse
import collections
import hashlib
import io
import json
import math
import re
import sys
import unicodedata

import numpy as np

import readlog

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8")
    except AttributeError:
        pass

EST, CACHE, MEDIA = "book-estimates.jsonl", "book-cache.json", "book-media.json"
READ, FACETS = "books-read.md", "book-read-facets.json"
PROMPT, PROFILES, OUT = "tools/similarity-prompt.md", "book-profiles.jsonl", "book-similarity.json"
NOTES_MAX, BLURB_MAX = 700, 300
MIN_TAGS, MAX_TAGS = 4, 18
COMPACT = ("id", "title", "alt", "author", "genre", "form", "blurb")

# Kind and setting are what "a book like this" usually means; telling and lead matter to
# this reader but should not on their own pull a war memoir next to a space opera.
GROUP_W = {"Audience": 1.5, "Setting": 1.0, "Kind": 1.2, "Theme": 0.8, "Tone": 0.7, "Telling": 0.5, "Lead": 0.6}
FACET_W = {"g": 4.0, "f": 3.0, "aud": 9.0}
# The shelf's own audience is `adult` by default on ~95% of candidates, picture books
# included, so only a value someone actually decided is used; the for-children and
# for-teens tags carry the rest.
AUDIENCE_DECIDED = ("katalog", "hand")
# Layout only. Same author or series pulls books together on the map, but the page's live
# similarity leaves them out, or a ten-volume series would fill every "similar" list.
AUTHOR_W, SERIES_W = 4.0, 6.0
REGION_GROUPS = ("Audience", "Kind", "Setting")


def slug(s):
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")[:60]


def author_key(a):
    return re.sub(r"\s+", " ", slug(a or "").replace("-", " ")).strip()


def vocabulary():
    text = io.open(PROMPT, encoding="utf-8").read()
    body = text.split("## Vocabulary", 1)[1]
    tags, group = {}, None
    for line in body.splitlines():
        if line.startswith("### "):
            group = line[4:].strip()
        m = re.match(r"^\|\s*([a-z0-9-]+)\s*\|\s*(.+?)\s*\|\s*(.+?)\s*\|", line)
        if m and group and m.group(1) != "tag":
            tags[m.group(1)] = (m.group(2), m.group(3), group)
    digest = hashlib.sha256(" ".join(sorted(tags)).encode()).hexdigest()[:12]
    return tags, digest


def read_rows():
    return [{k: r[k] for k in ("title", "author", "notes")} for r in readlog.rows(READ)]


def shelf():
    """Every book the page can show on the map, as the batch line an agent sees."""
    est = [json.loads(l) for l in io.open(EST, encoding="utf-8") if l.startswith('{"key"')]
    cache = {b["key"]: b for b in json.load(io.open(CACHE, encoding="utf-8"))["books"]}
    media = json.load(io.open(MEDIA, encoding="utf-8")).get("media", {})
    facets = json.load(io.open(FACETS, encoding="utf-8")).get("facets", {})
    items = []
    for e in est:
        b = cache.get(e["key"], {})
        czt, en = b.get("czTitle"), b.get("title") or e.get("t")
        items.append({
            "id": "c:" + e["key"], "title": czt or en, "alt": en if czt and en != czt else None,
            "author": b.get("author"), "series": b.get("series"),
            "genre": b.get("genre"), "form": b.get("form"),
            "audience": b.get("audience") if b.get("audienceSource") in AUDIENCE_DECIDED else None,
            "blurb": (media.get(e["key"], {}).get("blurb") or "")[:BLURB_MAX] or None,
            "notes": (e.get("why") or "")[:NOTES_MAX],
        })
    for r in read_rows():
        s = slug(r["title"])
        f = facets.get(s, {})
        items.append({
            "id": "r:" + s, "title": r["title"], "alt": None, "author": r["author"], "series": None,
            "genre": f.get("genre"), "form": f.get("form"), "audience": f.get("audience"),
            "blurb": None, "notes": r["notes"][:NOTES_MAX],
        })
    return items


def load_profiles():
    try:
        lines = io.open(PROFILES, encoding="utf-8").read().splitlines()
    except FileNotFoundError:
        return {}
    return {p["id"]: p for p in map(json.loads, lines[1:]) if p.get("id")}


def save_profiles(profiles):
    head = {
        "_readme": "What each shelf book IS, in the controlled vocabulary of tools/similarity-prompt.md: "
                   "weight 3 defining, 2 clearly present, 1 minor. Written by tools/similarity.py merge "
                   "from agent output; book-similarity.json is built from it. A description, never a "
                   "judgement - nothing here may feed an estimate.",
        "schema": 1,
        "_id": "c:<book-cache.json key> for a candidate, r:<slug of the books-read.md title> for a read "
               "book - the same slug as book-media.json readMedia. A logged candidate changes id, so it "
               "is profiled again; its old line is pruned as an orphan.",
        "_vd": "Digest of the vocabulary's tag ids when the profile was made. An older vd still builds - "
               "unknown tags are dropped - but `status` counts it, because it never had the chance to use "
               "a tag added since.",
    }
    with io.open(PROFILES, "w", encoding="utf-8", newline="\n") as f:
        f.write(json.dumps(head, ensure_ascii=False) + "\n")
        for k in sorted(profiles):
            f.write(json.dumps(profiles[k], ensure_ascii=False) + "\n")


def status(a):
    _, vd = vocabulary()
    items, profiles = shelf(), load_profiles()
    ids = {i["id"] for i in items}
    have = [i for i in items if i["id"] in profiles]
    old = sum(1 for i in have if profiles[i["id"]].get("vd") != vd)
    print(f"{len(have)} of {len(items)} shelf books profiled; {len(items) - len(have)} missing; "
          f"{old} on an older vocabulary; {len(set(profiles) - ids)} orphan profiles")


def batches(a):
    _, vd = vocabulary()
    profiles = load_profiles()
    todo = [i for i in shelf() if a.redo or i["id"] not in profiles]
    for n in range(0, len(todo), a.size):
        path = f"{a.outdir}/profile_{n // a.size:03d}.jsonl"
        with io.open(path, "w", encoding="utf-8", newline="\n") as f:
            for i in todo[n:n + a.size]:
                line = {k: v for k, v in i.items() if v and (not a.compact or k in COMPACT)}
                f.write(json.dumps(line, ensure_ascii=False) + "\n")
        print(path, min(a.size, len(todo) - n))
    print(f"{len(todo)} books to profile")


def merge(a):
    tags, vd = vocabulary()
    ids = {i["id"] for i in shelf()}
    profiles = load_profiles()
    ok, refused, dropped = 0, [], collections.Counter()
    for path in a.files:
        for line in io.open(path, encoding="utf-8"):
            if not line.strip():
                continue
            d = json.loads(line)
            k = d.get("id")
            if k not in ids:
                refused.append(f"{k}: not on the shelf")
                continue
            got = {}
            for t, w in (d.get("tags") or {}).items():
                if t not in tags:
                    dropped[t] += 1
                elif w in (1, 2, 3):
                    got[t] = w
            if a.add:
                got = {**profiles.get(k, {}).get("tags", {}), **got}
            if not MIN_TAGS <= len(got) <= MAX_TAGS:
                refused.append(f"{k}: {len(got)} valid tags")
                continue
            profiles[k] = {"id": k, "tags": dict(sorted(got.items(), key=lambda x: (-x[1], x[0]))), "vd": vd}
            ok += 1
    for k in set(profiles) - ids:
        del profiles[k]
    save_profiles(profiles)
    print(f"merged {ok}, refused {len(refused)}")
    for r in refused:
        print("  !", r)
    if dropped:
        print("  unknown tags dropped:", ", ".join(f"{t} x{n}" for t, n in dropped.most_common()))


def _affinities(d2, perplexity):
    n = d2.shape[0]
    target = math.log(perplexity)
    beta, lo, hi = np.ones(n), np.zeros(n), np.full(n, np.inf)
    off = ~np.eye(n, dtype=bool)
    for _ in range(64):
        p = np.exp(-d2 * beta[:, None]) * off
        sp = p.sum(1) + 1e-12
        h = np.log(sp) + beta * (d2 * p).sum(1) / sp
        up = h > target
        lo = np.where(up, beta, lo)
        hi = np.where(up, hi, beta)
        beta = np.where(up, np.where(np.isinf(hi), beta * 2, (beta + hi) / 2), (beta + lo) / 2)
    return p / sp[:, None]


def tsne(x, perplexity=30.0, iters=1000, seed=0):
    """Exact t-SNE (van der Maaten 2008) with PCA init; fine up to a few thousand points."""
    n = x.shape[0]
    sq = (x * x).sum(1)
    d2 = np.maximum(sq[:, None] + sq[None, :] - 2 * x @ x.T, 0)
    p = _affinities(d2, min(perplexity, (n - 1) / 3))
    p = np.maximum((p + p.T) / (2 * n), 1e-12)
    xc = x - x.mean(0)
    _, _, vt = np.linalg.svd(xc, full_matrices=False)
    y = xc @ vt[:2].T
    y = y / y[:, 0].std() * 1e-4 + np.random.default_rng(seed).normal(0, 1e-6, (n, 2))
    vel, gains = np.zeros_like(y), np.ones_like(y)
    lr = max(n / 12 / 4, 50)
    for it in range(iters):
        exag, mom = (12.0, 0.5) if it < 250 else (1.0, 0.8)
        s = (y * y).sum(1)
        num = 1 / (1 + s[:, None] + s[None, :] - 2 * y @ y.T)
        np.fill_diagonal(num, 0)
        q = np.maximum(num / num.sum(), 1e-12)
        w = (exag * p - q) * num
        grad = 4 * (w.sum(1)[:, None] * y - w @ y)
        gains = np.where(np.sign(grad) != np.sign(vel), gains + 0.2, gains * 0.8).clip(0.01)
        vel = mom * vel - lr * gains * grad
        y = y + vel
        y -= y.mean(0)
    return y


def kmeans(y, k, seed=0, iters=60):
    rng = np.random.default_rng(seed)
    c = [y[rng.integers(len(y))]]
    for _ in range(k - 1):
        d = np.min(((y[:, None, :] - np.array(c)[None]) ** 2).sum(-1), 1)
        c.append(y[rng.choice(len(y), p=d / d.sum())])
    c = np.array(c)
    for _ in range(iters):
        lab = ((y[:, None, :] - c[None]) ** 2).sum(-1).argmin(1)
        c = np.array([y[lab == j].mean(0) if (lab == j).any() else c[j] for j in range(k)])
    return lab


def scaled(y):
    lo, hi = y.min(0), y.max(0)
    return (y - lo) / (hi - lo).max() * 1000


def regions(y, raw, tag_ids, groups, min_size=12):
    """One label per map region, from the Kind and Setting tags most over-represented in it."""
    k = max(6, round(math.sqrt(len(y) / 8)))
    lab = kmeans(y, k)
    eligible = np.array([groups[t] in REGION_GROUPS for t in tag_ids])
    overall = raw.mean(0)
    out = []
    for j in range(k):
        m = lab == j
        if m.sum() < min_size:
            continue
        excess = np.where(eligible, raw[m].mean(0) - overall, -np.inf)
        top = [i for i in np.argsort(-excess)[:2] if excess[i] > 0.25]
        if top:
            cx, cy = np.median(y[m], 0)
            out.append({"x": round(float(cx), 1), "y": round(float(cy), 1), "tags": [tag_ids[i] for i in top]})
    return out


def audience_of(b, tags):
    """A decided shelf value wins; otherwise the profiler's verdict, where no tag means adult."""
    if b.get("audience"):
        return b["audience"]
    return "childrens" if "for-children" in tags else "ya" if "for-teens" in tags else "adult"


def vectors(books, profiles, tags):
    """Raw tag weights, and unit content vectors: tags by rarity and group, then facets."""
    tag_ids = list(tags)
    tix = {t: i for i, t in enumerate(tag_ids)}
    groups = {t: g for t, (_, _, g) in tags.items()}
    n, T = len(books), len(tag_ids)
    raw = np.zeros((n, T))
    for r, b in enumerate(books):
        for t, w in profiles[b["id"]]["tags"].items():
            if t in tix:
                raw[r, tix[t]] = w
    df = (raw > 0).sum(0)
    idf = np.log((n + 1) / (df + 1)) + 1
    gw = np.array([GROUP_W[groups[t]] for t in tag_ids])

    facets = [{"g": b.get("genre"), "f": b.get("form"), "aud": audience_of(b, profiles[b["id"]]["tags"])}
              for b in books]
    facet_names = sorted({f"{p}:{v}" for fs in facets for p, v in fs.items() if v})
    fix = {f: T + i for i, f in enumerate(facet_names)}
    content = np.zeros((n, T + len(facet_names)))
    content[:, :T] = raw * idf * gw
    for r, fs in enumerate(facets):
        for p, v in fs.items():
            if v:
                content[r, fix[f"{p}:{v}"]] = FACET_W[p]
    content /= np.linalg.norm(content, axis=1, keepdims=True)
    return raw, content, facet_names


def build(a):
    tags, vd = vocabulary()
    tag_ids = list(tags)
    groups = {t: g for t, (_, _, g) in tags.items()}
    items, profiles = shelf(), load_profiles()
    books = [i for i in items if i["id"] in profiles]
    if len(books) < 20:
        sys.exit(f"only {len(books)} profiled books - run batches/merge first")
    raw, content, facet_names = vectors(books, profiles, tags)
    n = len(books)

    akeys = [author_key(b["author"]) for b in books]
    skeys = [slug(b["series"]) if b.get("series") else None for b in books]
    extra = sorted({"a:" + k for k in akeys if k} | {"s:" + k for k in skeys if k})
    eix = {f: i for i, f in enumerate(extra)}
    layout = np.zeros((n, len(extra)))
    for r in range(n):
        if akeys[r]:
            layout[r, eix["a:" + akeys[r]]] = AUTHOR_W / 10
        if skeys[r]:
            layout[r, eix["s:" + skeys[r]]] = SERIES_W / 10
    lx = np.hstack([content, layout])
    lx /= np.linalg.norm(lx, axis=1, keepdims=True)
    print(f"laying out {n} books ...", flush=True)
    by = scaled(tsne(lx, 30))

    by_author = collections.defaultdict(list)
    for r, k in enumerate(akeys):
        if k:
            by_author[k].append(r)
    alist = sorted(by_author.items())
    ax = np.array([content[rows].sum(0) for _, rows in alist])
    ax /= np.linalg.norm(ax, axis=1, keepdims=True)
    araw = np.array([raw[rows].mean(0) for _, rows in alist])
    print(f"laying out {len(alist)} authors ...", flush=True)
    ay = scaled(tsne(ax, 20))

    out = {
        "_readme": "Map positions and content vectors for the viewer's Mapa tab. Built by "
                   "`python tools/similarity.py build` from book-profiles.jsonl - rebuild after every merge. "
                   "x/y are t-SNE coordinates on 0-1000: nearness is meaningful, distance across the map "
                   "is not. Presentation only - nothing here may feed an estimate.",
        "schema": 1,
        "vd": vd,
        "_v": "Sparse unit vector [[feature, value], ...]: tags weighted by rarity and group, plus genre, "
              "form and audience. Author and series are deliberately absent - they shape the layout, "
              "not the page's similarity lists. Cosine similarity is the plain dot product.",
        "_tags": "[id, English label, Czech label, group]; feature i < len(tags) is tag i.",
        "tags": [[t, *tags[t]] for t in tag_ids],
        "facets": facet_names,
        "books": [{"id": b["id"], "x": round(float(by[r, 0]), 1), "y": round(float(by[r, 1]), 1),
                   "v": [[int(i), round(float(content[r, i]), 3)] for i in np.nonzero(content[r])[0]]}
                  for r, b in enumerate(books)],
        "authors": [{"name": books[rows[0]]["author"], "x": round(float(ay[j, 0]), 1),
                     "y": round(float(ay[j, 1]), 1), "books": rows}
                    for j, (_, rows) in enumerate(alist)],
        "regions": {"books": regions(by, raw, tag_ids, groups),
                    "authors": regions(ay, araw, tag_ids, groups, min_size=8)},
    }
    with io.open(OUT, "w", encoding="utf-8", newline="\n") as f:
        json.dump(out, f, ensure_ascii=False, separators=(",", ":"))
        f.write("\n")
    missing = len(items) - n
    print(f"wrote {OUT}: {n} books, {len(alist)} authors"
          + (f"; {missing} shelf book{'s' if missing != 1 else ''} without a profile, not on the map" if missing else ""))


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("status")
    s = sub.add_parser("batches")
    s.add_argument("outdir"), s.add_argument("--size", type=int, default=150), s.add_argument("--redo", action="store_true")
    s.add_argument("--compact", action="store_true", help="identity and blurb only, for a pass that adds a tag or two")
    s = sub.add_parser("merge")
    s.add_argument("files", nargs="+")
    s.add_argument("--add", action="store_true", help="union the tags into the existing profile instead of replacing it")
    sub.add_parser("build")
    a = ap.parse_args()
    {"status": status, "batches": batches, "merge": merge, "build": build}[a.cmd](a)


if __name__ == "__main__":
    main()
