---
name: book-screen
description: "Screen new books into the shelf database: sweep the library catalogue for unconsidered titles, verify access routes, derive a first predicted score, and record rejections with the filter that killed them. Use when the user asks to find new books, screen a category or author, refresh access links, or fill gaps in the database. Also use for '/book-screen'."
allowed-tools:
  - Read
  - Edit
  - Write
  - Grep
  - Bash
---

# Book screen — put new books into the database

```
ORIENT -> DISCOVER -> ELIGIBILITY -> ACCESS -> ESTIMATE -> MEDIA -> RECORD
```

This skill owns *discovery*. `/book-log` owns judgements and recomputes
estimates when a rule moves; `/book-suggest` only picks from what is already
recorded; the viewer app (`index.html`) only displays it. **Every book the
reader can see came through here.**

## Two tiers — triage everything, promote what survives

**Every record you pull gets a row. No exceptions.** Before 2026-08-26 a sweep
could pull 16,687 records, review a few hundred authors by name and record 67
titles; the other 16,620 evaporated with the scratch directory, so the next run
paid to pull and re-review them from scratch.

| | Tier 1 — `book-triage.jsonl` | Tier 2 — cache + estimates + media |
|---|---|---|
| Unit | every pulled record | a title worth a real opinion |
| Cost | mechanical, thousands per run | expensive, a handful per run |
| Judgement | **none** — regex on title, author, publisher | access verified, worldbuilding verdict, `est` range |
| Confidence | `conf: auto` | `deps` / `leanedOn` / `risks` |
| Score | a **band** (`X` / `?` / `A?`) | a range, e.g. `[76, 86]` |
| Reversible | yes, freely | only by `/book-log` |

Write tier 1 with `python tools/triage.py <scratchdir>` — idempotent, rewrites
the file wholesale, and joins against `book-rejects.jsonl` so an author already
killed at author or series level is classed `rejected` instead of re-entering the
queue.

**`triage.py` is destructive on any run that is not a full re-pull, and its guard
does not catch that** (found 2026-08-27). It rebuilds `book-triage.jsonl` from
*only* the slice files present in the scratch dir, and the scratch dir does not
survive a session — so running it after a new one-slice sweep replaces 16,564 rows
from six earlier slices with the few thousand from yours. The empty-write guard
added on 2026-08-26 fires only when it reads *nothing*; one slice present is not
empty, so it writes happily. **So: run it only when you have just re-pulled every
slice in `SLICES`. Otherwise append your rows** — load the file, keep the header
and existing rows, dedupe new ones on `(t, a, y)`, and give them a new `src`. That
is what the 2026-08-27 kids-heading sweep did (6,174 appended, 605 already
present), and it is the only safe pattern for an incremental sweep.

**Author strings from MARC are inverted, and every join in `triage.py` assumed
they were not** (fixed 2026-08-27). `surname()` took the last token of the name,
which is right for `responsibilityStatement` ("Rick Riordan") and turns every
authority heading into a *first* name ("Riordan, Rick" → `rick`). A slice built
from MARC field 100-a therefore joined against nothing: `read_authors()`,
`rejected_authors()` and `known_authors()` all silently missed, and the 2026-08-27
kids slice carried 16 already-read rows where it should have had 97. The cost
landed downstream — already-read books reached a model pass, and **all five of its
top scores were books already in the log.** `surname()` now splits on the comma
when there is one, which is unambiguous because natural order never contains one.
**Whenever you build a slice from a new field, check one known-read author's
classification before spending anything on it** — one grep would have caught this.

**A new slice may need its own band logic, because `classify()` encodes the
default queue policy rather than the truth.** Its `childrens` class returns band
`X`, which is right when children's books are being kept *out* of the queue and
exactly wrong when they are the target — the 2026-08-27 screen would have
auto-dropped its entire pool. When a sweep deliberately targets an auto-dropped
class, set the band from the sweep's own filter and record what it means; `conf`
stays `auto` either way.

**A tier-1 `drop` is not a reject.** It means *not pursued, low confidence,
revisit on request*. Only `book-rejects.jsonl` kills a title, and only by naming
the axis. This distinction is what lets triage be cheap: it never has to justify
itself, so it can be wrong without silently excluding anything.

**Never quote a tier-1 band as a prediction.** `A?` means "a regex thought this
might be worth twenty minutes", nothing more.

### Tier 1.5 — cheap-model ranking, persisted

Between the free metadata scorer and a real estimate sits a Haiku pass. It exists
because the free scorer is measurably not good enough: `tools/rank.py` plateaus at
**53 % recall for a 16 %-of-corpus queue**, and on the same blind holdout Haiku hit
**77 % recall at a 24 % queue with 75 % precision** (47 known-good works hidden
among 153 random, 2026-08-26). Mean score 4.13 for known-good against 2.44 for
random.

```
python tools/fetch-annotations.py <scratchdir>       # FIRST: the catalogue's own summaries
python tools/ai_rank.py status                       # what is judged, what remains
python tools/ai_rank.py batches <outdir> --size 500 --max 4
#   -> spawn one Haiku subagent per batch file; each reads tools/ai-rank-prompt.md
python tools/ai_rank.py merge <outdir>/*.txt
python tools/ai_rank.py seal                         # AFTER promoting: mark works done
python tools/ai_rank.py dupes                        # same book under two keys?
```

**Give the model the catalogue's own summary — it was guessing for no reason.**
Under v2 the batch line was `title | author | publisher | year` and **58 % of all
verdicts came back `3`, meaning "I do not know this book"**, while a real Czech
plot summary sat unused in MARC field 520 of the same record. Measured 2026-08-26:
the **bulk search endpoint returns it** inside `detailTableRows`, so the whole
corpus costs ~253 requests instead of ~15,000; coverage is **91 %**; length is
median 386 chars, so ~96 tokens. `tools/fetch-annotations.py` re-sweeps the exact
queries the pulls recorded, so the join cannot drift, and truncates to 500 chars
because the premise and the protagonist are in the first sentences and the p90
tail is marketing.

**An annotation is publisher copy — rank with it, never estimate with it.** It
reliably carries premise, protagonist and setting. It does *not* carry opening
structure, whether occult is enacted in a scene, crudeness of sexual treatment, or
the idea the book leaves behind — and it overclaims in one direction, which is
worse than noise. The clearest case: the *Páté roční období* annotation sells the
premise and Essun's want, both real, and says nothing about the braided
second-person opening that is the whole reason it is recorded at 64-74 rather than
proposed.

**v3 splits recognition and idea out of the score.** Output is now
`id|rec|idea|score|why`. `rec` is whether the model knew the *work* — not the
author, not the series. `idea` is whether it can name what the book leaves you
thinking about, in a phrase it must then state. Both are binary, both are
auditable, and `idea` exists to order the ≥4 bucket, which had 1,024 works in it
and no tiebreak but a metadata score that backtests at median top 12.7 % and is
documented as plateaued.

**An unrecognised work has NO score — it is unranked, not a 3** (ruled by the reader
2026-08-27). `rec` has been stored since v3, but every consumer read `s` alone, so "I do
not know this book" and "I know it and it is middling" both presented as 3. **Check `rec`
before reading any score**, or use `ai_rank.ranked(r)`, which returns `None` for `rec: 0`.

The scale of it: at score 3, **10,425 of 10,821 verdicts carry `rec: 0`** — the bucket is
96% unrecognised works, so there is no "middling 3" population to promote or downgrade.
A 3 has never been a judgement under either prompt.

It is not cosmetic. Measured over the 100 books promoted from the score-4 bucket on
2026-08-27, the only real-outcome test available: a **recognised 4 reached the 68 propose
line 7 times in 25 (28%), an unrecognised 4 six times in 67 (9%)** — 3.1×, Fisher exact
two-tailed p = 0.038, rejects 4% against 12%. 73 of those 100 books were unrecognised.
The live queue at ≥4 falls from 822 works to **226** once the cutoff respects it.
`promote.py --include-unranked` is the escape hatch for a run that wants to sample them.

