"""Refill book-media.json — cover URLs for everything the viewer app renders.

Run from the repo root:  python tools/fetch-media.py 2026-08-26

Three namespaces, because the app has three tabs and their rows are keyed
differently:

  media       candidates  — keyed by the book key in book-cache.json
  readMedia   read books  — keyed by a slug of the title in books-read.md
  rejectMedia exclusions  — keyed by a slug of entity+author in book-rejects.jsonl

Idempotent and additive: existing covers and hand-written blurbs are preserved,
only missing covers are fetched, and entries whose source row is gone are
dropped. Blurbs are never fetched — they are authored, and a candidate without
one is reported so /book-screen can write it.

Two-pass cover lookup, because limit=1 on Open Library's search often returns a
coverless edition record even when the work has covers.

A row whose lookup came back empty is left with cover=null and a coverNote, and
later runs skip it: the note SETTLES the row. Pass --retry-missing to search for
those again, once Open Library has had time to gain the cover.
"""
import io
import json
import os
import re
import sys
import time
import unicodedata
import urllib.parse
import urllib.request

UA = {"User-Agent": "book-shelf/1.0 (personal reading list)"}
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CACHE = os.path.join(ROOT, "book-cache.json")
MEDIA = os.path.join(ROOT, "book-media.json")
READ = os.path.join(ROOT, "books-read.md")
REJECTS = os.path.join(ROOT, "book-rejects.jsonl")

# Entity strings that name a body of work rather than a book — look the author
# up instead of trying to search for "34 collections".
VAGUE = ("holdings", "short fiction", "collected fiction", "other titles",
         "non-fiction", "remaining", "religion treated", "titles on", "collections",
         "authors:")


def slug(s):
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")
    return s[:60]


def clean_title(s):
    s = re.sub(r"\([^)]*\)", " ", s)          # (series), (#2-5), (Hranicaruv ucen)
    s = s.split(" / ")[0]
    s = re.sub(r"\b(series|saga|full series|trilogy)\b", " ", s, flags=re.I)
    return re.sub(r"\s+", " ", s).strip(" ,#-")


def search(params):
    params = dict(params, fields="cover_i,isbn", limit="8")
    url = "https://openlibrary.org/search.json?" + urllib.parse.urlencode(params)
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=25) as r:
            docs = json.load(r).get("docs") or []
    except Exception:
        return None, None
    for d in docs:
        if d.get("cover_i"):
            return d["cover_i"], (d.get("isbn") or [None])[0]
    return None, None


def resolve(queries):
    for params in queries:
        cover_i, isbn = search(params)
        time.sleep(0.35)
        if cover_i:
            return cover_i, isbn
    return None, None


def fill(bucket, wanted, today, label, retry):
    """wanted: list of (key, [query dicts]). Returns (fetched, failed, dropped)."""
    fetched, failed, settled = [], [], 0
    for key, queries in wanted:
        rec = bucket.setdefault(key, {})
        if rec.get("cover"):
            continue
        if rec.get("coverNote") and not retry:
            settled += 1
            continue
        if not queries:
            rec["cover"] = None
            rec["coverNote"] = "names a group, not a book — no cover to fetch"
            continue
        cover_i, isbn = resolve(queries)
        if cover_i:
            rec["cover"] = "https://covers.openlibrary.org/b/id/%d-M.jpg" % cover_i
            rec.pop("coverNote", None)
            if isbn and not rec.get("isbn"):
                rec["isbn"] = isbn
            fetched.append(key)
        else:
            rec["cover"] = None
            rec["coverNote"] = "no cover on Open Library after two passes (%s)" % today
            failed.append(key)
    keys = {k for k, _ in wanted}
    dropped = [k for k in list(bucket) if k not in keys]
    for k in dropped:
        del bucket[k]
    print("%-12s %d rows | fetched %d | no cover %d | settled %d | dropped %d"
          % (label, len(wanted), len(fetched), len(failed), settled, len(dropped)))
    return failed


def read_rows():
    md = io.open(READ, encoding="utf-8").read().split("\n")
    head = next(i for i, l in enumerate(md)
                if re.match(r"^\|\s*Book\s*\|\s*Author\s*\|\s*Score\s*\|", l, re.I))
    out = []
    for l in md[head + 2:]:
        l = l.strip()
        if not l.startswith("|"):
            break
        c = [x.strip() for x in l.strip("|").split("|")]
        if len(c) == 5 and c[2].isdigit():
            out.append((c[0], c[1]))
    return out


