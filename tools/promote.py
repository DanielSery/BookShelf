"""Tier-2 promotion: queue the work, absorb what the model staged, measure it.

The model does the whole judgement — research, access, estimate — per
`tools/promote-prompt.md`. This file does only the things a model must not:

  queue     pick the next N works off book-ai-rank.jsonl and emit a task list
  absorb    fold staged per-book JSON into cache + estimates + media
  holdout   emit a task list of works that ALREADY have a hand-derived estimate,
            so the model's output can be scored against an answer it never saw
  score     compare absorbed-or-staged estimates against the hand-derived ones

WHY STAGING EXISTS. Promotions run in parallel and every one of them would
otherwise read-modify-write book-cache.json. That loses work silently and without
a diff worth reading. So a model writes `<dir>/<key>.json` and nothing else, and
absorb is the only writer of the shared files.

WHY THE MODEL IS BLIND TO THE EXISTING ESTIMATES. Two reasons, and both are
load-bearing. An estimate argued from another candidate is a guess anchored to a
guess and tools/crossrefs.py fails on it. And a holdout is only a measurement if
the answer was not on disk in front of the model.

MEASURE BEFORE TRUSTING. The est span is a median of 10 points and the
propose/record line sits at 68 with the median est low at 70, so 46% of estimates
are within 5 points of the boundary and a +/-5 point error flips the verdict on
45% of books. Run `holdout` first, on a handful, and `score` the result. The
previous step in this pipeline cost 1.5M tokens to discover it was worse than what
it replaced, and one batch of holdout up front would have caught it.

    python tools/promote.py holdout <dir> [--n 10]
    python tools/promote.py queue   <dir> [--n 10] [--min-score 4] [--include-unranked]
    python tools/promote.py batch   <dir> [--per 15] [--per-author 15] [--n 200]
                                          [--unknown]
    python tools/promote.py absorb  <dir> [--force-low]
    python tools/promote.py score   <dir>

`--unknown` queues the works the cheap model did NOT recognise, which every other
selection excludes. See cmd_batch.
"""
import json, io, os, re, sys, glob, statistics, collections, difflib, unicodedata

CACHE, EST, MEDIA = "book-cache.json", "book-estimates.jsonl", "book-media.json"
REJECTS, REVS = "book-rejects.jsonl", "book-revs.json"
STORE, TRIAGE = "book-ai-rank.jsonl", "book-triage.jsonl"
INFID = "book-infidelity-screen.jsonl"
CATALOG = "book-catalog.jsonl"
PROMPT = os.path.join("tools", "promote-prompt.md")
PROFILE = os.path.join("tools", "reader-profile.md")
TODAY = os.environ.get("BOOK_TODAY", "2026-08-26")
URL = "https://katalog.mekvalmez.cz/records/"

GENRE = {"sf", "fantasy", "litfic", "historical", "testimony", "allegory", "thriller"}
# `verse` added 2026-08-27: Havran 40 ties the lowest score in the log and the reader
# named the form itself as a cause, which no existing axis covered - short PROSE merely
# fails to earn points under the short-idea-driven suspension, verse actually costs.
FORM = {"novel", "novella", "stories", "nonfiction", "verse"}
# Who the EDITION was published for. A third filterable facet added 2026-08-27 at
# the reader's request; a fact like genre and form, NOT a verdict on whether an
# adult should read it, which is axis:childrens in the estimate. Optional on a
# staged file - a promotion agent is not asked to judge it - and defaulted to
# `adult` with audienceSource `default` so the viewer can always filter, which is
# what a missing value would silently break.
AUDIENCE = {"adult", "ya", "childrens"}
# Every estimate must have examined these, or a later rule change cannot find it.
MANDATORY = ("axis:worldbuilding", "axis:protagonist", "axis:opening",
             "axis:motives", "axis:occult", "axis:detective", "axis:infidelity",
             "axis:sexual-content")


def deacc(s):
    # Eszett has no combining form, so NFKD leaves it and slug() turns it into a
    # separator: `Preußler` became `preu-ler`, whose last token is `ler`, so
    # authorid() could never match the same author spelled `Preussler`. That defeated
    # a title-level reject on Carodejuv ucen, because _decided() trusts the
    # (title, author) pair and does not fall back to the title when the pair misses.
    s = (s or "").replace("ß", "ss")
    s = unicodedata.normalize("NFKD", s)
    return "".join(c for c in s if not unicodedata.combining(c))


def slug(s):
    return re.sub(r"[^a-z0-9]+", "-", deacc(s).lower()).strip("-")


def load_jsonl(path, skip_header=True):
    rows = []
    for l in io.open(path, encoding="utf-8"):
        if l.strip():
            r = json.loads(l)
            if skip_header and "_readme" in r:
                continue
            rows.append(r)
    return rows


def authorid(name):
    """author:<surname>, de-feminised, matching how book-revs.json spells them."""
    parts = slug(name).split("-")
    if not parts:
        return "author:unknown"
    n = parts[-1]
    for suf in ("ova", "ove", "ovi"):
        if n.endswith(suf) and len(n) > len(suf) + 2:
            n = n[: -len(suf)]
            break
    return "author:" + n


def groupkey(name):
    """Batching key: `authorid` plus the forename initial.

    `authorid` alone is surname-only because it must match how book-revs.json spells
    author ids, and on the 1,011-work queue that put 44 buckets' worth of *different
    people* in one batch - Robert, Tessa and Joanne Harris; Penelope Fitzgeraldova
    with F. Scott. Shared research is the entire reason to group by author, so a
    bucket of unrelated writers gives up the saving and hands the agent several
    authors' books as if they were one oeuvre.

    The initial cannot simply be dropped in favour of the full name either: the
    catalogue spells one author three ways (`Liou CCh'-Sin`, `Liou Cch'-sin`,
    `Liou Cchi'-sin` - Liu Cixin), and those must stay together. Surname plus
    initial keeps the transliteration variants and splits the namesakes.
    """
    parts = slug(name).split("-")
    return authorid(name) + ":" + (parts[0][:1] if parts and parts[0] else "?")


# An agent's peak CONTEXT, which is a different and harder limit than its token spend:
# spend is cumulative across turns, context is what has to fit at once. Ceiling set by
# the reader 2026-08-27 - ideally 100k, never above 150k.
#
# Measured from the 50-book run of 2026-08-27: 3.06 tool calls per book, staged output
# mean 2,619 B per book, task line ~575 B per book. Fixed reading is the real size of
# promote-prompt.md + reader-profile.md + books-read.md + the dispatch note. Czech text
# runs about 3.4 chars per token, search results nearer 3.8.
#
# CTX_RESULT is deliberately the pessimistic end of the search-result range (2.5-6 kB
# per call): a ceiling estimated optimistically is not a ceiling.
CTX_RESULT, CTX_OUT, CTX_TASK = 6000, 2600, 575
CTX_IDEAL, CTX_MAX = 100_000, 150_000
# Tool calls per book FALL as the batch grows, because author research is shared:
# measured 3.06 at 8 books/batch and 2.50 at 20. Interpolated between those two, and
# held flat outside them rather than extrapolated - a two-point trend does not license
# a prediction at 40 books.
CTX_CALLS = ((8, 3.06), (20, 2.50))


