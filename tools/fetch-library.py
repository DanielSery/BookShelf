"""Resolve each Czech-print candidate to its library catalogue record.

Run from the repo root:  python tools/fetch-library.py 2026-08-26

Writes, per matched book:
  book-cache.json   cz.recordId, cz.recordUrl   — the borrow link
  book-media.json   cover (Czech edition), coverSource, isbn

Verified 2026-08-26, not guessed:
  * the record page route is `/records/[recordId]` — found in the catalogue's
    own SvelteKit route manifest (`_bundle_/immutable/entry/app.*.js`). Probing
    URLs proves nothing: the server returns the same 113 KB SPA shell for every
    path, including nonsense ones.
  * `recordId` is the API record's `id` (a UUID), not its `directoryId`:
    `api/records/<uuid>` returns the record, while both a bogus UUID and the
    directoryId return ItemNotFoundException.
  * the cover lives behind `api/files/<record.cover.id>`, whose `source` field is
    an obalkyknih.cz URL. That is the edition the reader would actually borrow,
    so it beats the Open Library cover and overwrites it.

A book is only linked on a confident title match. A wrong borrow link is worse
than none, so an ambiguous result is left unlinked and reported.
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
BASE = "https://katalog.mekvalmez.cz"
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CACHE = os.path.join(ROOT, "book-cache.json")
MEDIA = os.path.join(ROOT, "book-media.json")

AUDIO_HINT = re.compile(r"zvukov|audiokni|\bčte\b|cte\b|mp3|CD-ROM", re.I)

# The publisher is often the only tell. *Pilíře země* matched the Témbr audio
# edition ahead of the Knižní klub print one on 2026-08-26, with nothing in the
# title or responsibility statement to distinguish them.
AUDIO_PUBLISHER = re.compile(r"t[eé]mbr|onehotbook|tympanum|audiot[eé]ka|k\.?\s*e\.?\s*macan|supraphon", re.I)


def deaccent(s):
    s = unicodedata.normalize("NFKD", s)
    return "".join(c for c in s if not unicodedata.combining(c))


def norm(s):
    return re.sub(r"[^a-z0-9 ]+", " ", deaccent(s).lower()).strip()


def api(path, params=None):
    url = BASE + path + ("?" + urllib.parse.urlencode(params, quote_via=urllib.parse.quote) if params else "")
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=25) as r:
            return json.load(r)
    except Exception as e:
        print("   ! %s: %s" % (path, type(e).__name__))
        return None


def search(query):
    # Diacritics in the first significant word return zero hits - a documented
    # trap in this catalogue, not a general URL-encoding issue.
    d = api("/api/search", {"q": deaccent(query), "pageSize": "30"})
    return ((d or {}).get("result") or {}).get("content") or []


def pick(records, want_title, want_author):
    wt, wa = norm(want_title), norm(want_author).split()
    surname = wa[-1] if wa else ""
    best, best_score = None, 0
    for r in records:
        name = norm(r.get("name") or "")
        resp = (r.get("responsibilityStatement") or {}).get("value") or ""
        blob = norm(name + " " + resp)
        if not name:
            continue
        if name == wt:
            score = 100
        elif wt and (wt in name or name in wt):
            score = 70
        else:
            continue
        if surname and surname in blob:
            score += 20
        if AUDIO_HINT.search(resp) or AUDIO_HINT.search(r.get("text") or ""):
            score -= 45
        pubs = " ".join((p.get("text") or p.get("name") or "") for p in (r.get("publishers") or []))
        if AUDIO_PUBLISHER.search(pubs):
            score -= 45
        if r.get("periodical"):
            score -= 30
        if score > best_score:
            best, best_score = r, score
    return (best, best_score) if best_score >= 70 else (None, best_score)


def cover_url(record):
    cid = (record.get("cover") or {}).get("id")
    if not cid:
        return None
    d = api("/api/files/%s" % cid)
    src = (d or {}).get("source")
    return src if src and src.startswith("http") else None


# --- a stable compact writer, so this file stays diffable and greppable -------
INLINE_MAX = 150


def dump(v, indent=0):
    pad = " " * indent
    if isinstance(v, dict):
        flat = json.dumps(v, ensure_ascii=False, separators=(", ", ": "))
        if len(flat) <= INLINE_MAX and not any(isinstance(x, (dict, list)) for x in v.values()):
            return flat
        inner = ",\n".join("%s  \"%s\": %s" % (pad, k, dump(x, indent + 2)) for k, x in v.items())
        return "{\n%s\n%s}" % (inner, pad)
    if isinstance(v, list):
        flat = json.dumps(v, ensure_ascii=False, separators=(", ", ": "))
        if len(flat) <= INLINE_MAX:
            return flat
        inner = ",\n".join("%s  %s" % (pad, dump(x, indent + 2)) for x in v)
        return "[\n%s\n%s]" % (inner, pad)
    return json.dumps(v, ensure_ascii=False)


def main():
    today = sys.argv[1] if len(sys.argv) > 1 else None
    if not today or not re.match(r"^\d{4}-\d{2}-\d{2}$", today):
        sys.exit("pass today's date as YYYY-MM-DD — this script must not guess it")
    force = "--force" in sys.argv
    only = next((a for a in sys.argv[2:] if not a.startswith("-")), None)

    cache = json.load(io.open(CACHE, encoding="utf-8"))
    media = json.load(io.open(MEDIA, encoding="utf-8"))
    mm = media.setdefault("media", {})

    linked, skipped, covers = [], [], 0
    for b in cache["books"]:
        cz = b.get("cz") or {}
        if cz.get("state") != "verified":
            continue
        if only and b["key"] != only:
            continue
        if not force and cz.get("recordUrl") and mm.get(b["key"], {}).get("coverSource") == "katalog":
            continue
        title = b.get("czTitle") or b.get("title") or ""
        author = b.get("author") or ""
        # WHICH EDITION is a judgement, not a lookup, so an id already on the row wins.
        # pick() only knows title, surname and audio-ness; on 2026-08-26 it moved eight
        # rows to a different edition and two of them were editions the estimate had
        # explicitly ruled out - Bozska komedie to the Vrchlicky translation and Jana
        # Eyrova to the abridged CooBoo one. Re-resolve only with --force, or when
        # there is no id, or when the stored id has stopped resolving.
        rec, score = None, 0
        if not force and cz.get("recordId"):
            rec = api("/api/records/%s" % cz["recordId"])
            if rec:
                score = 100
            time.sleep(0.2)
        if not rec:
            recs = search("%s %s" % (title, author.split()[-1] if author else ""))
            if not recs:
                recs = search(title)
            rec, score = pick(recs, title, author)
            time.sleep(0.3)
        if not rec:
            skipped.append("%s (%d hits, best score %d)" % (b["key"], len(recs), score))
            continue
        cz["recordId"] = rec["id"]
        cz["recordUrl"] = "%s/records/%s" % (BASE, rec["id"])
        cz["recordChecked"] = today
        # Overwrite only what this tool wrote. A hand-curated publisher stays;
        # one it filled in earlier must be corrected when the match moves, or a
        # re-resolve leaves the old edition's publisher next to the new record.
        if rec.get("publishers") and (not cz.get("publisher") or cz.get("publisherSource") == "katalog"):
            pub = rec["publishers"][0]
            cz["publisher"] = pub.get("text") or pub.get("name")
            cz["publisherSource"] = "katalog"
            # The year comes from the same record and must move with it. Updating the
            # publisher and not the year left 15 rows describing one edition while
            # linking another - Bozska komedie read "Academia 2009" beside a Dobrovsky
            # 2013 link.
            y = (rec.get("publicationStartYear") or {}).get("value")
            if y:
                cz["year"] = int(y)
        isbns = rec.get("isbns") or []
        url = cover_url(rec)
        time.sleep(0.3)
        m = mm.setdefault(b["key"], {})
        if url:
            m["cover"] = url
            m["coverSource"] = "katalog"
            m.pop("coverNote", None)
            covers += 1
        if isbns and not m.get("isbn"):
            m["isbn"] = isbns[0].get("value")
        linked.append(b["key"])

    io.open(CACHE, "w", encoding="utf-8", newline="\n").write(dump(cache) + "\n")
    media["fetched"] = today
    io.open(MEDIA, "w", encoding="utf-8", newline="\n").write(
        json.dumps(media, ensure_ascii=False, indent=1) + "\n")

    print("linked %d records | %d Czech-edition covers | %d unmatched"
          % (len(linked), covers, len(skipped)))
    for s in skipped:
        print("  no confident match:", s)


if __name__ == "__main__":
    main()
