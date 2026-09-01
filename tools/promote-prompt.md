# Promotion prompt — v2 (Sonnet)

This file IS the contract for a full tier-2 promotion: find out what the book
actually is, derive the estimate, emit it. **Every word here is re-sent on every turn
of every batch, so the evidence behind these rules lives in `tools/promote-notes.md`,
which you do not read.**

**Two structural rules, not negotiable.**

1. **You never write to `book-cache.json`, `book-estimates.jsonl` or
   `book-media.json`.** You write ONE JSON file per book into a staging directory;
   `python tools/promote.py absorb <dir>` folds them in. Promotions run in parallel,
   and read-modify-write on a shared JSON file loses work silently.
2. **`book-estimates.jsonl` is not calibration and must not be cited** — nor may you
   read `book-cache.json` or `book-recommendations.md`. **Every range in the
   estimates file is an unverified guess** written by a model about a book nobody has
   read; not one has been checked against a real reading. Anchoring to one anchors a
   guess to a guess, and `absorb` refuses any `why` that names another candidate or
   quotes another candidate's range. **`books-read.md` is your only ground truth.**

**Access is already resolved — never query the library catalogue.** Your task line
carries `cz`, the verified Czech print route, precomputed offline by
`tools/fetch-editions.py`. Copy it into your output unchanged. One such query returns
111 kB of JSON for 200 bytes of signal, which is why this step is gone. English-audio
checking is out of scope; leave `enAudio` alone.

---

You are promoting one book to tier 2 for a single reader's shelf database: research
the book and produce a predicted-score range with the reasoning that justifies it.

## Step 1 — read the reader

Read `books-read.md` in full — **real scores from this reader, your only
calibration** — and `tools/reader-profile.md` for the rules. The short version:

- **Loves** page time on what characters *want and why* over what they do; a premise
  whose consequences are actually worked out; a protagonist who is both interesting
  *and* worth rooting for; a book that leaves an idea behind.
- **Five hard filters, and only five:** a confusing opening with several plot lines
  starting at once; real-world occult *practised on the page*; detective/mystery; a book
  whose premise IS an affair within a marriage or engagement, whatever the framing; and
  a book whose plot is mainly sexual behaviour or a sexual relationship. Everything else
  is graded, never a veto. (No-readable-route was a sixth and is now decided for you in
  `cz`.)
- **Graded, with measured weights:** sexual content on three dimensions that all cost —
  volume, explicitness and crudeness (*Artemis* 69 docked for crudeness at small volume,
  *Ready Player One* 55 and *The Witcher* 53 sunk by volume); worldbuilding self-consistency; heavy
  description with little story; how far toward a children's book it sits; bleakness
  (mild); teen or child lead (small); prophecy, graded on reverence not resemblance.
- **Violence and swearing are not objections at all.**

## Step 1.5 — the exit ladder: STOP AS SOON AS THE ANSWER IS DECIDED

**Do the cheapest decisive check first.** A full promotion costs about 90k tokens and
the queue is a thousand books, so finishing the research on a book that was already
decided is the largest waste available.

### The budget is a number, and the last run inverted it

Measured over 128 books on 2026-08-26: every gate except the one with a stated ceiling
overran, and `C-low` — the cheapest question in the ladder — spent 3.25 sources against
a budget of 1, which is **23% of every source read in the whole run** wasted on one
gate. Rejects were only 8% of spend in total.

So the budgets below are counts, not encouragements, and **the count you may spend is
fixed by the gate you exit at, not by how interesting the book turns out to be.** If
you have already spent more than the gate allows by the time you decide, say so in
`why` — an honest overspend is recoverable, a silent one is not measurable.

### Read snippets; do not fetch whole pages

The same 128 books cited **117 large reference pages** — Wikipedia, Goodreads,
TVTropes, per-book Fandom wikis, SuperSummary, LitCharts. Fetched whole those are
50-200 kB each, and they stay in your context for the rest of the batch.

**A search result's snippet is usually the whole answer.** Fetch a page only when a
specific question is still open after the snippets — how many POVs are live at the end
of chapter one, or whether a rite is performed on the page — and then prefer the one
page most likely to say so over three that might.

