"""Cheap-model triage of the tier-1 queue, persisted so it is never repeated.

Why this exists: the free metadata scorer in rank.py plateaus at ~53% recall for
a 16%-of-corpus queue (see its _rankBacktest). A Haiku pass on the same holdout
hit 77% recall at a 24% queue with 75% precision. Measured 2026-08-26, 200 works,
47 of them known-good hidden blind among 153 random.

Persistence is the whole point. A verdict is stored against the sha256 of
tools/ai-rank-prompt.md; a work whose stored digest matches the current prompt is
NEVER re-sent. Edit the prompt and exactly the affected verdicts recompute.

    python tools/ai_rank.py batches <outdir> [--size 500] [--max 20]
    python tools/ai_rank.py merge <resultfile> [<resultfile> ...]
    python tools/ai_rank.py seal
    python tools/ai_rank.py dupes [--thresh 0.93]
    python tools/ai_rank.py status

`batches` writes pipe-delimited files for subagents and prints how many works are
still unjudged. `merge` folds `id|score|why` output back in, idempotently. `seal`
marks promoted works `done` so the no-repeat guarantee stops depending on the
title join in book-triage.jsonl — RUN IT AFTER EVERY PROMOTION. `dupes` reports
works that are probably the same book under two keys; it never merges them.

Known limit, measured 2026-08-26: a work is keyed on (title, author) as the
CATALOGUE spells them, so the guarantee is "one verdict per string pair", not "one
verdict per book". 20 exact duplicates and ~48 near-title pairs got two verdicts
each, and where the model saw the same book twice it disagreed with itself in 3 of
20 cases by a mean of 1.7 points — which is also the best available estimate of
single-verdict noise, and the reason the >=4 cutoff is soft at its boundary.
"""
import json, io, os, re, sys, glob, hashlib, collections, difflib, unicodedata

TRIAGE, STORE = "book-triage.jsonl", "book-ai-rank.jsonl"
ANNOT = "book-annotations.jsonl"
CATALOG = "book-catalog.jsonl"
PROMPT = os.path.join("tools", "ai-rank-prompt.md")
MODEL = "haiku-4.5"
# Batch lines are pipe-delimited and an annotation is free text, so the delimiter
# and the newline have to go. Trailing publisher puffery is cut too: the premise
# and the protagonist are in the first sentences and the p90 tail tripled the
# token cost of a run for nothing.
ANNOT_MAX = 420
# Controlled vocabulary, so it is short and repetitive across rows - unlike an
# annotation, where the tail is publisher puffery. 180 fits orig + heading + six
# keywords + series with room to spare.
FACTS_MAX = 180
# A work already at tier 2 has a real est range; re-triaging it is pure waste.
SKIP_NEXT = ("promoted",)
# Genre headings that ARE a verdict. Ruled by the reader 2026-08-28: MARC 655 is
# assigned by a librarian who held the book, so where it says `detektivni romany` one of
# his five hard filters is already answered and no model is paid to answer it again.
# A vetoed work is never sent to Haiku, has no rankable score if it already carries a
# verdict, and never reaches a promotion queue.
#
# THE GENRE HEADING ONLY, NEVER A SUBJECT KEYWORD. `gf` says what the book IS, `kw`
# says what it is ABOUT, and the same stems over `kw` take Jane Eyre, Dostoyevsky's
# Krotkaja, Cold Mountain and four more books above the 68 line.
#
# TWO STEMS ARE DELIBERATELY ABSENT AND BOTH WERE TRIED:
#   `milostn` - applied 2026-08-28 and REVERSED by the reader hours later. A romance
#     heading is not one of his five hard filters; a romance novel is graded low, not
#     excluded, which is what the [58, 68] band exists for. Reversal restored 10 shelf
#     books and 368 reject rows.
#   `thriller` - never applied: the filter is whodunnit, not tension, and it costs
#     Follett's `Nikdy` [70, 80] and `Kralovna mrtvol` [70, 80].
# Do not add either back without a ruling; both are one edit from looking reasonable.
HEADING_VETO = ((re.compile(r"detektiv|krimi"), "axis:detective"),
                (re.compile(r"erotick"), "axis:sexual-content"))
