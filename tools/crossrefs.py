"""Fail if a candidate's `why` argues from another candidate.

The rule (reader, 2026-08-26): a prediction may take inspiration from the saved
rules and from books that carry a real score, and from nothing else. Candidates
never mention each other. An estimate calibrated against another estimate is a
guess anchored to a guess, and it fails silently in both directions - 22 of the
2026-08-26 batch were derived that way, including one that argued from
"451 read" when Fahrenheit 451 is itself an unread candidate.

Scanned: the `why` of every line in book-estimates.jsonl. NOT scanned:
`flags` in book-cache.json, which is the facts layer and is *supposed* to name
sibling volumes and alternative editions - "read volume 1 first" is a fact about
the shelf, not a borrowed judgement.

    python tools/crossrefs.py            # exits 1 on any hit

Needles are every other candidate's title, czTitle and czTitleAliases. A row's
own titles are removed from the text first, so `Predehra k Nadaci` does not
report itself for containing `Nadace`. Multi-word needles match
case-insensitively; a **single-word** needle must match the title's own
capitalisation, because the alternative was `Nation` reporting a hit on the
phrase "a nation that has forgotten its atrocity".

MIN_LEN was 5 until 2026-08-26, which left `Zert`, `Syn`, `Hana`, `Silo`, `Wool`
and `Son` unsearchable - and the 56-book score-5 batch tripped exactly that: two
estimates argued "Ten points under Zert 70-80" and "the same cold register as
Zert" and the check passed clean. Lowered to 3, which only works because READ
TITLES ARE BLANKED FROM THE TEXT FIRST: without that, `Son` matched inside "Son
of Hamas 75", which is a legitimate citation of a scored book. That blanking is
the right rule in its own right - a read book's title can never be a forbidden
reference, so it should never be a needle's context either.

Residual false-positive shape: a one-word title used as an ordinary capitalised
noun.

Titles alone were not enough. A title check passed clean over eleven rows that
named a candidate without quoting one (found 2026-08-26 by hand, after the title
pass reported zero):

- **A series name.** "the same strengths as Licanius" - the series field is a
  needle now.
- **A batch-relative superlative.** "the strongest of the three Marquez volumes
  in this batch", "the largest idea payload of anything in this batch". Ranking
  a candidate inside its batch is the borrowed anchor with the title filed off,
  and the ranking dies the moment the batch changes.
- **Delegation.** "same reasoning as the Chekhov row - see that line". The app
  shows one card at a time, so a row that points elsewhere shows nothing.
- **A borrowed range.** "the Maly princ 82 / Racek 64-74 shape": one read score
  and one *estimate*, side by side, reading as equally solid. Any NN-NN that is
  not this row's own `est` is a hit.
"""
import json, io, re, sys, unicodedata

CACHE, EST, READ = "book-cache.json", "book-estimates.jsonl", "books-read.md"
PROFILE = "tools/reader-profile.md"
MIN_LEN = 3

# Not every NN-NN is a borrowed score. Six of the 2026-09-01 hits were not: two rows
# quoted the infidelity axis's own published "an approving subplot 30-40" (which happens
# to equal two unrelated candidates' est), and four counted something - "ages 11-15",
# "chapters 18-22". So a range the RULES publish is exempt, and so is one introduced as
# an age, chapter or page count. The rules mean reader-profile.md and NOT
# book-recommendations.md: that file carries the Candidate table, and whitelisting its
# ranges would whitelist every estimate in the repo.
# Cost, stated: the profile also publishes the scoring ladder (50-65, 65-75, 75-85,
# 85-95), so a row borrowing a neighbour's est that happens to BE a ladder band now
# passes. Small in practice - a real borrowed est is arbitrary (64-74, 72-82), and the
# title, series and batch-relative checks catch the citation itself either way.
COUNTED = re.compile(r"\b(?:age[sd]?|chapters?|pages?|pp\.?)\s+$", re.I)

