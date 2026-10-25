"""The second library: Městská knihovna Rožnov pod Radhoštěm (katalog.knir.cz).

Ruled by the reader 2026-10-25: pull books from Rožnov "if they are not at the primary
one", and keep the library a filterable source. So Rožnov never replaces a Valašské
Meziříčí print copy; it fills the gap where the primary has only an e-loan, nothing, or
was never asked. The route carries `library: "roznov"` and the viewer filters on it.

Same Portaro/Verbis software as the primary, so the same `api/search` and
`api/exemplars` endpoints, with two differences that matter:

  * Its monograph records carry `responsibilityStatement`, so authors are present and
    the work keys line up with `book-triage.jsonl` the way the primary's print rows do.
  * The full MARC is in `fields`, so language (008/35-37), media type (337 $b) and the
    branch holdings (910) come free with the bulk search. A record whose 337 is not
    `n` (unmediated) is an e-book or an audio carrier, never print.

    python tools/second-library.py pull <out.jsonl> [--primary]
    python tools/second-library.py routes <pull.jsonl> [--write]
    python tools/second-library.py triage <pull.jsonl> [--write]
    python tools/second-library.py resolve <pull.jsonl> <primary-pull.jsonl> [--write]

`pull` reads every monograph (~645 pages, ~30 min at three threads, ~2 GB on the wire)
into compact rows; it is an input, regenerable, and does not belong in the repo.
`routes` gives a Rožnov print route to every cache book and every edition row that has
no primary print route, after confirming a physical copy with `api/exemplars`.
`triage` appends the Rožnov records whose work `book-triage.jsonl` has never seen, and
their Anotace and MARC facts to `book-annotations.jsonl` / `book-catalog.jsonl`.
`resolve` takes a `pull --primary` of the primary too: it stamps `primary` on every
Rožnov triage row whose work the primary holds in print, and routes the ranked works
ahead of promotion. All three print what they would change and write only with `--write`.
"""
import json, io, os, re, sys, time, html, collections, importlib.util
import urllib.parse, urllib.request
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import triage as T
_spec = importlib.util.spec_from_file_location(
    "fetch_editions", os.path.join(os.path.dirname(os.path.abspath(__file__)), "fetch-editions.py"))
FE = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(FE)

BASE = "https://katalog.knir.cz"
PRIMARY = "https://katalog.mekvalmez.cz"
LIBRARY = "roznov"
UA = {"User-Agent": "Mozilla/5.0 (book-shelf/1.0 personal reading list)", "Accept-Language": "cs"}
CACHE, EDITIONS, TRIAGE = "book-cache.json", "book-editions.jsonl", "book-triage.jsonl"
ANNOT, CATALOG = "book-annotations.jsonl", "book-catalog.jsonl"
TODAY = os.environ.get("BOOK_TODAY", "2026-10-25")
TAG = re.compile(r"<[^>]+>")


def api(path, params=None, base=BASE):
    url = base + path + ("?" + urllib.parse.urlencode(params, quote_via=urllib.parse.quote) if params else "")
    for i in range(5):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=120) as r:
                return json.load(r)
        except Exception:
            time.sleep(5 * (i + 1))
    return None


def _subs(fl, code):
    return [html.unescape(TAG.sub("", x.get("text") or "")).strip(" :;,/.")
            for x in fl.get("fields") or [] if x.get("code") == code]


def compact(c):
    r = {"id": c.get("id"), "t": c.get("name"),
         "rs": (c.get("responsibilityStatement") or {}).get("text"),
         "pa": [a.get("text") for a in c.get("primaryAuthors") or []],
         "p": ((c.get("publishers") or [{}])[0]).get("text"),
         "y": (c.get("publicationStartYear") or {}).get("value"), "gf": [], "kw": [], "hold": []}
    for fl in c.get("fields") or []:
        code, txt = fl.get("code"), fl.get("text") or ""
        if code == "d8" and len(txt) >= 38:
            r["lang"] = txt[35:38]
        elif code == "d72":
            r["udc"] = (_subs(fl, "x") or [None])[0]
        elif code == "d245":
            b = _subs(fl, "b") + _subs(fl, "n") + _subs(fl, "p")
            if b:
                r["sub"] = " ".join(b)[:120]
        elif code == "d300":
            r["pages"] = (_subs(fl, "a") or [None])[0]
        elif code == "d337":
            r["media"] = (_subs(fl, "b") or [None])[0]
        elif code == "d520" and "ann" not in r:
            r["ann"] = " ".join(_subs(fl, "a"))[:500]
        elif code == "d653":
            r["kw"] += _subs(fl, "a")
        elif code == "d655":
            r["gf"] += _subs(fl, "a")
        elif code in ("d490", "d787") and "series" not in r:
            s = " ".join(_subs(fl, "t") + _subs(fl, "a") + _subs(fl, "g") + _subs(fl, "v"))
            if s:
                r["series"] = s[:120]
        elif code == "d910":
            r["hold"] += _subs(fl, "a")
    return r


