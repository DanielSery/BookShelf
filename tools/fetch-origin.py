"""Write book-origin.json: was the work WRITTEN in Czech, or is it read in translation.

    python tools/fetch-origin.py <scratchdir>

The viewer app's Origin filter reads it. Three rules, weakest last:

  translator  book-cache.json already records a Czech translator          -> foreign
  statement   the catalogue record says "z anglického originálu" or
              "Přeloženo z němčiny"                                       -> foreign
  author      the author is in CS_AUTHORS or FOREIGN_AUTHORS below        -> either

THE CATALOGUE EVIDENCE IS ONE-DIRECTIONAL. A translation statement proves a
translation; its absence proves nothing, because older records simply omit it - the
Czech records for Robinson Crusoe, Medvídek Pú and Jurassic Park carry no translation
note at all. Measured 2026-08-28 on the 203 shelf books with no translator: 73 had a
statement, 120 had a Czech record with none, and only 59 of those 120 were really
Czech. That is why an author whose language is not known here gets NO ROW rather than
a default: a wrong value in the small `cs` bucket is what the filter exists to show,
and the app's Gaps panel names an unrowed book instead of guessing.

Two inverse traps the audit caught, both handled: an English edition of a Czech
original reads "Přeloženo z češtiny" (Josef Čapek's A Doggie and a Pussycat), and a
plain "Original" in a note is not a translation statement (Prašina).

The `read` namespace cannot be derived - /book-log deletes the cache entry when it
logs a book - so existing read rows are MERGED, never recomputed. Carrying the row
across is part of the /book-log contract, the same as the facets.

The statement evidence is cached in <scratchdir>/origin-evidence.jsonl and reused, so
a re-run after screening in new books costs only the new titles.
"""
import json, io, os, re, sys, time, unicodedata
import urllib.parse, urllib.request

UA = {"User-Agent": "Mozilla/5.0 (book-shelf/1.0 personal reading list)"}
BASE = "https://katalog.mekvalmez.cz/api/search"
TAG = re.compile(r"<[^>]+>")

TRANS = re.compile(
    r"p[řr]elo[žz]|"
    r"origin[áa]lu?\s*:?\s*\w|"
    r"n[áa]zev\s+origin[áa]lu|"
    r"z\s+(angli|n[ěe]m|francouz|rus|špan|ital|pol|švéd|norš|dán|niz|holand|maďar|"
    r"japon|čín|hebrej|arab|finš|portug|katal|latin|island|turec|ukraj|vietnam)",
    re.I)
FROM_CS = re.compile(r"p[řr]elo[žz]\w*\s+z\s+[čc]e[šs]tiny", re.I)

