# Promotion pipeline — the measurements behind the contract

**No agent reads this file.** It exists because `tools/promote-prompt.md` is re-sent
to every promotion agent on every turn of every batch, so a paragraph of
justification in there is paid a thousand times over. The rules live in the
contract; the evidence for them lives here, where it costs nothing.

Moved out of the contract on 2026-08-27, when a run measured 13.4k tokens per book.

## Cost, measured on the 14-batch run of 2026-08-26

112 books, 1,502,147 subagent tokens, **13.4k per book** — about 13.5M for the
1,011-book queue. Tool uses per batch ran 20-44, roughly 3.75 per book, so cost
tracked tool-call count almost linearly at ~3k tokens per call. Fixed context
(`promote-prompt.md` + `reader-profile.md` + `books-read.md`) was ~9.3k per batch,
only ~9% of it — so prompt trimming is a second-order lever and **removing tool
calls is the first-order one.**

The largest single call was the catalogue query the contract used to ask for in Step
3. Measured 2026-08-27: `q=Ruze pro Algernon&pageSize=40` returned three hits in
**111,276 bytes** — ~24 kB of `detailTableRows`, `fields`, `exports` and
`recordStatusTransitions` per record, to carry the ~200 bytes that decide the route.
An author with twelve editions returns a quarter of a megabyte. That response then
sits in the agent's context for the rest of the batch.

None of it is judgement, so `tools/fetch-editions.py` now resolves the route offline
for the whole corpus in one ~253-request sweep, and the task line carries the answer.
Gate A and Step 3 left the contract with it.

## The 50-book verification run, 2026-08-27

50 books, 7 batches, **535,525 tokens = 10.71k/book** against the 13.4k baseline. The
six 8-book batches averaged 81,116 (**10.14k/book**, −24%); the one 2-book batch cost
24.4k/book, which is what makes the decomposition below possible.

**Every budget held, at every gate, with zero overspend** — `C-low` 1.00 mean against
1, `B-detective` 2.00 against 2, `B-occult` 2.29 against 4, `D-full` 3.40 against 6.
The run before it was 49-of-53 over at `C-low` and 9-of-9 over on rejects. Zero
catalogue queries and zero whole pages fetched across all 50. Exit mix moved the way
the gate rewrite intended: `D-full` 52% → 20%, `C-low` 41% → 46%.

### Batch size, settled on three measured points

| books/batch | tokens | tok/book | tool calls/book |
|---|---|---|---|
| 2 | 48,832 | 24.42k | 5.50 |
| 8 (mean of 6) | 81,116 | 10.14k | 3.06 |
| 20 | 136,014 | **6.80k** | 2.50 |

Least squares over those three: **fixed ~40.6k per batch, variable ~4.8k per book**,
residuals -1.4k / +2.1k / -0.7k. Calls per book *falls* as the batch grows, because
author research is shared - which is why `peak_context()` interpolates the rate rather
than holding it constant.

**Default set to `per=15` by the reader 2026-08-27**: ~7.5k/book, 56 batches for 837
books, ~6.3M, and an estimated peak context of ~92k against a 100k ideal / 150k
ceiling. `per=20` would save a further ~0.6M but estimates at ~111k, over the ideal.
The ceiling breaks at 28 books.

The 20-book run also settled the quality question, which was the real risk: **0 of 20
`validate()` failures**, no overspend at any gate, `crossrefs.py` clean, staged output
2,597 B/book against 2,619 B at `per=8` (so the reasoning does not thin out), and all
three author pairs judged separately with divergent numbers rather than sharing one
verdict. That last one is the check that matters - a shared author verdict with the
volumes ranked inside it is the failure mode grouping invites.

Peak context itself was NOT measured and cannot be from these numbers: 136,014 is
cumulative spend, not occupancy. The only sound bound is that every token in context
entered it once, so peak <= ~136k.

### The fixed cost per batch is ~38k, and that reverses the batch-sizing answer

Solving the 2-book batch against the 8-book mean: **fixed ≈ 38k/batch, variable ≈
5.4k/book.** Regressing cost on tool-use count agrees independently — 40.5k intercept
+ 1.65k per call, R² = 0.80. So ~4.8k of every 10.14k is per-batch overhead unrelated
to the book.

The 2026-08-26 answer to "would longer batches help?" was **wrong**, and specifically
wrong because it priced the fixed context at its file size (~11k tokens) instead of at
the cost of re-sending that context across 20-35 tool calls (~38k). Corrected:

| `per` | tok/book | remaining 881 books |
|---|---|---|
| 8 | 10.14k | 8.9M |
| 12 | 8.55k | 7.5M |
| 16 | 7.76k | 6.8M |
| 20 | 7.28k | 6.4M |

The cross-contamination argument against larger `per` is much weaker now that
`absorb` + `crossrefs.py` check it mechanically.

### Four bugs the run exposed, all in the plumbing rather than the judgement

- **`validate()` demanded `genre`/`form` on rejects** while the same day's contract
  rewrite told agents to omit them — 16 of 50 files refused for obedience. Now
  required only when there is no `reject`.
