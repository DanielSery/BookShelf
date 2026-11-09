"""books-read.md, the reader's own log.

The reader scores in five words (since 2026-11-09), and every tool, rule and estimate works
on 0-100, so a logged word becomes its value in WORDS here and nowhere else. Older rows keep
the number they were logged with, out of 10 (multiplied by ten here) or out of 100. The log
holds two tables with the same header: the scored books, and books not finished that he
chose not to score. An unscored row is still a read book (never proposed again), but its
`score` is None and it is not evidence of a dislike.
"""
import io
import re

READ = "books-read.md"
HEAD = re.compile(r"^\|\s*Book\s*\|\s*Author\s*\|\s*Score\s*\|", re.I)
SEP = re.compile(r"^\|[\s:|-]+\|$")
# Bands as the reader drew them in his 2026-11-09 rerank; a word counts as a typical score in its band.
WORDS = {"endorse": 92, "recommend": 75, "neutral": 60, "discourage": 50, "oppose": 30}
BANDS = [(85, "Endorse"), (65, "Recommend"), (55, "Neutral"), (45, "Discourage"), (0, "Oppose")]


def word(score):
    """92 -> 'Endorse': what the reader sees for a 0-100 score."""
    return next(w for floor, w in BANDS if score >= floor)


def score100(cell):
    """'Recommend' -> 80, '9.2' -> 92, '8' -> 80, anything else -> None (not scored)."""
    v = cell.strip().replace(",", ".")
    if v.lower() in WORDS:
        return WORDS[v.lower()]
    if not re.fullmatch(r"\d+(\.\d+)?", v):
        return None
    x = float(v)
    return round(x * 10) if x <= 10 else round(x)


def rows(path=READ):
    out, inside = [], False
    try:
        lines = io.open(path, encoding="utf-8").read().split("\n")
    except OSError:
        return out
    for line in lines:
        s = line.strip()
        if HEAD.match(s):
            inside = True
            continue
        if not inside:
            continue
        if not s.startswith("|"):
            inside = False
            continue
        if SEP.match(s):
            continue
        c = [x.strip() for x in s.strip("|").split("|")]
        if len(c) < 4 or not c[0]:
            continue
        out.append({"title": c[0], "author": c[1], "score": score100(c[2]), "notes": c[-1]})
    return out