**Fixed where the score is READ, not in the prompt.** Making the model emit no score for
`rec: 0` changes `ai-rank-prompt.md`, hence its digest, hence a ~1.3M-token re-run of all
12,382 verdicts — to recover information already sitting in the file.

**A wrong note in a data file will be believed.** `book-ai-rank.jsonl`'s own `_bucket3`
key asserted that a v3+ 3 means the model *could* see the book, which is the opposite of
what its rows say, and it misled a reading of the corpus before the `rec` column was
checked. Header prose is documentation and goes stale like any other.

**Why the scale stayed 1-5 and did not go to 0-10.** Count the decisions taken on
the number: promote first, join the queue, unrecognised, deprioritise. Four. Ten
levels needs ten actions. A longer scale would also have cost the only calibration
that exists — recall 77 % / precision 75 % at ≥4 on a 47-work holdout — and a
7-against-9 cannot be audited, where "name the idea" can. `merge` still accepts
the old `id|score|why` shape so nothing already recorded has to be rewritten.

**v4 is live since 2026-08-27 — v2's body plus the annotation and a `rec` flag.**
It was measured on a 264-work matched holdout *before* promotion (the step the v3
run skipped) and then run over the corpus: 12,382 works, 26 Haiku batches. Full
numbers in `book-cache.json` under `coverage.rankPromptV4Holdout` and
`coverage.aiRankRunV4`. Three things to carry into any future run:

- **`>=4` is the same size and mostly different stock.** 699 works entered the
  queue that v2 had at `<=3` and 681 left it, at a near-identical total — so the
  gain is composition, not volume. Of the 6,851 works v2 had parked at 3 on
  title/author/publisher/year alone, **581 moved to `>=4`** once it could read the
  premise. **Work from `>=5`** (34 works, ~80 % usable on a hand audit): that is
  where the precision is.
- **v4 trades recall for discrimination, deliberately.** 44 % recall against v2's
  85 %, but 24 % false positives against 92 %. v2's high recall was substantially
  an artefact of rewarding canonicity with no information. So a `3` is now even
  more strongly "could not call it" and even less a no.
- **Inter-agent variance is large and is a property of the run.** Batches are
  emitted best-first, so the `>=4` share should fall across batch numbers; instead
  one batch returned 0 fours of 500 and another 125 of 500. A work's score partly
  reflects which agent read it. Never re-litigate a single verdict; the cutoff is
  soft at its boundary.

**The reject gate had four independent holes and a rejected book was promoted
through all of them on 2026-08-27.** *Howlův putující zámek* and *Letní válka*
were rejected on the occult filter, queued anyway, researched by an agent,
estimated and absorbed — so the database briefly held a reject row *and* an `est`
for one book, which is the exact state absorb's guard exists to prevent. All four
are fixed in `already_decided()` / `_decided()`, and all four are the same shape
— **two modules normalising the same string differently**:

1. The reject entity was `lower()`ed but never `deacc()`ed, while both callers
   compare against `deacc(title)`. **Every Czech title-level reject was inert**,
   masked only because the older rows happened to be written ASCII-only.
2. `if level != "title": continue` skipped author- and series-level rows, so an
   author-level reject excluded nothing at all.
3. An entity written `Czech title (Original Title)` was indexed whole and matched
   neither half. `triage.py` had split on the parentheses since 2026-08-26; this
   module never did.
4. `ß` survives NFKD, so `slug()` turned `Preußler` into `preu-ler` and
   `authorid()` could not match the same author spelled `Preussler`.

**The general lesson, and it has now cost three separate incidents: any two pieces
of code that join on a name must share one normaliser.** Before trusting a join,
test it on a Czech title with diacritics, a feminised surname, an entity with a
parenthetical alias, and an author-level row.

**A title-level reject can also be bypassed by an author-string variant — check the
top bucket against the reject rows by hand** (found 2026-08-27). This is the
known "one verdict per *(title, author)* string pair, not per book" limit having a
*correctness* consequence for the first time rather than just wasting tokens.
*Howlův putující zámek* lives under two workkeys because two slices spell the
author differently — `Diana Wynne Jonesová` from `responsibilityStatement` and
`Jones, Diana Wynne` from MARC 100-a. The title-level reject killed the second key
correctly; the first went to the model and came back a **5**, hours after the
reject was written. Until rejects are matched on the normalised title alone as
well as on the pair, **read the `>=5` list against `book-rejects.jsonl` yourself.**
Related: `load_works()`'s "one usable edition rescues the work" rule is right for
an edition problem and wrong for a taste reject — an audio-only record should not
kill a work also held in print, but a title-level reject should kill it in every
edition.

**It is never repeated, and that is enforced rather than remembered.** Every
verdict in `book-ai-rank.jsonl` stores `pd`, the first 12 hex of
sha256(`tools/ai-rank-prompt.md`). `batches` emits only works whose stored `pd`
differs from the current digest, so a rerun costs nothing. Edit one character of
the prompt and every verdict goes stale at once — which is the intended escape
hatch, not a bug. Verified both ways on 2026-08-26: judged∩emitted = 0, and a
one-line prompt edit moved 200 verdicts from fresh to stale.

**`seal` after every promotion — the guarantee used to hinge on one string
compare.** Until 2026-08-26, "already promoted" existed *only* as
`book-triage.jsonl`'s `next: promoted`, itself derived from a title-string join
against `book-cache.json`. One string comparison was the single point of failure
for the whole no-repeat guarantee, and it failed three times that day. Worse,
`book-triage.jsonl` is regenerable only from the temp pulls, which do not survive
a session. `seal` writes `done: <cacheKey>` onto the verdict itself, so the store
is self-sufficient; `done` is a fact about the work, not the prompt, so a digest
change never clears it.

**"One verdict per work" means one per *(title, author) string pair*, not one per
book.** The keys use the strings the catalogue writes, so Tolkien under "J.R.R."
and "John Ronald Reuel" are two works, as are *Jana Eyrová* and *Jane Eyrová*.
Measured 2026-08-26: 20 duplicate groups, 0.2 % of the store, so the token waste
is negligible.

**Do not use them to argue about the scale.** They were computed three ways in one
session and gave σ = 0.47, then 0.24, depending only on how author collisions were
handled — of the 20 pairs just 9 survive a first-name check, and *vyvrhel* was
Anthony Ryan against Chris Ryan, two different books sharing a surname. On the
clean 9, one pair disagrees by one point. That is a fine number and it settles
nothing, because **duplicate records exist for books that got reprinted, reprinted
books are popular, and popular books are the ones the model recognises.** The
sample is drawn from precisely the population where low variance is expected and
says nothing about the 58 % of verdicts sitting at 3.

What actually fixes the scale question is counting the **decisions** taken on the
score — promote-first, queue, unknown, deprioritise, which is four. Ten levels
needs ten actions. See the header of `tools/promote.py`.

`dupes` reports the pairs and deliberately never merges them — *Letopisy královské
komory V* and *VI* are 96 % similar and different books, and so are two thirds of
the pairs it finds.

Batch size drives the cost, because the per-agent overhead is flat. Measured:
**309 tokens/work at `--size 100`**, because the data was 3k of a 31k call.
`--size 500` amortises that to roughly **95 tokens/work**, so the whole 15k corpus
is ~1.4M tokens over ~31 agents, and the top 2,000 is ~190k over 4.

**To rank a class the default queue drops, use a variant prompt — never edit the
live one** (added 2026-08-27). `ai_rank.py`'s `DROP_CLS` contains `childrens`, so
that class is never sent to a model at all, and `ai-rank-prompt.md` scores such
rows a 1 anyway. Both are correct policy and both make the standard pipeline
structurally unable to run a targeted screen of an auto-dropped class — it would
return all 1s. Editing the live prompt to fix one slice would invalidate every
stored verdict, so the pattern is additive: `tools/ai_rank_scoped.py` runs a named
`src` under a variant prompt (`tools/ai-rank-crossover-prompt.md` is the first) and
stamps each verdict with `pv` plus the variant's digest. The main ranker sees them
as foreign and re-ranks nothing; `seal` still works, because `done` is a fact about
the work.