CS_AUTHORS = {
    # Backfilled 2026-08-31 after the 119-book promotion run: every one is an
    # unambiguously Czech-language author, so this is a lookup gap being closed,
    # not a guess about a language. The no-row default stays for genuinely unknown ones.
    "Daniel Rušar", "David Kühn", "Egon Bondy", "Helena Bernardová", "Helena Zakova", "Irena Riclova Lachoutova", "Ivana Peroutkova", "Jan Liška", "Jana Olivova", "Josef Farkas", "Josef Formanek", "Kamila Ulčová", "Ladislav Chrudina", "Lucie Hlavinkova", "Ludmila Vaňková", "Marie Rejfova", "Martina Grmolenská", "Nada Revilakova", "Nikkarin", "Nina Spitalnikova", "Nina Špitálníková", "Petr Hugo Slik", "Petra Kvasnickova", "Samuel Hornek", "Tereza Kučírková", "Tomáš Cícha", "Veronika Zacharova & Stepanka Sekaninova", "Vilém Sacher", "Vojtěch Otčenášek", "Zdeněk Volný", "Zuzana Pospisilova",
    "Ivona Březinová", "Jana Sramkova", "Petula Bendula",
    "Alena Mornštajnová", "Alois Jirásek", "Arnošt Lustig", "Bohumil Hrabal",
    "Božena Němcová", "David Glockner", "David Senk", "Drahomíra Pithartová",
    "Edita Dufkova", "Eduard Štorch", "Ester Stará, Jiří Franta", "František Kotleta",
    "František Tichý", "Helena Beránková, Libor Adam, Jan Vohlídal", "Helga Weissová",
    "Ilka Pacovska", "Iva Pekárková", "Ivan Klima", "Ivan Olbracht", "Jakub Hoza",
    "Jan Dobias", "Jan Drnek", "Jan Kotouč, Lucie Lukačovičová", "Jan Neruda",
    "Jan Werich", "Jarmila Novotná", "Jaroslav Foglar", "Josef Frais", "Julie Novakova",
    "Julius Zeyer", "Karel Poláček", "Karel Čapek", "Kateřina Blažková",
    "Kateřina Tučková",
    "Kateřina Tučková, Jakuba Katalpa, Jaroslav Rudiš, Petra Dvořáková, Marie Hajdová, "
    "David Jan Žák, Petra Klabouchová, Michal Vrba, Michaela Klevisová, Leoš Kyša",
    "Kateřina Čupová, Karel Čapek", "Klára Svobodová", "Kristýna Freiová",
    "Ladislav Fuks", "Ladislav Klimeš", "Lenka Elbe", "Lenka Poláčková", "Lubos Taraba",
    "Lucie Paulova", "Luisa Nováková", "Marcela Mlynarova", "Marek Jandak",
    "Martin Vopěnka", "Martin Šinkovský (ill. Ticho762 / Petr Novák)",
    "Martina Šimůnková", "Mila Linc", "Milan Kundera", "Miroslav Kubes", "Ota Pavel",
    "Patrik Ouředník", "Pavel Brycz", "Pavel Kohout", "Petr Hugo Šlik", "Petr Neužil",
    "Petr Schink", "Petr Šesták", "Petra Machova", "Roman Bureš", "Silvie Seborova",
    "Svatopluk Čech", "Tatana Rubasova & Jindrich Janicek", "Tereza Boučková",
    "Tomas Bartos", "Tomas Padevet", "Tomáš Němec", "Veronika Hurdová", "Viktor Fischl",
    "Vladislav Vančura", "Vlastislav Toman, František Kobík, Karel Zeman",
    "Vojtěch Matocha", "Václav Dvořák", "Věra Mertlíková", "Zdena Frýbová",
    "Zuzana Hartmanová", "Zuzana Strachotová", "Zuzana Svěží",
    "written and drawn by Josef Čapek",
}

# Only the authors the two deterministic rules never reach: a Czech record that omits
# the translation note, or no Czech edition at all (the free-EN-audio route).
FOREIGN_AUTHORS = {
    "A. A. Milne", "Antoine de Saint-Exupéry", "Anton Pavlovič Čechov",
    "Astrid Lindgren", "Ayaan Hirsi Ali", "Blake Crouch", "Brandon Sanderson",
    "Chalíl Džibrán", "Christopher Paolini", "Clifford D. Simak", "Daniel Defoe",
    "Dennis E. Taylor", "Edgar Allan Poe", "Eduard Limonov", "Ernest Hemingway",
    "Ernest Thompson Seton", "F. Scott Fitzgerald", "Fjodor Michajlovič Dostojevskij",
    "Francis Scott Key Fitzgerald", "Francoise Sagan", "Franz Kafka",
    "Gabriel García Márquez", "Gerald Durrell", "H. G. Wells", "Haruki Murakami",
    "Ira Levin", "Isaak Emmanuilovič Babel", "Ivan Sergejevič Turgeněv",
    "James Islington", "James S. A. Corey", "Joe Abercrombie", "John Irving",
    "Jules Verne", "Józef Mackiewicz", "Lea Kampe", "Lewis Carroll", "Martha Wells",
    "Matt Dinniman", "Michael Crichton", "Monika Zgustova", "Neil White",
    "Pierce Brown", "Ray Bradbury", "Roald Dahl", "Robert Silverberg",
    "Sarah A. Parker", "Sarah Beth Durst", "Sequoia Nagamatsu", "TJ Klune",
    "William Gibson", "Yann Martel",
}

