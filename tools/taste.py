"""Taste markers: the per-book input of the no-agent estimate.

A book's markers say what in it moves the reader's score (book-markers.json holds the
vocabulary and each marker's prior effect). Screening sets them once per book; after that
the estimate is arithmetic: baseline plus each marker's effect, with the effects fitted
from the reader's reviews and pulled toward their priors.

    python tools/taste.py status
    python tools/taste.py batches <outdir> [--size 120] [--read] [--redo] [--min-mid 60]
        -> one agent per batch file, following tools/taste-prompt.md
    python tools/taste.py merge <files...>
    python tools/taste.py ticks <outdir>
        -> read books with the reader's notes, for the ticks step of tools/taste-prompt.md
    python tools/taste.py merge-ticks <files...>
    python tools/taste.py fit
"""
import argparse
import hashlib
import io
import json
import sys

import numpy as np

import similarity

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8")
    except AttributeError:
        pass

MARKERS, TASTE, REVIEWS = "book-markers.json", "book-taste.jsonl", "book-reviews.json"
DEFAULT_SHAPE = [0.33, 0.67, 1.0]
WORD = {"endorse": 92, "recommend": 75, "neutral": 60, "discourage": 50, "oppose": 30}


def vocabulary():
    markers = {m["id"]: m for m in json.load(io.open(MARKERS, encoding="utf-8"))["markers"]}
    digest = hashlib.sha256(" ".join(sorted(markers)).encode()).hexdigest()[:12]
    return markers, digest


def load_taste():
    try:
        lines = io.open(TASTE, encoding="utf-8").read().splitlines()
    except FileNotFoundError:
        return {}
    return {t["id"]: t for t in map(json.loads, lines[1:]) if t.get("id")}


def save_taste(taste):
    head = {
        "_readme": "Taste markers per shelf book: marker id -> strength (1 minor, 2 clear, 3 central), "
                   "in the vocabulary of book-markers.json. Written by tools/taste.py merge from agent "
                   "output following tools/taste-prompt.md. Ids as in book-profiles.jsonl.",
        "schema": 1,
        "_vd": "Digest of the marker ids when the book was marked; an older vd still counts, but "
               "`status` reports it because the book never had the chance to use a marker added since.",
    }
    with io.open(TASTE, "w", encoding="utf-8", newline="\n") as f:
        f.write(json.dumps(head, ensure_ascii=False) + "\n")
        for k in sorted(taste):
            f.write(json.dumps(taste[k], ensure_ascii=False) + "\n")


def load_reviews():
    try:
        return json.load(io.open(REVIEWS, encoding="utf-8"))
    except FileNotFoundError:
        return {
            "_readme": "The reader's reviews, keyed like book-taste.jsonl. `helped` / `hurt` name the "
                       "markers he says raised or lowered his score; `added` holds markers a book turned "
                       "out to have that screening missed. Read books logged before the page could take "
                       "reviews have their score in books-read.md and their ticks drawn from its notes.",
            "schema": 1,
            "reviews": {},
        }


def status(a):
    _, vd = vocabulary()
    items, taste = similarity.shelf(), load_taste()
    have = [i for i in items if i["id"] in taste]
    old = sum(1 for i in have if taste[i["id"]].get("vd") != vd)
    reads = [i for i in items if i["id"].startswith("r:")]
    ticked = load_reviews()["reviews"]
    print(f"{len(have)} of {len(items)} shelf books marked; {old} on an older vocabulary; "
          f"{sum(1 for i in reads if i['id'] in ticked)} of {len(reads)} read books ticked")


def shortlist(min_mid):
    """Candidates in Czech print whose agent estimate centres on min_mid or more."""
    cache = {b["key"]: b for b in json.load(io.open(similarity.CACHE, encoding="utf-8"))["books"]}
    out = set()
    for line in io.open(similarity.EST, encoding="utf-8"):
        if not line.startswith('{"key"'):
            continue
        e = json.loads(line)
        if (not e.get("blocked") and e.get("est") and sum(e["est"]) / 2 >= min_mid
                and cache.get(e["key"], {}).get("cz", {}).get("state") == "verified"):
            out.add("c:" + e["key"])
    return out


def batches(a):
    taste = load_taste()
    keep = shortlist(a.min_mid) if a.min_mid is not None else None
    todo = [i for i in similarity.shelf()
            if (a.redo or i["id"] not in taste) and (not a.read or i["id"].startswith("r:"))
            and (keep is None or i["id"] in keep)]
    for n in range(0, len(todo), a.size):
        path = f"{a.outdir}/taste_{n // a.size:03d}.jsonl"
        with io.open(path, "w", encoding="utf-8", newline="\n") as f:
            for i in todo[n:n + a.size]:
                # A read book is marked blind, as a candidate would be: its notes are the reader's
                # verdict, and marking from them would make the fit look better than it can be.
                line = {k: v for k, v in i.items() if v and not (k == "notes" and i["id"].startswith("r:"))}
                f.write(json.dumps(line, ensure_ascii=False) + "\n")
        print(path, min(a.size, len(todo) - n))
    print(f"{len(todo)} books to mark")