# Classes never sent to a model. Approved by the reader 2026-08-26 and MEASURED
# at a 0% false-drop rate against the 47-work known-good holdout, but only after
# three substring bugs were fixed first: "tor" matched Pistorius, "alpress"
# matched Talpress, and `mrtvo[lu]` classed a crematorium novel as detective.
# Before those fixes the same list lost 21% of the known-good works.
#
# Deliberately NOT here: romance-sentimental and rejected. Both still contain
# known-good false positives (5 and 3), so they keep costing model tokens until
# their classifiers are trustworthy. Cheap insurance against a silent loss.
# already-read and rejected were added 2026-08-26 AFTER the first full run, which
# exposed the cost of leaving them in: Haiku rewards canonicity and under-applies
# the exclusion list, so it returned 1984, Hobit, Enderova hra, seven Harry
# Potters, ten Discworlds and Dune as 4s and 5s. 155 of the 1,303 high scores -
# 12% - were by an author already read or already rejected. The model cannot be
# trusted to remember the log; a join can.
#
# romance-hi is included; romance-maybe deliberately is not. The reader declined a
# blanket romance drop 2026-08-26, and the split is what makes a partial drop
# defensible: hi = category imprint or title+commercial-house corroboration,
# maybe = a title regex firing alone, which is the case that misread Komensky.
# `childrens` was here until 2026-08-28 and the reader removed it: a children's book is
# graded, never vetoed, which is what the estimate step has said since 2026-08-26 (Hobbit
# 84, Little Prince 82, Narnia 67). Keeping the class in this tuple contradicted that at
# the only point where it was load-bearing - 6,834 works were dropped before any model
# saw them, 3,907 of them never ranked at all.
DROP_CLS = ("detective", "manga", "romance-hi", "already-read", "rejected",
            "edition-audio", "edition-ebook", "edition-foreign")


def digest():
    """Hash only what the model is actually sent — the text after the `---` rule.

    Hashing the whole file made every edit to the explanatory preamble invalidate
    all 200 stored verdicts, which is over-sensitive: rewording a comment about
    the prompt does not change the prompt. Only the body below the rule counts.
    """
    txt = io.open(PROMPT, encoding="utf-8").read()
    body = txt.split("\n---\n", 1)[-1].strip()
    return hashlib.sha256(body.encode()).hexdigest()[:12]


def norm(s):
    s = unicodedata.normalize("NFKD", s or "")
    s = "".join(c for c in s if not unicodedata.combining(c)).lower()
    return re.sub(r"[^a-z0-9]+", "-", s).strip("-")


def workkey(t, a):
    # '~' not '|': the key travels inside pipe-delimited batch files, and a key
    # containing the field delimiter made merge() parse only half of it, so the
    # no-repeat filter never matched and judged works were re-emitted.
    return f"{norm(t)[:48]}~{norm(a)[:32]}"


def load_works():
    """Collapse triage records into works, best-evidence record per work."""
    rows = [json.loads(l) for l in io.open(TRIAGE, encoding="utf-8")][1:]
    works = {}
    for r in rows:
        k = workkey(r["t"], r["a"])
        w = works.setdefault(k, {"k": k, "t": r["t"], "a": r["a"], "p": r["p"],
                                 "y": r["y"], "rank": -999, "skip": False,
                                 "cls": r["cls"], "clsAll": set()})
        w["clsAll"].add(r["cls"])
        w["skip"] |= r.get("next") in SKIP_NEXT
        if r.get("rank") is not None and r["rank"] > w["rank"]:
            w.update(rank=r["rank"], p=r["p"], y=r["y"], cls=r["cls"])
    # A work is dropped only if EVERY edition of it is droppable. One print
    # edition on a good imprint rescues a work whose other record is an audiobook.
    for w in works.values():
        w["skip"] |= bool(w["clsAll"]) and all(c in DROP_CLS for c in w["clsAll"])
    return works


def wants_annotation():
    """Only append the annotation when the live prompt actually asks for it.

    v2's body says "You get only title, author, publisher, year", and appending a
    sixth field it never mentions would both waste tokens and contradict the
    contract. The check is on the body so that editing the preamble cannot silently
    change what the model is sent.
    """
    body = io.open(PROMPT, encoding="utf-8").read().split("\n---\n", 1)[-1]
    return "annotation" in body.lower()


def load_annots():
    """Catalogue Anotace per work. Absent is normal — coverage is 91%, not 100%."""
    if not os.path.exists(ANNOT) or not wants_annotation():
        return {}
    out = {}
    for l in io.open(ANNOT, encoding="utf-8"):
        if not l.strip():
            continue
        r = json.loads(l)
        if "_readme" in r:
            continue
        a = re.sub(r"[|\r\n\t]+", " ", r.get("a") or "").strip()
        if a:
            out[r["k"]] = a[:ANNOT_MAX]
    return out


