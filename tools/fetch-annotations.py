"""Pull the catalogue's own Anotace for every work, so the ranking model is not guessing.

The single biggest weakness of the 2026-08-26 ranking run was that 58 % of verdicts
were `3`, which in that prompt meant "I do not know this book". The model was sent
`title | author | publisher | year` and nothing else. The catalogue holds a real
Czech plot summary in MARC field 520, labelled `Anotace`, and it was never used.

Measured 2026-08-26 on a 400-record sample:
  * the BULK SEARCH endpoint returns it inside `detailTableRows` - no per-record
    fetches, so the whole corpus costs ~253 requests rather than ~15,000
  * coverage 91 %
  * length p10 146 / median 386 / p90 1084 / max 3333 chars, so ~96 tokens median

Truncated to TRUNC chars on the way in. The first two or three sentences carry the
premise and the protagonist, which is what the axes need; the p90 tail is
publisher marketing and would triple the token cost of a ranking run for nothing.

    python tools/fetch-annotations.py <scratchdir> [--out book-annotations.jsonl]
    python tools/fetch-annotations.py --from-triage [--src a,b] [--max-queries N] [--out FILE]

The first form reads the `q` field the original pull files recorded, so it re-sweeps
exactly the queries that built book-triage.jsonl and the join cannot drift. Its
weakness: those pull files do not survive a session, so a slice pulled earlier can
never be re-swept — and two never were, leaving `ceska-proza` at 8.8% annotation
coverage and `povidky` at 14.7% against 90-99% elsewhere. `--from-triage` derives the
queries from book-triage.jsonl instead and MERGES rather than rewriting.

It also writes `book-catalog.jsonl`: page count, genre/form heading, subject keywords,
series statement and original title, all from the SAME response as the Anotace. Before
2026-08-27 every one of those was fetched and thrown away, while the ranking and
promotion steps paid a model to guess them.

WHAT AN ANNOTATION IS NOT: it is publisher copy. It reliably carries premise,
protagonist and setting. It does NOT carry opening structure, whether occult is
enacted in a scene, crudeness of sexual treatment, or what the book leaves you
thinking about - and it is promotional, so it overclaims in one direction. Good
enough to rank with, never enough to estimate with.
"""
import json, io, os, re, sys, time, collections, unicodedata, html, statistics
import urllib.parse, urllib.request

UA = {"User-Agent": "Mozilla/5.0 (book-shelf/1.0 personal reading list)"}
BASE = "https://katalog.mekvalmez.cz/api/search"
SLICES = ("full.jsonl", "cat.jsonl", "pov.jsonl", "proza.jsonl", "cz.jsonl",
          "sweep.jsonl", "sw2.jsonl")
TRUNC = 500
TAG = re.compile(r"<[^>]+>")


def norm(s):
    s = unicodedata.normalize("NFKD", s or "")
    s = "".join(c for c in s if not unicodedata.combining(c)).lower()
    return re.sub(r"[^a-z0-9]+", "-", s).strip("-")


def workkey(t, a):
    return f"{norm(t)[:48]}~{norm(a)[:32]}"


def anot(rec):
    for row in rec.get("detailTableRows") or []:
        c = row.get("columns") or []
        if len(c) >= 2 and "notac" in (c[0].get("content") or ""):
            txt = TAG.sub(" ", c[1].get("content") or "")
            txt = re.sub(r"\s+", " ", txt).strip()
            # The catalogue runs sentences together ("veci.Essun, ktera"), which
            # reads as one word to a tokeniser and to a human.
            txt = re.sub(r"([a-záčďéěíňóřšťúůýž])\.([A-ZÁČĎÉĚÍŇÓŘŠŤÚŮÝŽ])", r"\1. \2", txt)
            return txt[:TRUNC]
    return ""


