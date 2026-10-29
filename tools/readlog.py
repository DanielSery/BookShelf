"""books-read.md, the reader's own log.

The reader scores on 0-10 (since 2026-10-29), and every tool, rule and estimate works on
0-100, so a logged score is multiplied by ten here and nowhere else. The log holds two tables
with the same header: the scored books, and books not finished that he chose not to score.
An unscored row is still a read book (never proposed again), but its `score` is None and it
is not evidence of a dislike.
"""
import io
import re

READ = "books-read.md"
HEAD = re.compile(r"^\|\s*Book\s*\|\s*Author\s*\|\s*Score\s*\|", re.I)
SEP = re.compile(r"^\|[\s:|-]+\|$")


def score100(cell):
    """'9.2' -> 92, '8' -> 80, anything that is not a number -> None (not scored)."""
    v = cell.strip().replace(",", ".")
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
