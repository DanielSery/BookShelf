---
name: book-log
description: "Log a finished/DNF'd book with a tier rating and consolidate what it implies into book-recommendations.md. Use when the user reports having read, finished, or given up on a book, gives it a score out of 100 or a letter tier (F/C/B/A/S/S+), or asks to correct/update an existing rating. Also use for '/book-log'."
allowed-tools:
  - Read
  - Write
  - Edit
  - Grep
---

# Book log — record a read book and consolidate findings

Two files live at the repo root: `books-read.md` (flat tier log) and
`book-recommendations.md` (living analysis: reader profile, author rankings,
open questions, snooze list). This skill keeps the second one honest against
the first, the same way `/dream` consolidates transcripts into memory —
except the "transcript" here is just what the user says in this turn.

A third file, `book-estimates.jsonl`, holds the predicted score for every
unread candidate. **This skill owns it.** `/book-suggest` only reads it, so
every recomputation happens here, while the rule change that caused it is in
hand — see Phase 4.

```
CAPTURE -> LOG -> CONSOLIDATE -> PROPAGATE -> VERIFY
```

## Phase 1 — CAPTURE

From the user's message, extract:
- Book title and author (infer the author if the user only names the book and
  you're confident; say so if guessing).
- Score: **0-100**, with the letter tier as the derived band (95-100 S+,
  85-95 S, 75-85 A, 65-75 B, 50-65 C, <50 F; on a boundary the higher band
  wins). Record both. If the user gives only a letter, place it mid-band and
  say so. If the user gives stars or a vague sentiment
  instead of a tier, convert it and say what you mapped it to.

  **Elicit by comparison, not by number.** The reader finds it much easier to
  say what he liked better than to name a figure, so when a score is uncertain
  — a new book, a hesitant number, or a crowded band — don't ask "what score?".
  Pull 3-6 already-scored books from the neighbouring range, list them with
  their scores, and ask him to slot the new one in or to order the group.
  Then derive the number from where it lands and say what you derived.

  **The scale is absolute, not a ranking — any number of books may share a
  score, and ties are never a defect** (confirmed 2026-08-22). The log is
  heading past 100 entries, so collisions are inevitable and expected. Never
  offer to break one, never nudge a score by a point to avoid one, and use the
  comparison technique only to place a *new* book, never to re-litigate
  existing ones. A tie is a finding: two books liked the same amount.
- The *why*: what specifically worked or didn't (pacing, a confusing/unclear
  opening, content objections, ending, POV structure, DNF point). Capture it
  whenever it's offered — it's what Phase 3 runs on.

  **But completeness of the *why* column is not a goal** (stated 2026-08-22).
  Do not maintain a backlog of books with missing reasons, do not report it as
  a gap, and do not ask the reader to fill one in for its own sake. Ask about a
  specific older book only when its reason would actually change a conclusion
  you're about to write — then ask that one question, in context.

## Phase 2 — LOG

Read `books-read.md`. If the book is already a row, **update it in place**
(score, notes) rather than adding a duplicate — note in your reply what
changed from the old value. Otherwise add a new row in the existing table
format (`Book | Author | Score | Tier | Notes`), keeping the table sorted by
score, descending. **Where the new score equals an existing one, insert
adjacent to it and don't agonise over which side** — order within an equal
score is arbitrary and carries no meaning, so don't reorder tied rows or read a
preference out of their sequence.

## Phase 3 — CONSOLIDATE

`book-recommendations.md` is compact agent notes, not prose: short fact
bullets with an `Evidence:` tag, plus tables for Authors and Candidate books.
No narrative meta-commentary ("this was later revised because...") — if a
conclusion changes, replace it and let the Evidence tag carry the citation.
Read the whole file before editing it. For this one data point, work out:

1. **Does it confirm or deny an existing Author-table row?** Update that row's
   `Status`/`Evidence`/`Note` cells in place — move the author between
   statuses (`Top pick`, `Predicted fit`, `Revisit`, `Downgraded`, `Avoid`,
   `Mixed`, `Confirmed fit`) as the evidence now supports. Don't add a second
   row for the same author.
2. **Does it reveal a new Filter or Preference** not already listed? Add one
   compact bullet with an `Evidence:` tag. Prefer sharpening an existing
   bullet over adding a near-duplicate — e.g. "slow start" was later
   sharpened to "confusing/unclear opening" once a second data point came in;
   there should only ever be one bullet per axis of taste.
