"""Backfill and refresh book-triage.jsonl — the cheap tier of the two-tier screen.

Tier 1 (this file)  : every record ever pulled gets a row with a machine class and
                      a rough band. Cheap, high volume, low confidence, revisitable.
Tier 2 (the rest)   : book-cache.json + book-estimates.jsonl + book-media.json, with
                      a verified access route and a real est range. Expensive, precise.

Run:  python tools/triage.py <scratchdir>
Idempotent: rows are keyed on (title, author, year) and rewritten wholesale.
Classification is deliberately mechanical. `conf` says so, and a `drop` here is a
soft not-pursued, NOT a reject — book-rejects.jsonl is the only place a named
filter kills a title.
"""
import json, io, os, re, sys, unicodedata, collections

SLICES = {
    "full.jsonl": "genre-sf-f", "cat.jsonl": "categories", "pov.jsonl": "povidky",
    "proza.jsonl": "anglo-us-proza", "cz.jsonl": "ceska-proza",
    "sweep.jsonl": "genre-sf-f", "sw2.jsonl": "publishers",
}

AUDIO_PUB = ("onehotbook", "voxi", "témbr", "tembr", "listen", "audiostory", "radioservis",
             "supraphon", "tympanum", "macana", "audioteka", "audiolibrix")
EBOOK_PUB = ("palmknihy", "saga egmont", "e-knihy jedou", "ekniha", "eknihy",
             "ideaify", "ekultura", "pointa e", "millennium publishing")
# "portál" was in this list and had never fired, because the needles were accented
# and the haystack is not. When pub_has() was fixed on 2026-08-26 it went live and
# classed 120 adult psychology and pedagogy titles as children's books - Portal has
# a children's line but is a professional publisher. Removed rather than restored.
KIDS_PUB = ("fragment", "coobooo", "cooboo", "albatros", "bambook", "cpress", "egmont",
            "meander", "sun", "baobab", "pikola", "drobek", "thovt", "grada dětské",
            "mladá fronta dětské", "svojtka", "presco", "brio", "infoa")
# Single-genre romance imprints only. The broad trade houses that also publish
# canon (Baronet, Dobrovsky, Knizni klub, MOBA, Metafora) are deliberately NOT
# here - see the comment in classify().
ROMANCE_PUB_STRICT = ("harlequin", "cosmopolis")
# Substring matching on a publisher name is how "tor" caught Pistorius and
# "alpress" caught Talpress. Anything in this tuple must match at a word start.
_BOUNDARY = ("alpress", "ikar", "motto", "tor books", "sun", "brio", "plus", "beta")
# A needle that is a whole publisher name and also a fragment of Czech ones must match
# at BOTH ends. "tor books" was the word-start dodge for that and it silently missed the
# real records: this catalogue writes the imprint as plain "Tor", so two English-language
# Tor editions were classed `print`, became a verified Czech route, and reached a
# promotion agent as readable (found 2026-08-31). Both-sides matching keeps Torst,
# Pistorius and Motto out while catching "Tor" and "New York : Tor".
_WHOLE = ("tor", "orbit", "vintage", "picador", "abacus", "anchor")


def pub_has(p, tokens):
    """`p` always arrives de-accented, so the needles must be too.

    26 tokens across this file and rank.py were unreachable until 2026-08-26 for
    exactly this reason — including mlada fronta, knizni klub, dobrovsky, portal
    and the whole canon-era imprint bonus. It failed safe (a class that never
    fires leaves a row in the queue) but it silently flattened the ranking.
    """
    for k in tokens:
        k = strip(k)
        if k in _WHOLE:
            if re.search(r"(?<![a-z])" + re.escape(k) + r"(?![a-z])", p):
                return True
        elif k in _BOUNDARY:
            if re.search(r"(?<![a-z])" + re.escape(k), p):
                return True
        elif k in p:
            return True
    return False
CRIME_PUB = ("mystery press", "kalibr")
# Broad commercial houses. Corroborating evidence for romance, never sufficient alone.
ROMANCE_PUB_SOFT = ("alpress", "ikar", "motto", "dobrovský", "baronet", "domino",
                    "metafora", "víkend", "levné knihy", "moba", "knižní klub")