def cmd_pull(out, base=BASE, fond="1"):
    first = api("/api/search", {"pageSize": 1, "fond": fond}, base)
    pages = (first["result"]["totalElements"] + 99) // 100

    def page(n):
        d = api("/api/search", {"pageSize": 100, "pageNumber": n, "fond": fond}, base)
        return None if d is None else [compact(c) for c in d["result"]["content"]]

    bad = []
    with ThreadPoolExecutor(3) as ex, io.open(out, "w", encoding="utf-8", newline="\n") as f:
        for n, rows in zip(range(1, pages + 1), ex.map(page, range(1, pages + 1))):
            if rows is None:
                bad.append(n)
                continue
            for r in rows:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(f"{pages} pages -> {out}; failed pages: {bad}")


def load_pull(path):
    return [json.loads(l) for l in io.open(path, encoding="utf-8") if l.strip()]


def is_print(r):
    """Czech text on paper. `media` absent is an old record that predates RDA fields, and
    008 language is blank, `|||` or shifted on ~3,000 old records, so only a real foreign
    code excludes."""
    lang = r.get("lang") or ""
    foreign = re.fullmatch(r"[a-z]{3}", lang) and lang != "cze"
    return r.get("media") in (None, "n") and not foreign and \
        FE.classify(r["t"] or "", r.get("p") or "", r.get("rs") or "") == "print"


def author_of(r):
    a = FE.author_of({"responsibilityStatement": {"text": r.get("rs") or ""}})
    if a:
        return a
    pa = (r.get("pa") or [""])[0].rstrip(",")
    parts = [p.strip() for p in pa.split(",") if p.strip() and not re.fullmatch(r"[\d\s\-–.?]+", p)]
    return " ".join(parts[1:] + parts[:1]) if len(parts) > 1 else (parts[0] if parts else "")


def index(rows):
    """(normalised title, surname) -> print records, plus title alone for author-less works."""
    by_pair, by_title = collections.defaultdict(list), collections.defaultdict(list)
    for r in rows:
        if not is_print(r):
            continue
        t = FE.norm(r["t"] or "")[:48]
        by_pair[(t, T.surname(author_of(r)))].append(r)
        by_title[t].append(r)
    return by_pair, by_title


def copies(record_id):
    """Physical copies that can go home: the bulk record does not say, exemplars does.
    The department "Středisko, ztracené knihy" is where lost copies are parked."""
    ex = api("/api/exemplars", {"document": record_id}) or []
    text = lambda e, f: ((e.get(f) or {}).get("text") or "").lower()
    return [e for e in ex if not e.get("discarded") and "prezen" not in text(e, "loanCategory")
            and "ztracen" not in text(e, "department") and "ztracen" not in text(e, "status")]


def route_for(cands):
    """Newest edition with a copy that can be borrowed, like FE.resolve()."""
    for r in sorted(cands, key=lambda r: -(r.get("y") or 0)):
        held = copies(r["id"])
        if held:
            depts = sorted({(e.get("department") or {}).get("text") or "" for e in held} - {""})
            return {"state": "verified", "library": LIBRARY, "publisher": FE.imprint(r.get("p") or "") or None,
                    "year": r.get("y"), "translator": FE.translator(r.get("rs") or ""),
                    "recordId": r["id"], "edition": "print", "branches": depts}
        time.sleep(0.2)
    return None


def candidates(by_pair, by_title, title, author):
    t = FE.norm(title or "")[:48]
    sn = T.surname(author or "")
    if sn:
        return by_pair.get((t, sn), [])
    return by_title.get(t, [])


def primary_route(cands):
    """The primary's newest print record. Existence is the primary's bar, as everywhere
    else in this pipeline, so no exemplar check."""
    r = max(cands, key=lambda r: r.get("y") or 0)
    return {"state": "verified", "publisher": FE.imprint(r.get("p") or "") or None, "year": r.get("y"),
            "translator": FE.translator(r.get("rs") or ""), "recordId": r["id"], "edition": "print"}