Your task JSON carries `annotation` — the library's own summary — and `signals`, hard-
filter words that appeared in it. **`signals` is a hint about what to check first,
never a verdict.** "Laska" appears in serious literary fiction and "magie" in
invented systems that are explicitly fine; 17% of the queue trips one and most are
not exclusions.

### The six gates, in cost order

Each gate is a question that is cheaper than the work it lets you skip, and they are
ordered by what they cost to answer — **not** by which is most serious. The 2026-08-26
ladder asked both hard filters first, which put its single most expensive question
(occult, mean 6 sources) ahead of its cheapest decisive one (below-the-line, 1 source).
It is now split, and `axis:occult` comes after C. `axis:infidelity` was added
2026-08-27 and sits second, because its prominence half is blurb-cheap;
`axis:sexual-content` was added the same day and sits third for the same reason.

| # | gate | `exitAt` | budget | asks |
|---|---|---|---|---|
| 1 | detective | `B-detective` | 2 | is the satisfaction whodunnit? |
| 2 | infidelity | `B-infidelity` | 2 | is infidelity the premise of the book? |
| 3 | sex as the plot | `B-sexual-content` | 2 | is the plot mainly sexual behaviour or a sexual relationship? |
| 4 | below the line | `C-low` | 1 | will this land under 68 whatever else I find? |
| 5 | occult | `B-occult` | 4 | is a rite performed on the page? |
| 6 | full | `D-full` | 6 | everything else |

**NOT a filter: children's books.** Ruled by the reader 2026-08-26 — the exclusion
belongs to the *triage* sweep that keeps the children's section out of the queue, so
once a book is in front of you it is **graded on `axis:childrens`, never vetoed.**
Grade it by how far toward a children's book it actually sits: *Hobbit* 84 and *The
Little Prince* 82 cost nothing, *Ranger's Apprentice* 74 and Narnia 67 a little, a
picture book lands in the 30s or 40s. It always gets a number.

**Your task line may carry `orig`, `gf`, `kw` and `series`** — the original title, the
catalogue's genre/form heading, subject keywords and the series name, when the record
has them. **Search `orig` first when it is there**: *Králové Wyldu* returns nothing and
*Kings of the Wyld* returns everything, and they are the same book. When it is absent,
the Czech title plus the author is enough — measured over 360 books, every one was
identifiable that way.

**Gate 1 — detective/mystery.** The cheapest research question in the ladder: is the
reader's satisfaction finding out who did it? A blurb usually answers it, and the three
detective rejects of the last run cost 3, 3 and 4 sources. Two is the budget.

**Gate 2 — infidelity.** Ruled by the reader 2026-08-27. **Scope: marriage or
engagement only** — a betrayal between unmarried partners is ordinary relationship
drama and does not touch this axis at all.

Your task line may carry **`infidelity`** — `{tier, premise, hit}` from
`tools/screen-infidelity.py`, a lexicon pass over the catalogue annotation. `tier` is how
well the needle binds to a marriage (`strong` binds alone, `medium` needs a marriage word
nearby, `weak` neither); `premise` means the hit landed in the annotation's first
sentence. **It is a reason to look, never a finding** — publisher copy does not disclose
structure, and the screen's errors run both ways: `milenka` is "mistress" or merely
"lover", and 9% of works carry no annotation to search. **Absence of the field is not
evidence of absence** — this axis is in `MANDATORY`, so you examine it either way.

**If infidelity is the PREMISE, reject. Always, whatever the framing.** That is the
whole veto test and framing does not enter it: a novel that condemns the affair and
ruins the adulterer is rejected exactly like one that celebrates it. So the question is
only about prominence, which a blurb usually answers — hence two sources, and hence
this gate sitting at the cheap end. **You do not need to establish how it ends.**

**Premise means: remove the infidelity and there is no book.** It is the main plot, the
central relationship, or the engine of the conflict. Not premise: one marriage among
several threads, a betrayal in a character's backstory, an affair that starts in the
last act of a book about something else. If you genuinely cannot tell premise from
subplot, that is a `subplot` grading with the doubt stated in `why` — do not reach for
the reject, because a wrong reject is unrecoverable.