# Titles that are also ordinary language, and so unusable as needles. Each earned
# its place by blocking a correct estimate on 2026-08-26: `Empire` fired on the
# Martial Empire, which IS the setting of the two Tahir books being estimated, and
# again on Asimov's own galactic empire; `The Joke` fired on the phrase "the joke".
# Capitalisation matching does not save either - both appear capitalised, mid-prose.
# The cost is that these two candidates could now be cited unnoticed. That is the
# cheaper error: a false positive here blocks a correct estimate from being written
# at all, and the batch-relative and sibling-ordinal checks below are unaffected.
STOP_TITLES = {"empire", "the joke", "the truth",
               # Added 2026-08-31: the 119-book promotion run produced 18 hits and every
               # one was a needle being used as ordinary language, not as a citation.
               # "the band" fired six times on "the band Mort 83 occupies" and on actual
               # rock bands; "labyrint" and "raj" are ordinary Czech words AND both sit
               # inside the read title Labyrint sveta a raj srdce, so citing a scored book
               # tripped the check; "the city", "the choice", "the plague" and "christmas"
               # need no explanation. Cost, stated: these seven candidates could now be
               # cited unnoticed. That is the cheaper error - a false positive here blocks
               # a correct estimate from being written at all.
               "the band", "the city", "the choice", "the plague", "christmas",
               "labyrint", "raj",
               # Series names that are also real-world proper nouns, so a book ABOUT the
               # person, place or holiday trips them: "Robin" fired on "Robin-Hood-style"
               # and on a character called Fanny Robin, "Hannibal" and "Atlantis" on the
               # historical figure and the myth.
               "robin", "atlantis", "hannibal", "disney", "flawed",
               # Added 2026-09-01 from a full 1113-row pass: 40 hits, all one-word or
               # ordinary-phrase titles used as language rather than as citations. THE
               # PATTERN, now clear enough to state: a short single-word needle that is
               # also a common noun is unusable, and the capitalisation rule does not
               # save it because these appear capitalised at the start of a sentence.
               "rad", "the religion", "legie", "the legion", "the last human",
               "the first time",
               "poprve", "the names", "jmena", "underground", "gallant", "never",
               "nikdy", "eternal", "pure", "cisty", "den", "day", "the coup",
               "prevrat", "relentless", "nezdolna", "titans", "titani", "arena",
               "roman arena", "pisek", "sand", "moc", "malice", "led", "ice",
               "a small town", "zapadakov",
               # And more real-world proper nouns, the "robin"/"atlantis" case above:
               # franchises and places a row names as a cultural comparison, and a
               # character called Gerta inside a book whose own title is Gerty.
               "providence", "star wars", "minecraft", "einstein", "gerta",
               "warleggan", "the atlas",
               # 2026-09-02, the same shape again and every one a false positive: `Winter`
               # is a season and one half of a book's own declared premise, `Matilda` a
               # character in the book being estimated, `Protector` a rank in it, `The Fox`
               # the protagonist of Fantastic Mr Fox, and `Trans` the first half of
               # Trans-Siberian - flat() turns the hyphen into a space, so a compound
               # cannot be told from a citation once the text is normalised.
               "winter", "matilda", "protector", "the fox", "trans",
               # 2026-09-02, the science-fiction run: `On the Road` fired on "companionship
               # on the road", and `Foundation` on a tribute anthology listing the honoured
               # author's own universes - "robots, the Foundation, and several one-off
               # series". `Foundation` is a series name six candidates share, so exempting
               # it costs the most of any entry here; the alternative was blocking a
               # correct estimate, which is the trade this set has always made.
               "on the road", "foundation"}