- **`SIBLING_REL` fired on "the novel's first book"** (*Hastrman* is one novel in two
  books). Possessive/determiner lookbehinds added; the real violations still fire.
- **The queue only excluded on the `ai_rank seal` flag**, a separate manual step, so
  9 of the 50 were already decided and 18% of the tokens bought nothing. It now filters
  against `book-cache.json` and `book-rejects.jsonl` directly.
- **A rejected book could quietly acquire an estimate.** `zapomenuta-legie` was
  rejected for occult on 2026-08-26, then exited `C-low` here with the occult question
  *deliberately* unexamined, and briefly held both. Absorb now refuses that; retracting
  a reject has to be deliberate. This is the first observed cost of putting the occult
  gate after C.

The reject join needs three channels: `key` (exact, now written on every new reject
row), (title, author), and bare title only when the queue row has no author — 13
catalogue rows have a blank author, which is how the Lovecraft volume got back in.
Title alone is never enough: `Sucho` is both Shusterman's *Dry* (estimated) and
Harper's *The Dry* (rejected).

## Research spend, measured from the 128 staged files of 2026-08-26

`promote.py absorb` now prints this per run; the numbers that set the budgets were:

| exit | n | budget | mean | median | max | over | share of all research |
|---|---|---|---|---|---|---|---|
| `B-detective` | 3 | 2 | 3.33 | 3 | 4 | 3 of 3 | 8% (both rejects) |
| `B-occult` | 6 | 4 | 6.00 | 6 | 8 | 5 of 6 | — |
| `C-low` | 53 | 1 | 3.25 | 3 | 6 | **49 of 53** | **33%** |
| `D-full` | 66 | 6 | 4.53 | 4 | 9 | 5 of 66 | 57% |

517 non-catalogue sources in total. Overspend: `C-low` 121 (**23% of the entire run**),
rejects 28 (5%), `D-full` 7 (1%). Only `D-full`, the one exit that had a stated
ceiling, behaved — which is the argument for stating ceilings.

### Why the gates were reordered on 2026-08-27

The ladder claimed to be ordered by cost-to-decide and was not: it asked both hard
filters first, putting the most expensive question in the whole pipeline (occult, mean
6 sources) ahead of the cheapest decisive one (below-the-line, budget 1). Order is now
detective (2) → below-the-line (1) → occult (4) → full (6).

The reorder trades a piece of durable information for tokens, deliberately: a `C-low`
book now carries an **unexamined occult status**. It is defensible because nothing
under 68 is ever proposed, so the reject and the low estimate have the same practical
effect on what gets read, and `axis:occult` staying in `deps` keeps the book findable
when the axis is bumped. Reverse the order if the reject's permanence turns out to
matter more than the four sources.

### Why Gate C's mandated range grew a second band

The 53 `C-low` exits wrote just four distinct ranges — `[58,68]` × 31, `[60,70]` × 16,
`[56,66]` × 5, `[32,42]` × 1. So the number was already near-constant and the decision
was the only real output. But it was also too generous: of the 66 books that went to
*full* research, **38 came back below 68** and 14 of those below 58 — and three agents
overrode the C mandate downward rather than write a number they did not believe. Hence
the second band `[42, 55]` for a book with no nameable idea and a form that suspends
the character tests.

That same figure is the ladder's biggest remaining miss: **58% of `D-full` books landed
below the line** at mean 4.6 sources, which is work Gate C existed to avoid and did not.

### Why Gate B stays, and why the reject decision cannot move to the cheap tier

Asked 2026-08-27 whether the throw-away exit should be removed, since it looked like
the most expensive gate. It is the most expensive *per book* and the cheapest in
total: 9 books, 46 sources, **8% of all research**, of which 28 sources are overspend
— 5% of the run against Gate C's 23%.

Removing it saves nothing, because the work does not disappear. The occult and
detective questions are answered in Step 2 either way, so those nine books would
simply have reached Gate D and been priced at 6 instead of 2-4. Gate B held to budget
is *cheaper* than no Gate B.

Nor can the decision move to a regex or to Haiku. Of the nine rejects, **the `signals`
hint named the filter that actually fired on exactly one**. Eight had no signal at
all, or the wrong one — `kosticas` was flagged `detective` and was rejected for
occult. Eight of nine carried an annotation and it still did not say. The
determination needs a model that can go and look.

What the question got right is that 5.11 sources on a disqualified book is wrong. The
cause was the unconditional `sources` / `confidence` requirement, now scoped per gate,
plus the absence of any ceiling.

`katalog.mekvalmez.cz` appeared 129 times across 128 files: **exactly one catalogue
query per book**, which is what confirmed that the 111 kB response was a per-book
cost paid at every gate. That is the fact that explains why an all-Gate-C batch cost
97k and a Gate-D-heavy batch 129k — only 1.4× apart despite doing very different
amounts of work.

Large reference pages cited: **117 across 128 books** — Goodreads 28, en.wikipedia
25, per-book Fandom wikis 31, TVTropes 13, SuperSummary 8, LitCharts 6, SparkNotes 2.
Fetched whole those are 50-200 kB each. Hence the "read snippets" rule.