**Measured on the children's shelf, 2026-08-27 — 3,375 verdicts, and the pass paid
for itself exactly once.** Distribution: 8 fives, 795 fours, 2,283 threes, 88 twos,
201 ones. **Six of the eight fives were books already in the log** — *Hunger
Games*, *Malý princ*, two Percy Jacksons, plus a comic adaptation of *Malý princ*
and a licensed *Malý princ* Christmas spin-off. That is the documented
canonicity-bleed failure mode, and here it accounted for 75 % of the top bucket. The
two that survived were **worth the whole run**: *Miliony* (Frank Cottrell Boyce,
Argo 2009 — Carnegie Medal, a declared constraint with a clock on it) was in the
author list a full human name-review had already been over and had passed
over, and *Neplavec* is now recorded low with its uncertainty visible. So the
honest verdict on tier 1.5 for this kind of slice: it will not out-recall a careful
name review, but it catches what the reviewer's own blind spots drop, and one
recovery is the expected yield rather than a disappointment.

**Two calibration facts specific to a Czech children's slice.** `rec=1` on only
**79 of 3,375** works — 2 %, against a shelf where the adult pass recognises far
more — so almost every verdict here is the model reading the library's own
annotation, which the annotation rule says overclaims in one direction. Read a 4 on
this shelf as "the blurb sounded promising", not as recognition. And `idea=1` came
back on **622** works with no discriminating power whatever — it fired on fairy-tale
picture books and Minecraft diaries — which reproduces the v3 finding on a
completely different corpus. Do not use `idea` to order the ≥4 bucket here.

Three rules for using the scores:

- **A `3` is "not recognised", not "no".** That bucket is where untranslated Czech
  titles collect — 80 of 153 random rows *and* 10 of 47 known-good landed there.
  Never treat 3 as a rejection.
- **`s` is not a prediction.** It answers "is this worth twenty minutes", nothing
  more. `book-estimates.jsonl` owns predictions.
- **Feeding the auto-dropped classes to Haiku is a deliberate safety net.** The
  regex classifier misclassified *Jurský park* and *Proměna* at −40, so a model
  pass over the drops catches what the regex got wrong. Costs more; worth it.

### The promotion gate

Promote a tier-1 row when **all four** hold:

1. `cls` is eligible — `sf-fantasy`, `litfic`, `short-idea`, `testimony-allegory`.
2. `band` is `A?`, not `?`. A `?` means the classifier had nothing to go on;
   send it back for a name-review first, don't promote blind.
3. Nothing obviously trips a hard filter on the title itself.
4. A plausible access route exists — the record came from the catalogue, so Czech
   print is usually implied, but **verify the edition**, because audio-only and
   foreign-language publishers are dense in both directions.

`knownAuthor: true` is the strongest single signal, and it is a *priority* hint
rather than a fifth condition — an unknown author can still promote.

Then do the expensive work in full: both access routes, the worldbuilding verdict,
the `est` range with `deps`/`leanedOn`/`risks`, and cache + media entries. **A
promotion is not a copy** — the band is discarded, not converted.

**Not every promotion is a recommendation, and this matters for coverage.** A work
whose expensive pass comes out *low* still gets a cache entry and an `est` range —
that is the `spalovač mrtvol` 60-70 pattern, and it is what stops the same
canonical name resurfacing in every future run. Reserve a reject row for a **named
filter**; use a low range for a graded fail. The 2026-08-26 score-5 batch of 63
came out 22 proposable, 32 recorded low, 2 with no readable route and 3 reject
rows, and the 32 are the ones that make the run durable.

**Four ways a work already screened comes back as a fresh find.** All four were
live on 2026-08-26 and all four are now closed in code; check them before
concluding you have found something new.

1. **A title-level reject nothing reads.** `rejected_authors()` looked only at
   `level` `author` and `series`, so a title row was inert data — *Američtí
   bohové* had been rejected and still scored 5 in two separate model runs. There
   is now `rejected_titles()`.
2. **An exact-string title join.** The cache said "The City and Its Uncertain
   Walls", the record says "The city and its uncertain walls". Normalise both
   sides.
3. **A different Czech title for the same work.** Jota published the whole *Chaos
   Walking* trilogy as *Chaos* where Slovart used per-volume titles. That is what
   `czTitleAliases` in `book-cache.json` is for.
4. **A ruling that lives only in prose.** An exclusion recorded inside a
   `sweeps[].ruledOut` string is invisible to every join. If it is a decision, it
   goes in `book-rejects.jsonl`.

**Worked example, 2026-08-26.** Triage classed the Czech Foundation run
`sf-fantasy` / `A?` / `knownAuthor`. Asimov had sat as "confirmed unread" since
2026-08-19 with only *Já, robot* attached, and six sweeps had never surfaced
*Nadace* because none of them asked what else of his the library holds. Promotion
found the whole run in Argo/Triton print plus a 7 h 29 m English reading, and
produced `[76, 86]` leaning on ideas and motives — deliberately **not** on
worldbuilding, since Foundation's lead is not thin but absent.

### The unknown pool — works the ranker did not recognise

`rec: 0` in `book-ai-rank.jsonl` means the cheap model had no prior knowledge of the
*work* and scored the annotation instead. **Such a verdict has no score** (ruled
2026-08-27), so every score-based selection skips it — which leaves ~10,500 works
that no queue can reach, 596 of them at raw `s` 4.

```
python tools/promote.py batch <dir> --unknown --top 120     # rec=0 only, 8 batches
python tools/promote.py absorb <dir>
```

Two things differ from a ranked run, and each has a reason:

- **Ordered by researchability, not by score.** Every book in the pool carries the
  same (meaningless) raw score, so best-first is really the free metadata scorer —
  whose head here is Czech-original military history with no author parsed at all.
  `researchable()` ranks on an original title, a parsed author, a genre heading and a
  series instead.
- **The task line carries `orig`, `gf`, `kw` and `series`.** The original title is the
  load-bearing one: *Králové Wyldu* returns nothing, *Kings of the Wyld* returns
  everything.

**Measured four times. The fourth says STOP.** Runs 1-3 (2026-08-28, 360 books, ~9.8k
tokens/book) returned **18, 12 then 13 above the 68 line**, and the composition was
visibly thinning — run 1 translated adult SF/fantasy, run 3 historical series, tie-ins,
comics and graded readers. **Run 4 (2026-08-31, 119 books) returned 2.** Not 12, not 13:
**two**, and one of those is a `medium`-confidence row the agent could not source an
opening for. 80 of 119 exited at the cheap `C-low` gate on the default band and 15 were
hard rejects, so 95 of 119 were decided without the pool ever offering a real candidate.

**Read that as exhaustion, not variance.** The queue at this depth is Czech children's
serials, picture books, romance, regional war memoirs and mass-market historicals — the
`researchable()` ordering has already spent the translated-adult-fiction head, which is
where all three earlier runs' yield came from. **Do not queue a run 5 from `--unknown`.**
The remaining ~7,300 unranked works are not worth ~9.8k tokens each at a 1.7% hit rate;
the honest alternatives are a *targeted* screen (an author, a heading, a named canon list)
or a variant-prompt re-rank that puts a better head on the queue. Say the rate out loud
when proposing either — a run that returns 2 in 119 reads as a failure of the pipeline
when it is actually the pipeline correctly reporting an empty shelf.

**The recorded-low rows are still the durable half.** 99 books now carry a real range and
will not resurface as unscreened finds, which is what the two-tier design is for. That
does not make the run worth repeating.

**`orig` predicts translation, not findability, and translation is where the yield is.**
The slice that all carried one returned 18 proposals; the two that had almost none
returned 12 and 13. That is why `researchable()` survives even though the hypothesis it
was named for is false — see its docstring.

**A `gate 0` fast fail existed here and was removed on 2026-08-28 after 0 fires in 360
books.** Do not rebuild it: an absent original title means the cataloguer left the field
empty, not that the book cannot be found, and a Czech title plus an author locates
anything a publisher printed. The reasoning is in `tools/promote-notes.md`.

