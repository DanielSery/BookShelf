---
name: book-deep
description: "Deep-dive candidates one at a time until enough of them hold a good predicted score: read the opening from an authorized excerpt, read the critical reader reviews, settle every axis with a sourced verdict, and re-derive the estimate from that evidence. Takes a filter (genre, form, audience, access route), a target count and a dive budget. Use when the user asks for a deep dive, a deeper or verified recommendation, or 'find me N good <genre> books'. Also use for '/book-deep'."
allowed-tools:
  - Read
  - Write
  - Edit
  - Grep
  - Bash
  - Agent
  - WebSearch
  - WebFetch
---

# Book deep — dive until the shelf holds enough good books

```
SELECT -> DIVE (parallel) -> RECORD -> STOP? -> (loop) -> VERIFY -> PRESENT
```

**Why this exists.** Every prediction failure in `book-recommendations.md` (Open
questions) has the same shape: the axis the estimate never examined is the one that
decided the score. A screening estimate is one pass over a blurb, a catalogue record
and the screener's memory, and its `why` argues the two or three axes it leaned on.
A dive examines **every** axis against sources: the opening is read rather than
recalled, and the people who disliked the book are heard rather than averaged away.

**What it does not fix.** About half the recorded misses came from a rule that was
wrong (*Válka starého muže*, *Licanius* 1-2), not from an axis left unexamined. Only
`/book-log` corrects a rule. A dived range is still a prediction from second-hand
evidence.

## Ownership

A dive is new information about one book, not a rule change, so this skill is the
third writer of `book-estimates.jsonl`. It owns:

| File | Writes |
|---|---|
| `book-deep.jsonl` | one dossier line per dived book — the per-axis evidence |
| `book-estimates.jsonl` | the dived book's line: `est`, `leanedOn`, `risks`, `why`, `deps`, `at`, `depth` |

It never touches the rules, the revs, the cache, rejects or Snoozed. A hard filter
that fires becomes `blocked` on the estimate line; writing the reject row is
`/book-screen`'s job, so say it is needed and stop there.

`/book-log` keeps every *recomputation after a rule moves*, and for a deep line it
re-prices the dossier's verdicts under the new rule instead of re-deriving from
scratch. That is what keeps a dive from decaying back to a screening guess the
first time an axis is reworded.

## Arguments

- **Filter**: any of `genre` (sf · fantasy · litfic · historical · testimony ·
  allegory · thriller, or the tag `exploration`, which matches `tags` instead), `form`,
  `audience`, matched against `book-cache.json`.
  Several genres means one independent run per genre, each with its own target.
- **Route**: `cz` — Czech print verified in the library (what the reader means by
  "hard cover" or "paper") — `en`, or `either` (default).
- **Target**: how many good books to find. Default 3.
- **Budget**: the most dives per run. Default 8. Hitting it is a result, not a
  failure: report what was found.

`dive <title>` instead dives that one book, whatever its rank, and skips Phase 4. A
book already dived is re-dived only this way.

**Good** means `est[0] >= 80` **and** `risks` empty after the dive. A risk still
open after a dive is an axis the evidence could not settle, and a range conditional
on an unsettled axis is not a recommendation.

## Phase 1 — SELECT

`python tools/deep.py select --genre fantasy --route cz` does the mechanical part
of this. From `book-estimates.jsonl` × `book-cache.json`, keep lines that:

- match the filter and have the route verified (`cz.state` / `enAudio.state` ==
  `verified`, within `_ttlDays`);
- are not `blocked`, not in `books-read.md`, not in Snoozed;
- carry no `depth` yet. A book already dived is not re-dived: it counts toward the
  target from its recorded range and is reported from its dossier;
- **can be read next**: skip a volume whose earlier volume is unread. Check
  `prereq` (`need: hard`) and also `series` and `flags`, because most cache rows
  carry no `prereq`. Dive the earliest unread volume instead, if it is a candidate.

Order by `est` midpoint, highest first. Dive in batches: the first batch is the
target size, each later batch is the shortfall. Never more than the budget.

## Phase 2 — DIVE

One `general-purpose` subagent per book, all of a batch in parallel, run in the
background. Brief each with `python tools/deep.py payload <scratch>/deep <key>...`,
which writes the estimate line, the cache entry, the Czech edition, the blurb and
the valid axis ids to one file per book; the prompt names that file, tells the
subagent to follow "The dive" below, and adds anything specific to the book worth
checking first (a staged rite, a sequel's dependency, a collection's order). The
subagent writes **one file only**, its dossier JSON at `<scratch>/deep/out/<key>.json`,
and returns the same JSON. Repo files are the orchestrator's.

A dive takes 15-25 minutes and about 250k subagent tokens. When the shortfall is
certain before a batch finishes, launch the next candidate rather than waiting.

### The dive (subagent instructions)

**Read first:** `book-recommendations.md` from `## Scoring` up to `## Authors`
(the rules and the failure record; the Authors and Candidate tables below are off
limits) and `books-read.md` (the scores to anchor on).

**Gather, at minimum:**

1. **The opening, from text.** An authorized excerpt of the first chapter: a
   publisher's excerpt page, BookBrowse, the author's site, a Reactor/Tor excerpt, a
   Czech publisher's *ukázka*, Google Books. Read it and judge filter 2 on what it
   contains: how many threads start, and whether the reader has the context to read
   the first scene. **No excerpt found means `axis:opening` is `unknown`**, unless
   several readers independently describe the opening in the same way.