def calls_per_book(per):
    (a, ca), (b, cb) = CTX_CALLS
    if per <= a:
        return ca
    if per >= b:
        return cb
    return ca + (cb - ca) * (per - a) / (b - a)


def peak_context(per):
    fixed = sum(os.path.getsize(p) for p in (PROMPT, PROFILE, "books-read.md")
                if os.path.exists(p)) + 2500
    return int((fixed + per * (CTX_TASK + CTX_OUT)) / 3.4
               + per * calls_per_book(per) * CTX_RESULT / 3.8)


# --------------------------------------------------------------------- queueing
def _tasklist(works, path, note):
    with io.open(path, "w", encoding="utf-8", newline="\n") as f:
        for w in works:
            f.write(json.dumps(w, ensure_ascii=False) + "\n")
    print(f"{len(works)} tasks -> {path}\n{note}")


# Words in a catalogue annotation that say WHICH hard filter to check first. They
# are routing hints and nothing more: measured 2026-08-26, 17% of the queue trips
# one and most are not exclusions, because "laska" is in plenty of literary fiction
# and "magie" in the invented systems the reader explicitly allows.
SIGNALS = {
    "detective": re.compile(r"vražd|detektiv|komisař|zločin|pátrá|policejní|inspektor|"
                            r"kriminál|vyšetřov|pachatel|únos", re.I),
    "childrens": re.compile(r"pro děti|pro čtenáře od|dětsk|školák|prvňáč|pohádk|leporel|"
                            r"pro nejmenší", re.I),
    "romance": re.compile(r"milostn|romantick|zamilu|erotick|svatb", re.I),
    # Separate from `romance` because gate 3 asks a different question: `romance` says a
    # love plot is present, this says the book may be ABOUT sexual behaviour. Kept narrow
    # on purpose - the wide words are already in `romance`, and a signal that fires on
    # every love story routes attention nowhere.
    "sex": re.compile(r"erotick|sexuáln|smysln|tělesn.{0,12}(touh|láska|vztah)|"
                      r"vášniv.{0,12}(vztah|román)|nevázan|orgi|prostitu|bordel", re.I),
    # No `infidelity` entry on purpose. tools/screen-infidelity.py does that job better
    # and its result arrives on the task line as `infidelity`: it tiers the evidence
    # (strong needles bind to a marriage alone, medium ones need a marriage word nearby)
    # and marks premise-shaped hits, where a flat regex here found 9 of the queue
    # against the screen's 19. Two sources for one signal would only drift apart.
    "occult": re.compile(r"čarodějnic|magi|kouzl|rituál|vyvolává|duchy|věštb|okultn|"
                         r"seance|nekromant", re.I),
}


def load_annotations():
    out = {}
    if not os.path.exists("book-annotations.jsonl"):
        return out
    for l in io.open("book-annotations.jsonl", encoding="utf-8"):
        if l.strip():
            r = json.loads(l)
            if "_readme" not in r:
                out[r["k"]] = r["a"]
    return out


def load_editions():
    """Precomputed Czech print routes, keyed like the annotations.

    Shipping the route in the task line is what removed Gate A and Step 3 from the
    contract. Measured 2026-08-27: the catalogue query an agent used to run itself
    returned 111 kB of JSON for the ~200 bytes that decide the route, and it stayed in
    that agent's context for the rest of the batch. Regenerate with
    `python tools/fetch-editions.py <scratchdir>`.
    """
    out = {}
    if not os.path.exists("book-editions.jsonl"):
        return out
    for l in io.open("book-editions.jsonl", encoding="utf-8"):
        if l.strip():
            r = json.loads(l)
            if "_readme" not in r:
                out[r["k"]] = r
    return out


def load_facts():
    """MARC facts per work from book-catalog.jsonl: original title, genre/form heading,
    subject keywords, series.

    Sent ONLY on an `--unknown` run, and `orig` is why. A work the cheap model did not
    recognise is usually a translation whose Czech title is opaque - "Kralove Wyldu" is
    unsearchable, "Kings of the Wyld" returns the whole internet - so without the
    original title the research gate fails on books that were never hard, just renamed.
    51 of the first 120 of that pool carry one. The ranked queue does not get these
    fields: a recognised work needs no help identifying itself and the bytes are not free.
    """
    out = {}
    if not os.path.exists(CATALOG):
        return out
    for l in io.open(CATALOG, encoding="utf-8"):
        if not l.strip():
            continue
        r = json.loads(l)
        if "_readme" in r:
            continue
        f = {}
        if r.get("orig"):
            f["orig"] = str(r["orig"])[:120]
        if r.get("gf"):
            f["gf"] = [str(x) for x in r["gf"][:3]]
        if r.get("kw"):
            f["kw"] = [str(x) for x in r["kw"][:6]]
        if r.get("series"):
            f["series"] = str(r["series"])[:120]
        if f:
            out[r["k"]] = f
    return out


def researchable(w, f):
    """Orders the `--unknown` pool, 0-8.

    NAMED FOR A HYPOTHESIS THAT TURNED OUT FALSE, and kept because it works anyway.
    It was built to float books an agent could actually research; measured over 360
    promoted books, EVERY one was researchable from the Czech title plus the author, so
    `orig` does not predict findability at all. What it predicts is TRANSLATION, and
    translated adult fiction is where the yield is - the first 120, all carrying an
    `orig`, returned 18 books above the propose line against 12 and 13 for the two
    slices that had almost none.

    Ranked by the free metadata scorer instead, the head of this pool is Czech-original
    military and local history with no author parsed at all - 15 of the first 120.
    """
    n = 0
    if f.get("orig"):
        n += 4
    if (w["a"] or "").strip():
        n += 2
    if f.get("gf") or f.get("kw"):
        n += 1
    if f.get("series"):
        n += 1
    return n


def load_infidelity():
    """Per-work rows from tools/screen-infidelity.py, for gate 2's task-line hint.

    A LEXICON HIT, NOT A VERDICT - the reject turns on premise vs subplot and publisher
    copy does not disclose structure. `premise` here means the hit landed in the first
    sentence or the annotation framed the book around it, which is a reason to look, not
    a finding. Regenerate with `python tools/screen-infidelity.py --out <file>`.
    """
    out = {}
    if not os.path.exists(INFID):
        return out
    for r in load_jsonl(INFID):
        if r.get("src") == "annotation":
            out[r["k"]] = {"tier": r["tier"], "premise": r["premise"], "hit": r["hit"]}
    return out