# Phrasing that argues from the neighbours without naming one.
# "the Author(s) row" is exempt: that points at the Authors table in
# book-recommendations.md, which is the rules layer and is allowed.
# "in the batch" too, not just "in this batch": a row reading "the one Sharpe entry in
# the batch not built around a battle" passed the narrower version.
PHRASES = [r"in th(?:is|e) batch", r"the (?!Authors?\b)[A-Z][a-z]+ row\b", r"another candidate",
           r"already carrying", r"second route", r"see that line",
           r"same (?:reasoning|disposition|axis|range|method) as",
           # A superlative only counts when it ranks BOOKS. "the lead is widely
           # reported as the weakest of the three" ranks the three POV characters
           # inside one novel and is a legitimate observation about that book, so the
           # bare "weakest of the three" that used to be here reported Elantris on
           # 2026-08-26. Require a book-ish noun, or an explicit batch reference.
           r"(?:strongest|weakest|lowest|highest|largest|best) (?:of|range|idea)?\s*"
           r"(?:the |these )?(?:three|two|four|other)\s+"
           r"(?:books?|volumes?|novels?|entries|entry|titles?|rows?|instal+ments?|candidates?)",
           r"(?:strongest|weakest|lowest|highest|largest|best) (?:of|range|idea)?\s*"
           r"(?:the |these )?(?:three|two|four|other)\b(?=[^.]*\b(?:batch|queue|series)\b)",
           r"of the three [A-Z][a-z]+ (?:rows|volumes)",
           r"cheapest way to test", r"than the other [A-Z]"]


def flat(s, breaks=False):
    """Strip diacritics and punctuation, keep case: the file stores why-text as ASCII.

    `breaks` keeps sentence boundaries as `|`, and is set for the why-text only. Without
    it a multi-word needle matches straight across a full stop, because the stop becomes
    a space: "what you cannot see may still be there. There is a thought in that"
    flattened to "there There" and reported the candidate `There There` on 2026-09-02.
    `|` is not alphanumeric, so the single-word boundary assertions are unaffected.
    Cost, stated: a needle that itself spans a colon or dash - `Runes: The Creature of a
    Thousand Faces` - can no longer match a why that quotes it in full, since the text
    now carries `|` where the colon was. Such a title is cited by its short form or its
    Czech title in practice, and both are separate needles."""
    s = unicodedata.normalize("NFKD", s or "")
    s = "".join(c for c in s if not unicodedata.combining(c))
    if breaks:
        s = re.sub(r"[.!?;:]+", " | ", s)
        return re.sub(r"[^A-Za-z0-9|]+", " ", s).strip()
    return re.sub(r"[^A-Za-z0-9]+", " ", s).strip()


def titles(b):
    raw = [b.get("title"), b.get("czTitle")] + (b.get("czTitleAliases") or [])
    out = []
    for t in (flat(x) for x in raw if x):
        if len(t) >= MIN_LEN and t not in out and t.lower() not in STOP_TITLES:
            out.append(t)
    return out


def find(needle, text):
    pat = r"(?<![A-Za-z0-9])" + re.escape(needle) + r"(?![A-Za-z0-9])"
    return re.search(pat, text, 0 if " " not in needle else re.I)


def read_titles():
    """Titles with a real score. Citing these is the whole point, so they are
    blanked from the why-text before any candidate needle is looked for."""
    out = []
    try:
        lines = io.open(READ, encoding="utf-8").readlines()
    except OSError:
        return out
    for l in lines:
        if not l.startswith("| ") or l.count("|") <= 4:
            continue
        col = [x.strip() for x in l.split("|")]
        if len(col) > 1 and col[1] and col[1] not in ("Book", "Score"):
            # Also the part before the parenthetical: a why cites "Golden Son 92",
            # not "Golden Son (Red Rising #2)", and leaving that unblanked exposes
            # `Son` to a candidate needle.
            for t in (flat(col[1]), flat(col[1].split("(")[0])):
                if len(t) >= MIN_LEN:
                    out.append(t)
    return sorted(set(out), key=len, reverse=True)


