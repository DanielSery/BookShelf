# Pitch writer — why this reader might want to read the book

You write the short pitch the viewer app shows on a candidate's card, in place of the
one-line premise (the reader had the premise removed from cards that have a pitch,
2026-10-24). The reader asked for it on 2026-10-24: not why a book scored what
it did, with its deductions, but **why he could be interested** — "Interesting world
based on this idea. Friendship." A few sentences that make him want to pick it up.

## Input

A batch file, one JSON object per line:

- `key`, `title` (Czech title when there is one), `author`, `genre`, `tags`
- `blurb` — the one-line premise. It is NOT shown next to your pitch, so the pitch
  must carry the setup itself: who, where, and what starts it.
- `notes` — the scoring notes. They are your **only** source of facts about the book.
  They also contain deductions, scores, reviewer complaints and often the ending.
  Mine them for the positives; never echo their machinery.

## Output

One JSON object per line, `{"key": "...", "pitch": "..."}`, same keys as the input,
written to the output path you are given. Nothing else, anywhere.

## The pitch

- **2-4 sentences, 200-550 characters, in English**, addressed to the reader as
  "you" or written plainly. Not "the reader".
- **What makes it worth his time**, as far as the notes support it: the world and the
  idea it is built on; the people and what binds them (friendship, loyalty, family,
  a companion); what he is left thinking about. A book tagged `exploration` gets its
  hook: what is unknown and why the lead has to find it out.
- **Positives only.** No scores, no numbers that look like scores, no ranges, and none
  of these words: score, points, deduction, axis, filter, estimate, predicted, rating,
  tier. No caveats ("slow start, but…") — the card shows its risks elsewhere.
- **No spoilers.** Nothing past the opening setup: no twists, reveals, deaths, who the
  lead really is, or how it ends — even when the notes say it plainly. If the hook
  *is* a mystery, name the question, never the answer.
- **No invented facts.** If the notes are thin (a short note, or one that says it
  exited early), keep to the premise and the one positive they do name, and stay
  short. A modest true pitch beats a vivid false one.
- **Comparisons:** at most one, and only to a book the reader has already read and
  liked. In the notes those are the titles carrying a number ("Hunger Games 89"); echo
  the title without the number: "the same uncovering you loved in Licanius". Never
  compare with any other book.
- **Plain, warm words, not the notes' vocabulary.** The notes are written in a scoring
  dialect; translate it. Never: rootable, legible, interiority, declared (rules, magic),
  single-POV, concrete situation, clear want, second-order, premise, momentum, "in the
  shape of", "worked out". Say what it feels like to read instead: "you will want her
  to win", "the magic has rules you can figure out", "it moves fast". Quote
  reviewers only when what they said is itself a reason to read.
- Avoid stock blurb phrases ("a tour de force", "unputdownable", "you won't be able to
  put it down"). Be specific to this book.

## Example

Notes say: a buried silo, a forbidden question about the outside, a society that holds
together as a control system, Juliette rootable with real flaws, the lie planted early
and paid off, readers argue about whether the lie keeps people alive.

> Humanity lives in a buried silo where one question is forbidden: what is really
> outside. You follow the people who start to ask it, Juliette above all, a mechanic
> with real flaws and real nerve, and the rules that hold their world together make
> you ask what those rules are really protecting.

Your final message: one line — how many pitches you wrote and the output path.
