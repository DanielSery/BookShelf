"""Resolve the Czech print route for every work OFFLINE, so no promotion agent ever
queries the catalogue.

WHY THIS EXISTS — measured 2026-08-27. A promotion agent ran Step 3 of
`tools/promote-prompt.md` itself:

    curl ... --data-urlencode "q=Ruze pro Algernon" --data-urlencode "pageSize=40"

Three hits came back in **111,276 bytes**: ~24 kB of `detailTableRows`, `fields`,
`exports` and `recordStatusTransitions` per record, to carry the ~200 bytes that
decide the route. That response lands in the agent's context and is re-sent on every
subsequent turn of the batch. A twelve-edition author query is a quarter of a
megabyte. Over 1,011 queued books this was the single largest line item in the
13.4k-tokens-per-book measured on the 14-batch run of 2026-08-26 — and none of it is
judgement, so none of it needs a model.

The same bulk endpoint `tools/fetch-annotations.py` already sweeps also returns
`id`, `publishers`, `publicationStartYear`, `isbns` and `responsibilityStatement`.
That script kept only the longest `Anotace` per work and threw the rest away. This
one keeps every edition, classifies it, and picks the route.

    python tools/fetch-editions.py <scratchdir> [--out book-editions.jsonl]

`<scratchdir>` holds the original pull files, whose `q` field is replayed so the
join with `book-triage.jsonl` and `book-annotations.jsonl` cannot drift. ~253
requests, about two minutes, fully regenerable — an input, not a judgement.

WHAT IS AND IS NOT DECIDED HERE. Mechanical facts are: which holdings exist, which
are audio / foreign-language / e-book / a retelling, the record UUID, the publisher,
the year, and the named translator. A genuine judgement is *which* of two complete
translations a reader should prefer; those go to `alts` as facts, and the agent
still owns that call. What is gone is the fetching, not the choosing.
"""
import json, io, os, re, sys, time, collections
import urllib.parse, urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import triage as T

UA = {"User-Agent": "Mozilla/5.0 (book-shelf/1.0 personal reading list)"}
BASE = "https://katalog.mekvalmez.cz/api/search"
SLICES = ("full.jsonl", "cat.jsonl", "pov.jsonl", "proza.jsonl", "cz.jsonl",
          "sweep.jsonl", "sw2.jsonl")
MAX_EDS = 8

# Audio and adaptation tells that live in the responsibility statement rather than in
# the publisher name. Tympanum prints nothing, but Argo and Albatros both issue audio
# and comics alongside their print lists, so the publisher alone cannot decide it.
AUDIO_RS = re.compile(r"\bčte\b|\bčtou\b|načet|nahrál|zvukov|interpret|"
                      r"\bread by\b|audiokniha", re.I)
ADAPT_RS = re.compile(r"zkrácen|zkráceno|převyprávěl|převyprávěn|adaptac|adaptoval|"
                      r"volně podle|podle stejnojmenn|komiks|"
                      r"pro (?:děti|mládež) upravil|upravil pro", re.I)
# `kresl` was here and matched 93 rows, almost none of them adaptations: it fires on
# the AUTHOR NAME "Kresley Cole", on the title "Kordelie a kreslozemci", and on any
# illustrated edition of a full text - it made the 2007 Argo prose Hobit an
# adaptation. Comics are caught by `komiks` and `adaptac|adaptoval` instead, which is
# what correctly catches the Wenzl/Dixon graphic-novel Hobit. Likewise a bare
# `upravil` is usually a reviser or an editor of a complete text, so only the
# explicit "upravil pro deti" forms count.
ADAPT_NAME = re.compile(r"\(komiks\)|komiksov|pro nejmenší|převyprávěn", re.I)
TRANSLATOR = re.compile(r"(?:přeložil[aiy]?|přeloženo|přel\.|překlad|z\s+\S+\s+přeložil[aiy]?)"
                        r"\s*:?\s*([^;.]{2,60})", re.I)


def norm(s):
    return re.sub(r"[^a-z0-9]+", "-", T.strip(s)).strip("-")


def workkey(t, a):
    """Must stay identical to fetch-annotations.workkey — it is the join key into
    book-annotations.jsonl and ai_rank.load_works()."""
    return f"{norm(t)[:48]}~{norm(a)[:32]}"


