# AI triage prompt — v4 (staged, not live until it beats v2 on the holdout)

**This is v2's body with exactly two changes, both of them the ones v3 measured as
wins.** The v3 experiment (`tools/ai-rank-prompt-v3.md`) was built, run over the
whole corpus for ~1.5M tokens, measured, and reverted: recall at `>=4` fell from
77 % to 56 % and 11 of 64 known-good works dropped to a 1 or a 2. Its post-mortem
separated the three changes it had made all at once:

- **Feeding the catalogue annotation — the big win, kept here.** A row with an
  annotation scored `>=4` 11.1 % of the time against 2.4 % without: 4.6x. Named an
  idea 15.1 % vs 6.9 %, recognised 7.5 % vs 3.7 %.
- **The `rec` flag — kept here.** Asked directly, the model recognises only ~6 % of
  the corpus, while 42 % of v2 verdicts were non-3 and thereby *implied*
  recognition. Most of v2's confident scores were not based on knowing the book,
  and `rec` is what makes that visible instead of invisible.
- **The `idea` flag — dropped.** Measured useless: 70 % of known-good works had a
  nameable idea against 71 % of known-low, one point in the wrong direction.
- **Reframing what a `3` means — dropped, and it was the prime suspect for the
  recall collapse.** v3 told the model a 3 no longer meant "did not recognise"
  while also demanding an honest `rec` flag, and everything then collapsed toward
  the middle: the 3-bucket grew 58 % -> 72 % and `>=4` shrank from 1,310 to 813.
  Honesty pressure plus a widened middle produces a model that will not commit. So
  the scale below and the "say 3 and move on" instruction are **v2's, verbatim**.

**Why the annotation matters more now than it did in August.** The store held
11,626 annotations when v3 ran; it holds 16,078 today, because the children's-shelf
sweep of 2026-08-27 added 4,453. Coverage on the ranking population is what decides
whether the 6,519 works currently sitting at 3 are a dead bucket or the best
unopened one in the database — they were all scored blind on title, author,
publisher and year.

**Do not copy this file over `tools/ai-rank-prompt.md` until the holdout says so.**
Promoting it changes the live digest and marks every stored verdict stale, which is
the intended escape hatch and also a ~1.3M-token commitment. The holdout comes
first — that is the single step the v3 run skipped, and skipping it is what the
1.5M tokens bought.

An annotation is publisher copy. It reliably carries premise, protagonist and
setting. It does **not** carry opening structure, whether occult is enacted in a
scene, crudeness of sexual treatment, or the idea the book leaves behind — and it
overclaims in one direction, which is worse than noise. Weigh it accordingly.

---

You are triaging library catalogue rows for one specific reader. For each row output
a 1-5 plausibility score. You are NOT predicting how much he would enjoy the book —
another system does that properly. You are answering: **is this worth twenty minutes
of expensive investigation?**

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
- **3** — can't tell from this metadata alone
- **2** — probably not his kind of book
- **1** — hits a hard exclusion

Each row is `id|title|author|publisher|year|annotation`. The annotation is the
library's own Czech summary of that book and is often empty; where it exists it
gives you the premise, the protagonist and the setting. Judge on what you know of
the work, and on the annotation where you do not know it; if you have neither, say 3
and move on rather than guessing from the title. A 3 is a useful answer, not a
failure.

Output one line per row, nothing else, no preamble:

`<id>|<rec>|<score>|<≤6 words why>`

`rec` is 1 if you already knew this specific WORK and 0 if you did not — reasoning
from the annotation alone is a 0. Recognising the author, the series or the genre is
not recognising the work. It does not affect the score; it records what the score
was based on.