def wants_facts():
    """Only append the catalogue facts when the live prompt actually asks for them.

    Same gate as wants_annotation(), and for the same reason: the digest covers the
    prompt body, so a prompt that never mentions the facts must keep producing
    byte-identical batch lines or every stored verdict silently means something else.
    """
    body = io.open(PROMPT, encoding="utf-8").read().split("\n---\n", 1)[-1]
    return "catalogue facts" in body.lower()


def load_facts():
    """MARC 653/655/490 and the original title, per work, from book-catalog.jsonl.

    These were fetched in the same bulk responses as the annotations on 2026-08-27 and
    then never read by anything: cmd_batches sent title, author, publisher, year and
    annotation only. Measured over the 10,595 works the model failed to recognise —
    genre/form heading 57%, subject keywords 52%, series 37%, original title 14%, and
    69% carry at least one. `orig` is the field that can actually move `rec` 0 -> 1,
    because a Czech title is opaque to the model where the English one is not.
    """
    if not os.path.exists(CATALOG) or not wants_facts():
        return {}
    out = {}
    for l in io.open(CATALOG, encoding="utf-8"):
        if not l.strip():
            continue
        r = json.loads(l)
        if "_readme" in r:
            continue
        bits = []
        if r.get("orig"):
            bits.append("orig=" + str(r["orig"]))
        if r.get("gf"):
            bits.append("gf=" + ", ".join(r["gf"][:3]))
        if r.get("kw"):
            bits.append("kw=" + ", ".join(r["kw"][:6]))
        if r.get("series"):
            bits.append("series=" + str(r["series"]))
        if bits:
            out[r["k"]] = re.sub(r"[|\r\n\t]+", " ", "; ".join(bits)).strip()[:FACTS_MAX]
    return out


def load_headings():
    """{work key: [MARC genre/form headings]}, straight from the catalogue.

    Separate from `load_facts()` on purpose: that one is gated on whether the live
    prompt mentions facts and returns a flattened string for a batch line, whereas the
    veto must work whatever the prompt says and needs the headings apart from the
    keywords.
    """
    out = {}
    if not os.path.exists(CATALOG):
        return out
    for l in io.open(CATALOG, encoding="utf-8"):
        if not l.strip():
            continue
        r = json.loads(l)
        if "_readme" in r or not r.get("gf"):
            continue
        out[r["k"]] = [str(x) for x in r["gf"]]
    return out


def heading_veto(gf):
    """The axis a genre heading already decides, or None. `gf` is a list or a string."""
    h = " ".join(gf).lower() if isinstance(gf, (list, tuple)) else (gf or "").lower()
    return next((axis for rx, axis in HEADING_VETO if rx.search(h)), None)


def load_store():
    if not os.path.exists(STORE):
        return {}
    out = {}
    for l in io.open(STORE, encoding="utf-8"):
        if not l.strip():
            continue
        r = json.loads(l)
        if "_readme" in r:
            continue
        out[r["k"]] = r
    return out


def ranked(r):
    """The verdict's score, or None when the model did not recognise the work.

    Ruled by the reader 2026-08-27: **an unrecognised work has no score, it is not a 3.**
    The `rec` flag has been stored since v3 but every consumer read `s` alone, so
    "I do not know this book" and "I know it and it is middling" both presented as 3.

    Measured on the 100 books promoted from the score-4 bucket the same day: a
    RECOGNISED 4 reached the 68 propose line 7 times in 25 (28%), an unrecognised 4
    6 times in 67 (9%) - a 3.1x difference, Fisher exact two-tailed p = 0.038, and
    rejects ran 4% against 12%. So the conflation was costing real tokens: 73 of those
    100 books were unrecognised.

    Deliberately NOT fixed in the prompt. Making the model emit no score for rec=0 would
    change tools/ai-rank-prompt.md, hence its digest, hence re-send all 12,382 verdicts
    for ~1.3M tokens - to recover information already sitting in the file. The defect is
    in how `s` was read, so it is fixed where `s` is read.

    `dissent` is stamped by `ai_rank.py consensus` when two independent gradings of the
    same work disagreed about whether it clears the `>=4` line. Measured 2026-08-28 over
    7,343 twice-graded works: Cohen's kappa on that decision was +0.11, barely above
    chance, and only 20% of the first run's queue survived the second. A score two
    graders cannot reproduce is not a score, so it is withheld exactly as an
    unrecognised one is - the raw `s` stays on the row and stays readable.

    `veto` is stamped by `ai_rank.py veto` from the catalogue genre heading and outranks
    the score for the same reason: a librarian's classification answers the filter, so
    the model's plausibility is not a number anyone should act on. It is written onto the
    row rather than applied here from the catalogue because a downgrade has to be
    visible in the file - an invisible one is a score that silently means two things.
    """
    if r.get("veto") or r.get("dissent"):
        return None
    return None if not r.get("rec") else r.get("s")


