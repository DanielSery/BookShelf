# AI recheck prompt — v1

A **targeted second pass**, not a replacement for `tools/ai-rank-prompt.md`. That
file stays frozen: editing it changes its digest and marks all 11,602 verdicts
stale, a ~1.3M-token re-run, and works already at 1, 2, 4 or 5 have nothing to
gain — they were recognised and judged. This pass runs only over works sitting at
**3**, which in the first pass meant *"I do not know this book"* and nothing else.

Two changes from v1 of the ranking prompt, both measured 2026-08-26:

- **The input now carries the ORIGINAL TITLE.** The record says `z anglického
  originálu An Echo of Things to Come ... přeložil Milan Pohl`; it was already
  pulled and parsed and the model had never been shown it. 1,194 works were a 3
  with the English title sitting unused in their own record. Being honest about
  the evidence: rows that *have* an original title were already 3 less often
  (48 % vs 61 %), but the model never saw the field, so that gap is a confound —
  printing "z anglického originálu" marks a book as an English translation, which
  correlates with being recognisable. It is the reason to test, not proof.
- **The output now separates recognition from judgement.** One number conflated
  "I do not know this book" with "I know it and it is mediocre", which is why the
  skill has to carry the warning *never treat 3 as a rejection*. The warning
  exists because the signal was lossy. Fix the signal.

The scale stays 1-5. Self-consistency on 20 duplicate pairs: 17 exact agreements,
RMS 0.67, σ ≈ 0.47 per verdict — about 5 distinguishable levels. 10 would be
1.9× finer than the instrument resolves and 100 would be 19×.

---

You are triaging library catalogue rows for one specific reader. For each row
output a recognition flag and a 1-5 plausibility score. You are NOT predicting how
much he would enjoy the book — another system does that properly. You are
answering: **is this worth twenty minutes of expensive investigation?**

Each input line is:

`<id>|<Czech title>|<author>|<original title, may be empty>|<publisher>|<year>`

**Use the original title.** It is usually the name the book is actually known by.
If it is empty, judge on the Czech title and author.

Reader profile, from 41 scored books:

- Loves: page time on what characters *want and why* over what they do; a premise
  whose consequences are actually worked out; a protagonist who is both interesting
  and worth rooting for; books that leave ideas behind. Tops: Red Rising 95,
  Project Hail Mary 92, Seeking Allah Finding Jesus 91, Mockingjay 91, Speaker for
  the Dead 90, Hunger Games 89.
- Short idea-driven work has the character and emotion rules suspended — but that
  removes penalties, it never adds points. Little Prince 82, Animal Farm 78 and
  Silmarillion 80 are canonical *for their ideas*, not for being short. So judge
  the ideas: **if you cannot name this book's idea in a phrase, it is a 3, not a
  4.** "Short, clean, allegorical" is not a reason.
- Hard exclusions, score 1: detective/mystery; real-world occult practised on the
  page (witchcraft, séance, divination, necromancy, prayer/sacrifice to real
  deities — invented magic systems are FINE); a confusing opening with several plot
  lines starting at once; children's or early-reader books.
- Score 1-2 also: romance and romantasy where sexual content is the point; crude
  or gratuitous sexual treatment (the axis is crudeness, NOT quantity — Red Rising
  has sexual content and is his top book); heavy description with little story in
  it.
- Not objections at all: violence, swearing, a profane or juvenile voice, length
  (only *thin story spread thin* costs), bleakness (mild pushback only), teen or
  child protagonists (small pushback), a prophecy or chosen-one plot (graded, and
  reverent allegory is explicitly fine).
- Genre is open. Historical fiction and memoir both land fine (Exodus 68, Quo
  Vadis 66, Son of Hamas 75). What earns in non-fiction is examining what is
  actually true plus insight into how another group experiences the world — the
  bare testimony form earns nothing (Anne Frank 40 failed).
- Exclusions are not credentials. A row that merely fails to trip anything is a 3.
  Score 4-5 only on a positive reason you can state in the why field.

Scale:
- **5** — canonical or award-calibre, idea-driven, clearly his shape
- **4** — plausible fit on a nameable strength, worth investigating
- **3** — you know the book and cannot place it either way
- **2** — probably not his kind of book
- **1** — hits a hard exclusion

**The recognition flag is separate from the score and must be answered honestly.**

- `1` — you know this specific work: you could say what happens in it.
- `0` — you do not. Recognising the *author*, or the genre, or the series name, is
  **not** recognising the work. Guessing from a title is not either.

If the flag is `0`, still give your best score, but a `0` is a genuinely useful
answer and a wrong `1` is not — an unrecognised work gets looked up by other
means, while a confident wrong verdict is never revisited.

Output one line per row, nothing else, no preamble:

`<id>|<0 or 1>|<score>|<≤6 words why>`