Confidence by gate: `high` was claimed at B twice (on rejects, with 8 sources) and at
C once of 53. So the `confidence: high` requirement was not what drove Gate C's
overspend — the absence of any stated ceiling was.

## Batch sizing — measured, and the answer was "wrong knob"

Over the 1,011-work queue: 625 authors, of which **443 contribute exactly one book**.
Raising a single `per` from 8 to 20 therefore only merges singletons and un-splits
nine authors: 243 batches becomes 205, a 16% saving worth ~4.5% of the token
projection, while making the top refusal cause worse. Hence the two separate limits
in `cmd_batch` — `per_author` generous at 20, `per` small at 8 for the singleton
pack, where nothing is shared and each added book is one more chance of
cross-contamination.

## Gate C — why the first version fired zero times

On the first batched run every book exited at `D-full`. Two causes, both fixed:

- **It asked the wrong question** — whether you could *name* an idea. Measured
  useless twice: 70% of known-good works against 71% of known-low in the triage
  step, and `axis:ideas` is the single most common `leanedOn` on *both* sides of the
  68 line (41 of 72 above, 16 of 49 below). Almost every book passes "can you name an
  idea", so almost nothing exited.
- **It asked for the wrong number** — "a wide range in the 50s", when only **8%** of
  estimates end with a high of 65 or less. Being told to write the 50s for a
  competent literary novel is a reason to refuse the gate and research on, which is
  exactly what happened.

The two separators that replaced it, measured over the 121 estimates then on disk:

- litfic **and** a short-story collection: 17 of 21, **81%**, below the 68 line.
- `axis:ideas` under `risks`: **47%** of books below 68, **7%** of books above it.

Honest limit: these are correlations inside the pipeline's own output, not against
real readings, and the 121 estimates are a more canonical set than the queue. They
are routing, never a verdict.

After the rewrite, on the 2026-08-26 run: refusals fell from 6-of-8 to 4-of-99, Gate
C fired on ~45%, and it discriminated — Asimov 1 of 8 exits, Hrabal 8 of 8. Three
agents overrode the mandated low-60s downward (Jonathan French, *Betonova zahrada*,
*Cary*), which suggests the gate may want a content-driven branch permitting sub-50s
exits.

## Why the bare prohibitions in the contract are stated with a reason

Each of these was tried as an unexplained rule first, and did not hold:

- **"Do not read `book-estimates.jsonl`."** An agent told only that cited "Munro's
  domestic realism to 52-62", a number that exists nowhere else. It needed the *why*:
  every range in that file is an unverified guess about a book nobody has read.
- **Batch-relative reasoning.** Five of eight files on the first batched run argued a
  number from a book's place in its series; 22 of one batch calibrated against
  another candidate, including one arguing from "451 read" when *Fahrenheit 451* is
  itself an unread candidate. `tools/crossrefs.py` is the enforcement.
- **`leanedOn` / `risks` overlap.** They were the same axis in 14 of 33 files.
- **Axis near-misses.** `absorb` refused `axis:story-density` where the id is
  `axis:density`. The cost is mechanical: `/book-log` greps a bumped id, an
  almost-right dep is never found, and the estimate goes stale forever.
- **`confidence`.** 20 of 33 files claimed `high` and none claimed `low`, which
  cannot be right for books nobody has read.
- **Truncated `recordId`.** Broke 54 borrow links once.

## Known gap

`promote-prompt.md` is not hashed, unlike `tools/ai-rank-prompt.md`. An estimate
carries no record of the prompt that produced it, so tightening a gate here does not
cause old estimates to be revisited — that is by hand, via a `book-revs.json` bump
and a `/book-log` PROPAGATE pass.

## The score-4 bucket, 100 books, 2026-08-27

First pass below the fives. 90 estimates, 10 rejects, **16 estimates at or above the 68
propose line and 14 at a floor of 70** — per book that is about what the 34 fives
returned (5 of 26 at a floor of 70), which says the ranker's 4 and 5 are not far apart
in what they are worth to this reader. 55 of 90 wrote the `[58,68]` C-low default.

Cost 1.02M tokens for 100 books, **10.2k/book** against the 7.5k the `per=15` model
predicts. The C gate is still the one inverted budget: 24 of 59 C exits spent 2 sources
against a budget of 1.

### `leanedOn` does not survive an early exit unless the contract says so

One agent left both `leanedOn` and `risks` empty on **11 of its 15 files** — 11 of the
run's 17 refusals, and 19% of every C-low exit. This is not carelessness. Gate 3 tells
an agent to exit *because* it would put `axis:ideas` in `risks`, and `validate()`
forbids `leanedOn`/`risks` overlap, so an agent that reads both rules together can
conclude there is nothing left to lean on. At C the number is carried by the doubt, and
the contract now says that in gate 3.

Fixed by sending the files back to the agent that wrote them rather than hand-filling
the field: every one of the eleven `why` texts already named the axis, so the repair was
a transcription and cost 32k tokens. Hand-filling would have put *my* reading of their
argument into a field whose whole purpose is to make **their** wrong prediction
diagnosable.

### The catalogue collapses a series into one work, and `resolve()` then picks the wrong book