def state(r, annots):
    """`known` / `premise` / `blind` — what the verdict was actually made of.

    Refined 2026-08-27 after the reader asked the right question: if the model does not
    know the book, is it not judging from the annotation? It is. `rec: 0` means no prior
    knowledge of that WORK - no reviews, no reputation - not that the model had nothing.
    The annotation is in the input and is what the score is built from.

    So the three states measure different instruments, not different amounts of the same
    one, and lumping the last two together was too blunt:

      known    the model has read *about* the book, so it can weigh what a blurb omits
      premise  a judgement of the PREMISE from publisher copy, which per
               book-annotations.jsonl's own `_isnot` cannot carry opening structure,
               occult enacted on the page, crudeness of sexual treatment, or the idea
               the book leaves behind - three of the six hard filters and the strongest
               graded axis
      blind    title, author, publisher, year. Nothing. This is the reader's NaN.

    Measured over the 100 books promoted from score 4 on 2026-08-27: known reached the 68
    floor 28% of the time (n=26), premise-only 10% (n=71), blind 0 of 2. **That gap is
    NOT purely signal quality** - a book Haiku recognises is a book famous enough to be
    widely reviewed, which is better on average by any measure, so population and
    information are confounded and this data cannot separate them. There is also no
    random-sample baseline yet, so 10% is not yet known to be above or below chance.
    """
    if r.get("rec"):
        return "known"
    return "premise" if annots.get(r["k"]) else "blind"


def save_store(store):
    hdr = {
        "_readme": "Persisted cheap-model triage verdicts, one per WORK. Written by "
                   "tools/ai_rank.py. `s` is 1-5 plausibility - is this worth expensive "
                   "investigation - and is NOT a predicted reader score; "
                   "book-estimates.jsonl owns those. Never show `s` as a prediction.",
        "schema": 1,
        "_pd": "First 12 hex of sha256(tools/ai-rank-prompt.md). A work whose stored `pd` "
               "equals the current digest is never re-sent to a model. This is the "
               "no-repeat guarantee: change the prompt and only then does work recur.",
        "_measured": "Pilot 2026-08-26, 200 works with 47 known-good hidden blind among "
                     "153 random. Cutoff >=4: recall 77%, queue 24% of corpus, precision "
                     "75%. Cutoff >=5: recall 40%, precision 83%. Mean score 4.13 for "
                     "known-good vs 2.44 for random. The single apparent false negative "
                     "was a title collision (Nora Roberts' Promena vs Kafka's), not a "
                     "model error - so there were no genuine misses at <=2.",
        "_unranked": "READ THIS BEFORE READING ANY SCORE. `rec: 0` means the model did not "
                     "recognise the work, and ruled by the reader 2026-08-27, such a verdict "
                     "HAS NO SCORE - it is unranked, not a 3. `s` is still stored because it "
                     "is the model's raw output, but tools/ai_rank.py ranked() returns None "
                     "for it and promote.py will not queue it on a --min-score cutoff without "
                     "--include-unranked. Measured on the 100 books promoted from the score-4 "
                     "bucket on 2026-08-27: a RECOGNISED 4 reached the 68 propose line 7 times "
                     "in 25 (28%), an unrecognised 4 six times in 67 (9%) - 3.1x, Fisher exact "
                     "two-tailed p = 0.038, rejects 4% against 12%.",
        "_bucket3": "The earlier note here was WRONG and it misled a reading of this file on "
                    "2026-08-27. It said a v3+ 3 means the model could see the book and could "
                    "not call it. The data says the opposite: 10,425 of the 10,821 verdicts at "
                    "3 carry rec=0, so the bucket is 96% unrecognised works. UNDER v2 a 3 also "
                    "meant unrecognised and 58% of verdicts landed there. So a 3 has never "
                    "been a judgement in either prompt - check `rec` first, always.",
        "_rec": "v3 onward. 1 = the model already knew the WORK, 0 = it did not and was "
                "reasoning from the catalogue annotation. Recognising the author, the series "
                "or the genre is not recognising the work. A 0 with a good score is a book "
                "to look up; a 0 with a low score is cheap to drop.",
        "_idea": "v3 only. 1 = the model could name what the book leaves a reader thinking "
                 "about, in a phrase, and said it in `w`. This exists to ORDER the >=4 "
                 "bucket, which had 1,024 works in it and no tiebreak but a metadata score "
                 "that backtests at median top 12.7%. A binary flag was chosen over a longer "
                 "scale because it is auditable - name the idea - and a 7-against-9 is not.",
        "_done": "Set by `seal` when the work reaches tier 2. A fact about the work rather "
                 "than about the verdict, so it is NOT cleared by a prompt change and "
                 "survives a re-merge.",
        "_dissent": "Written by `ai_rank.py consensus`. 1 = two independent gradings of "
                    "this work disagreed about whether it clears the >=4 queue line, so "
                    "ranked() returns None for it whatever `s` says. Measured 2026-08-28 "
                    "over 7,343 twice-graded works: Cohen's kappa on that decision was "
                    "+0.11 and only 20% of the first run's queue survived the second. `s1` "
                    "carries the first run's score beside it; neither is deleted.",
        "_veto": "Written by `ai_rank.py veto` from the catalogue's MARC genre heading, "
                 "ruled by the reader 2026-08-28: `detektivni|krimi` -> axis:detective and "
                 "`eroticke` -> axis:sexual-content. `milostne` was in this list for a few "
                 "hours the same day and the reader reversed it - romance is graded low, "
                 "not excluded - so a stray axis:romance veto is a bug, not history. A "
                 "librarian who held the book already answered the filter, so ranked() "
                 "returns None for a vetoed row whatever its score - it is a DOWNGRADE of "
                 "an existing verdict, not a deletion, and `s` is left as the model wrote "
                 "it. The genre heading only; the subject keyword takes Jane Eyre.",
    }
    with io.open(STORE, "w", encoding="utf-8", newline="\n") as f:
        f.write(json.dumps(hdr, ensure_ascii=False) + "\n")
        for r in sorted(store.values(), key=lambda r: (-r.get("s", 0), r["k"])):
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