def cmd_resolve(pull, primary_pull, write=False, min_score=4):
    """Stamp `primary` (the primary's record id) on every Rožnov triage row whose work the
    primary holds in print, and route every Rožnov work the ranker scored >= min_score:
    the primary's record when there is one, else a Rožnov copy confirmed by exemplars.
    The reader ranks and promotes only the unstamped ones (2026-10-25)."""
    k_pair, k_title = index(load_pull(pull))
    p_pair, p_title = index(load_pull(primary_pull))
    store = {}
    for l in io.open("book-ai-rank.jsonl", encoding="utf-8"):
        r = json.loads(l)
        if "k" in r:
            store[r["k"]] = r
    raw = io.open(TRIAGE, encoding="utf-8", newline="").read()
    nl = "\r\n" if "\r\n" in raw else "\n"
    lines = [l for l in raw.replace("\r\n", "\n").split("\n") if l]
    out, works, stamped = [lines[0]], {}, 0
    for l in lines[1:]:
        r = json.loads(l)
        if r.get("knir"):
            pc = candidates(p_pair, p_title, r["t"], r["a"])
            if pc:
                r["primary"] = max(pc, key=lambda x: x.get("y") or 0)["id"]
                stamped += 1
            else:
                r.pop("primary", None)
            works.setdefault(FE.workkey(r["t"], r["a"]), (r, pc))
            l = json.dumps(r, ensure_ascii=False)
        out.append(l)
    print(f"{len(works)} Rožnov works, {sum(1 for _, pc in works.values() if pc)} held in print by the primary "
          f"({stamped} rows stamped `primary`)")

    elines = [l for l in io.open(EDITIONS, encoding="utf-8").read().split("\n") if l]
    ehead, eds = elines[0], {json.loads(l)["k"]: json.loads(l) for l in elines[1:]}
    todo = {k: v for k, v in works.items()
            if (store.get(k) or {}).get("s", 0) >= min_score and not store[k].get("done")
            and (eds.get(k) or {}).get("cz", {}).get("state") != "verified"}
    routed, jobs = {}, {}
    for k, (r, pc) in todo.items():
        if pc:
            routed[k] = primary_route(pc)
        else:
            jobs[k] = candidates(k_pair, k_title, r["t"], r["a"])
    print(f"{len(todo)} scored >= {min_score}: {len(routed)} routed to the primary, "
          f"{len(jobs)} to check for a Rožnov copy ...", flush=True)
    with ThreadPoolExecutor(3) as ex:
        for k, rt in zip(jobs, ex.map(route_for, jobs.values())):
            if rt:
                routed[k] = rt
    print(f"routed {len(routed)} ({sum(1 for v in routed.values() if v.get('library'))} Rožnov); "
          f"{len(todo) - len(routed)} have no borrowable copy at either library")
    if not write:
        return
    io.open(TRIAGE, "w", encoding="utf-8", newline="").write(nl.join(out) + nl)
    for k, rt in routed.items():
        eds[k] = {**eds.get(k, {"k": k}), "cz": rt}
    io.open(EDITIONS, "w", encoding="utf-8", newline="\n").write(
        "\n".join([ehead] + [json.dumps(eds[k], ensure_ascii=False) for k in sorted(eds)]) + "\n")
    print(f"wrote {TRIAGE} and {EDITIONS}")