LIT_PUB = ("host", "argo", "odeon", "paseka", "prostor", "torst", "atlantis", "větrné mlýny",
           "kniha zlin", "labyrint", "vyšehrad", "academia", "plus", "pistorius", "mervart",
           "malvern", "dauphin", "druhé město", "volvox", "garamond", "maraton", "trigon")
SF_PUB = ("triton", "planeta9", "laser", "polaris", "brokilon", "talpress", "straky",
          "gnóm", "gnom", "fantom print", "classic", "návrat", "epocha", "perseus",
          "wales", "zoner", "fobos", "abramis")
MANGA_PUB = ("crew",)
# A foreign-language edition fails the readable-in-Czech filter outright.
FOREIGN_PUB = ("walker books", "titan books", "usborne", "bloomsbury", "viz media",
               "tor books", "tor", "orbit", "vintage", "picador", "abacus", "anchor",
               "penguin", "harpercollins", "vintage books", "faber and",
               "orbit books", "gollancz", "scholastic", "macmillan", "simon &",
               "random house", "hodder", "corgi books", "wolters", "membran",
               "oxford univ", "cambridge univ", "langenscheidt", "klett")

KIDS_TITLE = re.compile(r"pohádk|princezn|dráče|drak[ou]|jezevec|medvídek|víl[ay]|čarodějnic[ea] a |"
                        r"kouzeln[ýáé]|zlobr|strašidýlk|kluk|holčič|školk|prvňáč|zvířátk|"
                        r"veverk|kočičí|psíč|dobrodružství malé", re.I)
CRIME_TITLE = re.compile(r"vražd|detektiv|komisař|zločin|pátrán|policejní|inspektor|"
                         r"kriminál|soudní|vyšetřov", re.I)
ROMANCE_TITLE = re.compile(r"milenec|milenk|polibek|sváděn|vášn|nevěst|románek|"
                           r"hřích[uy] těla|obětí lásky|zamilovan", re.I)


def strip(s):
    s = unicodedata.normalize("NFKD", s or "")
    return "".join(c for c in s if not unicodedata.combining(c)).lower()


def titlekey(t):
    return re.sub(r"[^a-z0-9 ]+", " ", strip(t)).strip()


def surname(a):
    """Surname of a name, de-feminised so Rowlingova == Rowling.

    Handles BOTH orders, because a slice's author string depends on where it was
    read from: `responsibilityStatement` gives natural order ("Rick Riordan") and
    the MARC 100-a authority heading gives inverted order ("Riordan, Rick").
    Taking the last token unconditionally turned every inverted name into a first
    name, so the already-read, rejected and known-author joins all silently
    missed - on 2026-08-27 that let Collins, Riordan and Saint-Exupery through to
    a model pass, and all five of its top scores were books already in the log.
    A comma is unambiguous: nothing in natural order contains one.
    """
    a = strip(a)
    parts = (a.split(",")[0] if "," in a else a).split()
    if not parts:
        return ""
    n = parts[-1]
    for suf in ("ova", "ove", "ovi"):
        if n.endswith(suf) and len(n) > len(suf) + 2:
            return n[: -len(suf)]
    return n


def known_authors():
    """Surnames the database has a *recorded* opinion about.

    Built only from author ids in book-revs.json and the author column of the
    cache — NOT from every capitalised word in the prose notes. The loose version
    matched 'Pyotr Ilyich Tchaikovsky' against Adrian Tchaikovsky and put a
    symphony score in the review queue.
    """
    out = set()
    try:
        revs = json.load(io.open("book-revs.json", encoding="utf-8"))["revs"]
        for k in revs:
            if k.startswith("author:"):
                out.add(surname(k.split(":", 1)[1].replace("-", " ")))
    except OSError:
        pass
    try:
        for b in json.load(io.open("book-cache.json", encoding="utf-8"))["books"]:
            n = surname(b.get("author", ""))
            if n:
                out.add(n)
    except OSError:
        pass
    return {a for a in out if len(a) > 3}


def read_authors():
    """Surnames with a real score in books-read.md. Never send these to a model."""
    out = set()
    try:
        lines = io.open("books-read.md", encoding="utf-8").readlines()
    except OSError:
        return out
    for l in lines:
        if not l.startswith("| ") or l.count("|") <= 4:
            continue
        col = [x.strip() for x in l.split("|")]
        if len(col) > 2 and col[2] and col[2] != "Author":
            n = surname(col[2])
            if len(n) > 3:
                out.add(n)
    return out