KID_WHY = re.compile(r"child|kid|juvenil|picture|early.read|pohadk|fairy|pro deti|"
                     r"young read", re.I)


def cmd_restamp(write=False):
    """Carry verdicts across a prompt edit that cannot have changed them.

    `batches` re-sends every work whose stored `pd` differs from the current digest.
    That is the no-repeat guarantee and it is right by default - a changed prompt is a
    changed question, and the alternative is stale verdicts nobody can find. This is the
    deliberate exception, and it is only defensible for an edit scoped to ONE rule.

    WHAT IT IMPLEMENTS TODAY: the 2026-08-28 removal of the children's exclusion. A
    stored verdict can only have been affected if the work is classed `childrens` or its
    `why` mentions children's at all; every other verdict answered a question the edit
    did not touch, so it is stamped with the new digest and not re-bought. That takes the
    re-rank from 16,633 works to ~4,700.

    **Edit this rule when the next scoped change comes, or delete the command.** A
    restamp whose stated reason no longer matches the prompt edit is a silent freeze of
    stale judgements, which is the one failure this file's digest mechanism exists to
    prevent.
    """
    pd, works, store = digest(), load_works(), load_store()
    keep, affected, already = 0, 0, 0
    for k, r in store.items():
        if r.get("pd") == pd:
            already += 1
            continue
        w = works.get(k)
        kid = (w and "childrens" in (w.get("clsAll") or [])) or KID_WHY.search(r.get("w") or "")
        if kid:
            affected += 1
            continue
        r["pd"] = pd
        keep += 1
    print(f"digest {pd} | {len(store)} verdicts\n"
          f"  {already} already current\n"
          f"  {affected} touched by the children's rule - left stale, so they re-rank\n"
          f"  {keep} carried forward" + ("" if write else "  (dry run)"))
    if not write:
        print("\nRerun with --write. Then `batches` queues only the affected works "
              "plus everything never ranked.")
        return
    save_store(store)
    print(f"stamped {keep} rows in {STORE}")


def cmd_consensus(run1dir, write=False):
    """Withhold the score where two independent gradings disagreed at the `>=4` line.

    Only touches works present in `run1dir`, which holds the FIRST grading of the
    re-ranked cohort; the store already holds the second. A work both runs put at `>=4`
    keeps its score and is queueable. Everything else in that cohort gets `dissent: 1`
    and `s1` (the first run's score, for audit) and is unqueueable until something better
    than a coin-flip decides it.

    Carried-forward verdicts are untouched: they were graded once, by a prompt this test
    did not run, and pretending otherwise would hide the difference.
    """
    store = load_store()
    first = {}
    for path in glob.glob(os.path.join(run1dir, "*.txt")):
        for line in io.open(path, encoding="utf-8"):
            q = line.strip().split("|")
            if len(q) >= 4 and "~" in q[0] and q[2].strip().isdigit():
                first[q[0].strip()] = int(q[2])
    agree = dissent = missing = 0
    for k, s1 in first.items():
        r = store.get(k)
        if not r or "s" not in r:
            missing += 1
            continue
        if s1 >= 4 and r["s"] >= 4:
            r.pop("dissent", None)
            agree += 1
        else:
            r["dissent"] = 1
            dissent += 1
        r["s1"] = s1
    print(f"{len(first)} works graded twice | both runs >=4: {agree} | "
          f"withheld as dissent: {dissent} | not in store: {missing}")
    if not write:
        print("dry run. Rerun with --write")
        return
    save_store(store)
    print(f"stamped {agree + dissent} rows in {STORE}")