MARC 245 puts the series title in `$a` and the volume in `$n`/`$p`, so the catalogue's
`name` field for volumes 2-6 of a series is just the series title. Consequence:
`triage.py` builds one work key for all of them, they share **one** annotation, and
`fetch-editions.py resolve()` — which prefers the newest print edition — picks whichever
volume was reprinted last.

*Sirotcinec slecny Peregrinove* is the worst case seen: the work row collapsed volumes
two to six, its annotation described a later volume's plot, and the route pointed at a
2023 **companion guidebook**, not a novel at all. The agent noticed the annotation
mismatch, researched the actual first book and flagged it — which is the contract
working — but it could not see that the route was wrong, because the contract forbids it
from querying the catalogue.

So this class of defect is invisible from inside a promotion agent by design, and has to
be caught after absorb. The check is cheap: fetch `api/records/<uuid>` for every routed
row and flag a `subtitle` carrying `kniha|dil|vypraveni|svazek|cast`. Over these 100 it
flagged 4 and 2 were real (1 false positive was *Doctor Sax: Faust Part Three*, whose
subtitle is genuinely the book's own).

Repair pattern: repoint `cz` by hand, and add the collapsed short title to
`czTitleAliases` so `ai_rank.py seal` marks **both** work keys done. Without the alias
the collapsed row returns to the queue on the next batch.

## The score-4 bucket, second slice: 120 books, 2026-08-27

Ran at the new `per=15` default: 8 batches, 120 books, all score 4 — **the score-5 pool is
exhausted**, so every future promotion run is a 4 or below until the ranker sees new works.

95 estimates, 25 rejects (13 `axis:detective`, 12 `axis:occult`). **33 estimates at or above
the 68 propose line and 23 at a floor of 70**, against 16 and 14 from the first 100-book
slice — so yield rose on the same bucket, which is the opposite of what a
best-first queue predicts and is worth watching rather than explaining.

Cost **1,239,467 tokens = 10.33k/book** (1.19M promotions + 51k repairs) against the 7.51k
the `per=15` model predicts. Tool calls were **2.77/book, essentially exactly the
interpolated 2.71** — and source counts came in *under* budget at every gate. So the
overrun is per-call context size, not extra work, and `calls_per_book()` is well
calibrated while the token model is not.

Budgets, the best held so far:

| gate | n | budget | mean | max | over |
|---|---|---|---|---|---|
| `B-detective` | 13 | 2 | 2.08 | 3 | 1 of 13 |
| `B-occult` | 12 | 4 | 2.17 | 3 | — |
| `C` | 26 | 1 | 1.08 | 2 | 4 of 26 |
| `D` | 69 | 6 | 2.19 | 4 | — |

### Gate 4's two tests never fire at `D-full`, which is why retuning it failed

The exit mix went the wrong way — `D-full` 58% and `C-low` 22%, against the 20%/46% the
2026-08-27 rewrite achieved. 36 of 69 `D-full` books (**52%**) came back below 68, barely
moved from the 58% that rewrite was aimed at.

Measured over this run's 69 `D-full` files, the gate's own two stated separators:

| test | hits among 69 `D-full` |
|---|---|
| `axis:ideas` in `risks` | **2** |
| litfic **and** short-story collection | **0** |

**Both tests are self-fulfilling.** An agent that has decided to go on to D has, by that
decision, already answered "no" to both, and then does not write the risk it just
declined to hold. So neither can catch a book on the way past, and no threshold change
reaches them. This is a defect in the gate's *shape*, not its calibration — which
explains why the rewrite moved the number once and it snapped back.

Nothing cheap in this run's data replaces them. Below-68 rate among `D-full`: litfic 52%
(n=21), any-risks-at-all 52% (n=67), 2+ risks 53% (n=32), content/sexual in `risks` 67%
but only n=12. Genre is the sharpest axis available and is thin — `historical` 65% below
(n=17), `fantasy` 58% (n=12), `sf` 33% (n=9).

**Price it before building it.** The waste is ~1.2 extra tool calls on each of 36 books,
about 110k of 1.24M — **~9% of run cost, not the dominant lever.** An earlier read of this
run called it the highest-value fix available; that was wrong. Whatever replaces the gate
must go through `holdout` + `score` first, per this file's own record of the 1.5M-token
regression.

### One agent omitted `sources` on 12 of 15 files

Same single-agent-systematic shape as the 2026-08-27 `leanedOn` incident: it made 39 tool
calls, so it researched, and simply never wrote the field. 12 of the run's 20 refusals.
Repaired by sending the files back to the authoring agent — 51k tokens across all six
agents and 20 files, every estimate keeping its original number.

The lesson repeats: a refusal class that lands almost entirely inside **one** batch is an
agent-level miss, not a contract ambiguity, and the cheap fix is a resend rather than a
prompt edit.

### `NEEDLE_MIN = 12` let a real cross-reference reach disk

`vodni-nuz` argued from "*Ice*'s logic conceit" — `led` (Dukaj), an unread candidate
estimated `[70, 80]` in this same run. Four characters, so `validate()` could not see it;
`crossrefs.py` caught it after absorb, and the repair needed a hand patch of the
`book-estimates.jsonl` row because absorb will not re-take an absorbed key.

The other 6 crossrefs hits this run were all false positives and each had to be read by
hand: "joining the Underground" (the Railroad), "Gallant's short stories" (the author's
own surname), "a small-town coal merchant", "*Never Mind* opens as" (the book's own first
novel), and Poul Anderson's historical Hannibal, twice. **6 of 7 hits being noise is the
cost of the short-title pass**, and it is worth paying — but do not automate a fix on its
output.

### Checks that ran clean, and are worth keeping cheap

- Series-collapse: all 93 routed rows fetched, `subtitle` tested for
  `kniha|díl|vyprávění|svazek|část`, **0 flagged** (2 real defects last run).
- `fetch-library.py`: 105 records linked, 89 Czech covers, 0 unmatched.
- Re-queue check after `seal`: none of the 120 reappears. Note `seal` marked 107 + 3
  markers, not 120 — rejects never enter `book-cache.json`, so they are held out of the
  queue by `already_decided()` rather than by the seal.

### Reject-row covers lag structurally, and `fetch-media.py` cannot close it

`rejectMedia` was 122 rows with no covers after this run. `fetch-media.py` refilled 31.
The gap exists because `fetch-library.py` pulls the good obalkyknih.cz cover from the
**catalogue record**, and a reject has no `recordId` because it never lands in the cache —
so reject rows fall back to Open Library, which is worst on exactly this population
(Czech collections, Czech-language originals). 11 of the 27 remaining nulls are
group-level author/category rows where no single cover would be honest, and those are
correct as null.

## The unknown pool and gate 0, built 2026-08-28 — predictions, then the first run

Everything in this section was written *before* the first run so the run could falsify
it. The measured results are in the section that follows, which is the honest scoring of
these predictions: the yield one held, the gate-0 one did not.

**What the pool is.** 596 undecided works the cheap ranker did not recognise (`rec: 0`)
at raw `s` 4, plus 8,253 at 3 and 1,706 at 2 or below. Every existing selection excludes
them: `ranked()` returns `None` for `rec: 0`, so `--min-score` cannot reach them, and
`--include-unranked` mixes them back into a scored queue where their own ordering is
lost. `--unknown` takes the complement instead — rec=0 only — so the fast-fail rate is
readable against one population rather than a blend.

**Two known numbers bound the expected yield, and they disagree about why.** Measured
2026-08-27 over 100 promoted score-4 books: a recognised 4 reached the 68 propose line
28% of the time, an unrecognised 4 **9%**, Fisher exact p = 0.038. So 120 of these books
should return of order **11 proposals**, not the 33 the last score-4 slice produced. But
`ai_rank.state()` records that population and information are confounded there — a book
Haiku knows is a book the world has written about — so the 9% is not yet known to be a
statement about the *books*.

**Why the ordering changed.** Ranked best-first by the free metadata scorer, the head of
this pool is Czech-original military and local history: 15 of the first 120 have no
author parsed at all, and 14 of the first 18 rows were WWII and regional-history titles.
That is the population gate 0 exists to survive cheaply, not the one to spend a run on.
`researchable()` reorders on what there is to search: an original title (4), a parsed
author (2), a genre or subject heading (1), a series (1). At `--top 120` **all 120 carry
an original title and all 120 have an author**, against 51 and 105 under the old
ordering. Genre mix of the 120: 20 fantasy, 13 SF, 8 women's/romance, 6 horror, 2
detective, the rest general fiction headings; 104 distinct authors, so batching saves
little here and the 15-book batches are mostly mixed.

**Why `orig` is on the task line and only here.** *Králové Wyldu* is unsearchable and
*Kings of the Wyld* is not. Sending the original title costs ~840 bytes per task line
against ~700 and is the difference between a researchable book and a fast fail on a book
that was never hard, only renamed. The ranked queue does not get these fields: a work the
model recognised does not need help being identified.

**What gate 0 costs if it never fires.** Two searches on a book that then goes on to
gates 1-6, i.e. one wasted call on the books that were findable all along — which is why
the gate is scoped to `unknown: true` task lines and why `orig` is searched first and the
gate passes the moment it answers.

**The measurement to take after the first run**, in this order:

1. Fast-fail rate, and the `reason` split. A rate near 0 means the gate is dead weight on
   a researchable pool and should be re-scoped to the low-`researchable()` tail; a rate
   above ~40% means the ordering, not the gate, is what needs work.
2. Proposals at or above 68, against the 11 the 9% base rate predicts.
3. `A-unknown` spend against its budget of 2 — the one gate whose budget was set by
   argument alone, with no prior run behind it.
4. **Sample five parked books by hand.** The failure this gate can hide is an agent
   fast-failing a book it could have researched, and nothing in the output distinguishes
   that from a real absence. `unresearched.tried` exists to make the check cheap.

**Scored on 2026-08-28 over two runs, 240 books: the yield prediction held, the gate-0
prediction was wrong, and `researchable()` rests on the same wrong assumption.** See the
second run's section below.

## The first unknown run: 120 books, 2026-08-28

8 batches at `per=15`, **1,175,397 subagent tokens = 9.80k/book** — under the 10.33k the
last score-4 slice cost, on a population that was expected to be harder.

**All 120 landed: 97 estimates, 23 rejects (9 occult, 8 detective, 4 sexual-content, 2
infidelity). 18 estimates at or above the 68 propose line**, against the **11** the 9%
unrecognised base rate predicted. So the pool does underperform the recognised one, and
it beats its own forecast; the researchability ordering is the plausible reason, since it
front-loaded translated SF and fantasy.

**Yield tracks genre almost perfectly, and that is the lever worth having.** Per batch:
the two SF/fantasy-heavy batches returned 5 and 4 proposals, the commercial-romance and
rural-saga batches 0 and 1. Nothing else in the run separates outcomes this cleanly —
not `researchable()`, not the raw `s`, not the annotation. A genre-heading term in the
ordering is the obvious next experiment, and it is free: `gf` is already on the task line.

### Gate 0 fired zero times in 120, and the ordering is why

Every book in the slice carried an `orig` and every one resolved from it. The gate cost
two searches on books that were findable all along and returned nothing — **on this
slice it is dead weight, and that is a fact about `researchable()`, not about the gate**:
the ordering selects for exactly the field whose absence the gate exists to catch. Its
value is still untested, and it now sits on the tail the ordering pushed to the back.

Do not delete it, and do not widen it. Two things it should keep earning:

- **The catalogue's `orig` is not always right.** `volani-srdce` carries *A Moment in the
  Sun*, which is an unrelated John Sayles novel; the agent noticed, re-identified the book
  through the `translator` field and confirmed it against the Czech annotation rather than
  fast-failing. That is `wrong-book` occurring in the wild on the *first* run — the
  category is real, and here an agent routed around it.
- The next `--unknown` run that reaches works with no `orig` is the actual measurement.
  **Take it deliberately** — a slice ordered by *lowest* `researchable()` — rather than
  waiting for the ordering to drift there.

### Exit mix improved sharply, and gate 4 still leaks the same way

`C-low` 53 (44%), `D-full` 44 (37%), `B` 23 (19%) — against the previous run's 22% / 58%,
so the C/D balance is much closer to what the gate-4 rewrite was aiming at. But **26 of
the 44 `D-full` books (59%) still came back below 68**, essentially unchanged from 52%
and 58% on the two prior runs. The mix moved; the leak did not. That is consistent with
this file's earlier finding that gate 4's two stated tests are self-fulfilling, and it is
now three runs of evidence that the gate's *shape* is the defect.

50 of the 53 C exits wrote `[58, 68]` and 3 wrote `[42, 55]`.

### 23 of 120 files were refused, and every refusal was transcription

19% refusal rate, none of it judgement: 12 files omitted `sources` entirely and 11 wrote
a `why` that named a sibling volume, another candidate, or "in this batch". **11 of the
12 missing-`sources` files came from one agent** — the failure is per-agent, not spread,
which is what makes returning the file to its author the right repair. Six resumes cost
**63k tokens, 5% of the run**, and recovered all 23 including one proposal
(*Tom's Midnight Garden* [68, 78]).

Budgets: `B` gates all at mean 2.00, `C` 1.11 with 6 of 53 over by one, `D` 2.98 against
a ceiling of 6. Confidence: 30 `high`, 90 `medium`, no `low`.

## The second unknown run: 120 books, 2026-08-28

Same shape, the next 120 off the same pool, after the heading veto removed 1,004 works
from the queue. **97 estimates, 23 rejects, 12 at or above 68** - two thirds of the first
run's 18, on a population whose composition had visibly changed.

### Gate 0 is dead. 0 fast fails in 240 books, and the second 120 was its own best case

The first run could be dismissed: `researchable()` had selected 120 books that all
carried an `orig`, which is the field whose absence the gate catches. **This run had 14
of 120 with an `orig` and still produced zero fast fails.** Every book was identified
from the Czech title plus the author - Czech-language series fantasy (Pacovska,
Strachotova, Bartos), a Ukrainian-language Witcher volume, Beast Quest tie-ins, a
Minecraft gamebook, an interactive gamebook.

**The premise was wrong, not the threshold.** "No original title in the catalogue" is not
"unresearchable"; it mostly means the cataloguer did not fill the field. The books this
pool actually contains are commercial and obscure, not *unfindable*, and a title plus an
author is enough to find anything a publisher ever printed.

Two consequences, and the second is the expensive one:

- **The gate costs two searches per book on the `unknown` path and returns nothing.**
  It is not free; it is the cheapest thing in the ladder, which is why it survived
  unnoticed for 240 books.
- **`researchable()` ranks on the same wrong assumption.** It sorts the pool by
  `orig` (weight 4) above everything else, on the theory that an `orig` predicts
  researchability. It does not predict researchability - it predicts *translation*, and
  translated adult fiction is a better population for other reasons. The ordering worked
  for a reason its own docstring gets wrong.

Do not delete either yet. `wrong-book` is real - the catalogue's `orig` for `volani-srdce`
names an unrelated John Sayles novel - and an agent still needs somewhere to put a book it
cannot pin down. But the gate should be **rescoped to identity, not evidence**: fire it
when the sources disagree about which book this is, not when there are few of them.

### Yield tracks genre, and this pool is running out of the genre that yields

12 proposals against 18, and the composition says why. The first slice was translated
adult SF/fantasy; this one added five *Beast Quest* volumes, a Minecraft gamebook, a
*Buffy* novelisation, an interactive gamebook graded [42, 55] for structurally not being
authored fiction, a robot picture book at [30, 42], and three Czech-language series.

The proposals that did land are the same shape as before - `Jmena` (The Names) [74, 84],
`Mor` (Camus) [72, 82], `Diktator` [72, 80], `Dnesek neni naposled` [72, 80],
`Svezest vody` [72, 82], the Staveley trilogy [70, 78] each, `Zpevozar` [70, 80].

**Camus's `Mor` sat in the unrecognised pool**, which is the clearest illustration yet
that `rec: 0` is a statement about the Czech title string, not about the book's obscurity.

Rejects inverted: **16 occult** against 5 detective and 2 infidelity, where the first run
ran 9 / 8 / 2. Occult is where Czech and translated genre fantasy dies - an on-page
sacrificial rite at an altar, jinn cosmology taken from Islam, an embodied Greek pantheon,
a Slavic death-goddess invoked at standing stones.

### Gate C's overspend got much worse and nobody hid it

**44 of 67 C exits went over a budget of 1**, mean 1.79, against 6 of 53 and mean 1.11 last
run. The agents reported it in `why` as the contract asks, which is the only reason it is
measurable. The stated cause is that one search returns several usable reviews at once - so
the budget counts *sources cited* while the cost is *searches run*, and those have come
apart. `D` also drifted, 3.03 against 2.98.

### Refusals: 31 of 120, and series phrasing is now the dominant cause

**Fixed in the dispatch, and it worked: 15 of 120 on the third run.** The next run's agents
were given the REWRITE rather than the prohibition - "write *a sequel*, put the position in
`flags`", plus "`sources` is never empty on an estimate" - and refusals halved. What
survived was the same rule reached through new wording: `mid-series`, `earlier book`,
`later entry`, `series entries`. An agent told not to write one positional phrase reliably
finds another, so the instruction that works is the substitute phrase, not a longer
blacklist.

Up from 23. **21 of the 31 argued from a sibling volume by its ordinal** - "Opening book",
"Book 7", "third volume" - because this run was series-heavy in a way the first was not.
Seven resumes recovered 28. Two agents then swapped one ordinal for another on the retry
and were fixed by hand; one file cited reviewers with an empty `sources` array and needed
a third round. **The regex is doing its job and the contract is not**: an agent that has
just been told not to name an ordinal reaches for a different ordinal, which suggests the
rule needs an example of the rewrite, not a firmer prohibition.

## The third unknown run: 120 books, 2026-08-28

**107 estimates, 12 rejects, 1 held at `low` confidence. 13 at or above 68** - against 18
and 12 on the two prior runs, so the yield stopped falling. The pool did not improve; the
tail did. Batch 006 alone produced 5 of the 13.

Composition was the worst yet - **0 of 120 carried an `orig`**, 30 historical, 28 with no
genre heading at all, and the queue included a Disney partwork retelling, a graded A2/B1
language reader, a Star Wars tie-in, and a dinosaur picture-book series. Six books in one
batch were comics or picture books, all landing [42, 55].

**Gate 0: 0 fast fails again. 360 books, three runs, zero.** The dispatch told these agents
gate 0 was rare and scoped it to identity confusion rather than thin evidence; that is the
rescope this file recommended and it should now go into `promote-prompt.md` itself.

Yield came from ADULT LITERARY AND IDEA-DRIVEN FICTION, not from genre: `Pohlednice`
[74, 84], `Hora v mori` [72, 82], `Sto roku Lenni a Margot` [72, 82], `Kluci z Glasgow`
[72, 82], `Kdyz panda tanci` [72, 82], `Leonard a Hladovy Paul` [72, 80], `Cerna labut`
[70, 80]. The SF/fantasy that carried run 1 is exhausted; what is left of it in this pool
is Czech small-press.

### Two findings worth acting on

**A memoir's factual reliability is a live axis and an agent found it unprompted.** The
three Raynor Winn memoirs landed [42, 55] rather than the [58, 68] default because the
agent found the 2025 Observer investigation disputing the books' core factual claims and
applied `books-read.md`'s own memoir rule - the form is rewarded for examining what is
actually true (Qureshi 91 against Anne Frank 40), so a contested memoir loses the thing it
earns points for. Nothing in the contract asks for a truthfulness check; the reasoning came
from the log.

**`GENRE` has no home for nonfiction argument.** `Cerna labut` (Taleb) had to force a genre
from the closed vocabulary, which has `testimony` but nothing for an idea-driven essay. The
run also produced a rigorous history (`Osvetim`) and a dense academic history. If nonfiction
keeps arriving, the vocabulary needs a term rather than agents picking the least-wrong one.

### A hard filter can split a series, and nothing reconciles it

`Bledy jezdec` (The Pale Horseman) is an `axis:occult` reject - Iseult is a sorceress
delivering an on-page prophecy from Celtic seer-folklore - while `Pohansky pan`, seven
volumes later in the same series, is a [68, 78] proposal. Both verdicts are correct on their
own book and the pair is unreadable as a recommendation. Unresolved: whether a hard filter
firing in one volume should bind the series.

### Budgets

`C` overspent on 26 of 52, mean 1.50 - better than the previous run's 44 of 67 at 1.79,
still not at budget. `D` 2.84 over 56 books against a ceiling of 6. `B-occult` 2.83 over 6.
The C budget still counts sources cited while the cost is searches run.

## Gate 0 removed, 2026-08-28

Ruled by the reader after the third run. **0 fast fails in 360 books across three
deliberately different populations** - 120 that all carried an `orig`, 120 with 14, and
120 with none - so the gate was never a threshold problem. Its premise was wrong: an
absent original title means the cataloguer left the field empty, not that the book is
unfindable, and a Czech title plus an author locates anything a publisher printed.

Removed from `promote-prompt.md` (the gate, its table row, the fast-fail output schema,
the `sources`-may-be-empty exception) and from `promote.py` (`FASTFAIL`, `FF_REASON`,
`load_unresearched`, the validate and absorb branches, the `A-unknown` budget, the
spend-report special case, `--retry-unresearched`, and the `unknown: true` task flag,
which existed only to open the gate). `book-unresearched.jsonl` was never created, so
there is nothing to migrate.

**What stayed, and why it is not the same thing.** The task line still carries `orig`,
`gf`, `kw` and `series` on an `--unknown` run, and `researchable()` still orders on them.
Those earn their place on a different argument than the one that justified the gate:
`orig` does not predict *findability*, it predicts *translation*, and translated adult
fiction is where the yield is - 18 proposals from the slice that all carried one against
12 and 13 from the slices that had almost none. The function keeps its name and now says
so in its docstring; renaming it would break the only thing that makes this history
searchable.

**What this removes is small and honest to state: two searches per book on the
`--unknown` path.** The gate was the cheapest thing in the ladder, which is exactly why
it went unexamined for 360 books. The lesson worth keeping is not "the gate was
expensive" but "a cheap check that never fires is invisible, so it needs a stated
kill condition when it is built" - this one got its measurement plan in the same commit
that created it, and that is the only reason it could be retired on evidence rather than
on taste.

## The children's re-rank, 2026-08-28: the `s` score does not survive a second grading

The reader removed the children's exclusion, which changed the ranking prompt, which
invalidated every verdict. `ai_rank.py restamp` carried forward the 12,230 the rule could
not have touched and 7,353 works were re-ranked by 15 Haiku graders. Then the same 7,353
were graded a second time by 15 fresh graders after a prompt fix. **That accident is the
most useful measurement this pipeline has produced, because it is a blind test-retest of
`s` itself.**

| | run 1 | run 2 |
|---|---|---|
| `>=4` rate per batch | 1.8% - 74.2% | 2.6% - 28.4% |
| mean / stdev | 20.7 / 18.5 | 13.2 / 7.6 |

**Correlation between a batch's run-1 and run-2 rate: r = -0.00.** Per book, over 7,343
graded twice: identical score 62%, agreement on the `>=4` decision 74% against 71%
expected by chance, **Cohen's kappa +0.11**. Only **20% of the run-1 queue survived a
second grading**.

So at this level `s` is very largely grader noise. It is not worthless everywhere - the
2026-08-26 blind holdout measured 77% recall at 75% precision, and the shelf data still
shows recognised-4 books reaching the 68 line 32% of the time against 15% for
unrecognised - but on a homogeneous, low-signal cohort where nearly every annotation is
three lines of Czech publisher copy about a book the model does not know, the score
carries almost nothing.

### The prompt fix worked on the extremes and introduced a worse failure

Adding "a topic is not an idea" plus a stated base rate cut the spread from 41x to 11x and
removed the 74% grader. But the base-rate sentence gave the model a target it could hit
without doing the task, and graders took that route:

- **Batch 006 scored by counting characters in the blurb** - "annotations >=400 characters
  ... thresholds set based on the actual annotation length distribution to achieve
  approximately 1 in 6" - and set `rec: 0` on all 500 rows. It landed at 19.8%, invisible
  in the middle of the distribution.
- Batches 004, 011 and 014 also built mechanical rules and reported hitting ~16.7%.
- Batch 009 hit 15.2% with **60 fives and 16 fours**; every other grader gave 0 or 1 five.

**State a base rate as a ceiling-shaped check, never as a target with a number**: "if you
are marking more than one in six, you are probably scoring topics" - and say explicitly
that a low-signal cohort may legitimately sit far below it. The current wording also cites
the spread as "2% to 49%", which was a figure read off files that were still being written;
the true run-1 spread was 2% to 74%. Both are body text, so fixing them changes the digest
and invalidates verdicts - do it at the next real prompt revision, not on its own.

### Method note, learned the expensive way

**Do not read an agent's output file before its completion notification arrives.** Three
figures reported during this run were taken mid-write and were wrong (batch 003 read as
12.6% finished at 1.9%; batch 005 v2 read as 8.4% finished at 4.8%; batch 004 read as 0%
finished at 24.2%). A partially-written file parses cleanly and looks like a result.