def imprint(pub):
    """`V Praze : Knizni klub, 2000` -> `Knizni klub`, accents intact.

    The year carries copyright and approximation marks in this catalogue -
    `Supraphon, p1988`, `Tympanum, [c2011]`, `Argo, [2014?]` - so the trailing chunk
    has to be matched from the punctuation onward, not from the digits."""
    s = re.split(r"\s*:\s*", pub or "")[-1]
    s = re.sub(r"[,;]?\s*[\[\(]?\s*(?:[pc©]|cop\.)?\s*(?:19|20)\d\d.*$", "", s)
    return s.strip(" ,.;[]()")


def author_of(rec):
    a = re.split(r"\s*;\s*", (rec.get("responsibilityStatement") or {}).get("text") or "")[0]
    return re.sub(r"^(napsal\w*|text|příběh:?|scénář:?)\s+", "", a.strip(), flags=re.I)


def classify(name, pub, rs):
    p = T.strip(pub)
    if T.pub_has(p, T.AUDIO_PUB) or AUDIO_RS.search(rs):
        return "audio"
    if T.pub_has(p, T.FOREIGN_PUB):
        return "foreign"
    if T.pub_has(p, T.EBOOK_PUB):
        return "ebook"
    if ADAPT_RS.search(rs) or ADAPT_NAME.search(name):
        return "adapt"
    return "print"


def translator(rs):
    m = TRANSLATOR.search(rs or "")
    if not m:
        return None
    t = re.sub(r"\s+", " ", m.group(1)).strip(" ,.[]()")
    return t or None


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


def resolve(eds):
    """Pick the route. Prefer a full print translation, newest first; fall back to a
    retelling only when nothing else is in Czech, because a children's retelling of an
    adult novel is a different book and the agent must be told which it got."""
    for kinds in (("print",), ("adapt",)):
        pool = [e for e in eds if e["kind"] in kinds]
        if pool:
            best = max(pool, key=lambda e: (e["y"] or 0, e["tr"] is not None))
            return {"state": "verified", "publisher": best["pub"], "year": best["y"],
                    "translator": best["tr"], "recordId": best["id"],
                    "edition": best["kind"]}
    return {"state": "none", "publisher": None, "year": None, "translator": None,
            "recordId": None, "edition": None}


def alts(eds, route):
    """Facts for the agent's `flags`, never judgements. Names other editions, which
    is exactly what `flags` is for."""
    out = []
    others = [e for e in eds if e["id"] != route.get("recordId")]
    for kind, label in (("print", "another print edition"), ("adapt", "a retelling or comics adaptation"),
                        ("audio", "an audio edition"), ("foreign", "a foreign-language edition"),
                        ("ebook", "an e-book edition")):
        g = [e for e in others if e["kind"] == kind]
        if not g:
            continue
        bits = ", ".join(f"{e['pub']} {e['y']}" + (f", {e['tr']}" if e["tr"] else "")
                         for e in sorted(g, key=lambda e: -(e["y"] or 0))[:3])
        out.append(f"The catalogue also holds {label}: {bits}.")
    return out


def main(scratch, out):
    queries = collections.Counter()
    for fn in SLICES:
        p = os.path.join(scratch, fn)
        if os.path.exists(p):
            for l in io.open(p, encoding="utf-8"):
                queries[json.loads(l).get("q", "")] += 1
    if not queries:
        sys.exit(f"no pull files in {scratch!r}; expected any of {', '.join(SLICES)}")
    print(f"{len(queries)} queries, "
          f"{sum((v + 99) // 100 + 1 for v in queries.values())} pages to fetch")

    store, seen = {}, 0
    for q, n in queries.most_common():
        pages = (n + 99) // 100 + 1
        for page in range(1, pages + 1):
            d = get(q, page)
            recs = ((d or {}).get("result") or {}).get("content") or []
            if not recs:
                break
            for c in recs:
                name = c.get("name") or ""
                k = workkey(name, author_of(c))
                rs = (c.get("responsibilityStatement") or {}).get("text") or ""
                pub = ((c.get("publishers") or [{}])[0].get("text")) or ""
                ed = {"id": c.get("id") or "", "pub": imprint(pub),
                      "y": ((c.get("publicationStartYear") or {}).get("value")),
                      "tr": translator(rs), "kind": classify(name, pub, rs)}
                seen += 1
                if not ed["id"]:
                    continue
                cur = store.setdefault(k, {})
                cur[ed["id"]] = ed
            time.sleep(0.25)
        print(f"  {q[:36]!r:38s} pages<={pages}  works so far {len(store)}", flush=True)

    rows, nroute = [], 0
    for k in sorted(store):
        eds = sorted(store[k].values(),
                     key=lambda e: (e["kind"] != "print", -(e["y"] or 0)))[:MAX_EDS]
        route = resolve(eds)
        nroute += route["state"] == "verified"
        r = {"k": k, "cz": route}
        a = alts(eds, route)
        if a:
            r["alts"] = a
        rows.append(r)

    with io.open(out, "w", encoding="utf-8", newline="\n") as f:
        f.write(json.dumps({
            "_readme": "Resolved Czech print route per WORK, keyed like book-annotations.jsonl. "
                       "Written by tools/fetch-editions.py and fully regenerable in about two "
                       "minutes. Exists so a promotion agent never runs a catalogue query: one "
                       "such query returned 111 kB for 200 bytes of signal.",
            "schema": 1,
            "_kinds": "print | adapt (retelling, comics, abridgement - a different book) | "
                      "audio | foreign | ebook (e-lending declined by the reader 2026-08-26)",
            "_isnot": "A JUDGEMENT. `cz` is the mechanical pick - newest full print translation. "
                      "Choosing between two complete translations is the agent's call, and the "
                      "alternatives are listed in `alts` as facts for `flags`.",
        }, ensure_ascii=False) + "\n")
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(f"\nrecords seen {seen} | works {len(rows)} | "
          f"with a Czech print route {nroute} ({nroute * 100 // max(1, len(rows))}%)")
    print(f"-> {out}")