def _check_markers(got, markers, where, bad):
    out = {}
    for t, s in (got or {}).items():
        if t not in markers:
            bad.append(f"{where}: unknown marker {t}")
        elif s not in (1, 2, 3):
            bad.append(f"{where}: {t} strength {s!r}")
        else:
            out[t] = s
    return out


def merge(a):
    markers, vd = vocabulary()
    ids = {i["id"] for i in similarity.shelf()}
    taste = load_taste()
    ok, bad = 0, []
    for path in a.files:
        for line in io.open(path, encoding="utf-8"):
            if not line.strip():
                continue
            d = json.loads(line)
            k = d.get("id")
            if k not in ids:
                bad.append(f"{k}: not on the shelf")
                continue
            taste[k] = {"id": k, "m": dict(sorted(_check_markers(d.get("m"), markers, k, bad).items())), "vd": vd}
            ok += 1
    for k in set(taste) - ids:
        del taste[k]
    save_taste(taste)
    print(f"merged {ok}")
    for b in bad:
        print("  !", b)


def ticks(a):
    taste = load_taste()
    reads = [i for i in similarity.shelf() if i["id"].startswith("r:") and i.get("notes")]
    path = f"{a.outdir}/ticks.jsonl"
    with io.open(path, "w", encoding="utf-8", newline="\n") as f:
        for i in reads:
            f.write(json.dumps({"id": i["id"], "title": i["title"], "author": i["author"], "notes": i["notes"],
                                "m": taste.get(i["id"], {}).get("m", {})}, ensure_ascii=False) + "\n")
    print(path, len(reads))


def merge_ticks(a):
    markers, _ = vocabulary()
    ids = {i["id"] for i in similarity.shelf() if i["id"].startswith("r:")}
    doc = load_reviews()
    ok, bad = 0, []
    for path in a.files:
        for line in io.open(path, encoding="utf-8"):
            if not line.strip():
                continue
            d = json.loads(line)
            k = d.get("id")
            if k not in ids:
                bad.append(f"{k}: not a read book")
                continue
            r = doc["reviews"].setdefault(k, {})
            for side in ("helped", "hurt"):
                unknown = [t for t in d.get(side) or [] if t not in markers]
                bad += [f"{k}: unknown marker {t}" for t in unknown]
                r[side] = sorted(t for t in d.get(side) or [] if t in markers)
            r["added"] = dict(sorted(_check_markers(d.get("added"), markers, k, bad).items()))
            ok += 1
    with io.open(REVIEWS, "w", encoding="utf-8", newline="\n") as f:
        json.dump(doc, f, ensure_ascii=False, indent=1)
        f.write("\n")
    print(f"merged ticks for {ok}")
    for b in bad:
        print("  !", b)


def design(markers, profiles, taste, reviews):
    """Scored books as rows: blind markers (what screening sees) and reviewed markers (what training sees)."""
    graded = [m for m in markers.values() if m["kind"] == "graded"]
    tags = sorted({t for p in profiles.values() for t in p["tags"]})
    cols = [m["id"] for m in graded] + ["tag:" + t for t in tags]
    prior = np.array([m["prior"] for m in graded] + [0.0] * len(tags))
    is_tag = np.array([False] * len(graded) + [True] * len(tags))
    shape = {m["id"]: m.get("shape", DEFAULT_SHAPE) for m in graded}

    def row(m, tagw):
        x = np.zeros(len(cols))
        for i, mid in enumerate(cols[:len(graded)]):
            if m.get(mid):
                x[i] = shape[mid][m[mid] - 1]
        for j, t in enumerate(tags):
            x[len(graded) + j] = tagw.get(t, 0) / 3
        return x

    # Read books score in books-read.md; shelf books reviewed on the page carry a dated score word.
    scored = [("r:" + similarity.slug(r["title"]), r.get("score")) for r in similarity.readlog.rows(similarity.READ)]
    scored += [(k, WORD.get(rv.get("score"))) for k, rv in reviews.items() if k.startswith("c:") and rv.get("at")]
    rows = []
    for k, y in scored:
        rv = reviews.get(k, {})
        if y is None or (k not in taste and not rv.get("added")):
            continue
        blind = taste.get(k, {}).get("m", {})
        seen = {**blind, **{t: max(s, blind.get(t, 0)) for t, s in (rv.get("added") or {}).items()}}
        seen = {t: s for t, s in seen.items() if t not in (rv.get("removed") or [])}
        if any(markers[t]["kind"] == "veto" for t in seen):
            continue
        tagw = profiles.get(k, {}).get("tags", {})
        ticked = set(rv.get("helped", [])) | set(rv.get("hurt", []))
        rows.append({"id": k, "y": float(y), "blind": row(blind, tagw), "seen": row(seen, tagw),
                     "ticked": {cols.index(t) for t in ticked if t in cols}})
    return cols, prior, is_tag, rows