FACTS = "book-catalog.jsonl"
# MARC subfield $a of the fields worth having, by the class the catalogue renders.
SUBA = re.compile(r'<span class="field_a fieldtype-d(\d+)-a"[^>]*>(.*?)</span>', re.S)
PAGES = re.compile(r"(\d[\d\s]*)\s*(?:s\.|str\.|stran)", re.I)
# "z anglického originálu An Echo of Things to Come ... přeložil Milan Pohl"
ORIG = re.compile(r"origin[áa]lu?\s+(.+?)(?:\s+(?:\.\.\.|p[řr]elo[žz]il\w*|vydan\w*|\[)|\s*;|\s*$)",
                  re.I)


def cell(rows, want):
    """Every $a value under a label matching `want`, entity-decoded, tags stripped."""
    out = []
    for lab, val in rows:
        if not want(lab):
            continue
        got = [html.unescape(TAG.sub("", m.group(2))).strip() for m in SUBA.finditer(val)]
        if not got:
            got = [html.unescape(re.sub(r"\s+", " ", TAG.sub(" ", val))).strip()]
        out += [g for g in got if g]
    return out


def facts(rec):
    """Structured MARC the ranking and promotion steps currently pay a model to guess.

    Added 2026-08-27 at the reader's request. Coverage measured on a 500-record sample:
    physical description 83%, keywords (653) 41%, genre/form (655) 33%, series ~20%,
    original title 11%. All of it arrives in the SAME bulk-search response as the
    Anotace, which the earlier sweep was fetching and discarding.

    Why each one is worth a field rather than a guess:
      pages   decides `form` (novella vs novel, which suspends the character rules) and
              feeds axis:density. The promotion contract currently asks an agent to
              research it.
      gf      a LIBRARIAN's controlled genre heading - `detektivni romany`,
              `eroticke romany`. That answers gate 1 and the new gate 3 better than a
              model reading promotional copy, and better than triage.py's title regex.
      kw      free subject terms, so filter routing rather than a verdict: carodejnictvi,
              nevera, erotika.
      series  the volume's series statement, which is what would have caught the
              MARC 245 $a collapse that mislinked Sirotcinec slecny Peregrinove.
      orig    the original title - the name a translated book is actually known by, and
              the only field here that can move `rec` from 0 to 1 rather than merely
              improving a premise guess. ~11% of records, ~1,200 unranked works.
    """
    rows = []
    for row in rec.get("detailTableRows") or []:
        c = row.get("columns") or []
        if len(c) >= 2:
            rows.append((TAG.sub("", c[0].get("content") or "").strip(),
                         c[1].get("content") or ""))
    d = {}
    phys = cell(rows, lambda l: l.startswith("Fyzick"))
    for p in phys:
        m = PAGES.search(p)
        if m:
            n = int(re.sub(r"\s+", "", m.group(1)))
            # A three-digit floor is not imposed: a 48-page picture book is a real and
            # useful reading. Only absurd values are dropped.
            if 4 <= n <= 5000:
                d["pages"] = n
                break
    gf = cell(rows, lambda l: "nr/forma" in l)
    kw = cell(rows, lambda l: "kl" in l and "slova" in l)
    ser = cell(rows, lambda l: l.startswith("Údaje o edici") or "propojen" in l)
    if gf:
        d["gf"] = sorted({g.lower() for g in gf})
    if kw:
        d["kw"] = sorted({k.lower() for k in kw})
    if ser:
        d["series"] = ser[0][:120]
    m = ORIG.search((rec.get("responsibilityStatement") or {}).get("text") or "")
    if m:
        t = m.group(1).strip(" .,:;")
        if 2 < len(t) <= 120:
            d["orig"] = t
    return d


def merge_facts(cur, new):
    """One work, several editions. Union the vocabularies; take the MEDIAN page count.

    Median, not max: an omnibus and a school abridgement of the same work both appear,
    and the number that decides `form` is the ordinary single-volume one.
    """
    for f in ("gf", "kw"):
        if new.get(f):
            cur[f] = sorted(set(cur.get(f, [])) | set(new[f]))
    for f in ("series", "orig"):
        if new.get(f) and not cur.get(f):
            cur[f] = new[f]
    if new.get("pages"):
        cur.setdefault("_pp", []).append(new["pages"])
        cur["pages"] = int(statistics.median(cur["_pp"]))
    return cur