def main():
    argv = sys.argv[1:]
    retry = "--retry-missing" in argv
    today = next((a for a in argv if not a.startswith("-")), None)
    if not today or not re.match(r"^\d{4}-\d{2}-\d{2}$", today):
        sys.exit("pass today's date as YYYY-MM-DD — this script must not guess it")

    cache = json.load(io.open(CACHE, encoding="utf-8"))
    try:
        data = json.load(io.open(MEDIA, encoding="utf-8"))
    except FileNotFoundError:
        data = {"schema": 1}
    media = data.setdefault("media", {})
    read_media = data.setdefault("readMedia", {})
    reject_media = data.setdefault("rejectMedia", {})

    candidates = [(b["key"], [{"title": b.get("title", ""), "author": b.get("author", "")},
                              {"q": "%s %s" % (b.get("title", ""), b.get("author", ""))},
                              {"q": b.get("czTitle") or b.get("title", "")}])
                  for b in cache["books"]]

    reads = []
    for title, author in read_rows():
        t = clean_title(title)
        reads.append((slug(title), [{"title": t, "author": author},
                                    {"q": "%s %s" % (t, author)}]))

    rejects = []
    skipped_bulk = 0
    for line in io.open(REJECTS, encoding="utf-8").readlines()[1:]:
        r = json.loads(line)
        # A heading veto is a bulk mechanical exclusion written by
        # tools/screen-headings.py, not a book anybody looked at, and there are ~1,200
        # of them against ~160 rows a model or the reader actually decided. Fetching
        # covers for them would be ~2,400 Open Library requests - the two-pass lookup
        # doubles it - on the population Open Library is worst at (Czech-language
        # titles), to illustrate rows nobody needs to recognise by their cover.
        if (r.get("source") or "").startswith("catalogue-heading"):
            skipped_bulk += 1
            continue
        author = r.get("author") or ""
        key = slug(r["entity"] + "-" + author)
        ent, level = r["entity"], r["level"]
        vague = (ent.startswith("(") or ent[:1].isdigit()
                 or any(v in ent.lower() for v in VAGUE))
        if level == "category" or not author or author.startswith("("):
            queries = []
        elif vague or level == "author":
            queries = [{"author": author}]
        else:
            t = clean_title(ent)
            queries = [{"title": t, "author": author}, {"author": author}]
        rejects.append((key, queries))

    fill(media, candidates, today, "candidates", retry)
    fill(read_media, reads, today, "read", retry)
    fill(reject_media, rejects, today, "rejected", retry)
    if skipped_bulk:
        print("%-12s %d rows | heading vetoes, no cover fetched by design"
              % ("bulk", skipped_bulk))

    data["fetched"] = today
    data["schema"] = 2
    data["_readme"] = (
        "Cover URLs and neutral blurbs for everything the viewer app renders. Three "
        "namespaces because the tabs are keyed differently: `media` by book-cache.json key, "
        "`readMedia` by a slug of the books-read.md title, `rejectMedia` by a slug of "
        "entity+author in book-rejects.jsonl. Fully regenerable: run tools/fetch-media.py. "
        "Kept out of book-cache.json so a cover refresh never has to reserialise that "
        "hand-formatted file. Blurbs say what the book IS; whether the reader would like it "
        "is book-estimates.jsonl's `why` and must not be duplicated here. A slug join is "
        "deliberately loose - editing a title in books-read.md costs a placeholder cover, "
        "never a broken row.")
    data["_null_cover"] = (
        "null with a coverNote is a SETTLED row, not a gap: the search already ran on "
        "the date in the note and Open Library had nothing, so the app draws a "
        "typographic placeholder and its Gaps panel does not count it - re-running this "
        "script cannot clear it, and reporting it would name a shortfall the reader can "
        "do nothing about. Later runs skip it too; --retry-missing searches again. "
        "'names a group, not a book' means the row covers an author or a category, so "
        "there is no single cover that would be honest. null with NO coverNote is the "
        "real gap: a row nothing has looked up yet.")
    io.open(MEDIA, "w", encoding="utf-8", newline="\n").write(
        json.dumps(data, ensure_ascii=False, indent=1) + "\n")

    noblurb = [k for k, _ in candidates if not media[k].get("blurb")]
    if noblurb:
        print("NO BLURB (write one in /book-screen Phase 6):", ", ".join(noblurb))


if __name__ == "__main__":
    main()
