---
name: book-suggest
description: "Pick what to read next from the already-screened shelf, or snooze a title. Reads the recorded predictions; it does not screen, derive or recompute. Use when the user asks what to read next, for a book/author suggestion, or says to snooze/skip a suggestion for a while. Also use for '/book-suggest'."
allowed-tools:
  - Read
  - Edit
  - Grep
---

# Book suggest — pick from what is already screened

```
READ -> PICK -> PRESENT -> SNOOZE (on request)
```

**This skill computes nothing.** The predicted score, the risks, the
worldbuilding verdict and the access routes are all already recorded, and three
other things own them:

| Owner | Writes | Invalidated by |
|---|---|---|
| `/book-log` | judgements — every `est` recomputation | a rule moving |
| `/book-screen` | discovery, access facts, first estimates, rejects, covers | time passing |
| `index.html` | nothing — read-only viewer | — |
| **this skill** | the Snoozed list, and nothing else | — |

If you find yourself deriving a score, searching a catalogue or checking a
YouTube link, you are in the wrong skill: that is `/book-screen`. The reason for
the split is that a proposal computed here and a number recorded there would
drift, and two lists that disagree is the exact failure the cache was built to
stop.

**The viewer app does this job better for browsing.** `./serve.ps1` then
<http://localhost:8777/> gives a sortable, filterable grid with covers. Use this
skill when the reader wants a *decision* — "just tell me what to read" — or
wants to snooze something. If they ask to browse, point them at the app.

## Phase 1 — READ

- `book-estimates.jsonl` — the predictions. Roughly sorted best-first, so the
  first 10 book lines are usually the whole shortlist. Line 1 is the header.
- `book-revs.json` — the current counters.
- `book-cache.json` — access routes for the titles you shortlist.
- `book-media.json` — the blurb, so you can say what the book *is*.
- `books-read.md` — so nothing already read is proposed.
- `book-recommendations.md` — the Snoozed section, and only that, unless the
  reader asks *why* a rule says what it says.

State today's date to yourself: Snoozed and the access TTLs both compare dates.

## Phase 2 — PICK

Exclude, in order:

- Anything with `blocked` set — it fails a hard filter.
- Anything in `books-read.md`.
- Anything in Snoozed whose `until` date has not passed.
- Anything with no access route in `book-cache.json`. **But a cached `none` past
  its TTL is not an absence** — *Mistborn* was cached "no audio exists" twice and
  the identical query found a full reading four days later. If the shortlist is
  thin because of stale access data, say so and offer `/book-screen`; do not
  quietly drop the title and do not check it yourself.

Then rank by `est` midpoint and pick. Lead with whichever candidate best matches
the *most recently resolved* open question or preference — that is the freshest
signal about the reader, and it is the one thing the app's static sort can't do.

**Three checks before you hand anything over:**

1. **Dep revs match `book-revs.json`.** A mismatch means a `/book-log` run did
   not finish its PROPAGATE phase. Say so plainly and stop — do not quote the
   stale number, and do not silently re-derive it here.
2. **Access TTLs.** `enAudio: verified` is only 30 days old at most, and every
   link must be liveness-checked before it is handed over. If it is expired, say
   the link needs re-verifying and offer `/book-screen`.
3. **No estimate at all** for a book that has a cache entry — that is a broken
   invariant, not a book to skip. Report it; `/book-screen` fixes it.

## Phase 3 — PRESENT

Default to **three** titles, not ten: the app exists for breadth, so this skill's
job is a short, argued shortlist. Give more if asked.

Per title, quote what is recorded — never a fresh number:

- **The range and its band**, e.g. "predicted 78-85, A/S border". Never collapse
  it to one number.
- **Every axis in `risks`**, stated as a condition. The range assumes none of
  them fires. *Neuromancer* is 72-80 if its opening holds and a 30 if it doesn't,
  and "76" would be a lie about both outcomes.
- **`leanedOn`** — what the prediction rests on. If the reader disagrees with
  *that*, the number is wrong and it is worth knowing which axis to argue.
- **The blurb** (what it is) and **`why`** (why they'd like it) — in that order.
  They are different fields on purpose.
- **The access route**, Czech title first for print, and every part linked for a
  multi-part audiobook.

**Argue each title against read books, never against the others on the
shortlist** (2026-08-26). Order them by `est` midpoint, but do not invent a
comparison — "cleaner than the other Hrabal" is a judgement nobody recorded, and
it is exactly the reasoning the estimates were rewritten to remove. A recorded
`flag` naming a sibling volume is a fact and is fine to pass on ("read volume 1
first").

Group by access route — Czech print and free English audio are different
decisions for this reader. Say when the unofficial-upload caveat applies: once
for the whole group, not per title.

## Phase 4 — SNOOZE (on request)

Append to the Snoozed section of `book-recommendations.md`:
`- **Title** — until YYYY-MM-DD (reason)`.

Snooze is for *preference* — not right now, not in this mood. **An absent access
route is never a snooze**: that is a dated fact, it belongs in
`book-cache.json`, and eight titles were once snoozed for "not in the library"
and had to be un-snoozed when that stopped being true. A taste objection is not a
snooze either — that is a reject row, and `/book-screen` writes it.