def already_decided():
    """Keys in book-cache.json and de-accented titles in book-rejects.jsonl.

    The queue's only exclusion used to be the `done` flag in book-ai-rank.jsonl, which
    `ai_rank.py seal` sets as a SEPARATE manual step after absorb. On 2026-08-27 a
    50-book run dispatched 9 books that were already decided - 6 already carried a
    reject row from the previous run - because that run was stopped before it sealed.
    18% of the tokens bought nothing, and absorb then threw the work away as duplicate.
    The seal is an optimisation; the output files are the truth, so filter on both.

    Matched on title AND author, never title alone: `Sucho` is Shusterman's *Dry* and
    Harper's *The Dry*, one estimated and one rejected, so a title-only match excludes
    a legitimate book.

    Three channels, because no single one covers everything. `key` is exact and is what
    new reject rows carry. The (title, author) pair covers rows written before that.
    Bare title is used only when the QUEUE row has no author at all - 13 catalogue rows
    have a blank author, and `Volani Cthulhu - Spisy 3/II` slipped back into the queue
    after being rejected because `authorid("")` cannot match `authorid("H. P. Lovecraft")`.
    A blank author cannot disambiguate anything, so the title is the best evidence there.
    """
    keys, pairs, titles, authors, series = set(), set(), set(), set(), set()
    try:
        keys = {b["key"] for b in json.load(io.open(CACHE, encoding="utf-8"))["books"]}
    except OSError:
        pass
    for r in load_jsonl(REJECTS):
        # deacc(), NOT just lower(). Both callers compare against deacc(title), so a
        # reject entity written WITH diacritics never matched and the whole
        # title-reject channel was dead for Czech titles - which is most of them.
        # Found 2026-08-27 when `Howluv putujici zamek`, rejected on the occult filter
        # hours earlier, was queued, promoted by an agent and absorbed with an
        # estimate, so the database briefly held a reject row and an est for one book.
        # It had been masked because the earlier rows happened to be written ASCII-only:
        # `Ve stinu Hvozdu` matched, `Howlův putující zámek` did not.
        e = deacc(r.get("entity") or "").strip().lower()
        if not e:
            continue
        # An entity is often written `Czech title (Original Title)`, and indexing only
        # the whole string missed both halves: `Zlobryne a sirotci (The Girl Who Drank
        # the Moon)` never matched the catalogue's `Zlobryne a sirotci`.
        # triage.py's rejected_titles() has always split on the parentheses; this
        # function did not, so the same reject row was visible to one module and
        # invisible to the other. Index the bare form and every alias.
        alias = [x.strip().lower() for x in re.split(r"[()]", e) if len(x.strip()) > 4]
        lvl = r.get("level")
        # An AUTHOR- or SERIES-level reject was skipped outright, so it excluded
        # nothing here: the same run promoted Naomi Novik's `Letni valka` with an
        # author-level reject on file. An author reject kills every one of their books,
        # which is the whole point of recording it at that level.
        if lvl == "author" and (r.get("author") or "").strip():
            authors.add(authorid(r["author"]))
            continue
        if lvl == "series" and (r.get("author") or "").strip():
            # A series reject is scoped to that author, and the series NAME rarely
            # matches a volume title, so the author id is the only usable key. Held
            # separately from `authors` because it must not veto the author's other work.
            series.add((e, authorid(r["author"])))
            continue
        if lvl != "title":
            continue
        titles.update(alias)
        if r.get("key"):
            keys.add(r["key"])
        if (r.get("author") or "").strip():
            aid = authorid(r["author"])
            pairs.update((a, aid) for a in alias)
    return keys, pairs, titles, authors, series


def _decided(w, keys, pairs, titles, authors=(), series=()):
    t = deacc(w["t"]).strip().lower()
    if slug(w["t"])[:44] in keys:
        return True
    if (w["a"] or "").strip():
        aid = authorid(w["a"])
        if aid in authors:
            return True
        # A series reject names the SERIES, and a volume is titled after it rather than
        # equal to it: `Jefferson` rejected at series level, volumes `Jefferson dela, co
        # muze` and `Jefferson se zlobi`. Prefix match, and only with the author
        # agreeing - which is what keeps it from vetoing an unrelated book that happens
        # to start with the same word.
        if any(t.startswith(sn) for sn, sa in series if sa == aid and len(sn) > 4):
            return True
        return (t, aid) in pairs
    return t in titles


def mktask(s, key, k, w, ann, eds, inf=None, facts=None):
    """One task line. `key` is the staging filename; `k` is the work key used to join
    the annotation, the route and the infidelity screen.

    `facts` - the original title, the genre heading, subject keywords and the series -
    is sent only on an `--unknown` run, where the model has no verdict to lean on and
    `orig` is what makes an opaque Czech title searchable."""
    t = {"key": key, "czTitle": w["t"], "author": w["a"],
         "publisher": w["p"], "year": w["y"], "aiScore": s}
    if facts is not None:
        # An unrecognised verdict has no score (ai_rank.ranked, ruled 2026-08-27), so
        # sending the raw 4 would hand the agent a number the file says not to read.
        t.pop("aiScore", None)
        t.update(facts.get(k) or {})
    # The library's own summary, so Gate B costs searches only for the question the
    # signals actually raise.
    a = ann.get(k, "")
    if a:
        t["annotation"] = a
    h = sorted(nm for nm, rx in SIGNALS.items() if a and rx.search(a))
    if h:
        t["signals"] = h
    if inf and k in inf:
        t["infidelity"] = inf[k]
    e = eds.get(k)
    if e:
        t["cz"] = e["cz"]
        if e.get("alts"):
            t["alts"] = e["alts"]
    else:
        # No precomputed route. The agent must NOT go and fetch one - that is the cost
        # this change removed - so it estimates the book and leaves access unresolved.
        t["cz"] = {"state": "unchecked", "publisher": w["p"], "year": w["y"],
                   "translator": None, "recordId": None, "edition": None}
    return t


def eligible_score(A, r, unranked_ok):
    """The score a queue filter may compare against, honouring `ranked()`.

    An unrecognised verdict has no score (ruled 2026-08-27), so it cannot satisfy
    `--min-score` — it belongs in a re-rank pool, not a promotion queue. Measured the
    same day over 100 promoted score-4 books: recognised 4s reached the propose line
    28% of the time, unrecognised 4s 9%. `--include-unranked` puts them back for a run
    that deliberately wants to sample them.
    """
    s = A.ranked(r)
    if s is None and unranked_ok:
        return r.get("s")
    return s