def profile_bands():
    try:
        p = io.open(PROFILE, encoding="utf-8").read()
    except OSError:
        return set()
    return {(int(a), int(b)) for a, b in
            re.findall(r"(?<![\d-])(\d{2})\s*-\s*(\d{2})(?![\d-])", p)}


def series_names(books):
    """series -> the keys carrying it. A name only one candidate holds is not a
    cross-reference when that candidate uses it, so the owner is checked per row."""
    out = {}
    for b in books:
        s = flat((b.get("series") or "").split("#")[0])
        # STOP_TITLES applies here too, and did not until 2026-08-31: series needles were
        # built without consulting it, so `The Band` fired 13 times in one run - on the
        # phrase "the band", on actual rock bands, and on "the band Mort 83 occupies".
        # A series name that is also ordinary language is as unusable as a title that is.
        if len(s) >= MIN_LEN + 2 and s.lower() not in STOP_TITLES:
            out.setdefault(s, set()).add(b["key"])
    return out


def main():
    books = json.load(io.open(CACHE, encoding="utf-8"))["books"]
    names = {b["key"]: titles(b) for b in books}
    series = series_names(books)
    own_series = {b["key"]: (b.get("series") or "").split("#")[0] for b in books}
    scored = read_titles()
    bands = profile_bands()
    rows = []
    for i, line in enumerate(io.open(EST, encoding="utf-8"), 1):
        if line.strip():
            r = json.loads(line)
            if "key" in r:
                rows.append((i, r))

    hits = 0
    for lineno, r in rows:
        text = flat(r.get("why", ""), breaks=True)
        own = names.get(r["key"], []) + [flat(r.get("t", ""))]
        # Longest first, and read titles before own titles: "Son of Hamas" must go
        # before the bare "Son" of any candidate can match inside it.
        for o in scored + sorted(own, key=len, reverse=True):
            if o:
                text = re.sub(re.escape(o), " ", text, flags=re.I)
        # A needle whose every word already appears in THIS row's own title or series is
        # the row talking about its own book or its own world, not citing a neighbour.
        # `Nyxia` is a candidate and also the in-world substance the Nyxia Triad is named
        # after, so "Nyxia itself remains a material with declared rules" reported the
        # sibling volume on 2026-09-02. Blanking own titles cannot catch it: the row's
        # title is `Nyxia Uprising`, and the bare word survives.
        ownw = set()
        for o in own + [flat(own_series.get(r["key"], ""))]:
            ownw |= {w.lower() for w in o.split() if w}
        for key, ts in names.items():
            if key == r["key"]:
                continue
            for t in ts:
                if ownw and {w.lower() for w in t.split()} <= ownw:
                    continue
                if find(t, text):
                    print(f"{EST}:{lineno} {r['key']} -> names candidate {key} ({t})")
                    hits += 1
        for s, owners in series.items():
            if r["key"] not in owners and find(s, text):
                print(f"{EST}:{lineno} {r['key']} -> names series {s} ({len(owners)} candidate(s))")
                hits += 1
        for p in PHRASES:
            m = re.search(p, r.get("why", ""))
            if m:
                print(f"{EST}:{lineno} {r['key']} -> batch-relative or delegating: {m.group(0)!r}")
                hits += 1
        # Dates are NN-NN too, so only ranges outside a YYYY-MM-DD are read as one.
        est = r.get("est") or []
        why = r.get("why", "")
        for m in re.finditer(r"(?<!\d[-\d])\b(\d{2})\s*-\s*(\d{2})\b(?!-)", why):
            pair = tuple(map(int, m.groups()))
            if pair in bands or COUNTED.search(why[max(0, m.start() - 12):m.start()]):
                continue
            if list(pair) != list(est):
                print(f"{EST}:{lineno} {r['key']} -> cites range {m.group(0)}, own est {est}")
                hits += 1
    print(f"{len(rows)} estimates scanned, {hits} cross-references")
    return 1 if hits else 0


if __name__ == "__main__":
    sys.exit(main())