Below premise level it is **graded on two dimensions that multiply, each severe enough
on its own**: *prominence* (incidental / subplot) and *framing* (condemned or shown as
destructive / neutral / **approving** — celebrated, presented as liberation, or simply
unpunished).

| | condemned | neutral | approving |
|---|---|---|---|
| **incidental** | a point or two | a few points | **50-60** |
| **subplot** | a few points | **45-55** | **30-40** |
| **the premise** | **REJECT** | **REJECT** | **REJECT** |

- **Literary reputation earns nothing here.** *Anna Karenina*, *Madame Bovary* and
  *Effi Briest* are rejects, not low scores. The adulterer being ruined is not a
  defence — the reader is still being asked to spend a novel inside the affair.
- **Approving framing bites even when brief.** One scene that treats an affair as the
  brave or romantic choice is worth a drop into the 50s on its own. On this axis "only
  occasional" is not a defence at all, because framing is what bites.

**Gate 3 — sex as the plot.** Ruled a **separate axis** from gate 2 by the reader
2026-08-27: an affair and a sex plot are different objections and are graded
independently, then both applied. A book can fail one and be clean on the other, so
`axis:infidelity` and `axis:sexual-content` each get their own examination and neither
verdict is evidence about the other. Do not merge them into one deduction.

**If the plot is mainly sexual behaviour or a sexual relationship, reject** — the same
premise test as gate 2: remove it and there is no book.

Below premise level, grade on **three dimensions that compound, each costing on its
own**, and note there is **no framing dimension here** — condemned or approving belongs
to gate 2 alone, and that is precisely what separates the two axes:

| dimension | what it costs, anchored in the log |
|---|---|
| **volume** | *Ready Player One* 55 and *The Witcher* 53, both sunk mainly by this |
| **explicitness** | how much is enacted on the page rather than implied |
| **crudeness** | *Artemis* 69, docked for this at small volume |

- **"Only occasional" mitigates volume and nothing else.** It never rescues high
  explicitness or crudeness, and is never an argument for eligibility.
- **Do not cite *Red Rising* 95 as evidence that volume is free** — it is low on all
  three dimensions and so was barely docked. A book that never incurred a penalty is not
  proof the penalty does not exist.
- Amount counts here as it does at gate 2 (corrected 2026-08-27 — earlier versions of
  this file said this axis ignored quantity, and the reader overruled that).

**Gate 5 — occult** comes *after* C on purpose, and the reason is worth stating because
it looks like a downgrade of the reader's own filter and is not. The occult question is
the most expensive one here — it turns on what is enacted in a scene, so it needs
textual evidence, and it cost mean 6 sources. **A book that already exits at C-low is
off the reading list either way**, since nothing under 68 is ever proposed, so paying 4
sources to also learn it is occult buys a distinction that changes no decision.
Consequence, and it is deliberate: **a C-low book carries an unexamined occult status.**
Say so in `why` in one clause, and keep `axis:occult` in `deps` — that is exactly what
makes it findable when `/book-log` bumps the axis.

When a filter fires at gate 1, 2, 3 or 5, fill `reject` with it and the evidence, set `est`
to null and `exitAt` accordingly, and STOP. Do not research the graded axes; they
cannot change the outcome. Require actual evidence — never infer a reject from
`signals` alone, because being wrong on a reject is not recoverable and being wrong at
C is.

**On a reject, `sources` supports the reject and nothing else, and `confidence` is
about the reject.** You are not expected to have established the opening structure of a
book you just disqualified for being a murder mystery, so do not go and find out.

**Gate 4 — will this book land below the 68 line whatever else you find?** After the
annotation and *one* search, establish two cheap and largely factual things — **what
form** (novel / novella / stories / non-fiction) and **what genre** — then answer:

> **Do you doubt the idea holds up?** Not "can you name an idea" — name one, then ask
> whether you would list `axis:ideas` under `risks`. If you would, exit.

Exit at C on either:

- **Literary fiction *and* a short-story collection.** 81% of such books sit below
  the 68 line: two penalties compound, since `axis:short-idea-driven` suspends the
  character rules but adds nothing, and a collection with no single premise has no
  `axis:ideas` to lean on.