def cmd_batch(outdir, per=15, n=200, minscore=4, per_author=15, top=0, unranked_ok=False,
              unknown=False):
    """Group the queue so one agent covers several books and the fixed context is
    paid once instead of once per book.

    Measured 2026-08-26: promote-prompt.md + books-read.md + book-recommendations.md
    is ~22k tokens, re-read PER BOOK. Over 1,011 books that is ~22.4M tokens of pure
    duplication, 26% of a naive 85M budget. Batching 8 books to an agent and swapping
    the 16k-token book-recommendations.md for the 2k-token tools/reader-profile.md
    takes the fixed cost from ~22k/book to well under 1k/book.

    Grouped BY AUTHOR, because 56% of the queue is by an author with two or more
    books in it and author-level research is otherwise repeated: one determination
    that an author writes police procedurals covers all seventeen of their books.

    TWO SIZES, because the two kinds of batch have opposite economics. Measured over
    the 1,011-work queue on 2026-08-26: 625 authors, of which 443 contribute exactly
    one book. So raising a single `per` from 8 to 20 only merges singletons and
    un-splits nine authors - 243 batches becomes 205, a 16% saving worth ~4.5% of the
    token projection, while making the top refusal cause worse.

      `per_author` is generous (20, above the largest group). An author group shares
      its research, so keeping it whole is the only genuine saving batching offers,
      and splitting the 17-book author into three pays for that research three times.

      `per` is 15, set by the reader 2026-08-27, and the reason it is not 8 is a
      CORRECTED measurement. The 2026-08-26 paragraph above priced the fixed context at
      its file size, ~11k tokens, and concluded larger batches were worth ~4.5%. Three
      measured batch sizes later - 2 books 48,832 tok, 8 books 81,116 mean, 20 books
      136,014 - a least-squares fit gives **~40.6k fixed per batch and ~4.8k per book**,
      with residuals of -1.4k, +2.1k and -0.7k. What costs is re-sending the context
      across the batch's tool calls, not the file size. So per=8 pays 5.1k/book of pure
      overhead and per=15 pays 2.7k: 9.88k/book against 7.51k.

      The ceiling is CONTEXT, not spend - the reader capped an agent at 100k ideal /
      150k absolute. peak_context() is built from worst-case inputs and puts per=15 at
      almost exactly 100k; the 20-book run's measured 2.5 tool calls per book (author
      research is shared, so the rate FALLS as batches grow, from 3.06 at per=8) implies
      nearer 87k in practice. Verified at per=20: 0 validate failures over 20 files, no
      overspend at any gate, staged output 2,597 B/book against 2,619 B at per=8, and
      all three author pairs judged separately rather than sharing a verdict.

      `per_author` matches `per` at 15 because the context ceiling applies to a
      single-author group too - it is the one batch `per` cannot otherwise cap.
    """
    sys.path.insert(0, "tools")
    import ai_rank as A
    wk, store, ann = A.load_works(), A.load_store(), load_annotations()
    eds, inf = load_editions(), load_infidelity()
    facts = load_facts() if unknown else None
    # Belt and braces. A vetoed work is already excluded three other ways - it is never
    # sent to Haiku, `ranked()` gives it no score, and screen-headings.py has written it
    # a reject row - but the `--unknown` path reads the raw `s` and so bypasses the
    # second of those. This is the one check that cannot be bypassed.
    hdgs = A.load_headings()
    donekeys, donepairs, donetitles, doneauthors, doneseries = already_decided()
    cand, redone, unranked, vetoed = [], 0, 0, 0
    for k, w in wk.items():
        r = store.get(k)
        if not r or r.get("done") or w["skip"] or "s" not in r:
            continue
        if A.heading_veto(hdgs.get(k, [])):
            vetoed += 1
            continue
        if unknown:
            # The complement of every other selection: rec=1 works are what --min-score
            # already reaches, and mixing the two populations makes the yield unreadable.
            if r.get("rec"):
                continue
            # This path reads the RAW score, so it is the one place `ranked()` cannot
            # protect: without this check 527 works whose two gradings disagreed would
            # enter the queue through the back door, which is exactly what the consensus
            # filter exists to stop.
            if r.get("dissent"):
                vetoed += 1
                continue
            s = r.get("s")
        else:
            s = eligible_score(A, r, unranked_ok)
            if s is None:
                unranked += 1
                continue
        if s is None or s < minscore:
            continue
        if _decided(w, donekeys, donepairs, donetitles, doneauthors, doneseries):
            redone += 1
            continue
        cand.append((s, w["rank"], k, w))
    if unknown:
        cand.sort(key=lambda x: (-researchable(x[3], (facts or {}).get(x[2], {})), -x[0], -x[1]))
    else:
        cand.sort(key=lambda x: (-x[0], -x[1]))
    # `top` slices BEFORE grouping, so an author whose books straddle the cut is
    # deliberately split: the slice is a promise about which books get done, and
    # silently pulling in a 20th book to keep a group whole breaks that promise.
    if top:
        cand = cand[:top]

    # A key built from the Czech title alone collides, and the staged file is named
    # after it, so one book silently overwrites another. Measured on the 1,011-work
    # queue: 9 colliding keys over 18 works. Two different causes, and the surname
    # suffix separates them - `Sucho` is Shusterman AND Harper, so it disambiguates;
    # `Povidky z jedne a druhe kapsy` is Capek twice under two catalogue rows, so
    # both land on the same suffixed key and the duplicate row is dropped below.
    base = collections.Counter(slug(w["t"])[:44] for _, _, _, w in cand)

    def keyfor(w):
        b = slug(w["t"])[:44]
        if base[b] == 1:
            return b
        sur = authorid(w["a"]).split(":", 1)[1] or "anon"
        return (b[:44 - len(sur) - 1] + "-" + sur)

    def task(s, k, w):
        return mktask(s, keyfor(w), k, w, ann, eds, inf, facts)

    seen_keys = set()
    cand = [c for c in cand if not (keyfor(c[3]) in seen_keys or seen_keys.add(keyfor(c[3])))]

    by = collections.OrderedDict()
    for s, _, k, w in cand:
        # A catalogue row with no parsed author must never form a group: 13 of them
        # bucketed together on 2026-08-26 (Wells, Lovecraft, Herbert, Poe, Capek,
        # Kipling...) and would have been handed to one agent as a single oeuvre.
        gk = groupkey(w["a"]) if (w["a"] or "").strip() else "?" + k
        by.setdefault(gk, []).append(task(s, k, w))
    # One policy, two limits: up to `per_author` books when they share an author,
    # up to `per` when they do not. So a group larger than `per` gets its own batch
    # (split only if it exceeds `per_author`), and everything smaller is bin-packed
    # whole into mixed batches of at most `per`. Packing NEVER splits a group - that
    # would pay the author research twice, which is the one thing grouping buys.
    whole, small = [], []
    for aid, ts in sorted(by.items(), key=lambda kv: -len(kv[1])):
        if len(ts) > per:
            for i in range(0, len(ts), per_author):
                whole.append(ts[i:i + per_author])
        else:
            small.append(ts)
    mixed = []
    for ts in sorted(small, key=len, reverse=True):        # first-fit decreasing
        for g in mixed:
            if len(g) + len(ts) <= per:
                g += ts
                break
        else:
            mixed.append(list(ts))
    groups = whole + mixed

    os.makedirs(outdir, exist_ok=True)
    for i, g in enumerate(groups[:n]):
        with io.open(os.path.join(outdir, f"batch_{i:03d}.jsonl"), "w",
                     encoding="utf-8", newline="\n") as f:
            for t in g:
                f.write(json.dumps(t, ensure_ascii=False) + "\n")
    nb = sum(len(g) for g in groups[:n])
    pure = sum(1 for g in groups[:n] if len({groupkey(t["author"]) for t in g}) == 1)
    sent = [t for g in groups[:n] for t in g]
    route = collections.Counter(t["cz"]["state"] for t in sent)
    fixed = sum(os.path.getsize(p) for p in (PROMPT, PROFILE, "books-read.md")
                if os.path.exists(p)) // 4          # chars -> rough tokens
    unrankedNote = " - INCLUDED by --include-unranked" if unranked_ok else ""
    biggest = max((len(g) for g in groups[:n]), default=per)
    ctx = peak_context(biggest)
    warn = ("" if ctx <= CTX_IDEAL else
            "  <- over the 100k ideal" if ctx <= CTX_MAX else
            "  <- OVER THE 150k CEILING, lower --per")
    mode = ""
    if unknown:
        withorig = sum(1 for t in sent if t.get("orig"))
        noauthor = sum(1 for t in sent if not (t.get("author") or "").strip())
        mode = (f"  UNKNOWN pool (rec=0 only), ordered by researchability: "
                f"{withorig} carry an original title, {noauthor} have no author at all\n")
    print(f"{len(cand)} queued works -> {min(len(groups), n)} batches ({nb} books) in {outdir}\n"
          f"{mode}"
          f"  heading-vetoed (catalogue genre heading decides the filter): {vetoed}\n"
          f"  skipped as UNRANKED (unrecognised work, so no score): {unranked}{unrankedNote}\n  one-author batches: {pure} (up to {per_author})\n"
          f"  mixed batches: {min(len(groups), n) - pure} (whole author groups packed, up to {per})\n"
          f"  mean {nb / max(1, min(len(groups), n)):.1f} books/batch\n"
          f"  infidelity screen: {sum(1 for t in sent if t.get('infidelity'))} flagged, "
          f"{sum(1 for t in sent if (t.get('infidelity') or {}).get('premise'))} premise-shaped\n"
          f"  routes precomputed: {route['verified']} verified, {route['none']} no Czech print, "
          f"{route['unchecked']} unchecked (agent must not fetch)\n"
          f"  fixed context ~{fixed}tok/batch, "
          f"~{fixed * min(len(groups), n) // max(1, nb)}tok/book\n"
          f"  est peak agent context ~{ctx // 1000}k tok at {biggest} books/batch{warn}")