def get(q, page):
    url = BASE + "?" + urllib.parse.urlencode(
        {"q": q, "pageSize": 100, "pageNumber": page}, quote_via=urllib.parse.quote)
    for _ in range(3):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=45) as r:
                return json.load(r)
        except Exception:
            time.sleep(2)
    return None


STOP = {"a", "o", "v", "na", "do", "za", "ze", "se", "po", "pro", "od", "u", "s", "k",
        "the", "de", "la", "der", "die", "das", "and", "of"}


def sigword(title):
    """First significant word of a title, de-accented — the query triage itself used."""
    for w in re.split(r"[^0-9A-Za-zÁ-Žá-ž]+", title or ""):
        if len(w) > 1 and norm(w) not in STOP:
            return norm(w).replace("-", " ")
    return ""


def from_triage(out, srcs=None, maxq=0):
    """Fill annotation gaps with queries derived from book-triage.jsonl.

    `main()` reconstructs its queries from the original pull files, which do not survive
    a session — so a slice pulled in an earlier session can never be re-swept, and two
    of them never were: measured 2026-08-27, `ceska-proza` sat at 8.8% annotation
    coverage and `povidky` at 14.7% against 90-99% everywhere else. That gap is
    mechanical and it lands on the ranking: annotation coverage by score runs 94% at 5
    and 90% at 4 but **53% at 3**, a dip rather than a gradient, which is the signature
    of works parked at 3 for want of any evidence rather than judged there.

    MERGES rather than rewrites. `main()` writes the file wholesale, so running it with a
    partial query set would silently drop the other 16,000 annotations — the same shape
    as the triage.py hazard.
    """
    have = {}
    if os.path.exists(out):
        for l in io.open(out, encoding="utf-8"):
            if l.strip():
                r = json.loads(l)
                if "_readme" not in r:
                    have[r["k"]] = r
    seenfacts = set()
    if os.path.exists(FACTS):
        for l in io.open(FACTS, encoding="utf-8"):
            if l.strip():
                r = json.loads(l)
                if "_readme" not in r:
                    seenfacts.add(r["k"])
    rows = [json.loads(l) for l in io.open("book-triage.jsonl", encoding="utf-8")][1:]
    want, queries = {}, collections.Counter()
    for r in rows:
        if srcs and r.get("src") not in srcs:
            continue
        k = workkey(r["t"], r["a"])
        if k in want:
            continue
        # A work already annotated may still be missing its catalogue facts, which were
        # never harvested at all, so the target is the union of the two gaps.
        if k in have and k in seenfacts:
            continue
        q = sigword(r["t"])
        if not q:
            continue
        want[k] = q
        queries[q] += 1
    print(f"{len(have)} annotations already on file | "
          f"{len(want)} works missing an annotation or catalogue facts")
    print(f"{len(queries)} distinct queries, "
          f"{sum((v + 99) // 100 + 1 for v in queries.values())} pages at worst")

    fx = {}
    if os.path.exists(FACTS):
        for l in io.open(FACTS, encoding="utf-8"):
            if l.strip():
                r = json.loads(l)
                if "_readme" not in r:
                    fx[r["k"]] = r
    print(f"{len(fx)} works already carry catalogue facts")

    # A cap, because coverage per query falls off hard and the catalogue's latency does
    # not. Measured 2026-08-27: the top 200 queries name 27% of the missing works, the
    # top 800 47%, and all 8,106 would take ~20 h at the 3 s/request the API was serving.
    # The real yield is ~2.5x the naming curve, because a 100-record page also fills in
    # works that belong to other queries - 150 queries recovered 10,850 annotations
    # earlier the same day, 72 per query against the 28 the curve implies.
    order = queries.most_common(maxq or None)
    if maxq:
        print(f"capped at {len(order)} queries "
              f"({sum(n for _, n in order)} works named directly)")
    store, seen, hit, fhit = dict(have), 0, 0, 0
    for i, (q, n) in enumerate(order, 1):
        for page in range(1, (n + 99) // 100 + 2):
            d = get(q, page)
            recs = ((d or {}).get("result") or {}).get("content") or []
            if not recs:
                break
            for c in recs:
                a = re.split(r"\s*;\s*",
                             ((c.get("responsibilityStatement") or {}).get("text") or ""))[0]
                a = re.sub(r"^(napsal\w*|text|příběh:?|scénář:?)\s+", "", a.strip(), flags=re.I)
                k = workkey(c.get("name") or "", a)
                seen += 1
                f = facts(c)
                if f:
                    if k not in fx:
                        fx[k] = {"k": k}
                        fhit += 1
                    merge_facts(fx[k], f)
                txt = anot(c)
                if not txt:
                    continue
                if len(txt) > len(store.get(k, {}).get("a", "")):
                    if k not in have:
                        hit += 1
                    store[k] = {"k": k, "a": txt, "id": c.get("id") or ""}
            time.sleep(0.05)
            # A short page is the last page. The pessimistic `+1` in the range would
            # otherwise pay a spare request on every one of the ~3,000 single-work
            # queries, which is most of the sweep.
            if len(recs) < 100:
                break
        # CHECKPOINT. The 2026-08-27 run wrote only at the end and was killed at query
        # 150 with 10,850 recovered annotations in memory; all of them were lost.
        if i % 50 == 0 or i == len(order):
            write(out, store)
            write_facts(fx)
            print(f"  {i}/{len(order)} queries | +{hit} annotations | "
                  f"+{fhit} fact rows | checkpointed", flush=True)
    write(out, store)
    write_facts(fx)
    cov = collections.Counter()
    for r in fx.values():
        for f in ("pages", "gf", "kw", "series", "orig"):
            cov[f] += bool(r.get(f))
    print(f"\nrecords seen {seen} | NEW annotations {hit} | annotation file {len(store)}")
    print(f"catalogue facts: {len(fx)} works (+{fhit} new)")
    for f in ("pages", "gf", "kw", "series", "orig"):
        print(f"   {f:7s} {cov[f]:6d}  {100 * cov[f] / max(1, len(fx)):5.1f}%")
    print(f"-> {out}  and  {FACTS}")


def write_facts(fx):
    with io.open(FACTS, "w", encoding="utf-8", newline="\n") as f:
        f.write(json.dumps({
            "_readme": "Structured MARC per WORK from the catalogue's bulk search, keyed like "
                       "book-ai-rank.jsonl. Written by tools/fetch-annotations.py --from-triage. "
                       "FACTS, not judgements, and fully regenerable - an input like the "
                       "annotations beside it.",
            "schema": 1,
            "_pages": "MARC 300 $a, median across the editions of the work. Median rather than "
                      "max because an omnibus and a school abridgement of the same work both "
                      "appear and the number that decides `form` is the ordinary one.",
            "_gf": "MARC 655, the librarian's controlled genre/form heading. The most reliable "
                   "signal available for the detective and sex-as-plot filters - better than a "
                   "title regex and better than a model reading promotional copy. ~33% coverage.",
            "_kw": "MARC 653, free subject terms. ROUTING, never a verdict: `laska` is in plenty "
                   "of literary fiction. ~41% coverage.",
            "_series": "MARC 490. What would have caught the MARC 245 $a series collapse that "
                       "mislinked Sirotcinec slecny Peregrinove on 2026-08-27.",
            "_orig": "The original title parsed from responsibilityStatement - the name a "
                     "translated book is actually known by, and the only field here that can move "
                     "`rec` from 0 to 1 rather than only improving a premise guess. ~11%.",
        }, ensure_ascii=False) + "\n")
        for k in sorted(fx):
            r = {x: v for x, v in fx[k].items() if x != "_pp"}
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


def write(out, store):
    with io.open(out, "w", encoding="utf-8", newline="\n") as f:
        f.write(json.dumps({
            "_readme": "Catalogue Anotace (MARC 520) per WORK, keyed like book-ai-rank.jsonl. "
                       "Written by tools/fetch-annotations.py and fully regenerable in about "
                       "two minutes - it is an input, not a judgement.",
            "schema": 1,
            "_trunc": TRUNC,
            "_isnot": "PUBLISHER COPY. Carries premise, protagonist and setting. Does NOT "
                      "carry opening structure, occult enacted on the page, crudeness of "
                      "sexual treatment, or the idea the book leaves behind - and it is "
                      "promotional, so it overclaims in one direction. Rank with it; never "
                      "estimate with it.",
        }, ensure_ascii=False) + "\n")
        for k in sorted(store):
            f.write(json.dumps(store[k], ensure_ascii=False) + "\n")


def main(scratch, out):
    queries = collections.Counter()
    for fn in SLICES:
        p = os.path.join(scratch, fn)
        if not os.path.exists(p):
            continue
        for l in io.open(p, encoding="utf-8"):
            queries[json.loads(l).get("q", "")] += 1
    if not queries:
        sys.exit(f"no pull files in {scratch!r}; expected any of {', '.join(SLICES)}")
    print(f"{len(queries)} queries reconstructed from the pulls, "
          f"{sum((v + 99) // 100 for v in queries.values())} pages to fetch")

    store, seen, blank = {}, 0, 0
    for q, n in queries.most_common():
        pages = (n + 99) // 100 + 1
        for page in range(1, pages + 1):
            d = get(q, page)
            recs = ((d or {}).get("result") or {}).get("content") or []
            if not recs:
                break
            for c in recs:
                a = re.split(r"\s*;\s*",
                             ((c.get("responsibilityStatement") or {}).get("text") or ""))[0]
                a = re.sub(r"^(napsal\w*|text|příběh:?|scénář:?)\s+", "", a.strip(), flags=re.I)
                k = workkey(c.get("name") or "", a)
                seen += 1
                txt = anot(c)
                if not txt:
                    blank += 1
                    continue
                # Keep the longest annotation seen for a work: editions differ and a
                # 40-char one carries nothing.
                if len(txt) > len(store.get(k, {}).get("a", "")):
                    store[k] = {"k": k, "a": txt, "id": c.get("id") or ""}
            time.sleep(0.25)
        print(f"  {q[:36]!r:38s} pages<={pages}  works so far {len(store)}", flush=True)

    with io.open(out, "w", encoding="utf-8", newline="\n") as f:
        f.write(json.dumps({
            "_readme": "Catalogue Anotace (MARC 520) per WORK, keyed like book-ai-rank.jsonl. "
                       "Written by tools/fetch-annotations.py and fully regenerable in about "
                       "two minutes - it is an input, not a judgement.",
            "schema": 1,
            "_trunc": TRUNC,
            "_isnot": "PUBLISHER COPY. Carries premise, protagonist and setting. Does NOT "
                      "carry opening structure, occult enacted on the page, crudeness of "
                      "sexual treatment, or the idea the book leaves behind - and it is "
                      "promotional, so it overclaims in one direction. Rank with it; never "
                      "estimate with it.",
        }, ensure_ascii=False) + "\n")
        for k in sorted(store):
            f.write(json.dumps(store[k], ensure_ascii=False) + "\n")
    print(f"\nrecords seen {seen} | works with an annotation {len(store)} | "
          f"records with none {blank} ({blank / max(1, seen) * 100:.0f}%)")
    print(f"-> {out}")


if __name__ == "__main__":
    a = [x for x in sys.argv[1:] if not x.startswith("--")]
    o = sys.argv[sys.argv.index("--out") + 1] if "--out" in sys.argv else "book-annotations.jsonl"
    if "--from-triage" in sys.argv:
        s = sys.argv[sys.argv.index("--src") + 1].split(",") if "--src" in sys.argv else None
        mq = int(sys.argv[sys.argv.index("--max-queries") + 1]) if "--max-queries" in sys.argv else 0
        from_triage(o, s, mq)
    elif a:
        main(a[0], o)
    else:
        sys.exit("usage: python tools/fetch-annotations.py <scratchdir> [--out FILE]\n"
                 "       python tools/fetch-annotations.py --from-triage [--src a,b] [--out FILE]")