- **You would put `axis:ideas` in `risks`** — the strongest separator in the data,
  47% of books below 68 against 7% of books above it.

Then set `confidence` to `medium`, `exitAt` to `"C-low"`, do no further research, and
write **one of two bands** — nothing in between, because the decision is what matters
here and the number is not worth refining at one source:

- **`[58, 68]`** — the default. A competent book that will probably sit just under the
  line. 47 of the 53 C exits on the last run wrote this or `[60, 70]`.
- **`[42, 55]`** — no idea you can name at all, *and* a form that suspends the
  character tests: a slight collection, a picture book, an occasional piece. This band
  is new because the mandated 60s was measurably too generous — 14 of the books that
  went to *full* research came back with a low under 58, and three agents overrode the
  C mandate downward rather than write a number they did not believe.

**`leanedOn` is still mandatory at C, and it is the axis whose doubt carries the
number.** An early exit is not a reason to leave it empty — one agent left it empty on
11 of its 15 files on 2026-08-27 and every one was refused. At C the number is carried
by the thing you named in the `why`: `axis:ideas` when there is no idea, or
`axis:protagonist` / `axis:character-differentiation` / `axis:worldbuilding` when that
is what you actually argued. Transcribe the axis you already reasoned from; `risks` may
then be empty.

**One source is the budget and is sufficient.** A C-low range is a recorded, revisable
number, not a verdict that has to survive scrutiny, and `medium` is the right
confidence precisely because you stopped. Sourcing it four times over does not make the
number better — it makes it a `D-full` pass wearing a `C-low` label.

**Gate 4 is not a shortcut either.** It answers "will this land below 68 whatever else
I find", not "have I done enough". A canonical idea-driven book, a first-contact
premise worked out, a memoir that examines what is actually true — those go on. Exiting
at C on a book that deserved D is the same failure as the reverse, just cheaper.

**But the last run erred the other way, and by a lot.** 38 of its 66 `D-full` books —
**58%** — came back with a low *below* 68, at mean 4.6 sources each. Gate 4 existed to
catch those at one source and did not fire on a single one of them. So when you are
weighing C against going on, the base rate says C is more often right than it feels.

**Gate 6 — full promotion.** Only for books that survive 1 through 5. Set `exitAt` to
`"D-full"`. This is where the research below belongs, and where the estimate needs to
be tight enough to trust near the 68 line. **Four sources is normal and six is the
ceiling** — past that you are confirming what you already concluded. Where several
books share an author, the author-level research is shared and counts once.

**Being at Gate 6 is a decision, not a default.** If you are about to start deep
research you have implicitly answered gate 4 with "no, the idea holds" — and on the
last run that answer was wrong 58% of the time.

## Step 2 — find out what the book actually is (gate 6, and the narrow checks in 1, 2, 3 and 5)

Search the web. You need enough to answer the axes honestly, and the ones that decide
a hard filter are worth a specific search:

- **How does it open?** How many plot lines or POVs is a reader tracking by the end of
  chapter 1? The most reliable predictor in the log — three books scored 30 on it. If
  you cannot establish it, say so in `flags`.
- **The occult filter — two tests, and failing EITHER is a veto.** Ruled by the reader
  2026-08-26, replacing an earlier "an invented magic system is fine however
  elaborate", which was wrong.
  - *Source* — a system drawn from actual occultism fails: witchcraft, spellcasting in
    that mould, séance, divination, necromancy, sacrifice or prayer to real deities.
    An invented system passes this test.
  - *Depiction* — **a rite enacted on the page fails even when the system is
    invented.** A practice mentioned as having happened is fine.
  - **The escape is mechanism.** A system operated like technology or engineering —
    declared rules, no invocation, no devotion, no priesthood — passes Depiction even
    when used on the page: Sanderson's Allomancy, Bennett's Founders scriving,
    Asimov's mentalics, salvaged "elf-magic" that is really pre-collapse tech.
    **Resemblance still vetoes** — in the reader's words, "if it's mechanical it could
    be plausible explanation to keep it normal, but if too similar to occult it should
    be still vetoed". A mechanical label on something that reads like occultism does
    not save it.

  So the question is not "is the system invented?" but **"is a rite performed on the
  page, and is there a genuinely mechanical account of it?"** An invented goddess with
  a priesthood performing devotions is a veto; an invented physics is not.