def cmd_queue(outdir, n=10, minscore=4, unranked_ok=False):
    sys.path.insert(0, "tools")
    import ai_rank as A
    wk, store, ann = A.load_works(), A.load_store(), load_annotations()
    eds, inf = load_editions(), load_infidelity()
    donekeys, donepairs, donetitles, doneauthors, doneseries = already_decided()
    cand = []
    for k, w in wk.items():
        r = store.get(k)
        if not r or r.get("done") or w["skip"] or "s" not in r:
            continue
        s = eligible_score(A, r, unranked_ok)
        if s is None or s < minscore:
            continue
        if _decided(w, donekeys, donepairs, donetitles, doneauthors, doneseries):
            continue
        cand.append((s, w["rank"], k, w))
    cand.sort(key=lambda x: (-x[0], -x[1]))
    os.makedirs(outdir, exist_ok=True)
    tasks = [mktask(s, slug(w["t"])[:44], k, w, ann, eds, inf) for s, _, k, w in cand[:n]]
    withann = sum(1 for t in tasks if t.get("annotation"))
    sig = sum(1 for t in tasks if t.get("signals"))
    route = sum(1 for t in tasks if t["cz"]["state"] != "unchecked")
    _tasklist(tasks, os.path.join(outdir, "_tasks.jsonl"),
              f"from {len(cand)} works at ai score >= {minscore}, best-first | "
              f"{withann} carry an annotation, {sig} trip a signal word, "
              f"{route} carry a precomputed Czech route")