def rejected_authors():
    """Surnames killed at author or series level in book-rejects.jsonl."""
    out = {}
    try:
        lines = [l for l in io.open("book-rejects.jsonl", encoding="utf-8") if l.strip()]
    except OSError:
        return out
    for l in lines[1:]:
        r = json.loads(l)
        if r.get("level") not in ("author", "series"):
            continue
        n = surname(r.get("author") or r.get("entity") or "")
        if n:
            out[n] = r.get("filter", "?")
    return out


def rejected_titles():
    """Titles killed at title level. Nothing read these rows until 2026-08-26, so a
    title-level reject was inert data: Americti bohove had been rejected for months
    and still came back a 5 from two separate model runs."""
    out = {}
    try:
        lines = [l for l in io.open("book-rejects.jsonl", encoding="utf-8") if l.strip()]
    except OSError:
        return out
    for l in lines[1:]:
        r = json.loads(l)
        if r.get("level") != "title":
            continue
        # An entity may be written "American Gods (Americti bohove)"; index every
        # parenthesised alias as well as the bare form.
        ent = r.get("entity") or ""
        for part in re.split(r"[()]", ent):
            n = re.sub(r"[^a-z0-9 ]+", " ", strip(part)).strip()
            if len(n) > 4:
                out[n] = r.get("filter", "?")
    return out


def classify(name, author, pub, src):
    p, t = strip(pub), name or ""
    if pub_has(p, FOREIGN_PUB):
        return "edition-foreign", "X"
    if pub_has(p, MANGA_PUB):
        return "manga", "X"
    if pub_has(p, AUDIO_PUB):
        return "edition-audio", "X"
    if pub_has(p, EBOOK_PUB):
        return "edition-ebook", "X"
    # Only single-genre imprints and title evidence may set a dropping class.
    # A broad trade house (Baronet, Dobrovsky, Knizni klub) publishes romance AND
    # Crichton AND Kafka; treating it as a class scored Jursky park and Promena
    # at -40 and buried them. Those houses are handled as a WEIGHT in rank.py.
    # Band `?`, not `X`: a children's book is graded and never vetoed (reader, 2026-08-28),
    # so the class is a fact about the book and not a drop. `ai_rank.DROP_CLS` no longer
    # lists it either - the two have to agree or the band lies about what happens next.
    if KIDS_TITLE.search(t) or pub_has(p, KIDS_PUB):
        return "childrens", "?"
    if CRIME_TITLE.search(t) or pub_has(p, CRIME_PUB):
        return "detective", "X"
    # Two grades, because the reader declined a blanket romance drop. `romance-hi`
    # needs a romance title AND a broad-commercial imprint, or a category-romance
    # imprint on its own; that tier is safe to skip before the model. A title
    # regex firing alone is the weak case that misread Komensky's raj SRDCE, so it
    # stays in the queue and gets model tokens.
    if pub_has(p, ROMANCE_PUB_STRICT):
        return "romance-hi", "X"
    if ROMANCE_TITLE.search(t):
        return ("romance-hi" if pub_has(p, ROMANCE_PUB_SOFT) else "romance-maybe"), "X"
    if src == "categories":
        return "testimony-allegory", "A?"
    if src == "povidky":
        return "short-idea", "A?"
    if src in ("genre-sf-f", "publishers") or pub_has(p, SF_PUB):
        return "sf-fantasy", "A?"
    if pub_has(p, LIT_PUB):
        return "litfic", "A?"
    return "unknown", "?"