def fill(out, minscore=4):
    """Query the promotion queue's remaining works by title, and merge.

    The bulk sweep replays the ORIGINAL pull queries, so it inherits their coverage
    gap: 182 queued works were never returned by any of them, and have no annotation
    either. Those are few enough to query one at a time - still offline, still zero
    agent tokens - which is the whole point of resolving access here rather than in a
    promotion agent."""
    sys.path.insert(0, "tools")
    import ai_rank as A
    rows = [json.loads(l) for l in io.open(out, encoding="utf-8") if l.strip()]
    head, have = rows[0], {r["k"]: r for r in rows[1:]}
    wk, store = A.load_works(), A.load_store()
    todo = [(k, w) for k, w in wk.items()
            if (r := store.get(k)) and not r.get("done") and not w["skip"]
            and r.get("s", 0) >= minscore and k not in have]
    print(f"{len(todo)} queued works with no route; querying by title")

    added = 0
    for i, (k, w) in enumerate(todo, 1):
        # Diacritics must go: a query whose first significant word carries one returns
        # zero hits from this catalogue, which is how Tri musketyri hid on the shelf.
        d = get(re.sub(r"[^a-z0-9 ]+", " ", T.strip(w["t"]))[:70].strip(), 1)
        recs = ((d or {}).get("result") or {}).get("content") or []
        eds = {}
        for c in recs:
            name, aut = c.get("name") or "", author_of(c)
            if workkey(name, aut) != k:
                continue
            rs = (c.get("responsibilityStatement") or {}).get("text") or ""
            pub = ((c.get("publishers") or [{}])[0].get("text")) or ""
            if c.get("id"):
                eds[c["id"]] = {"id": c["id"], "pub": imprint(pub),
                                "y": ((c.get("publicationStartYear") or {}).get("value")),
                                "tr": translator(rs), "kind": classify(name, pub, rs)}
        if eds:
            e = sorted(eds.values(), key=lambda x: (x["kind"] != "print", -(x["y"] or 0)))[:MAX_EDS]
            route = resolve(e)
            r = {"k": k, "cz": route}
            a = alts(e, route)
            if a:
                r["alts"] = a
            have[k] = r
            added += 1
        time.sleep(0.25)
        if i % 25 == 0:
            print(f"  {i}/{len(todo)}  resolved {added}", flush=True)

    with io.open(out, "w", encoding="utf-8", newline="\n") as f:
        f.write(json.dumps(head, ensure_ascii=False) + "\n")
        for k in sorted(have):
            f.write(json.dumps(have[k], ensure_ascii=False) + "\n")
    print(f"\nresolved {added} of {len(todo)} | works now {len(have)}\n-> {out}")


if __name__ == "__main__":
    a = [x for x in sys.argv[1:] if not x.startswith("--")]
    o = sys.argv[sys.argv.index("--out") + 1] if "--out" in sys.argv else "book-editions.jsonl"
    if a and a[0] == "fill":
        fill(o)
    elif a:
        main(a[0], o)
    else:
        sys.exit("usage: python tools/fetch-editions.py <scratchdir>|fill [--out FILE]")