### A series is one work row, and its route can point at the wrong book

MARC 245 puts the series title in `$a` and the volume in `$n`/`$p`, so for volumes two
onward the catalogue's `name` is **just the series title**. Three consequences, and they
compound:

- `triage.py` builds one work key for every volume, so they share one `book-ai-rank.jsonl`
  verdict and one `book-annotations.jsonl` row — whichever volume the cataloguer summarised.
- `fetch-editions.py resolve()` prefers the newest print edition, so the route lands on
  whichever volume was reprinted last.
- A promotion agent cannot detect either, because the contract forbids it from querying
  the catalogue. **This defect is invisible from inside the agent by design.**

Found 2026-08-27 on *Sirotčinec slečny Peregrinové*: the work row collapsed volumes two
to six, its annotation described a later volume's plot, and the route pointed at a 2023
**companion guidebook** rather than any novel. The agent caught the annotation mismatch,
researched the actual first book and flagged it — but linked the guidebook.

**Check after every absorb.** Fetch `api/records/<uuid>` for each routed row and flag a
`subtitle` carrying `kniha|díl|vyprávění|svazek|část`. Over 100 books it flagged 4, of
which 2 were real; the false positives are books whose own subtitle is a part number
(*Doctor Sax: Faust Part Three*).

**Repair:** repoint `cz` by hand with a `cz.linkCheck` stamp, and add the collapsed short
title to `czTitleAliases` so `ai_rank.py seal` marks *both* work keys done. Without the
alias the collapsed row is back in the next queue.