def main(scratch):
    known, rejected, promoted = known_authors(), rejected_authors(), set()
    already_read, rejected_t = read_authors(), rejected_titles()
    # Normalised, because the catalogue's casing is its own: the cache said "The City
    # and Its Uncertain Walls" and the record says "The city and its uncertain walls",
    # and exact-string matching let that work back into the queue as a fresh find.
    try:
        for b in json.load(io.open("book-cache.json", encoding="utf-8"))["books"]:
            # A work re-published under a different Czech title is a different string
            # too: Jota titled the whole Chaos Walking trilogy "Chaos" where Slovart
            # used per-volume titles.
            for t in [b.get("czTitle") or b.get("title")] + (b.get("czTitleAliases") or []):
                promoted.add(titlekey(t))
    except OSError:
        pass
    rows = {}
    for fn, src in SLICES.items():
        path = os.path.join(scratch, fn)
        if not os.path.exists(path):
            continue
        for line in io.open(path, encoding="utf-8"):
            r = json.loads(line)
            a = re.split(r"\s*;\s*", r.get("rs", ""))[0].strip()
            a = re.sub(r"^(napsal\w*|text|příběh:?|scénář:?)\s+", "", a, flags=re.I).strip()
            k = (r["name"], a, r.get("yr", ""))
            if k in rows:
                continue
            cls, band = classify(r["name"], a, r.get("pub", ""), src)
            sn, tn = surname(a), titlekey(r["name"])
            filt = None
            if sn in already_read:
                cls, band = "already-read", "X"
            elif tn in rejected_t:
                cls, band, filt = "rejected", "X", rejected_t[tn]
            elif sn in rejected:
                cls, band, filt = "rejected", "X", rejected[sn]
            row = {"t": r["name"], "a": a, "p": (r.get("pub") or "")[:34],
                   "y": r.get("yr", ""), "cls": cls, "band": band, "src": src, "conf": "auto"}
            if filt:
                row["filter"] = filt
            if tn in promoted:
                row.update(band="tier2", next="promoted", conf="screened")
            elif band == "X":
                row["next"] = "drop"
            elif sn in known:
                row["next"] = "review"
                row["knownAuthor"] = True
            else:
                row["next"] = "review"
            rows[k] = row
    # Refuse to write an empty file. Running this with no scratchdir on 2026-08-26
    # truncated book-triage.jsonl from 16,564 rows to its header line: the default
    # argument was "." and none of the slice files are there, so it read nothing and
    # then serialised that nothing over the real data. Recovering it needed the temp
    # pulls, which do not survive a session.
    if not rows:
        sys.exit(f"refusing to write an empty book-triage.jsonl: no slice files found "
                 f"in {scratch!r}. Expected any of {', '.join(SLICES)}.")
    hdr = {
        "_readme": "Tier 1 of the two-tier screen: every record ever pulled from the "
                   "catalogue, with a MACHINE class and a rough band. Written by "
                   "tools/triage.py. Nothing here is a judgement about a book - `conf: "
                   "auto` means a regex looked at the title, author and publisher and "
                   "nothing else.",
        "schema": 1,
        "_cls": "already-read (the author has a real score in books-read.md) | "
                "rejected (already killed at title, author or series level in "
                "book-rejects.jsonl) | "
                "edition-foreign (not readable in Czech) | edition-audio | "
                "edition-ebook (e-lending route declined by the reader 2026-08-26) | manga | "
                "childrens | detective | romance-sentimental | testimony-allegory | "
                "romance-hi (category imprint, or romance title AND commercial house - "
                "dropped before the model) | romance-maybe (romance title alone, weak "
                "evidence, still gets model tokens) | short-idea | sf-fantasy | litfic | "
                "unknown",
        "_band": "rough prior only. X = auto-dropped class · ? = unclassifiable · A? = "
                 "plausible, worth a look · tier2 = already promoted to "
                 "book-estimates.jsonl, which is authoritative for it.",
        "_next": "drop | review | promoted. A `drop` here is a SOFT not-pursued and is "
                 "revisitable on request - it is NOT a reject. book-rejects.jsonl is the "
                 "only place a named filter kills a title.",
        "_promotion": "A row is promoted when its class is eligible, its band is A?, and "
                      "a plausible access route exists. Promotion means doing the "
                      "expensive work: verify both access routes, derive the "
                      "worldbuilding verdict, write the est range with deps/leanedOn/"
                      "risks, and add cache + media entries. Until then the rough band "
                      "must never be quoted as a prediction.",
    }
    with io.open("book-triage.jsonl", "w", encoding="utf-8", newline="\n") as f:
        f.write(json.dumps(hdr, ensure_ascii=False) + "\n")
        for r in rows.values():
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    c = collections.Counter(r["cls"] for r in rows.values())
    n = collections.Counter(r["next"] for r in rows.values())
    print(f"rows: {len(rows)}")
    for k, v in c.most_common():
        print(f"  {v:6d}  {k}")
    print("next:", dict(n))


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit("usage: python tools/triage.py <scratchdir>   (required — there is no "
                 "safe default; see the empty-write guard in main())")
    main(sys.argv[1])