def solve(rows, prior, lam, relax):
    """Ridge toward the priors, each marker kept on its prior's side of zero.

    A marker the reader has ticked on n books is pulled toward its prior 1 + relax*n times
    more weakly: he has said it matters, so his scores may move it further.
    """
    X = np.array([r["seen"] for r in rows])
    y = np.array([r["y"] for r in rows])
    A = np.c_[np.ones(len(y)), X]
    n = np.zeros(len(lam))
    for r in rows:
        for c in r["ticked"]:
            n[c] += 1
    base = np.r_[0.0, lam / (1 + relax * n)]
    lock = np.r_[0.0, np.sign(prior)]
    pinned = np.zeros(len(base), bool)
    for _ in range(len(base)):
        L = np.diag(np.where(pinned, 1e9, base))
        target = np.where(pinned, 0.0, np.r_[0.0, prior])
        theta = np.linalg.solve(A.T @ A + L, A.T @ y + L @ target)
        wrong = (lock * theta < 0) & ~pinned
        if not wrong.any():
            break
        pinned |= wrong
    return theta


def fit(a):
    markers, _ = vocabulary()
    profiles = similarity.load_profiles()
    cols, prior, is_tag, rows = design(markers, profiles, load_taste(), load_reviews()["reviews"])
    y = np.array([r["y"] for r in rows])
    print(f"{len(rows)} scored read books with markers (vetoed ones left out); "
          f"guess-the-mean {np.mean(np.abs(y - y.mean())):.1f}")

    def loo(lam, relax):
        err = []
        for i, r in enumerate(rows):
            theta = solve([t for j, t in enumerate(rows) if j != i], prior, lam, relax)
            err.append(abs(theta[0] + r["blind"] @ theta[1:] - r["y"]))
        return float(np.mean(err))

    lam_of = lambda lt, lg: np.where(is_tag, lg, lt)
    theta0 = solve(rows, prior, lam_of(1e9, 1e9), 0)
    print(f"priors only, baseline fitted: {np.mean(np.abs(theta0[0] + np.array([r['blind'] for r in rows]) @ prior - y)):.1f}")
    best = None
    for lt in a.lam_taste:
        for lg in a.lam_tags:
            for relax in a.relax:
                e = loo(lam_of(lt, lg), relax)
                if best is None or e < best[0]:
                    best = (e, lt, lg, relax)
                print(f"lam_taste={lt:<4} lam_tags={lg:<4} relax={relax:<3} LOO {e:.1f}")
    e, lt, lg, relax = best
    theta = solve(rows, prior, lam_of(lt, lg), relax)
    print(f"\nbest LOO {e:.1f} at lam_taste={lt} lam_tags={lg} relax={relax}; baseline {theta[0]:.1f}")
    moved = sorted(((theta[i + 1] - prior[i], cols[i], prior[i], theta[i + 1]) for i in range(len(cols)) if not is_tag[i]),
                   key=lambda x: -abs(x[0]))
    for d, c, p, w in moved[:15]:
        print(f"  {c:28} prior {p:+6.1f} -> {w:+6.1f}")


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("status")
    s = sub.add_parser("batches")
    s.add_argument("outdir"), s.add_argument("--size", type=int, default=120)
    s.add_argument("--read", action="store_true"), s.add_argument("--redo", action="store_true")
    s.add_argument("--min-mid", type=float, help="only Czech-print candidates whose agent estimate centres here or higher")
    s = sub.add_parser("merge")
    s.add_argument("files", nargs="+")
    s = sub.add_parser("ticks")
    s.add_argument("outdir")
    s = sub.add_parser("merge-ticks")
    s.add_argument("files", nargs="+")
    s = sub.add_parser("fit")
    s.add_argument("--lam-taste", type=float, nargs="+", default=[2, 5, 10])
    s.add_argument("--lam-tags", type=float, nargs="+", default=[50])
    s.add_argument("--relax", type=float, nargs="+", default=[0, 1, 3])
    a = ap.parse_args()
    {"status": status, "batches": batches, "merge": merge, "ticks": ticks,
     "merge-ticks": merge_ticks, "fit": fit}[a.cmd](a)


if __name__ == "__main__":
    main()