# Only where the honest value needed something no field in the repo states.
NOTES = {
    "a-doggie-and-a-pussycat":
        "Czech original; this is the English edition, so its record reads "
        "'Přeloženo z češtiny' — the inverse of a translation into Czech.",
    "jsem-milena-z-prahy":
        "The Spanish 'Soy Milena de Praga' (Galaxia Gutenberg, Feb 2024) preceded the "
        "Czech Ikar edition; no translator is recorded because Zgustová writes in both "
        "languages.",
    "ortel-kafka": "Kafka wrote in German — Czech-born is not Czech-language.",
    "zert-kundera":
        "Kundera's Czech-language period. The French novels (Slowness, Identity, "
        "Ignorance) are translations into Czech and carry a translator.",
}

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRATCH = sys.argv[1] if len(sys.argv) > 1 else "."
EVIDENCE = os.path.join(SCRATCH, "origin-evidence.jsonl")


def norm(s):
    s = unicodedata.normalize("NFKD", s or "")
    s = "".join(c for c in s if not unicodedata.combining(c)).lower()
    return re.sub(r"[^a-z0-9]+", "-", s).strip("-")


def slug(x):
    return norm(x)[:60]


def rd(name):
    return io.open(os.path.join(REPO, name), encoding="utf-8")


def search(q):
    url = BASE + "?" + urllib.parse.urlencode(
        {"q": q, "pageSize": 60, "pageNumber": 1}, quote_via=urllib.parse.quote)
    for _ in range(3):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=45) as r:
                return json.load(r)
        except Exception:
            time.sleep(2)
    return None


def notes(rec):
    out = []
    for row in rec.get("detailTableRows") or []:
        c = row.get("columns") or []
        if len(c) < 2:
            continue
        lab = TAG.sub("", c[0].get("content") or "").lower()
        if "pozn" in lab or "unifikovan" in lab:
            out.append(re.sub(r"\s+", " ", TAG.sub(" ", c[1].get("content") or "")).strip())
    return [x for x in out if x]


def statements(book):
    """Every responsibility statement and note on any catalogue edition of the work."""
    t = book.get("czTitle") or book.get("title") or ""
    d = search(" ".join(re.split(r"\s+", t)[:6])) or {}
    atoks = {w for w in norm(book["author"]).split("-") if len(w) > 3}
    tk = norm(t)[:18]
    out = []
    for r in ((d.get("result") or {}).get("content")) or []:
        rs = (r.get("responsibilityStatement") or {}).get("text") or ""
        ra = norm(" ".join(a.get("text") or "" for a in (r.get("primaryAuthors") or [])))
        if tk and tk not in norm(r.get("name")):
            continue
        if atoks and not (atoks & set((ra + "-" + norm(rs)).split("-"))):
            continue
        out += [rs] + notes(r)
    return [s for s in out if s]


cache = json.load(rd("book-cache.json"))
need = [b for b in cache["books"] if not (b.get("cz") or {}).get("translator")]

ev = {}
if os.path.exists(EVIDENCE):
    for l in io.open(EVIDENCE, encoding="utf-8"):
        r = json.loads(l)
        ev[r["key"]] = r["statements"]
if any(b["key"] not in ev for b in need):
    f = io.open(EVIDENCE, "a", encoding="utf-8", newline="\n")
    for i, b in enumerate(need):
        if b["key"] in ev:
            continue
        ev[b["key"]] = statements(b)
        f.write(json.dumps({"key": b["key"], "statements": ev[b["key"]]},
                           ensure_ascii=False) + "\n")
        f.flush()
        print("fetched", i, "/", len(need), b["key"], flush=True)
        time.sleep(0.25)
    f.close()