def cmd_holdout(outdir, n=10):
    """Works that already have a hand-derived estimate — the measurement set."""
    est = {r["key"]: r for r in load_jsonl(EST) if "key" in r}
    books = {b["key"]: b for b in json.load(io.open(CACHE, encoding="utf-8"))["books"]}
    pool = [k for k in est if k in books and est[k].get("est")]
    pool.sort()
    step = max(1, len(pool) // max(1, n))          # spread across the est range
    pick = [pool[i] for i in range(0, len(pool), step)][:n]
    os.makedirs(outdir, exist_ok=True)
    # The route comes from the cache rather than book-editions.jsonl, because a
    # holdout book is already promoted. It has to be present either way: the contract
    # promises a `cz` on every task line and forbids fetching one, so a holdout task
    # without it would be measuring a different job from the one agents actually do.
    tasks = []
    for k in pick:
        cz = dict(books[k].get("cz") or {})
        tasks.append({"key": k, "czTitle": books[k].get("czTitle") or books[k]["title"],
                      "author": books[k]["author"], "publisher": cz.get("publisher", ""),
                      "year": cz.get("year", ""), "holdout": True,
                      "cz": {"state": cz.get("state", "unchecked"),
                             "publisher": cz.get("publisher"), "year": cz.get("year"),
                             "translator": cz.get("translator"),
                             "recordId": cz.get("recordId"), "edition": cz.get("edition")}})
    _tasklist(tasks, os.path.join(outdir, "_tasks.jsonl"),
              "HOLDOUT — each already has a hand-derived est the model must not see. "
              "Run `score` afterwards.")


# ---------------------------------------------------------------------- absorb
# 12, not 6. A short title is usually also ordinary prose, or a piece of the very
# worldbuilding vocabulary the estimate has to discuss, and it then blocks legitimate
# work: "The Joke" fired on the phrase "the joke", and "Empire" fired on the Martial
# Empire, which IS the setting of the book being estimated. Case-sensitive matching
# was tried first and is not enough - casing varies too much to rely on. Titles under
# this length are dropped instead, and tools/crossrefs.py runs a second pass anyway.
NEEDLE_MIN = 12


def _candidate_needles():
    """Titles of works already in the cache, plus their est ranges.

    The prompt tells a model not to read book-estimates.jsonl, and on 2026-08-26 that
    instruction was NOT reliably obeyed: one staged estimate cited "Munro's domestic
    realism to 52-62", a range that exists nowhere but that file. Instruction-based
    isolation does not hold, so the gate moved here - in front of the write - instead
    of running after it.
    """
    titles, ranges = [], set()
    try:
        for b in json.load(io.open(CACHE, encoding="utf-8"))["books"]:
            for t in [b.get("title"), b.get("czTitle")] + (b.get("czTitleAliases") or []):
                t = deacc(t or "")
                if len(t) >= NEEDLE_MIN:
                    titles.append(t)
    except OSError:
        pass
    try:
        for r in load_jsonl(EST):
            if r.get("est"):
                ranges.add(f"{r['est'][0]}-{r['est'][1]}")
    except OSError:
        pass
    return titles, ranges


# Batch-relative reasoning, found on the first batched run 2026-08-26. Worse than
# naming a candidate: an estimate that depends on which books were grouped with it
# is not reproducible, because regrouping the queue moves the number.
BATCH_REL = re.compile(r"in this batch|of these (?:eight|seven|six|five|four|three|two|books)|"
                       r"the strongest of the|unlike the others|compared with the other", re.I)

# Ordinal references to a sibling volume, which the title needles cannot catch
# because they name no title. Raising per_author to 20 puts a 17-book author in one
# context, and 5 of the 8 files refused on 2026-08-26 were one such author arguing a
# volume's number from its position in the series. A sibling fact is a FACT and
# belongs in `flags`; it must not be load-bearing in `why`.
SIBLING_REL = re.compile(
    # A possessive or determiner in front means the ordinal names a PART OF THIS BOOK,
    # not a sibling: "the novel's first book" refused Hastrman on 2026-08-27, where
    # Hastrman is one novel structured in two books. Same false-positive shape as the
    # Elantris "weakest of the three", which ranked three POV characters in one novel.
    r"(?<!novel's )(?<!novels )(?<!book's )(?<!books )(?<!its )(?<!this )"
    r"(?:series|first|second|third|fourth|later|earlier|previous|preceding|next|"
    r"opening|final|last)\s+(?:opener|volume|book|instal+ments?|instal+ment|entry|entries)|"
    r"\b(?:vol\.?|volume|book)\s*(?:[2-9]|1\d)\b|"
    r"the (?:series )?opener|\bmid-series\b|"
    r"(?:stronger|weaker|better|best|weakest|strongest) (?:entry|volume|instal+ment)", re.I)


def validate(d, needles=None):
    bad = []
    titles, ranges = needles if needles else _candidate_needles()
    why = deacc(d.get("why") or "")
    m = BATCH_REL.search(why)
    if m:
        bad.append(f"why is batch-relative ({m.group(0)!r}) — an estimate must stand alone "
                   f"against books-read.md, not against whatever was grouped with it")
    m = SIBLING_REL.search(why)
    if m:
        bad.append(f"why argues from a sibling volume ({m.group(0)!r}) — reading order and "
                   f"which entry is stronger are facts, so move them to `flags`; `why` "
                   f"carries only this book against books-read.md")
    own = {deacc(d.get("title") or ""), deacc(d.get("czTitle") or "")}
    for t in titles:
        if t in own:
            continue
        if re.search(r"(?<![A-Za-z0-9])" + re.escape(t) + r"(?![A-Za-z0-9])", why, re.I):
            bad.append(f"why names another candidate: {t!r} — argue from books-read.md only")
    for rg in ranges:
        if re.search(r"(?<!\d)" + re.escape(rg) + r"(?!\d)", why):
            bad.append(f"why cites another candidate's est range {rg!r} — that number only "
                       f"exists in book-estimates.jsonl, which you must not read")
    for f in ("key", "author", "why", "blurb"):
        if not d.get(f):
            bad.append(f"missing {f}")
    # Only an estimate needs a genre and a form. The contract tells an agent that on a
    # reject most fields are unknown and that this is correct - you do not classify the
    # form of a book you disqualified two sources in - and requiring them here refused
    # 16 of 17 otherwise-good reject files on 2026-08-27 for obeying the contract.
    if not d.get("reject"):
        if d.get("genre") not in GENRE:
            bad.append(f"genre {d.get('genre')!r} not in {sorted(GENRE)}")
        if d.get("form") not in FORM:
            bad.append(f"form {d.get('form')!r} not in {sorted(FORM)}")
    else:
        for f, ok in (("genre", GENRE), ("form", FORM)):
            if d.get(f) and d[f] not in ok:
                bad.append(f"{f} {d[f]!r} not in {sorted(ok)}")
    cz = d.get("cz") or {}
    # `unchecked` is honest and allowed: the route is precomputed by
    # tools/fetch-editions.py and a work missing from that sweep has no route yet.
    # The agent is forbidden to fetch one, so it must be able to say so.
    if cz.get("state") not in ("verified", "none", "unchecked"):
        bad.append(f"cz.state {cz.get('state')!r}")
    if cz.get("state") == "verified":
        rid = cz.get("recordId") or ""
        if len(rid) != 36:
            bad.append(f"recordId must be a full 36-char uuid, got {len(rid)} chars")
    rej, est = d.get("reject"), d.get("est")
    if rej and est is not None:
        bad.append("reject set but est is not null")
    if not rej:
        if not (isinstance(est, list) and len(est) == 2):
            bad.append("est must be [low, high]")
        elif not (0 < est[0] < est[1] <= 100):
            bad.append(f"est {est} out of order or out of range")
        if not d.get("leanedOn"):
            bad.append("leanedOn is empty")
    if rej and not (rej.get("filter") or "").startswith("axis:"):
        bad.append("reject.filter must be an axis: id")
    if not d.get("sources"):
        bad.append("no sources — an unsourced claim about how a book opens is the "
                   "failure mode this step exists to avoid")
    # An INVENTED axis id is the quiet failure this whole dep mechanism exists to
    # prevent: /book-log bumps a counter when a named rule changes and greps the
    # estimates for that id, so a dep spelled `axis:story-density` when the table
    # says `axis:density` can never be found and the estimate is never revisited.
    # absorb used to register unknown ids silently, which made the breakage
    # invisible. Author and series ids are legitimately new; axes are not.
    known = set()
    try:
        known = set(json.load(io.open(REVS, encoding="utf-8"))["revs"])
    except OSError:
        pass
    seen = set(d.get("deps") or []) | set(d.get("leanedOn") or []) | set(d.get("risks") or [])
    for x in sorted(seen):
        if x.startswith("axis:") and known and x not in known:
            near = difflib.get_close_matches(x, [k for k in known if k.startswith("axis:")], 1)
            bad.append(f"unknown axis id {x!r}" + (f" — did you mean {near[0]!r}?" if near else
                                                  " — not in book-revs.json"))
    return bad


def cmd_absorb(outdir, force_low=False):
    files = sorted(p for p in glob.glob(os.path.join(outdir, "*.json")))
    if not files:
        sys.exit(f"no staged *.json in {outdir!r}")
    # Needles must include the batch being absorbed, or books staged together can
    # cite each other freely — six such references got through on 2026-08-26 because
    # the cache did not contain them yet.
    titles, ranges = _candidate_needles()
    for p in files:
        try:
            s = json.load(io.open(p, encoding="utf-8"))
        except ValueError:
            continue
        for t in (s.get("title"), s.get("czTitle")):
            t = deacc(t or "")
            if len(t) >= NEEDLE_MIN:
                titles.append(t)
    needles = (titles, ranges)
    cache = json.load(io.open(CACHE, encoding="utf-8"))
    media = json.load(io.open(MEDIA, encoding="utf-8"))
    revs = json.load(io.open(REVS, encoding="utf-8"))
    have = {b["key"] for b in cache["books"]}
    # A reject never lands in book-cache.json, so the `key already in cache` guard
    # below cannot see it and a second absorb of the same directory appended every
    # reject again - 14 duplicate rows on 2026-08-26. Reject rows are keyed by the
    # de-accented title, which is what rejected_titles() joins on.
    have_rej = set()
    try:
        for r in load_jsonl(REJECTS):
            have_rej.add(deacc(r.get("entity") or ""))
    except OSError:
        pass
    _, rejected_pairs, rejected_titles, rejected_authors, _rejseries = already_decided()
    est_rows, rej_rows, added, held, refused = [], [], [], [], []

    for p in files:
        d = json.load(io.open(p, encoding="utf-8"))
        bad = validate(d, needles)
        if bad:
            refused.append((os.path.basename(p), bad))
            continue
        if d.get("confidence") == "low" and not force_low:
            held.append(d["key"])
            continue
        if d["key"] in have:
            refused.append((os.path.basename(p), ["key already in book-cache.json"]))
            continue
        # A book already rejected must not quietly acquire an estimate. `zapomenuta-legie`
        # did on 2026-08-27: rejected for occult in one run, then exited C-low in the next
        # with the occult question deliberately unexamined, and ended up holding both.
        # Retracting a reject is a decision, not a side effect of a cheaper second look.
        if not d.get("reject"):
            ent = (deacc(d.get("czTitle") or d["title"]).strip().lower(), authorid(d["author"]))
            if ent in rejected_pairs:
                refused.append((os.path.basename(p),
                                ["already rejected in book-rejects.jsonl — retracting a "
                                 "reject has to be deliberate, so absorb will not do it"]))
                continue

        if d.get("reject"):
            ent = deacc(d.get("czTitle") or d["title"])
            if ent in have_rej:
                refused.append((os.path.basename(p), ["already in book-rejects.jsonl"]))
                continue
            have_rej.add(ent)
            rej_rows.append({"entity": deacc(d.get("czTitle") or d["title"]),
                             "key": d["key"],
                             "level": "title", "author": d["author"],
                             "filter": d["reject"]["filter"],
                             "why": deacc(d["reject"]["why"]), "at": TODAY,
                             "source": "promote-sonnet"})
            added.append((d["key"], "REJECT " + d["reject"]["filter"]))
            continue

        cz = dict(d["cz"])
        cz["checked"] = TODAY
        if cz.get("state") == "verified":
            cz["recordUrl"] = URL + cz["recordId"]
            cz["recordChecked"] = TODAY
            cz["publisherSource"] = "katalog"
        cz = {k: v for k, v in cz.items() if v not in (None, "")}
        b = {"key": d["key"], "title": d.get("title") or d["czTitle"],
             "author": d["author"], "cz": cz,
             # enAudio is deliberately untouched: out of scope for this pass.
             "enAudio": {"state": "unchecked"},
             "genre": d["genre"], "form": d["form"],
             "audience": d.get("audience") if d.get("audience") in AUDIENCE else "adult",
             "audienceSource": "hand" if d.get("audience") in AUDIENCE else "default"}
        if d.get("czTitle") and d["czTitle"] != b["title"]:
            b["czTitle"] = d["czTitle"]
        if d.get("series"):
            b["series"] = d["series"]
        if d.get("flags"):
            b["flags"] = d["flags"]
        cache["books"].append(b)

        aid = authorid(d["author"])
        dep = {k: 1 for k in MANDATORY}
        dep[aid] = 1
        for k in (d.get("deps") or []) + (d.get("leanedOn") or []) + (d.get("risks") or []):
            dep[k] = 1
        # Stamp the CURRENT rev so the estimate is not born stale, and register any
        # id the table has never seen.
        for k in list(dep):
            if k in revs["revs"]:
                dep[k] = revs["revs"][k]
            elif k.startswith(("author:", "series:")):
                revs["revs"][k] = 1          # a new author or series is expected
                dep[k] = 1
            else:
                raise SystemExit(f"refusing to register unknown axis id {k!r} for "
                                 f"{d['key']} — validate() should have caught this")
        label = deacc(d.get("czTitle") or d["title"])
        if d.get("title") and d.get("czTitle") and d["title"] != d["czTitle"]:
            label += f" ({deacc(d['title'])})"
        est_rows.append({"key": d["key"], "t": label, "est": d["est"],
                         "leanedOn": d["leanedOn"], "risks": d.get("risks") or [],
                         "at": TODAY, "why": deacc(d["why"]),
                         "deps": dict(sorted(dep.items()))})
        media.setdefault("media", {})[d["key"]] = {"blurb": d["blurb"]}
        added.append((d["key"], f"est {d['est']}"))

    json.dump(cache, io.open(CACHE, "w", encoding="utf-8", newline="\n"),
              ensure_ascii=False, indent=1)
    json.dump(media, io.open(MEDIA, "w", encoding="utf-8", newline="\n"),
              ensure_ascii=False, indent=1)
    json.dump(revs, io.open(REVS, "w", encoding="utf-8", newline="\n"),
              ensure_ascii=False, indent=1)
    with io.open(EST, "a", encoding="utf-8", newline="\n") as f:
        for r in est_rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    with io.open(REJECTS, "a", encoding="utf-8", newline="\n") as f:
        for r in rej_rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(f"absorbed {len(added)} | held (confidence:low) {len(held)} | "
          f"refused {len(refused)}")
    for k, v in added:
        print(f"   + {k:36s} {v}")
    for k in held:
        print(f"   ~ {k:36s} held — rerun with --force-low to take it anyway")
    for f, bad in refused:
        print(f"   ! {f}")
        for b in bad:
            print(f"       {b}")
    _spend_report(files)
    print("\nNext: python tools/fetch-library.py <today>   (covers + link check)")
    print("      python tools/crossrefs.py                (no candidate cross-refs)")
    print("      python tools/ai_rank.py seal             (mark them done)")


# Budgets from the exit ladder in promote-prompt.md. Reported, never enforced: by the
# time absorb runs the tokens are already spent, and refusing the file would throw
# away good work to punish an overspend the agent cannot now undo. What this buys is
# that the next run's overspend is a number instead of a suspicion - the 2026-08-26
# inversion (Gate B, the exit where the book is DISQUALIFIED, spent mean 5.11 sources
# against a budget of 2, more than Gate D's 4.53) was invisible until it was counted.
#
# Gate B is split by filter because the two hard filters are not the same kind of
# question. "Is the reader's satisfaction whodunnit" is answerable from a blurb and the
# three detective rejects of 2026-08-26 cost 3, 3 and 4 sources. "Is a rite performed
# on the page, and is there a mechanical account of it" is a claim about the text, and
# the six occult rejects cost 3, 6, 6, 6, 7 and 8. A flat budget of 2 would price the
# occult test below what it demonstrably takes, and a wrong reject is the one outcome
# the ladder calls unrecoverable.
# `B-infidelity` gets 2, the same as detective. The 2026-08-27 ruling made a premise-
# level affair an unconditional reject, so framing no longer enters the veto and there
# is no need to establish how the book ends - the test is prominence alone, and a blurb
# usually settles that. The first draft of the rule cost 3 for exactly that ending.
BUDGET = {"A": 0, "B-detective": 2, "B-infidelity": 2, "B-occult": 4,
          "B-sexual-content": 2, "B": 2, "C": 1, "D": 6}


def _spend_report(files):
    by = collections.defaultdict(list)
    for p in files:
        try:
            d = json.load(io.open(p, encoding="utf-8"))
        except (OSError, ValueError):
            continue
        ex = d.get("exitAt") or "?"
        gate = ex if ex in BUDGET else ex.split("-")[0]
        if gate == "B":
            f = ((d.get("reject") or {}).get("filter") or "").replace("axis:", "")
            if "B-" + f in BUDGET:
                gate = "B-" + f
        spent = len([u for u in (d.get("sources") or [])
                     if "katalog.mekvalmez.cz" not in u])
        by[gate].append(spent)
    if not by:
        return
    print("\nresearch spend, non-catalogue sources per book:")
    for g in sorted(by):
        v = sorted(by[g])
        b = BUDGET.get(g)
        over = sum(1 for x in v if b is not None and x > b)
        print(f"   gate {g:2s} n={len(v):3d}  mean {statistics.mean(v):4.2f}  "
              f"median {statistics.median(v):4.1f}  max {v[-1]:2d}  "
              f"budget {b if b is not None else '-'}"
              + (f"  OVER on {over}/{len(v)}" if over else ""))


# ----------------------------------------------------------------------- score
def cmd_score(outdir):
    """Compare staged estimates against the hand-derived ones they never saw."""
    truth = {r["key"]: r for r in load_jsonl(EST) if "key" in r and r.get("est")}
    rows = []
    for p in sorted(glob.glob(os.path.join(outdir, "*.json"))):
        d = json.load(io.open(p, encoding="utf-8"))
        t = truth.get(d.get("key"))
        if not t:
            continue
        rows.append((d["key"], t["est"], d.get("est"), d.get("reject"),
                     d.get("leanedOn") or [], t.get("leanedOn") or []))
    if not rows:
        sys.exit("no staged file matches a hand-derived estimate — was this a holdout run?")
    print(f"{len(rows)} holdout books scored blind\n")
    err, flips, leanmatch = [], 0, 0
    for k, tr, md, rej, ml, tl in rows:
        if rej or not md:
            print(f"  {k:34s} hand {tr}  model REJECTED ({(rej or {}).get('filter')})")
            flips += 1
            continue
        e = md[0] - tr[0]
        err.append(e)
        f = (tr[0] >= 68) != (md[0] >= 68)
        flips += f
        leanmatch += bool(set(ml) & set(tl))
        print(f"  {k:34s} hand {tr}  model {md}  low delta {e:+3d}"
              f"{'   <-- VERDICT FLIP' if f else ''}")
    if err:
        print(f"\nlow-end error: mean {statistics.mean(err):+.1f}, "
              f"median {statistics.median(err):+.1f}, "
              f"abs mean {statistics.mean([abs(x) for x in err]):.1f}, "
              f"max {max(err, key=abs):+d}")
        within = sum(1 for e in err if abs(e) <= 5)
        print(f"within 5 points: {within}/{len(err)} ({within / len(err) * 100:.0f}%)")
    print(f"propose/record verdict flips: {flips}/{len(rows)} "
          f"({flips / len(rows) * 100:.0f}%)  <- the number that decides usability")
    print(f"leanedOn shares an axis with the hand estimate: {leanmatch}/{len(err) or 1}")
    print("\nBoth recorded prediction failures came from leaning on the wrong axis, so a "
          "matching est with a different leanedOn is a warning, not a pass.")


if __name__ == "__main__":
    a = sys.argv[1:]
    g = lambda flag, dflt: int(sys.argv[sys.argv.index(flag) + 1]) if flag in sys.argv else dflt
    if not a:
        print(__doc__)
    elif a[0] == "queue":
        cmd_queue(a[1], g("--n", 10), g("--min-score", 4), "--include-unranked" in sys.argv)
    elif a[0] == "batch":
        cmd_batch(a[1], g("--per", 15), g("--n", 200), g("--min-score", 4),
                  g("--per-author", 15), g("--top", 0), "--include-unranked" in sys.argv,
                  "--unknown" in sys.argv)
    elif a[0] == "holdout":
        cmd_holdout(a[1], g("--n", 10))
    elif a[0] == "absorb":
        cmd_absorb(a[1], "--force-low" in sys.argv)
    elif a[0] == "score":
        cmd_score(a[1])
    else:
        print(__doc__)