- **Is the reader's satisfaction an investigation?** A mystery-shaped subplot in an
  otherwise eligible book is a flag, not a veto — say which it is.
- **Sexual content: how is it handled**, not how much there is.
- **What does it leave you thinking about**, in a phrase? If nothing, say nothing —
  "beautifully written" is not an idea, and claiming one you cannot name is the
  easiest way to produce a wrong estimate.

## Step 3 — the Czech route (given, not researched)

Copy `cz` from your task line into your output verbatim, including the full 36-char
`recordId`. Two fields need reading rather than copying:

- `cz.edition` is `print` normally, or **`adapt`** when the only Czech holding is a
  retelling, abridgement or comics adaptation. That is a different book from the one
  you are researching — say so in `flags` and let it affect the estimate.
- `cz.state: "none"` means no Czech print edition exists. **Still produce the
  estimate.** Absence of a route is a dated fact, not a verdict on the book.

`alts` on the task line lists other editions the catalogue holds. Those are facts;
put the relevant ones in `flags`.

## Step 4 — derive the estimate

**Argue only from `books-read.md` scores and the rules.** Never from another
candidate. Cite the specific read book that anchors each claim: "the axis
*Mockingjay* 91 and *Speaker for the Dead* 90 both score on", not "similar to other
books in the queue".

- `est` is `[low, high]`, **conditional on nothing in `risks` firing**. Typical span
  about 10 points. Use `null` only when a hard filter already fails, and then fill
  `reject` instead.
- `leanedOn` is the axis or two actually carrying the number. Both recorded prediction
  failures came from leaning on the wrong axis: *Artemis* was predicted 80 and scored
  69 because the prediction leaned up on strong worldbuilding while the lead was
  visibly thin, and *Mortal Engines* was abandoned on premise logic the prediction had
  never examined.
- `risks` are the axes that could collapse the estimate below its range. Always a
  subset of `deps`.
- **A low estimate is a valid, wanted outcome.** A book that fails on a graded axis
  gets recorded in the 50s or 60s, not rejected — that is how the same canonical name
  stops resurfacing forever. Reserve `reject` for a *named hard filter*.
- **Clearing the filters is not a reason to score well.** "Short, in Czech, no occult"
  describes a book that has merely failed to disqualify itself. Every estimate needs a
  positive case in its own words.

## If you are given several books at once

Batching pays the fixed reading cost once. It does **not** make the books a
comparison set:

- **Never write "in this batch", "the strongest of these", "unlike the others"** or
  anything else batch-relative. An estimate that depends on which books happened to
  be grouped with it is not reproducible — regroup the queue and the number moves.
- **Never name a sibling volume in `why`, or refer to one by position.** That the
  series opener was rejected, that volume 2 is missing, that a later volume is the
  stronger entry point: those are **facts**, and facts go in `flags`, where naming
  other titles is correct and expected. `absorb` refuses a `why` containing "the
  series opener", "volume 3", "the stronger entry", "mid-series" and the like.

  **`axis:sequels` itself is a legitimate argument** — "a sequel, and sequels are not
  safe bets in this log: Hitchhiker's 83 to 70" reasons from a *read* book. What is
  banned is the ordinal: write "a sequel", not "a volume 3".

A batch may hold up to twenty books by one author. **Research the author once, then
judge each book on its own.** Shared research is what the grouping buys; a shared
verdict is not.

`why` answers "why this number for this book, against books he has actually read".
Nothing else belongs in it.

## Step 5 — write exactly one JSON file

Path: `<staging-dir>/<key>.json`, using the `key` from your task line.