3. **Does it contradict something already written?** Resolve destructively —
   overwrite the old claim and its Evidence tag, never leave two bullets
   asserting different things about the same axis.
4. **Does it turn a Candidate book into a read book?** Remove its row from
   "Candidate books not yet read" — it now belongs only in `books-read.md`.
5. **Does it close or sharpen an Open question?** Delete it if resolved, edit
   the wording if sharpened, reopen (don't just add a duplicate question) if
   new data undercuts a prior resolution.

Keep edits surgical — this is a single new fact, not a rewrite of the file.
Every bullet/row should be traceable to a specific book+tier; if you can't
point to one, it doesn't belong in the file.

**The doc must not grow with the log.** The log is heading past 100 books
(2026-08-22), so evidence tags cite the two or three *strongest* exemplars for
an axis — ideally a controlled pair, same author or same series — not every
book that touches it. When adding a book to a bullet would make it a list,
replace a weaker citation instead. Same for the Authors table: one row per
author, and group authors that carry no individual signal.

## Phase 4 — PROPAGATE

Phase 3 may have moved a rule. Every predicted score derived under the old
wording is now wrong, and this is where they get fixed — **not at suggestion
time.** `/book-suggest` is a pure reader of `book-estimates.jsonl`; if it ever
has to recompute, this phase failed.

`book-revs.json` holds the revision counter for everything an estimate can
depend on. In `book-estimates.jsonl`, line 1 is a schema header and every other
line is one candidate, carrying the `deps` it was computed under, the `leanedOn`
dep that actually produced the number, and the `risks` that could collapse it.
The two files are split so that a grep for a dep id returns book lines only.

**1. Retire the logged book.** It has a real score now, so delete its line —
but first record the calibration point, because a prediction that missed is
worth more than one that hit. If the actual score falls outside the cached
`est` range, add or sharpen one bullet under Open questions in
`book-recommendations.md` naming **which `leanedOn` dep was wrong**. Both
failures so far — *Artemis* (predicted 80, scored 69 after its 2026-08-27
revision down from 76) and *Mortal Engines* 55
— came from leaning on the wrong axis, not from bad information, and
`leanedOn` is what makes the third instance visible instead of anecdotal.

**2. List the dep ids this entry actually moved.** These are already decided by
Phase 3 — you don't re-derive them:

- `axis:<x>` for every rule you added, sharpened, contradicted or reworded.
  A rule whose *wording* changed counts. New evidence cited under an unchanged
  rule does **not** — that bumps nothing.
- `author:<x>` and `series:<x>` for the book just logged, always. A real score
  is new information about that author.
- `_epoch` only when you suspect the deps themselves are wrong, e.g. after
  editing the profile by hand outside this skill. It revalidates everything.

Bump each by one in `book-revs.json`. When nothing but an author moved — the
common case, since most entries confirm the profile rather than change it — that
single edit plus step 3 is the entire propagation.

**3. Grep the subset — don't read the file.** One search per bumped id:

```
Grep -n "axis:worldbuilding" book-estimates.jsonl
```

The dep ids are literal tokens on one line per book, so the matched line
numbers *are* the affected subset — grep is the reverse index, which is why
there is no index to maintain and nothing that can drift out of step with the
deps. Take the union across bumped ids. **Report the size of that union before
touching anything** — "worldbuilding sharpened → 12 of 35 estimates affected" —
because a heavy-axis change can reorder the top of the candidate list, and the
reader needs to know that happened.

Subsets are genuinely small for most rules: the sexual-treatment axis reaches 5
of 35 lines, prophecy 4, a single author 1-3. The mandatory-minimum axes reach
all 35 by design, and that whole file is ~22 KB of one-line records — the access
data that would have made a full pass expensive lives in `book-cache.json` and
is never read here.

**4. Recompute the subset, at two depths.** Read only the matched lines.

- **The bumped id is in that line's `leanedOn`** → re-derive the range from
  scratch against the new rule text. Expect it to move.
- **The bumped id is only in `deps`** → ask whether the new wording moves this
  book at all. Usually it does not, and the honest outcome is the same numbers
  with a fresh stamp. Do not manufacture a change to look diligent.

Either way update `deps` to the new revs, set `at` to today, and rewrite `why`
if the reasoning changed. Every matched line gets its stamp updated even when
the number holds — an un-stamped line reads as stale forever.

Three guards on the numbers themselves:

- **Never predict a book up on worldbuilding when the lead looks thin.** That
  is the *Artemis* error, and the protagonist axis outranks worldbuilding.
- **The range is conditional on `risks` not firing.** A book whose risk axis is
  the hard clarity filter is not a 75 with a caveat — it is a 75 or a 30. Keep
  the range and the risk separate rather than averaging them into a hedge.
- **Re-derive from read books and rules only — candidates never mention each
  other** (2026-08-26). A range calibrated against a neighbouring estimate is a
  guess anchored to a guess, and this phase is where that would spread: a book
  logged today moves its author's rev, and any estimate that had leaned on a
  sibling candidate would inherit the correction silently instead of being
  re-argued. So a rewritten `why` cites scores from `books-read.md` and the axes,
  in full, even when two volumes end up making the same case. Sequence and
  edition notes are facts — they live in `flags` in `book-cache.json`. Run
  `python tools/crossrefs.py` before reporting done.

**5. Hard filters produce `blocked`, not a low number.** If a rule change means
a book now fails an absolute bar, set `blocked` to that axis id and `est` to
null; if it un-blocks one, derive a real range. **Access never appears here** —
`book-cache.json` is authoritative for that, and an access state is a dated
fact about the world, not a judgement about the book. Duplicating it is what
let *Mistborn*'s "no audio exists" survive two passes after it stopped being
true.

**6. Carry the facets across** (added 2026-08-27). A logged book leaves
`book-cache.json`, and with it the `genre` / `form` / `audience` the viewer app
filters on — so every new row in `books-read.md` needs a matching entry in
**`book-read-facets.json`**, keyed on `slug(title)` (the same key as
`book-media.json`'s `readMedia`). Copy the three values straight off the cache
entry you are deleting; that is the whole job when the book was a candidate, and a
one-line judgement when it was not. Values: `genre` sf · fantasy · litfic ·
historical · testimony · allegory · thriller; `form` novel · novella · stories ·
nonfiction · poetry; `audience` adult · ya · childrens.

Miss it and nothing breaks loudly — the Gaps panel names the book and the Read
tab's facet filters exclude it, deliberately, because an unclassified book is not
evidence of being an adult one. **Delete the facet row when you delete a read row**,
or it shows up as an orphan key.

The same applies to **`book-origin.json`** (added 2026-08-28), on the same
`slug(title)` key: move the `books` entry of the book you are deleting into `read`.
Nothing can rederive it afterwards — `tools/fetch-origin.py` regenerates `books` from
the cache entry that no longer exists, and it merges `read` rather than recomputing
it, precisely because this step is the only place the value survives.

**7. Keep the invariant:** one line in `book-estimates.jsonl` for every book in
`book-cache.json`, and no line for a book in `books-read.md`.

## Phase 5 — VERIFY

Before reporting done:
- No duplicate rows for the same book in `books-read.md`, and no author
  appearing in two rows of the Authors table in `book-recommendations.md`.
- `book-read-facets.json` has exactly one entry per row of `books-read.md` — no
  missing key and no orphan:
  ```
  python -c "import json,io,re,unicodedata;s=lambda x:re.sub(r'[^a-z0-9]+','-',''.join(c for c in unicodedata.normalize('NFKD',x) if not unicodedata.combining(c)).lower()).strip('-')[:60];f=set(json.load(io.open('book-read-facets.json',encoding='utf-8'))['facets']);L=io.open('books-read.md',encoding='utf-8').readlines();h=[i for i,l in enumerate(L) if re.match(r'^\|\s*Book\s*\|\s*Author\s*\|\s*Score\s*\|',l,re.I)][0];r=set();
  [r.add(s(c[0])) for c in ([x.strip() for x in l.strip().strip('|').split('|')] for l in L[h+2:] if l.strip().startswith('|')) if len(c)==5 and c[2].isdigit()];print('missing:',r-f);print('orphan:',f-r)"
  ```
- Every bullet/row added or changed traces to a specific tier/note you just
  logged, not to a hunch.
- No book appears in both the Authors/Candidate-books tables as "unread" and
  in `books-read.md` as read.
- `book-estimates.jsonl` still parses one object per line, the logged book's
  line is gone, and no line carries a dep rev that isn't the current one.
- `python tools/crossrefs.py` exits 0 — no `why` argues from another candidate.
- Report, briefly: what was logged, what changed in the recommendation doc,
  any contradiction you resolved, and — from Phase 4 — which revs you bumped,
  how many estimates that touched, and which predictions actually moved, with
  the old and new range for each.