def cmd_veto(write=False):
    """Stamp `veto` on every stored verdict whose genre heading already decides it.

    Downgrades what has already been screened; `cmd_batches` keeps the same works from
    ever being screened again. Both are needed - one run of the ranker predates the rule.
    """
    works, store, hdgs = load_works(), load_store(), load_headings()
    hit, already, byaxis = [], 0, collections.Counter()
    for k, r in store.items():
        axis = heading_veto(hdgs.get(k, []))
        if not axis:
            continue
        if r.get("veto") == axis:
            already += 1
            continue
        hit.append((k, r, axis))
        byaxis[axis] += 1
    lost = sum(1 for k, r, a in hit if r.get("rec") and r.get("s", 0) >= 4)
    print(f"{len(store)} verdicts | {already} already vetoed | {len(hit)} to downgrade")
    print("   " + ", ".join(f"{v} {k}" for k, v in byaxis.most_common()))
    print(f"   of those, {lost} were recognised works scoring 4+ - the ones a promotion "
          f"queue could still have reached")
    if not write:
        print("dry run. Rerun with --write")
        return
    for k, r, axis in hit:
        r["veto"] = axis
    save_store(store)
    print(f"stamped {len(hit)} rows in {STORE}")


def cmd_seal():
    """Stamp `done` on every work that reached tier 2, so the store says so itself.

    Before this existed, "already promoted" lived ONLY in book-triage.jsonl's `next`
    field, which is derived from a title-string join against book-cache.json. That
    made the join a single point of failure for the whole no-repeat guarantee, and it
    failed three separate times on 2026-08-26 (exact-string casing, a work
    re-published under another Czech title, and a title-level reject nothing read).
    book-triage.jsonl is also regenerable only from the temp pulls, which do not
    survive a session — losing it re-exposed 113 promoted books to the next model run.

    `done` is a fact about the work, not about the prompt, so it is deliberately NOT
    invalidated by a digest change. Run this after every promotion.
    """
    works, store = load_works(), load_store()
    try:
        cache = json.load(io.open("book-cache.json", encoding="utf-8"))["books"]
    except OSError:
        sys.exit("book-cache.json not readable — nothing to seal against")
    bykey = {}
    for b in cache:
        for t in [b.get("czTitle") or b.get("title")] + (b.get("czTitleAliases") or []):
            bykey[norm(t)] = b["key"]

    sealed = created = 0
    for k, w in works.items():
        ck = bykey.get(norm(w["t"]))
        if not ck:
            continue
        r = store.get(k)
        if r is None:
            # A tier-2 work no model ever scored. It still needs the marker, or a
            # prompt change would queue it as unjudged. Deliberately no `s`: writing
            # a 0 there put fake scores into the distribution and made the dupes
            # report show Siddhartha as "(0) ~ (5), disagrees".
            store[k] = {"k": k, "w": "tier-2, never model-scored", "m": "-",
                        "pd": "-", "at": os.environ.get("BOOK_TODAY", "2026-08-26"),
                        "done": ck}
            created += 1
        elif r.get("done") != ck:
            r["done"] = ck
            sealed += 1
    save_store(store)
    print(f"sealed {sealed} existing verdicts, created {created} marker rows | "
          f"store now {len(store)}, of which "
          f"{sum(1 for r in store.values() if r.get('done'))} done")


def _volnum(t):
    """Volume markers, so two volumes of a series are not reported as one book."""
    return re.findall(r"\b(\d+|i{1,3}v?|vi{0,3}|ix|xi{0,3})\b", t)