```json
{
  "key": "ruze-pro-algernon",
  "title": "Flowers for Algernon",
  "czTitle": "Růže pro Algernon",
  "author": "Daniel Keyes",
  "series": null,
  "genre": "sf",
  "form": "novel",
  "cz": {"state": "verified", "publisher": "Knižní klub", "year": 2000,
         "translator": null, "recordId": "4a3c1c67-....-full-uuid"},
  "est": [84, 92],
  "leanedOn": ["axis:ideas", "axis:protagonist"],
  "risks": ["axis:bleakness"],
  "deps": ["axis:ideas", "axis:short-idea-driven", "axis:bleakness"],
  "why": "One premise declared precisely and the whole book is its consequences...",
  "blurb": "Charlie Gordon, a man with an IQ of 68, keeps a diary through the surgery that makes him a genius.",
  "flags": ["A second print translation exists (Lucie Bohemia 2011, Richard Podaný)."],
  "reject": null,
  "confidence": "high",
  "exitAt": "D-full"
}
```

On a reject most fields are unknown and that is correct — send `key`, `author`,
`czTitle`, `cz`, `exitAt`, `why`, `blurb`, `sources`, and `reject`. Do not invent a
genre, a form or a page count you did not establish.

Field rules:

- `genre`: one of `sf fantasy litfic historical testimony allegory thriller`.
  `form`: one of `novel novella stories nonfiction verse`. **`verse` carries a penalty
  of its own** — ruled 2026-08-27 on *Havran* 40, which ties the lowest score in the log
  and where the reader named the form itself as a cause. Grade it on `axis:verse`. This
  is NOT the short-idea-driven suspension: short prose merely fails to earn points,
  whereas verse costs.
- `deps`: axis and author ids you examined. **Do not invent revision numbers** —
  `absorb` fills them from `book-revs.json` and adds the six mandatory axes plus the
  author id.

  **The axis vocabulary is closed. These 25 ids are the only ones that exist:**

  ```
  axis:bleakness                  axis:character-differentiation
  axis:childrens                  axis:content
  axis:density                    axis:detective
  axis:faith                      axis:ideas
  axis:infidelity                 axis:life-phase
  axis:memoir-form                axis:momentum
  axis:motives                    axis:multi-pov
  axis:occult                     axis:opening
  axis:prophecy                   axis:protagonist
  axis:sequels                    axis:sexual-content
  axis:sexual-treatment           axis:short-idea-driven
  axis:unearned-competence        axis:verse
  axis:worldbuilding
  ```

  A near-miss is worse than an omission and your file will be refused: when a rule
  changes, `/book-log` bumps that id's counter and greps the estimates for it, so a
  dep spelled almost-right is never found and the estimate goes stale forever.

  `axis:childrens` is how juvenile the book itself is — register, audience, simplicity
  of the telling. Keep it distinct from `axis:life-phase`, which is only the small
  pushback for a protagonist far from the reader's age.

- **`leanedOn` and `risks` must not overlap.** `leanedOn` is what carries the number
  and is what makes a wrong prediction diagnosable; `risks` is what could collapse it
  *below* the range. If you want to say "my number depends on this axis and I am
  unsure how it resolves", **widen the range or lower `confidence` instead**.
- `why`: a few sentences. The positive case, then the deductions, then which axis you
  leaned on and why *not* another. De-accented ASCII, to match the file.
- `blurb`: one or two neutral sentences of plot. No evaluation.
- `flags`: facts, not judgements — other editions, reading order, an `adapt`-only
  route. This is where sibling titles are allowed to be named.
- `reject`: `null`, or `{"filter": "axis:occult", "why": "..."}` naming exactly one
  hard filter with the evidence. When set, `est` must be `null`.
- `confidence`: **tied to the two questions that decide a hard filter**, not to how
  you feel about the estimate. `high` — you established *both* the opening structure
  and the occult question from sources you can cite. `medium` — one is inferred rather
  than sourced. `low` — neither; the file is then held back for a human check instead
  of absorbed. If you did not find a source that says how the book opens, you are not
  `high`.

  **`high` is a `D-full` outcome only.** At any earlier exit you deliberately stopped
  before establishing those two things, so `medium` is correct and complete there —
  `medium` at an early exit is the ladder working, not a gap to go and close.

- `sources`: the URLs you actually used, within the gate's budget — 2 at B, 1 at C, four
  normal and six the ceiling at D. **Never empty.** An unsourced claim about how a book
  opens is the failure mode this whole step exists to avoid. The catalogue record is not
  a source; it is given to you.

Write the file. Do not print it. Your final message is one line: the key, the est
range, and `reject` if you set one.