def cmd_routes(pull, write=False):
    by_pair, by_title = index(load_pull(pull))
    cache = json.load(io.open(CACHE, encoding="utf-8"))
    lines = [l for l in io.open(EDITIONS, encoding="utf-8").read().split("\n") if l]
    head, eds = lines[0], [json.loads(l) for l in lines[1:]]
    works = {}
    for l in io.open(TRIAGE, encoding="utf-8"):
        r = json.loads(l)
        if "t" in r:
            k = FE.workkey(r["t"], r["a"])
            works.setdefault(k, (r["t"], r["a"] or r.get("aCat") or ""))

    jobs = {}
    for b in cache["books"]:
        cz = b.get("cz") or {}
        if cz.get("state") == "verified":
            continue
        for t in [b.get("czTitle") or b.get("title")] + (b.get("czTitleAliases") or []):
            c = candidates(by_pair, by_title, t, b.get("author"))
            if c:
                jobs[("cache", b["key"])] = c
                break
    for e in eds:
        if e["cz"]["state"] == "verified" or e["k"] not in works:
            continue
        c = candidates(by_pair, by_title, *works[e["k"]])
        if c:
            jobs[("ed", e["k"])] = c
    print(f"{len(jobs)} works with a Rožnov print candidate; confirming copies ...", flush=True)
    found = {}
    with ThreadPoolExecutor(3) as ex:
        for job, rt in zip(jobs, ex.map(route_for, jobs.values())):
            if rt:
                found[job] = rt
    stat = collections.Counter(k[0] for k in found)
    print(f"confirmed: {stat['cache']} cache books, {stat['ed']} edition rows "
          f"({len(jobs) - len(found)} candidates had no borrowable copy)")
    for (kind, k), rt in sorted(found.items()):
        print(f"  {kind:5s} {k[:50]:50s} {rt['publisher']} {rt['year']} {','.join(rt['branches'])}")
    if not write:
        return
    for b in cache["books"]:
        rt = found.get(("cache", b["key"]))
        if not rt:
            continue
        old = b.get("cz") or {}
        cz = {k: v for k, v in rt.items() if v not in (None, "", [])}
        cz.update(checked=TODAY, recordUrl=f"{BASE}/records/{rt['recordId']}", recordChecked=TODAY,
                  publisherSource="katalog")
        if old.get("state") == "eloan":
            cz["eloanRecordId"] = old.get("recordId")
        elif old.get("eloanRecordId"):
            cz["eloanRecordId"] = old["eloanRecordId"]
        b["cz"] = cz
    io.open(CACHE, "w", encoding="utf-8", newline="\n").write(
        json.dumps(cache, ensure_ascii=False, indent=1) + "\n")
    for e in eds:
        rt = found.get(("ed", e["k"]))
        if rt:
            e["cz"] = {k: v for k, v in rt.items() if k != "branches"}
    io.open(EDITIONS, "w", encoding="utf-8", newline="\n").write(
        "\n".join([head] + [json.dumps(e, ensure_ascii=False) for e in eds]) + "\n")
    print(f"wrote {CACHE} and {EDITIONS}")


# Read off the genre heading (655), the keywords (653) and the Konspekt class (072),
# because 60% of these records have no 655 at all. Mirrors the primary's sweeps:
# SF/F by keyword, stories, the children's shelf, prose by heading, testimony.
SRC_BY_HEADING = (
    (re.compile(r"fantasy|vědeckofantast|sci-fi|science fiction|fantastik|utopi|dystopi", re.I), "genre-sf-f"),
    (re.compile(r"povídk|novel(y|a)\b", re.I), "povidky"),
    (re.compile(r"pro děti|pro mládež|young adult|dívčí|pohádk", re.I), "kids-heading"),
    (re.compile(r"romány|próza", re.I), "proza"),
    (re.compile(r"vzpomínk|deník|svědectv|autobiograf|paměti", re.I), "categories"),
)
SRC_CLASS = {"genre-sf-f": "genre-sf-f", "povidky": "povidky", "categories": "categories"}


def slice_of(r):
    h = " ".join((r.get("gf") or []) + (r.get("kw") or []) + [r.get("udc") or ""])
    for rx, src in SRC_BY_HEADING:
        if rx.search(h):
            return src
    return None