**The mirror-image defect: an OMNIBUS hides a whole second novel in `$b`** (found
2026-08-31 on Talpress's Discworld run). Where the volume-collapse above loses volumes
two onward *behind* a series title, an omnibus loses a novel *inside* a record named
after a different novel: `name` = "Malí bohové", `subtitle` = "Dámy a pánové", and
`Údaje o edici` = "13, 14". Nine records held eighteen novels that way, so a
title-string sweep found half the series and would have reported the rest as not held.
**Read `subtitle` and the edition-number field before concluding a title is absent**, and
give the hidden novel **its own cache key** with a `flags` note saying which volume it is
bound into and what the other half of that volume is — one of the two is often rejected
on a filter the other passes, and "borrow this book and read the second half" is a fact,
not a caveat. Second, related trap: **a translated series' numbering is not the original's.**
This catalogue numbers *Going Postal* 30 where the English canon has 33, because the Czech
run omits sub-series the English one counts. Record the catalogue's number and name the
original title beside it; never renumber from memory.

### A required field has to be required at every exit, or agents will disagree

`leanedOn` was mandatory in `validate()` but the contract only ever discussed it under
full research. On 2026-08-27 one agent left `leanedOn` *and* `risks` empty on 11 of its
15 files — 19% of that run's C-low exits. The reading was defensible: gate 3 says to exit
because you would put `axis:ideas` in `risks`, and the two fields may not overlap, so
"nothing to lean on" follows. Fixed in the contract, at the gate, not in `validate()`.

When a refusal is a **transcription** the agent could do itself, send the file back to
the agent that wrote it. Eleven `why` texts already named the axis; resuming five agents
cost 53k tokens, and hand-filling would have put the reviewer's reading of the argument
into the one field whose purpose is to make the *agent's* wrong prediction diagnosable.

## "Screened" means exactly one thing

Four different levels of scrutiny got called "screened" on 2026-08-26, which
produced the claim "16,687 records screened, 35.5% of the shelf" when the true
figure was **67 titles**. Use these words:

| Level | Means | Survives the session? |
|---|---|---|
| **Pulled** | the API returned it into a scratch file; zero judgement | **no** |
| **Bulk-triaged** | a group decision touched it — author subtraction, publisher skip-list, a `category` reject | only as the category row |
| **Name-reviewed** | you read the author or title and formed a view | **no** |
| **Screened** | it has a durable row, per the contract below | yes |

**Only the last one counts, and only because it is written down.** Pull counts
are throughput, not coverage — quoting one as coverage overstates the work by
orders of magnitude. If you report a number, report screened titles.

The costliest of the four is **name-reviewed**: deciding "looked at this author,
not interesting" leaves no trace, so the next run pays to review them again. When
you review a name and reject it, write the row — `author` level is cheap and it
is the only thing that stops the same 4,000-author tail being re-read forever.

## The output contract — one row per screened title, always

A title that is screened and not recorded might as well not have been screened.
This was the failure that made the viewer app impossible: on 2026-08-26 sixteen
assessed titles existed only as prose in `book-recommendations.md` and as
strings in `sweeps[].yield`, including *Výdech* — the title the Authors table
calls the best axis match in the whole catalogue. It had no cache entry, so it
had no estimate, so nothing could ever propose it.

So every title you screen lands in exactly one of two places:

- **Eligible** → an entry in `book-cache.json`, a line in
  `book-estimates.jsonl`, and an entry in `book-media.json`. All three, or the
  invariants below break.
- **Excluded without being read** → a line in `book-rejects.jsonl` naming the
  axis id that decided it. Not a sentence in the Authors table.

**Invariants, checkable in one command each:**

```
# every cache entry has an estimate and vice versa
python -c "import json,io;c={b['key'] for b in json.load(io.open('book-cache.json',encoding='utf-8'))['books']};e={json.loads(l)['key'] for l in io.open('book-estimates.jsonl',encoding='utf-8').readlines()[1:]};print('cache only:',c-e);print('est only:',e-c)"

# every cache entry is filterable in the app on all three facets
python -c "import json,io;b=json.load(io.open('book-cache.json',encoding='utf-8'))['books'];print('unfilterable:',[x['key'] for x in b if not (x.get('genre') and x.get('form') and x.get('audience'))])"

# no estimate argues from another candidate — exits 1 on a hit
python tools/crossrefs.py
```

- No key in `books-read.md` may appear in either file.
- `sweeps[].yield` holds **book keys**, not author slugs. Mixed identifiers made
  the 2026-08-26 yields unusable as a foreign key.

## Phase 1 — ORIENT

Read `book-recommendations.md` (the rules), `books-read.md` (what not to
re-screen), `book-cache.json` (`sweeps`, so you don't redo covered ground), and
`book-rejects.jsonl` (so you don't re-reject what is already rejected). Note
`notYetSwept` on the most recent sweeps — that is the live gap list, and it is
where a sweep should start.

State today's date to yourself before anything else. The TTL table below
compares dates, and a guessed one silently corrupts it.

## Phase 2 — DISCOVER

**Name-first searching only ever confirms books already thought of** (learned
2026-08-26). If every candidate comes from the Authors table plus your own recall
of famous genre fiction, the pool inherits exactly those blind spots, and
everything the library holds in Czech translation that never got famous in English
stays invisible. A sweep on 2026-08-26 found four proposable titles that eleven
prior name-first passes had all missed, including the single strongest
worldbuilding case in the catalogue (*Děti času*).

**Run a sweep when** the Authors table can't fill 10 slots without reaching
`Mentioned, no signal`, or the user asks to branch out, or the last `sweeps` entry
in `book-cache.json` is more than ~2 months old. Skip it when the reader wants a
quick answer from known picks.

The catalogue **is sweepable** — see the corrected parameters in Phase 4. Two axes
actually yield:

- **Publisher-scoped, because Czech imprints sort themselves by audience.**
  Adult/translated SF-F: *Triton* / *Planeta9*, *Laser-books*, *Argo*, *Baronet*,
  *Návrat*, *Polaris*, *Host*. Skip for this reader: *Fragment*, *CooBoo*,
  *Dobrovský*, *Mystery Press* and *Slovart* romantasy (crude sexual content is
  central there, not incidental), and *Crew* (manga — wrong format, not a
  judgement).
- **Theme keywords tied to the profile, not the genre** — `první kontakt`,
  `kolonizace vesmíru`, `utopie`, `totalitní`, `svědectví`, `vzpomínky`.

**What does not work:** genre terms (`fantasy`, `science fiction`) sorted
`-REZS_ROK`. That returns the library's current intake, which is overwhelmingly
YA, romantasy and manga — ~1000 records scanned for almost nothing usable. Sort
`REZS_ROK` (oldest first) or scope by publisher to reach the canon instead.

### Completeness — the catalogue is fully enumerable (found 2026-08-26)

**Every sweep before this date was keyword-first, so it could only ever find
records somebody had tagged.** That is a real blind spot and it is now a *choice*,
not a limit:

- **`q=` (empty) returns the whole catalogue** — 109,269 records, 1093 pages at
  `pageSize=100`. Deep pagination genuinely works: page 1093 returns the 69-record
  tail, and 1200 returns HTTP 500 because it is past the end, not because of a
  result cap. So there is no 10k ceiling to work around.
- **Nationality-of-prose headings are applied far more systematically than genre
  tags**, and they are the right axis for this reader, because almost every
  candidate ever proposed is Anglophone fiction in Czech translation:
  `anglicka proza` 4,129 · `americka proza` 2,796 · `ceska proza` 8,803 ·
  `romany` 12,440. The first two together are 6,925 records / 70 pages and cover
  the translated shelf **regardless of whether anyone tagged the book "fantasy"**.
  That pass found 2,721 authors no genre sweep had ever surfaced.

**Prefer a heading sweep over a genre sweep** when the goal is coverage rather
than a quick top-up. Genre terms are for targeting; nationality headings are for
completeness.

**One category breaks that rule, and it is the children's shelf** (found
2026-08-27). `literatura pro deti a mladez` enumerates cleanly at 6,779 records
and yielded twenty proposable crossover titles — but the *best* of the crossover
canon is not in it, because a library files a book by who borrows it, and once a
children's book becomes an adult classic it moves to the adult prose shelf.
*Nekonečný příběh*, *Momo*, *Sofiin svět*, *Alenka*, *Medvídek Pú*, *Zlodějka
knih*, *Robinson Crusoe*, *Huckleberry Finn* and *Chlapec v pruhovaném pyžamu*
were **all absent** from the heading and were recovered only by a named-canon pass
afterwards. So for a *crossover* target the heading sweep and the name-first pass
are complements, not alternatives: the heading finds what is shelved as children's,
the names find what outgrew the shelf. Run both, and say which found what.
The same pass also established that a named-canon query is the only way to prove a
famous title is *absent* — the sole Richard Adams holding is *Příběhy z Kamenitého
vrchu*, which is the *Tales from Watership Down* sequel, so "Adams is held"
would have been the wrong conclusion from a surname match.

### The bottleneck is triage, not discovery

The `anglicka proza` + `americka proza` pass returned **3,011 distinct authors, of
which 2,721 had never been considered** — 90 %. Do not read that as 90 % missed
value. The dominant unconsidered genres are crime/detective (hard filter),
romance and romantasy (crude sexual treatment, the costly kind), and children's —
Cornwell 34 titles, Steel 30, Walliams 29, May 24, Cartland 23 and so on down.
The list is long because the shelf is mostly things this reader does not read.

**So the scarce resource is reviewer attention, and the fix is negative filtering
recorded once.** `book-rejects.jsonl` already has a `category` level — use it.
A `category` row for "Anglophone crime/procedural imprints and headings" costs one
line and removes hundreds of records from every future sweep; recording Cornwell's
34 titles individually costs 34 lines and removes nothing else. **After a
heading sweep, write the category rejects first, then review only the residue.**

Sweep, then subtract every author already in the Authors table and in
`books-read.md` before reading the results — otherwise the known names drown the
new ones. An author with 2+ distinct titles held is a stronger signal than one; so
are multiple printings of the same title (a popularity proxy). Record the sweep in
`book-cache.json` under `sweeps` so the next run knows what ground is covered and
what is still untouched.

## Phase 3 — ELIGIBILITY

Decide, per title, whether it becomes a candidate row or a reject row. Skip
outright, recording nothing:

- Anything already in `books-read.md` (case-insensitively match title, not
  just author — an author can appear once at S+ and still have unread books).
- Anything already in `book-rejects.jsonl` at a scope that covers this title.

Then apply the rules below. Note what does **not** belong in the reject file:
`Avoid`, `Mixed` and `Downgraded` are author-level *priors*, and a prior is not
a verdict on a title — see the two-directional rule immediately following.
Reject on a filter the title itself trips, never on its author's row.

Old exclusion note, retained because the scoping trap it describes is live:
authors with `Status` = `Avoid`, `Mixed`, or `Downgraded` were skipped unless the user
  explicitly asks to revisit that status **or the row's scope doesn't cover the
  title you're holding** — see the leakage rule below.

**Author status is a prior, never a licence — check it in both directions**
(added 2026-08-26, after four splits in one day and one false negative):

- **Downward:** never propose a title because its author is `Top pick` or
  `Predicted fit`. Every title needs its own filter pass and its own
  worldbuilding verdict. Bennett's *Divine Cities* was nearly proposed on a
  "Predicted fit — strong" row and it fails a hard filter.
- **Upward:** never let a title-specific objection sink the whole author. Le Guin
  sat at `Downgraded` over *Earthsea*'s true-name spellcasting while *Levá ruka
  tmy* — a near-ideal match — sat unproposed. Downgrade the work, scope the row.
- **The unit is the work: author → series → volume → component.** The log's own
  within-author spread proves the author level can't predict — Collins runs 91 to
  65 inside one `Top pick`, wider than the gap between `Top pick` and `Fine, low`.
  Bennett needed three verdicts for three series; *Příběhy vašeho života* needed
  flags on two individual stories. **A Status cell with no scope is a bug** — if
  you touch a row that lacks one, add it.
- Known splits to respect: Bennett (Founders yes / Divine Cities no / Tainted Cup
  no), Čapek (kapsa collections are crime), Chiang (*Výdech* clean), Hirsi Ali
  (*Rebelka* not *Kacířka*), Qureshi (memoir not apologetics), Le Guin (Hainish
  not Earthsea), Abercrombie (Shattered Sea not First Law), Adams (book 1 only),
  Brown (trilogy only), Card (Ender canon only), Pratchett (**corrected 2026-08-31 —
  Discworld reopened by *Mort* 83 and now splits four ways: witches rejected on occult,
  Watch rejected on detective, wizards recorded low on opening, Death / Moist /
  standalones eligible**).
- Anything that trips a genuinely **hard** Filter bullet — and there are only
  four: no readable route (no Czech edition and no free English audio), a
  confusing/unclear opening, real-world occult practised on the page (invented
  magic systems are fine), and detective/mystery. Drop those rather than
  caveat them.

Everything else is **graded, not filtered** — flag it and let the reader
decide, don't silently exclude:

- *Sexual content* — **three dimensions and all three cost: volume, explicitness,
  crudeness** (corrected 2026-08-27, overruling the 2026-08-22 "crudeness, not
  quantity"). Crude treatment costs even in small doses (*Artemis* 69) and volume
  sinks a book on its own (*Ready Player One* 55, *The Witcher* 53). **Do not cite
  *Red Rising* 95 as proof that volume is free** — it is low on all three dimensions,
  so it was barely docked; a book that never incurred a penalty is not evidence the
  penalty does not exist. **"Only occasional" is mitigation, never clearance**, and
  never an argument for eligibility. **Above all three, sex as the plot is a HARD
  FILTER** (2026-08-27) — if the plot is mainly sexual behaviour or a sexual
  relationship, reject on `axis:sexual-content`. **It is the sexual references
  specifically, not a vulgar register** — a profane or juvenile voice is not an
  objection, so judge what the book is crude *about*.
- *Violence and swearing* — not objections at all within limits. Never filter
  on them.
- *Worldbuilding logic* — graded; see the verdict required in Phase 5.
- *Bleakness, teen or child protagonists, length* — small pushbacks at most,
  never grounds for exclusion.
- *Prophecy / chosen-one plots* — graded, scaled by how present and how hard
  leaned into; "some prophecy about a saviour is ok". **Never screen out epic
  fantasy for having one.** The axis is **reverence, not resemblance**: Aslan is
  the closest Christ figure there is and is explicitly fine, so don't flag a
  parallel for existing. Flag careless Jesus-resonance a book hasn't earned, or
  a treatment played for ridicule. Subverted or manufactured prophecies are
  judged on tone — serious is fine, cynical is not.

## Phase 4 — ACCESS (cache-first)

The reader always borrows from the same library: Městská knihovna Valašské
Meziříčí, catalogue at https://katalog.mekvalmez.cz/. Check every candidate's
access yourself — never ask the user to check or wait for them to report back.

**Check the cache first.** For each candidate, look it up in `book-cache.json` and
honour the TTLs in `_ttlDays`:

| Cached state | TTL | On a hit within TTL | On expiry |
|---|---|---|---|
| `cz: verified` | 180 days | trust it; library holdings don't vanish | re-query the catalogue |
| `cz: none` | 90 days | trust it | re-query |
| `enAudio: verified` | 30 days | **don't re-search, but liveness-check every link** before handing it out | re-search |
| `enAudio: none` / `doubtful` | 30 days | trust it | re-search |
| absent / `unchecked` | — | — | check both routes |

**A cached `none` is a dated fact, not a property of the book.** *Mistborn* was
cached "no audio exists" on 2026-08-19 and again on 2026-08-22, and the identical
query returned a full three-part reading on 2026-08-26. Never report a book as
unavailable from a cache entry older than its TTL, and never let a stale `none`
keep a book off the list.

**Check both routes for every candidate, not just the first that hits** — the
reader decides differently depending on format, so a title available both ways must
be reported as both.

### Route 1 — Czech print from the library

```
curl -sL -A "Mozilla/5.0" --get --data-urlencode "q=<title without diacritics> <author surname>" \
  --data-urlencode "pageSize=100" "https://katalog.mekvalmez.cz/api/search"
```

Read `result.content[].name` plus `responsibilityStatement.text` — that field
distinguishes a translation, a comic adaptation and an audio edition.
`result.totalElements` / `totalPages` give the real hit count.

- **Strip the diacritics.** A query whose first significant word carries one
  returns zero hits: `Tři mušketýři`, `Půl krále`, `Jurský park`, `Temná hmota` all
  came back empty while the books are on the shelf. Author surname alone also
  works. Never treat a diacritic query's `NO HITS` as absence.
- **Working parameters** (corrected 2026-08-26 — the old note had the names wrong
  and wrongly concluded the API returns 10 hits only): `pageNumber` and `pageSize`
  work, `pageSize` up to **100** (150+ → HTTP 500). `page` / `size` do 500.
  **`pageNumber` is 1-based** (added 2026-08-27): `pageNumber=0` returns HTTP 500,
  which reads as a broken parameter rather than an off-by-one and cost a whole
  68-page pull before it was diagnosed. Page 1 through `totalPages` inclusive.
- **The MARC detail is in the search response, and it is worth parsing.** Every
  record carries `detailTableRows`, whose labelled fields include *Hlavní záhlaví -
  osobní jméno* (the authority-controlled author, far cleaner than splitting
  `responsibilityStatement`), *Rejstříkový termín - žánr/forma*, *Rejstříkový termín
  - klíčová slova*, *Anotace* and *Fyzický popis*. Two of those are strong cheap
  filters: the genre/form term separates `leporela` / `komiksy` / `manga` /
  `populárně-naučné` / `pracovní sešity` from actual prose, and the page count in
  *Fyzický popis* is **the cheapest picture-book discriminator there is** — 1,142 of
  6,779 children's records are under 100 pages. **But it cuts exactly at Little
  Prince length**, so a short canonical title has to be recovered by name; the
  2026-08-27 pass had to treat its own under-100 bucket as an unreviewed gap.
  `sorting` takes `relevance`, `PNAZEV`, `REZS_AUTOR`, `REZS_ROK` (oldest first),
  `-REZS_ROK` (newest first). `q` supports boolean `AND` and trailing wildcards.

  **Parse it as `columns`, not as `label`/`value`** (cost a whole pass 2026-08-31).
  The shape is `detailTableRows[].columns[0].content` = the label, `columns[1].content`
  = the value **as HTML** needing tag-stripping and `html.unescape`. There are no
  `label` or `value` keys, so a parser that reads them returns an empty dict for every
  record and **fails silently** — 52 records read as annotation-free when 40 carried a
  real Czech summary. Labels repeat (the same term twice, once per language), so
  concatenate rather than overwrite.
- **Check the edition, not just the title.** An audiobook-only publisher (Témbr,
  OneHotBook, Tympanum) can mean the catalogue carries no print copy.
- **An ENGLISH-language print holding is not a route, and the publisher list missed it**
  (found 2026-08-31). The rule is Czech print *or* a free English **audiobook**; English
  *print* fails, because English text breaks immersion. `triage.classify()` detects a
  foreign edition from `FOREIGN_PUB` alone, and that list held `"tor books"` while this
  catalogue writes the imprint as plain **`Tor`** — so two English Tor editions were
  classed `print`, became `cz.state: verified`, and reached a promotion agent as readable.
  The word-start-only matching in `_BOUNDARY` was the dodge that hid it (bare `"tor"`
  would have caught Torst and Pistorius). Fixed with a `_WHOLE` tuple that matches at
  **both** ends. **The general rule: when a needle is both a whole publisher name and a
  fragment of a Czech one, it needs two boundaries, not one** — and the record's own
  `angličtina` keyword is a second signal worth checking before trusting a route.
- **The other fields, verified against a live record 2026-08-26:**
  `publishers[0].text` (the whole "V Praze : Odeon, 2008" string), 
  `publicationStartYear.value`, `isbns[0].text`, and `id` — the record UUID, which
  is the borrow link. Flat `publisher` / `year` keys do not exist, and reading them
  returns empty strings that look like missing data.
- **Match `čtou` as well as `čte`.** A two-narrator record says "čtou Josef Somr a
  Magdalena Sidonová", and a singular-only pattern read Hrabal's *Pábitelé* — held
  in this library solely as a Popron audiobook — as print. Use `čt[eo]u?`, `načet`
  and the audio publisher list together.
- **Unavailable, don't retry:** facet values come back empty and `requestedFacets`
  500s; the CSV/XLS export (`/export?target=…&object=…`, capped at 400 records)
  returns HTTP 504 even with a session cookie.

Existence is the bar — this confirms the catalogue *carries* the title, not
real-time loan status, and that is fine.

**Record the borrow link, not just the fact.** Every Czech-print hit gets
`cz.recordId` and `cz.recordUrl` so the viewer app can link straight to the
catalogue record:

```
python tools/fetch-library.py <today YYYY-MM-DD> [book-key] [--force]
```

That tool also pulls the **Czech edition cover** — `api/files/<record.cover.id>`
returns a `source` pointing at obalkyknih.cz — which beats the Open Library
cover, because it is the edition actually on the shelf.

Three facts about it, all verified 2026-08-26 rather than guessed:

- The record page is `https://katalog.mekvalmez.cz/records/<uuid>`. The route was
  read out of the catalogue's own SvelteKit route manifest
  (`_bundle_/immutable/entry/app.*.js` contains `records/[recordId]`).
  **Probing URLs proves nothing here** — the server returns the same 113 KB SPA
  shell for every path, including nonsense ones, so every candidate route
  "worked".
- `recordId` is the search record's `id` (a UUID), not `directoryId`:
  `api/records/<uuid>` resolves, while a bogus UUID and the directoryId both
  return `ItemNotFoundException`.
- **Match on the publisher, not only the title.** *Pilíře země* matched the
  Témbr **audio** edition ahead of the Knižní klub print one, with nothing in
  the title or responsibility statement to tell them apart. Témbr, OneHotBook,
  Tympanum, Audiotéka, K. E. Macan and Supraphon are audio imprints and are
  penalised. A wrong borrow link is worse than none, so an ambiguous match is
  left unlinked and reported.
- **Read back every link it writes for a title with many print editions**
  (2026-08-27). `pick()` scores title, surname and audio-ness only, so when a
  classic is held in eight print printings it has nothing left to choose with and
  reports a confident match anyway — 0 unmatched, 5 of 30 rows pointing at the
  wrong edition. It linked *Záhada hlavolamu* to a 1985 Munich émigré printing
  rather than the Albatros 2019 one, *V šeru dávných věků* to 1972 rather than the
  Burian 2024, and *Bylo nás pět* to 1994 rather than 2016. All are real print
  records, so nothing is *broken* — but the row then describes one edition and links
  another, which is the same silent-disagreement failure the publisher/year note
  above was written for. Diff `cz.recordId` against the edition the row claims and
  repoint by hand, stamping `cz.linkCheck` so the next `--force` run does not undo it.

### Route 2 — free English audiobook

English *text* breaks immersion, but a free English **audiobook** is fine. Sources:
LibriVox for public-domain titles, the library's own eKnihy/eAudio, and YouTube for
most modern genre fiction.

**Use the LibriVox API for anything public-domain — it is one request and it gives
you the runtime** (added 2026-08-27, five routes verified in one pass):

```
curl -sL -A "Mozilla/5.0" "https://librivox.org/api/feed/audiobooks/?format=json&limit=5&title=<exact English title>"
```

Read `books[].title`, `totaltime` and `url_librivox`. **A 404 means "no record
matched that title string", not "no such recording"** — `The Wind in the Willows`
and `The Secret Garden` both 404 while the books are there under other strings. So
a 404 is a cue to retry with a shorter title, never a `none` to cache. This route is
also the only one that comes back `unofficial: false`, so it needs no in-copyright
caveat.

```
curl -sL -A "Mozilla/5.0" "https://www.youtube.com/results?search_query=<title>+<author>+full+audiobook" \
 | grep -oE '"videoId":"[^"]{11}"|"title":\{"runs":\[\{"text":"[^"]{10,140}"' \
 | sed 's/"videoId":"/ID /;s/"$//;s/.*"text":"/T /' \
 | awk '/^ID /{id=$2} /^T /{sub(/^T /,""); if(id!=""&&!seen[id]++){print id" | "$0}}' \
 | grep -iE 'audio ?book' | grep -viE 'summary|recap|review' | head -8
```

**Always duration-check before giving a link out** (learned 2026-08-19, four dead
links in one pass):

```
curl -sL -A "Mozilla/5.0" "https://www.youtube.com/watch?v=<ID>" \
 | grep -oE '"lengthSeconds":"[0-9]+"|"ownerChannelName":"[^"]{2,60}"' | head -2
```

- Uploads titled "Full Audiobook Free" are routinely 1-5 minute stubs — that
  channel style is the tell.
- Compare against published runtime. Under ~60 % is abridged or AI-compressed —
  cache it `doubtful` and say so rather than linking it plain.
- **A single search returning only stubs does not mean no reading exists.** Full
  uploads are usually found by searching `<title> <author> audiobook part 1`, or by
  the narrator's name. That third query is what found *Mistborn*; the first two had
  failed twice. Run all three before caching `none`.
- Multi-part uploads need every part linked. Once one part is found, get the rest
  from the same `ownerChannelName` — sum the parts and report coverage against
  published runtime.
- When the only free English audio is an unofficial upload of an in-copyright book
  rather than a public-domain or library recording, say so **once** for the whole
  group and let the reader decide — don't count it silently as available, and don't
  repeat the caveat per title.

Only if *neither* route exists, drop the candidate, cache both routes as `none`
with today's date, and keep pulling replacements until 10 confirmed-available
options are found. **Library absence alone is not a reason to snooze** — absence of
a route is a fact to re-check, so it belongs in the cache, not in Snoozed.

## Phase 5 — ESTIMATE (first computation only)

Every eligible title needs a line in `book-estimates.jsonl` before it can ever
be proposed. **This is the only skill besides `/book-log` that writes one, and
it only writes first computations** — if a line already exists, leave it alone
even if you disagree with it. Recomputation belongs to `/book-log`, in the turn
where the rule that changed it was written.

Derive, using the current counters from `book-revs.json`:

- `est`: a `[low, high]` range, **conditional on nothing in `risks` firing**.
  Anchor it against real scores in `books-read.md`, never against another
  candidate. Width is confidence: *Den trifidů* 74-80 is a narrow, low-risk
  read; *Leviathan Wakes* 74-84 is wide because a whole strand of it is a
  detective case.
- `leanedOn`: the dep that actually produces the number. Both prediction
  failures so far — *Artemis* (predicted 80, scored 69 after its 2026-08-27
  revision down from 76) and *Mortal Engines* 55
  — came from leaning on the wrong axis, so this field is the audit trail.
- `risks`: axis ids that could collapse the estimate below its range. A risk is
  not a hedge: *Neuromancer* is 72-80 if its opening holds and a 30 if it
  doesn't, and averaging that to 55 would say nothing.
- `deps`: the mandatory minimum — `axis:opening`, `axis:occult`,
  `axis:detective`, `axis:worldbuilding`, `axis:protagonist`, `axis:motives`,
  `author:<x>` — plus every axis you actually engaged, each stamped with its
  current rev. Add `series:<x>` where one exists, and add the author or series
  id to `book-revs.json` if it is new.
- `blocked`: set to the axis id instead of an `est` when the title fails a hard
  taste filter. **Never `blocked` for access** — that is a dated fact and lives
  in `book-cache.json`; a blocked-for-access row would go stale exactly the way
  *Mistborn*'s "no audio exists" did.

Three guards on the numbers:

- **Never predict a book up on worldbuilding when the lead looks thin.** That is
  the *Artemis* error; the protagonist axis outranks worldbuilding.
- **Style-based predictions are weaker than plausibility-based ones.** *Mortal
  Engines* was argued on its opening and lost on the axis the prediction never
  examined. Before leaning on prose or pacing, state whether the world holds.
- **Candidates never mention each other** (2026-08-26). Inspiration comes from
  the rules and from books that carry a real score, and from nothing else — an
  estimate calibrated against another estimate is a guess anchored to a guess.
  So the `why` names read books and axes, never a sibling candidate, and it
  repeats a shared argument in full rather than saying "same reasoning as that
  line": each row has to stand up alone in the app. Sequence and edition notes
  ("read volume 1 first", "also inside that collection") are **facts** and go in
  `flags` in `book-cache.json`, where naming another title is correct. Checked by
  `python tools/crossrefs.py`, which was written after 22 lines had been derived
  the other way — one of them arguing from "451 read" when *Fahrenheit 451* is
  itself an unread candidate.

## Phase 6 — MEDIA

`book-media.json` carries a cover URL and a neutral blurb per key, in three
namespaces because the viewer app's three tabs are keyed differently:
`media` by cache key, `readMedia` by a slug of the `books-read.md` title,
`rejectMedia` by a slug of `entity + author`. Regenerable: if it is missing or
stale, refetch rather than hand-writing it.

The slug join is deliberately loose — renaming a title in `books-read.md` costs a
placeholder cover, never a broken row. **The slug function in
`tools/fetch-media.py` and the one in `index.html` must stay identical**, or half
the covers silently stop joining.

```
python tools/fetch-media.py <today YYYY-MM-DD>
```

Idempotent and additive — it fills only missing covers, keeps existing blurbs,
drops entries for keys no longer in the cache, and prints the keys that still
need a blurb. Run it after every screening pass; it refuses to guess the date.

- **Cover** — Open Library search by English title + author, then
  `https://covers.openlibrary.org/b/id/<cover_i>-M.jpg`. `limit=1` frequently
  returns a coverless edition record even when the work has covers, so widen to
  `limit=8` and take the first hit that actually has `cover_i`; fall back to a
  plain `q=` search for Czech-only titles. A null cover with a `coverNote` is a
  gap, not an error — the app draws a typographic placeholder.
- **Blurb** — one neutral sentence saying *what the book is*. Authored, not
  scraped. It must not contain the judgement of whether the reader would like it:
  that is `why` in the estimate, and duplicating it there is how two files start
  disagreeing.

## Phase 7 — RECORD

1. **`book-cache.json`** — one entry per eligible title: `key`, `title`,
   `czTitle`, `author`, `series`, `genre`, `form`, `cz{}`, `enAudio{}` with
   today's `checked` date, and every verified link with its runtime in minutes.
   Add `flags` for a per-title caution and `occultCheck` when you ran one. Append
   a `sweeps` entry for any sweep, with `queries`, counts, `yield` (book keys),
   `lesson`, `ruledOut`, and `notYetSwept` so the next run starts at the gap.

   **`genre`, `form` and `audience` are required — the viewer app filters on them,
   and a missing value silently hides the book from a filtered view.**

   **`audience`** (added 2026-08-27, at the reader's request that the children's
   shelf be filterable): `adult` · `ya` · `childrens`. It is **who the edition was
   published for**, which makes it a fact like the other two — *not* a verdict on
   whether an adult should read it, which is `axis:childrens` in the estimate.
   Keeping those apart is the whole point: a cache field that carried the judgement
   would be the same silent-disagreement bug as a duplicated access cell. It is a
   third field rather than a `genre` value because the two are orthogonal —
   *Nekonečný příběh* is fantasy **and** children's, and collapsing them would throw
   the genre away. Derive it from the catalogue's own žánr/forma index term
   (`publikace pro děti` → `childrens`, `publikace pro mládež` / `literatura young
   adult` → `ya`) and record how you got it in **`audienceSource`**: `katalog`,
   `hand` (the record carries no term, so it was read off the edition and imprint),
   or `default` (nothing known — and `adult` is then an assumption, not a finding,
   which is why the source field exists at all). 239 of 296 rows are `adult` by
   default, so treat that value as unverified unless the source says otherwise.
   `genre`: `sf` · `fantasy` · `litfic` · `historical` · `testimony` ·
   `allegory` · `thriller`. `form`: `novel` · `novella` · `stories` ·
   `nonfiction`. They are **facts, so they belong here, not in the estimate**,
   and they stay two fields rather than one because they are orthogonal: Chiang's
   *Výdech* and Saki's collection are both `stories` and share nothing else.
   `stories` covers single-author collections and anthologies alike, since the
   unit catalogued is the volume. One value each — where a book straddles two,
   pick what a reader looking for that shelf would expect and let `flags` carry
   the nuance. **`form: stories` or `novella` is not a scoring signal**; see the
   short-form rule, which the 2026-08-26 sharpening made explicit.
2. **`book-estimates.jsonl`** and **`book-media.json`** — per Phases 5 and 6.
3. **`book-rejects.jsonl`** — one line per exclusion: `entity`, `level`
   (`author` / `series` / `title` / `category`), `author`, `filter` (the axis id,
   or `access` for an edition problem), `why`, `at`, `source`. **`author` is
   omitted entirely on `category` rows**, where it does not apply — never write a
   placeholder like `"(various)"`, which reads as data. **Scope matters:**
   an *Earthsea* objection must not sink Le Guin, which is the false negative
   that produced the scoping rule in the first place.
4. **`book-recommendations.md`** — only what changes a *conclusion*: a new
   author row, a status change, a scope correction. Access links, per-title
   assessments and reject lists do **not** go here any more; they have machine
   files now, and that file is explicitly not allowed to grow with the log.
5. **A method error is worth more than a book.** If a documented query,
   parameter or search pattern turns out wrong, fix it in this file — a wrong
   parameter costs every future run.

## Phase 8 — VERIFY

- All three invariant commands above come back clean — the last one,
  `tools/crossrefs.py`, exits 1 if any `why` you wrote names another candidate.
- Every new estimate's `deps` revs match `book-revs.json`.
- Every new cache entry has today's `checked` date on any route you actually
  checked, and no route is marked `verified` on an unverified guess.
- Report: how many titles screened, how many eligible, how many rejected and on
  which filters, what ground the sweep covered, and what is still in
  `notYetSwept`. **Never let a bounded pass read as an exhaustive one** — say
  what you did not reach.

## Appendix — the worldbuilding-and-logic derivation

Needed in Phase 3 and Phase 5, and quoted into the estimate's `why`.

**Every suggestion must carry an explicit read on whether its world holds up**
(required 2026-08-22, after *Mortal Engines* 55 was abandoned in the first
chapters on this axis alone — the prediction that proposed it had never
examined it). This is the reader's heaviest axis, so a proposal that skips it
is incomplete however good the access route is.

**The verdict is carried in the `why` field of the estimate line, and it is
current because `/book-log` keeps it current** (changed 2026-08-26; this used to
say a cached verdict was stale whenever the global `profileRev` moved, which
invalidated every verdict at once and meant nothing was ever really cached).
What makes the cache safe now is that invalidation is per-dependency and
recomputation happens in the log turn: when the 2026-08-22 revisions to the
sexual-content and prophecy axes landed, only the 5 and 4 lines that actually
carry those axes would have been re-derived, and they would have been re-derived
*then*, not lazily on the next proposal. **Access facts and judgements now cache
the same way — what differs is what invalidates them.** A judgement is
invalidated by a rule moving, an access fact by time passing.

**The principle: the author must follow the rules he lays down.** This is
self-consistency with what the book commits to, not an external realism audit.
Nothing obliges an author to explain anything — but whatever he asserts,
foregrounds or undertakes to explain becomes binding. Full derivation: the
"Does it hold up under thought?" bullet in `book-recommendations.md`.

Say it in one or two lines per title, and only where it bites:

- **What did the book promise?** Declare a capability (FTL, magic) → the
  society must be different for it. Undertake to explain the physics → the
  explanation must hold. Take a society as the subject → it must cohere.
  Declare a resource scarce or sacred → it must behave that way. Declare a
  trait in a character → it must be shown. All the same breach.
- **Where nothing is declared, reality binds — set by the tech level the book
  *presents*, not the date it's set in.** A far-future setting that reads
  low-tech is still bound by real costs (*Mortal Engines* 55); one that reads
  genuinely advanced is not (*Ender's Game* 87). Presented tech, not chronology.
- **Jurisdiction is per world; cross-world duty scales with the traffic — and
  traffic has a direction.** Each world answers to its own rules. Check each
  direction separately and ask whether the book's declared mechanism actually
  covers *that* direction. Narnia 67 owes nothing either way — a wardrobe now
  and then is negligible. *Harry Potter* 51 is fine outbound (secrecy is a
  declared, enforced rule, and it earns magic's absence from mundane life) but
  breaches inbound: muggle-borns are admitted to the school every year and
  wizarding society absorbs nothing they bring. **A declared institution can
  discharge the duty one way and leave the other wide open.**
- **For hidden-world and portal fiction, find who crosses over and stays, and
  ask what they bring.** Policy can hide a society; it cannot make its members
  un-know what they arrived with. That is where the obligation bites.
- **The obligation scales with how precisely the thing is declared** — the
  author sets his own bar. Vague, numinous magic owes little (Narnia 67,
  Tolkien); a spelled-out system owes a lot. Rules add obligation, not bonus.
- **Exemption is about how hard the book *leans* on the thing, not what it's
  nominally about.** *Harry Potter* 51 is a school story and still takes a
  worldbuilding hit, because magic is the medium of every scene. *Hunger Games*
  89 merely mentions its economics. Lean, not aboutness — so don't grant the
  exemption just because a book is character-led.
- **"Explained later in the book" is a valid defence — but verify it.** The
  reader searches online before condemning a book, so an unchecked claim will
  be caught. A sequel does not count.
- **Grade it, never filter on it.** The deduction tracks centrality *and*
  magnitude together; physical and social implausibility weigh the same.
- **It adds points too** — predict a worldbuilding-strong candidate *up*. It
  doesn't cancel other pushbacks: Tolkien's is good and still caps at 84, and a
  thin protagonist beats it outright (*Artemis* 69).
- **Kind and rules don't matter** — "consequences, not rules".
- Say when you don't know. A guess about an unread book is a flag, not a
  finding, and should be labelled as one.

If fewer than 10 clear the filters and the access check, present the ones
that did and say what fell short and why — never pad the list to 10 with
titles that failed a check.