2. **The critical voices.** Goodreads 1-3 star reviews, and the comments on
   databazeknih.cz (`?c=all`, every page) and cbdb.cz. Look for the reasons people
   stopped and where.
3. **The facts the filters key on.** Plot summaries and content notes (Wikipedia,
   StoryGraph content warnings, reviews): how power is *conferred* in the world, not
   only how it is used; any investigation-shaped strand; sexual content on volume,
   explicitness and crudeness; infidelity; a same-sex romance and its prominence; a
   one-sided competence contrast between the sexes; how prophecy and faith are
   handled; the ending.
4. **The praise, priced as carefully as the complaints.** Five of the ten recorded
   misses were *under*-predictions. A dive that only hunts for problems repeats them.

**Verdict per axis.** Cover the six mandatory axes (opening, occult, detective,
worldbuilding, protagonist, motives), every axis in the line's `leanedOn` and
`risks`, and every other axis the evidence touches:

| `v` | Meaning |
|---|---|
| `earns` | the evidence shows this axis adding points |
| `clear` | checked, costs nothing |
| `costs` | a graded deduction; say how big, in the rule's own terms |
| `fires` | a hard filter fails: the estimate becomes `blocked` |
| `unknown` | the sources do not settle it |

Each verdict carries a `note` (one to three sentences, a short quote where one
exists) and `src` (the URLs it rests on). A verdict with no source is the reader's
memory, not evidence: say so in the note, and never use it to clear a hard filter.

**Price it.** Derive the range from read books in `books-read.md` and from the
verdicts, never from another candidate and never from the screening range: the
dive replaces that number rather than adjusting it. Rules for the range:

- **`risks`** = the `unknown` axes that could put the book below its range. A known
  cost is priced into the range, not listed as a risk.
- **No narrower than 6 points.** The evidence is still second-hand.
- **`leanedOn`** = the axes that actually carry the number.
- If a hard filter fires: `est` null, `blocked` = that axis id.
- Name the reading-order situation: standalone, volume 1, or which volume it needs
  first.

**Write the `why`** (600-1400 characters) in the shelf's register: it argues from
read books with their scores and from the axes, in its own words. It names no other
candidate, no series other than its own, no other book's predicted range, and
nothing batch-relative ("the strongest of these"). `python tools/crossrefs.py` scans
both files and fails on any of those.

**Return** exactly one JSON object and nothing else:

```json
{"key": "...", "est": [80, 86], "blocked": null, "leanedOn": ["axis:..."],
 "risks": [], "why": "...", "readingOrder": "standalone",
 "axes": {"axis:opening": {"v": "clear", "note": "...", "src": ["https://..."]}}}
```

## Phase 3 — RECORD

`python tools/deep.py record <scratch>/deep/out/<key>.json ...` does steps 1-3 and
refuses the whole call if any file fails a check (`--check` only validates). For
each returned dossier:

1. **Sanity-check it before writing.** Every axis id exists in `book-revs.json`; the
   six mandatory axes are present; no `fires` without `blocked`; `risks` lists only
   `unknown` axes; the width is at least 6; the `why` cites read books. Send it back
   to the subagent (SendMessage) rather than patch a judgement yourself. **Read the
   `fires` and the hard-filter `costs` verdicts yourself**: two subagents can draw
   one boundary differently, and a rule question is the reader's to settle, so
   name it in Phase 6 rather than smoothing it over.
2. **`book-deep.jsonl`**: append one line, `json.dumps(ensure_ascii=False)`:
   `key`, `at`, `pre` (the line's `est`, `leanedOn`, `risks` before the dive),
   `est`, `blocked` if set, `readingOrder`, `axes`. `pre` is what makes a dive
   measurable: when the book is read, `/book-log` compares both against the real
   score.
3. **`book-estimates.jsonl`**: rewrite that one line in place. `est`/`blocked`,
   `leanedOn`, `risks`, `why` from the dossier; `deps` = the line's `author:` and
   `series:` ids plus every axis in `axes`, each stamped with its current rev; `at`
   = today; `"depth": "deep"`. Keep the file's format: one
   `json.dumps(ensure_ascii=False)` object per line, in whatever newline the
   working copy has (LF in git, CRLF after an autocrlf checkout).

## Phase 4 — STOP?

Count good books per run. Under target and under budget: select the next batch and
go back to Phase 2. Otherwise stop.

## Phase 5 — VERIFY

- Both files parse one object per line; every `depth: deep` line has exactly one
  dossier line and vice versa (read books' dossiers stay, with `actual`).
- No dep rev on a touched line differs from `book-revs.json`.
- `python tools/crossrefs.py` exits 0.
- **Liveness-check the library record** of every good book before presenting it —
  the catalogue API with the title's diacritics stripped (see Access-checking
  methods in `book-recommendations.md`).

## Phase 6 — PRESENT

Per run: the good books first, each with the range out of 10 in whole numbers, what it leaned on, the
two or three verdicts that moved it most since the screening range (old → new), and
the library route. Then every other book dived, one line each with old → new range
and the axis that kept it out. Say plainly when a run hit its budget short of the
target. Dived ranges are predictions: never present one as more than that.