def cmd_triage(pull, write=False):
    rows = load_pull(pull)
    have_keys, have_titles = set(), collections.defaultdict(set)
    for l in io.open(TRIAGE, encoding="utf-8"):
        r = json.loads(l)
        if "t" in r:
            have_keys.add(FE.workkey(r["t"], r["a"]))
            have_titles[FE.norm(r["t"])[:48]].add(T.surname(r["a"] or r.get("aCat") or ""))
    known, rejected = T.known_authors(), T.rejected_authors()
    already_read, rejected_t = T.read_authors(), T.rejected_titles()
    new, seen, stat = [], set(), collections.Counter()
    for r in rows:
        if not is_print(r):
            stat["not Czech print"] += 1
            continue
        src = slice_of(r)
        if not src:
            stat["outside the swept headings"] += 1
            continue
        a = author_of(r)
        k, t = FE.workkey(r["t"], a), FE.norm(r["t"])[:48]
        sn = T.surname(a)
        if k in have_keys or sn in have_titles.get(t, ()) or "" in have_titles.get(t, ()):
            stat["work already in triage"] += 1
            continue
        if (r["t"], a, str(r.get("y") or "")) in seen:
            continue
        seen.add((r["t"], a, str(r.get("y") or "")))
        cls, band = T.classify(r["t"], a, r.get("p") or "", SRC_CLASS.get(src, src))
        filt = None
        tn = T.titlekey(r["t"])
        if sn in already_read:
            cls, band = "already-read", "X"
        elif tn in rejected_t:
            cls, band, filt = "rejected", "X", rejected_t[tn]
        elif sn in rejected:
            cls, band, filt = "rejected", "X", rejected[sn]
        row = {"t": r["t"], "a": a, "p": (FE.imprint(r.get("p") or "") or "")[:34], "y": str(r.get("y") or ""),
               "cls": cls, "band": band, "src": "knir-" + src, "conf": "auto", "lib": LIBRARY, "knir": r["id"]}
        if filt:
            row["filter"] = filt
        row["next"] = "drop" if band == "X" else "review"
        if row["next"] == "review" and sn in known:
            row["knownAuthor"] = True
        new.append(row)
        stat["new row: " + row["next"]] += 1
    print(dict(stat))
    print(collections.Counter(r["src"] for r in new).most_common())
    if not write:
        return
    raw = io.open(TRIAGE, encoding="utf-8", newline="").read()
    nl = "\r\n" if "\r\n" in raw else "\n"
    lines = [l for l in raw.replace("\r\n", "\n").split("\n") if l]
    hd = json.loads(lines[0])
    hd["_lib"] = ("Rows with `lib: roznov` came from the second library (katalog.knir.cz, record id in "
                  "`knir`), appended by tools/second-library.py triage for works the primary's sweeps never "
                  "returned. `src` is `knir-<slice>`, the slice read off the MARC 655 genre heading. Whether "
                  "the primary holds the work too is settled at route time, not here.")
    lines[0] = json.dumps(hd, ensure_ascii=False)
    io.open(TRIAGE, "w", encoding="utf-8", newline="").write(
        nl.join(lines + [json.dumps(r, ensure_ascii=False) for r in new]) + nl)
    print(f"appended {len(new)} rows to {TRIAGE}")
    append_facts({r["id"]: r for r in rows}, new)


ORIG = re.compile(r"origin[áa]lu?\s+(.+?)(?:\s+(?:\.\.\.|p[řr]elo[žz]il\w*|vydan\w*|\[)|\s*;|\s*$)", re.I)


def append_facts(pull, new):
    """The ranker reads book-annotations.jsonl and promotion reads book-catalog.jsonl,
    both by work key; without these rows a Rožnov work is ranked on its title alone."""
    have_a = {json.loads(l).get("k") for l in io.open(ANNOT, encoding="utf-8") if l.strip()}
    have_c = {json.loads(l).get("k") for l in io.open(CATALOG, encoding="utf-8") if l.strip()}
    add_a, add_c, seen = [], [], set()
    for r in new:
        k = FE.workkey(r["t"], r["a"])
        p = pull.get(r["knir"]) or {}
        if k in seen:
            continue
        seen.add(k)
        if p.get("ann") and k not in have_a:
            a = re.sub(r"([a-záčďéěíňóřšťúůýž])\.([A-ZÁČĎÉĚÍŇÓŘŠŤÚŮÝŽ])", r"\1. \2", re.sub(r"\s+", " ", p["ann"]))
            add_a.append({"k": k, "a": a.strip()[:500], "id": p["id"], "lib": LIBRARY})
        f = {}
        m = re.search(r"(\d[\d\s]*)\s*(?:s\.|str\.|stran)", p.get("pages") or "")
        if m:
            f["pages"] = int(re.sub(r"\s", "", m.group(1)))
        for fld, n in (("gf", 3), ("kw", 6)):
            if p.get(fld):
                f[fld] = p[fld][:n]
        if p.get("series"):
            f["series"] = p["series"]
        o = ORIG.search(p.get("rs") or "")
        if o:
            f["orig"] = o.group(1)[:120]
        if f and k not in have_c:
            add_c.append({"k": k, **f})
    for path, out in ((ANNOT, add_a), (CATALOG, add_c)):
        with io.open(path, "a", encoding="utf-8", newline="\n") as fh:
            for r in out:
                fh.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(f"appended {len(add_a)} annotations to {ANNOT}, {len(add_c)} fact rows to {CATALOG}")


if __name__ == "__main__":
    a = sys.argv[1:]
    w = "--write" in a
    a = [x for x in a if not x.startswith("--")]
    if a[:1] == ["pull"] and len(a) == 2:
        cmd_pull(a[1], PRIMARY if "--primary" in sys.argv else BASE)
    elif a[:1] == ["routes"] and len(a) == 2:
        cmd_routes(a[1], w)
    elif a[:1] == ["triage"] and len(a) == 2:
        cmd_triage(a[1], w)
    elif a[:1] == ["resolve"] and len(a) == 3:
        cmd_resolve(a[1], a[2], w)
    else:
        sys.exit(__doc__)