def cmd_dupes(thresh=0.93):
    """Report works that are probably the same book under two keys.

    REPORTS, never merges. The naive merge is wrong: Letopisy kralovske komory V and
    VI are 96% similar and are different books, as are Rekni ano vevodovi and Rekni ne
    vevodovi. A human decides; this only makes the candidates visible.

    Pairs whose only difference is a volume number are suppressed. Without that the
    output was 62 rows of which ~47 were Egyptanky 1-7, Toulky ceskou minulosti 6-8
    and Korist a zold 1395-1397 — series volumes, correctly separate works, drowning
    the 15 real duplicates.
    """
    works, store = load_works(), load_store()
    # Only live, scored works: a pair that is already sealed or class-dropped costs
    # nothing to leave duplicated, and including them buried the actionable rows.
    judged = {k: w for k, w in works.items()
              if k in store and "s" in store[k] and not store[k].get("done")
              and not w["skip"]}
    by_sur = collections.defaultdict(list)
    for k, w in judged.items():
        n = norm(w["a"]).split("-")
        by_sur[re.sub(r"(ova|ove|ovi)$", "", n[-1]) if n else ""].append(k)
    out = []
    for sur, ks in by_sur.items():
        if not sur or len(ks) < 2 or len(ks) > 60:
            continue
        for i in range(len(ks)):
            for j in range(i + 1, len(ks)):
                a, b = norm(works[ks[i]]["t"]), norm(works[ks[j]]["t"])
                if _volnum(a) != _volnum(b):
                    continue
                r = difflib.SequenceMatcher(None, a, b).ratio()
                if r >= thresh:
                    out.append((r, sur, a, store[ks[i]]["s"], b, store[ks[j]]["s"]))
    out.sort(reverse=True)
    dis = [x for x in out if x[3] != x[5]]
    print(f"{len(out)} candidate duplicate pairs at >={thresh:.0%} title similarity; "
          f"{len(dis)} of them scored DIFFERENTLY")
    for r, sur, a, s1, b, s2 in out:
        mark = "  <-- disagrees" if s1 != s2 else ""
        print(f"  {r:.2f} {sur:14s} {a[:38]:38s}({s1}) ~ {b[:38]:38s}({s2}){mark}")


def cmd_batches(outdir, size=500, mx=20):
    pd, works, store, ann = digest(), load_works(), load_store(), load_annots()
    fx, hdgs = load_facts(), load_headings()
    # `done` is checked as well as `skip`: skip comes from book-triage.jsonl and is
    # only as good as its title join, `done` is recorded on the verdict itself.
    # A heading veto is checked here rather than only at promotion time because this is
    # where the money is: sending a book the catalogue already calls a detective novel
    # buys a verdict nothing may act on.
    vetoed = 0
    todo = []
    for k, w in works.items():
        if w["skip"] or store.get(k, {}).get("done") or store.get(k, {}).get("pd") == pd:
            continue
        if heading_veto(hdgs.get(k, [])):
            vetoed += 1
            continue
        todo.append(w)
    todo.sort(key=lambda w: -w["rank"])          # best-first, so a partial run still helps
    os.makedirs(outdir, exist_ok=True)
    n = withann = withfx = 0
    for i in range(0, min(len(todo), size * mx), size):
        chunk = todo[i:i + size]
        p = os.path.join(outdir, f"airank_{i // size:03d}.txt")
        with io.open(p, "w", encoding="utf-8", newline="\n") as f:
            for w in chunk:
                a = ann.get(w["k"], "")
                withann += bool(a)
                if fx:
                    g = fx.get(w["k"], "")
                    withfx += bool(g)
                    f.write(f"{w['k']}|{w['t']}|{w['a']}|{w['p']}|{w['y']}|{a}|{g}\n")
                else:
                    f.write(f"{w['k']}|{w['t']}|{w['a']}|{w['p']}|{w['y']}|{a}\n")
        n += 1
    emitted = min(len(todo), size * mx)
    print(f"digest {pd} | works {len(works)} | unjudged {len(todo)} | "
          f"wrote {n} batches of {size}")
    print(f"  heading-vetoed, never sent: {vetoed}")
    print(f"annotations available on {withann}/{emitted} emitted rows "
          f"({withann / max(1, emitted) * 100:.0f}%) | store has {len(ann)}")
    if fx:
        print(f"catalogue facts on {withfx}/{emitted} emitted rows "
              f"({withfx / max(1, emitted) * 100:.0f}%) | store has {len(fx)}")
    else:
        print("catalogue facts NOT sent — the live prompt does not mention them")
    print(f"  -> {outdir}")
    return n