books, unknown = {}, []
for b in cache["books"]:
    k, a = b["key"], b["author"]
    translated = [s for s in ev.get(k, []) if TRANS.search(s) and not FROM_CS.search(s)]
    if (b.get("cz") or {}).get("translator"):
        o, src = "foreign", "translator"
    elif translated:
        o, src = "foreign", "statement"
    elif a in CS_AUTHORS:
        o, src = "cs", "author"
    elif a in FOREIGN_AUTHORS:
        o, src = "foreign", "author"
    else:
        unknown.append((k, a))
        continue
    books[k] = {"orig": o, "src": src}
    if k in NOTES:
        books[k]["note"] = NOTES[k]

prev = {}
if os.path.exists(os.path.join(REPO, "book-origin.json")):
    prev = (json.load(rd("book-origin.json")).get("read")) or {}
L = rd("books-read.md").readlines()
h = [i for i, l in enumerate(L)
     if re.match(r"^\|\s*Book\s*\|\s*Author\s*\|\s*Score\s*\|", l, re.I)][0]
read, lost = {}, []
for l in L[h + 2:]:
    if not l.strip().startswith("|"):
        break
    c = [x.strip() for x in l.strip().strip("|").split("|")]
    if len(c) < 5:
        continue
    s = slug(c[0])
    if s in prev:
        read[s] = prev[s]
    else:
        lost.append(c[0])

doc = {
    "_readme":
        "Was the work WRITTEN in Czech, or is the reader reading a translation. The "
        "viewer app's Origin filter, on the Candidates and Read tabs. A fact about the "
        "work, never a judgement about it - what a translation costs the reading is the "
        "reader's own call and is not recorded anywhere here. Regenerable for "
        "`books` by tools/fetch-origin.py; `read` is merged, never recomputed, because "
        "/book-log deletes the cache entry it would have to derive from. Kept out of "
        "book-cache.json so that regenerating it never forces that hand-formatted file "
        "to be reserialised, and out of book-read-facets.json because this covers both "
        "tabs and that file covers only the read table.",
    "schema": 1,
    "_key": "`books` by book-cache.json key; `read` by slug(title) of a books-read.md "
            "row - the SAME key as book-media.json's readMedia and "
            "book-read-facets.json. A renamed title costs a missing row, which the "
            "Gaps panel reports, not a wrong one.",
    "_orig": "cs = written in Czech. foreign = written in another language, so the "
             "Czech edition is a translation. The language of the original is "
             "deliberately NOT recorded: it would be a third covered at best, and a "
             "half-filled field invites being trusted.",
    "_src": "How the value was decided, weakest last. `translator` - book-cache.json "
            "records a Czech translator. `statement` - the catalogue record says "
            "'z anglického originálu' or 'Přeloženo z němčiny'. `author` - the author "
            "writes in Czech, or does not. That last rule exists because the catalogue "
            "evidence is ONE-DIRECTIONAL: a statement proves a translation, its ABSENCE "
            "proves nothing, since older records omit it - Robinson Crusoe, Medvídek Pú "
            "and Jurassic Park all have a Czech record with no translation note.",
    "_missing": "A book whose author is in neither list in tools/fetch-origin.py gets NO "
                "ROW. The filter then excludes it under either value and the Gaps panel "
                "names it, which is the same contract as an unfaceted read row: "
                "unclassified is not evidence of being a translation.",
    "books": books,
    "read": read,
}
io.open(os.path.join(REPO, "book-origin.json"), "w", encoding="utf-8", newline="\n").write(
    json.dumps(doc, ensure_ascii=False, indent=1) + "\n")

n = lambda d, v: sum(1 for x in d.values() if x["orig"] == v)
print(f"books: cs {n(books, 'cs')}, foreign {n(books, 'foreign')}, "
      f"no row {len(unknown)} of {len(cache['books'])}")
print(f"read:  cs {n(read, 'cs')}, foreign {n(read, 'foreign')}, no row {len(lost)}")
for k, a in unknown:
    print("  no row:", k, "-", a, "(add the author to CS_AUTHORS or FOREIGN_AUTHORS)")
for t in lost:
    print("  no read row:", t, "(carry it across when /book-log logs a book)")
