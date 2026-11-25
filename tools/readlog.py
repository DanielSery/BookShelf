"""The reader's log in book-reviews.json: every book read, the one reader every tool goes through.

The reader scores in five words (since 2026-11-09), and every tool, rule and estimate works
on 0-100, so a word becomes its value in WORDS here and nowhere else. Books scored before the
words keep the number they were given in `logged`, out of 10 (multiplied by ten here) or out
of 100. A book not finished and left unscored has `score` None: still read (never proposed
again), but not evidence of a dislike. A `withdrawn` book is left out unless asked for.

Ids: c:<book-cache key> for a shelf book reviewed on the page, r:<slug> for a book read before
it was on the shelf; `key` is the id without its prefix, and for r: it is the join key of
book-read-facets.json, book-media.json readMedia, book-origin.json read and book-read-radar.json.

    python tools/readlog.py        # every read book, withdrawn included
"""
import io
import json
import math
import sys

REVIEWS = "book-reviews.json"
# Bands as the reader drew them in the 2026-11-09 rerank; a word counts as a typical score in its band.
WORDS = {"endorse": 92, "recommend": 75, "neutral": 60, "discourage": 50, "oppose": 30}
BANDS = [(85, "Endorse"), (65, "Recommend"), (55, "Neutral"), (45, "Discourage"), (0, "Oppose")]


def word(score):
    """92 -> 'Endorse': what the reader sees for a 0-100 score."""
    return next(w for floor, w in BANDS if score >= floor)


def score100(rv):
    """A review's score on 0-100: the number it was logged with, else its word (also when `logged`
    is not a number); None when unscored."""
    if rv.get("withdrawn"):
        return None
    try:
        x = float(str(rv.get("logged")).replace(",", "."))
    except ValueError:
        x = math.nan
    if math.isfinite(x):
        return round(x * 10) if x <= 10 else round(x)
    return WORDS.get(rv.get("score"))


def rows(path=REVIEWS, kind=None, withdrawn=False):
    """Every read book in log order; kind 'c' or 'r' keeps only that kind of id."""
    try:
        reviews = json.load(io.open(path, encoding="utf-8")).get("reviews", {})
    except FileNotFoundError:
        return []
    out = []
    for k, rv in reviews.items():
        if "score" not in rv or (kind and not k.startswith(kind + ":")) or (rv.get("withdrawn") and not withdrawn):
            continue
        out.append({"id": k, "key": k[2:], "title": rv.get("title", ""), "author": rv.get("author", ""),
                    "score": score100(rv), "notes": rv.get("notes", ""), "withdrawn": bool(rv.get("withdrawn"))})
    return out


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    for r in rows(withdrawn=True):
        s = "withdrawn" if r["withdrawn"] else "not finished" if r["score"] is None else word(r["score"])
        print(f"{r['id']} | {r['title']} | {r['author']} | {s}")