def cmd_merge(paths):
    """Fold the live prompt's output back in, accepting every shape ever emitted:
    v4's `id|rec|score|why`, v3's `id|rec|idea|score|why`, and v2's `id|score|why`,
    so the 11,602 verdicts written before any flag existed merge unchanged.

    The two-digit case has to be tested BEFORE the fallback that reads the last
    digit: v4 lines have mid == [rec, score], which the fallback parses to the right
    score and then silently throws `rec` away — the one field v4 exists to add."""
    pd, store = digest(), load_store()
    added = skipped = 0
    for p in paths:
        for line in io.open(p, encoding="utf-8"):
            line = line.strip()
            if not line or "|" not in line:
                continue
            parts = line.split("|")
            if len(parts) < 3:
                continue
            k, why = parts[0], parts[-1]
            if "~" not in k:          # malformed key — refuse rather than corrupt the store
                skipped += 1
                continue
            mid = [x.strip() for x in parts[1:-1]]
            rec = idea = None
            if len(mid) >= 3 and all(x.isdigit() for x in mid[:3]):
                rec, idea, s = int(mid[0]), int(mid[1]), mid[2]
            elif len(mid) == 2 and all(x.isdigit() for x in mid) and int(mid[0]) in (0, 1):
                rec, s = int(mid[0]), mid[1]          # v4: id|rec|score|why
            elif mid and mid[-1].isdigit():
                s = mid[-1]
            else:
                skipped += 1
                continue
            if not s.isdigit() or not 1 <= int(s) <= 5 or rec not in (None, 0, 1) \
                    or idea not in (None, 0, 1):
                skipped += 1
                continue
            row = {"k": k, "s": int(s), "w": why[:48], "m": MODEL, "pd": pd,
                   "at": os.environ.get("BOOK_TODAY", "2026-08-26")}
            if rec is not None:
                row["rec"] = rec
            # v4 has no idea flag — measured useless in v3 — so don't write a null one.
            if idea is not None:
                row["idea"] = idea
            # `done` is a fact about the work, not about this verdict, so it survives.
            if store.get(k, {}).get("done"):
                row["done"] = store[k]["done"]
            store[k] = row
            added += 1
    save_store(store)
    print(f"merged {added} verdicts ({skipped} unparseable) | store now {len(store)}")
    flagged = [r for r in store.values() if "rec" in r]
    if flagged:
        print(f"  with flags: {len(flagged)} | recognised {sum(r['rec'] for r in flagged)} "
              f"| nameable idea {sum(r.get('idea', 0) for r in flagged)}")


def cmd_status():
    pd, works, store = digest(), load_works(), load_store()
    fresh = {k: r for k, r in store.items() if r.get("pd") == pd}
    done = {k for k, r in store.items() if r.get("done")}
    live = [w for k, w in works.items() if not w["skip"] and k not in done]
    print(f"prompt digest   {pd}")
    print(f"works           {len(works)}  ({len(live)} neither tier-2 nor sealed)")
    print(f"judged (fresh)  {len(fresh)}   stale/other-prompt {len(store) - len(fresh)}")
    print(f"sealed done     {len(done)}   (promoted; never re-sent even on a new prompt)")
    print(f"remaining       {sum(1 for w in live if store.get(w['k'], {}).get('pd') != pd)}")
    unsealed = [r for r in fresh.values() if "s" in r and not r.get("done")]
    d = collections.Counter(ranked(r) for r in unsealed)
    raw = collections.Counter(r["s"] for r in unsealed if not r.get("rec"))
    for s in (5, 4, 3, 2, 1):
        print(f"   score {s}: {d[s]}   (excludes sealed)")
    print(f"   UNRANKED: {d[None]}   the model did not recognise the work, so it has no "
          f"score at all")
    print(f"      what those would have counted as: "
          + ", ".join(f"{s}->{raw[s]}" for s in (5, 4, 3, 2, 1) if raw[s]))


if __name__ == "__main__":
    a = sys.argv[1:]
    if not a or a[0] == "status":
        cmd_status()
    elif a[0] == "batches":
        size = int(a[a.index("--size") + 1]) if "--size" in a else 500
        mx = int(a[a.index("--max") + 1]) if "--max" in a else 20
        cmd_batches(a[1], size, mx)
    elif a[0] == "merge":
        cmd_merge([x for x in a[1:] if not x.startswith("--")])
    elif a[0] == "consensus":
        cmd_consensus(a[1], "--write" in a)
    elif a[0] == "restamp":
        cmd_restamp("--write" in a)
    elif a[0] == "veto":
        cmd_veto("--write" in a)
    elif a[0] == "seal":
        cmd_seal()
    elif a[0] == "dupes":
        cmd_dupes(float(a[a.index("--thresh") + 1]) if "--thresh" in a else 0.93)
    else:
        print(__doc__)
