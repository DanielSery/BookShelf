# AI triage prompt — v5 (CANDIDATE, not live)

**v5 = v4's body and scale verbatim, plus one thing: the catalogue facts field.**
Nothing else changes — not the scale, not the reader profile, not what a `3` means.
v3 lost by changing two things at once and v4 won by changing one, so this changes one.

## Why

`book-catalog.jsonl` has held structured MARC per work since 2026-08-27 — 48,069 rows
— and nothing has ever read it. `cmd_batches()` sent title, author, publisher, year and
annotation, so the librarian's own genre heading and subject keywords were fetched in
the same responses as the annotation and then thrown away, while the model was left to
guess from a Czech title.

Coverage measured over the 10,595 works v4 failed to recognise:

| field | MARC | coverage |
|---|---|---|
| `gf` genre/form heading | 655 | 56.8% |
| `kw` subject keywords | 653 | 51.7% |
| `series` | 490 | 36.6% |
| `orig` original title | — | 13.9% |
| **any of gf/kw/orig** | | **69.5%** |

Only 8.9% of that pool has nothing at all. The bet is that a controlled genre heading
answers the detective and sex-as-plot exclusions more reliably than a model reading
promotional copy, and that `orig` moves recognition where a Czech title is opaque.

## Pre-registered gate

Measured against v4 on the SAME works, one variable changed:

1. **`rec` rises on rows carrying `orig`** — the direct test, and the only one where a
   causal story exists. If this does not move, `orig` is not doing what is claimed.
2. **The `>=4` share does not inflate.** v4's win was precision, not recall: v2 scored
   nearly everything a 4 and produced a 857-work shortlist nobody would work through.
   A v5 that recovers recall by scoring everything 4 again has lost, not won.
3. **Score-1 recall rises on rows whose `gf` names a detective or romance heading** —
   the cheapest claim in the table and the one most likely to hold.

Keep it compressed. It is sent once per batch, so every token here is multiplied by
the batch count.

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

Each row is `id|title|author|publisher|year|annotation|facts`. The annotation is the
library's own Czech summary of that book and is often empty; where it exists it
gives you the premise, the protagonist and the setting.

The last field is the **catalogue facts** — what the librarian catalogued, not what
the publisher wrote. Any part may be missing. It is `;`-separated:

- `orig=` the ORIGINAL title of a translated work. Use it first: a Czech title can be
  opaque where the English one is a book you know. If it names a work you know, you
  know the work — say `rec` 1 and judge on what you know.
- `gf=` the controlled genre/form heading. **This is the most reliable exclusion
  signal you get.** A heading naming detective, crime or mystery fiction is a 1, and
  so is one naming erotic or romantic fiction where that is the whole point. It is a
  librarian's classification of the actual book, so trust it over your reading of
  promotional copy — but a heading alone is never a reason to score 4 or 5.
- `kw=` free subject terms. **Routing, never a verdict** — `láska` sits in plenty of
  serious literary fiction and `magie` in invented systems that are explicitly fine.
  Use them to see what the book is about when the annotation is empty.
- `series=` the series statement.

Judge on what you know of the work; where you do not know it, judge on the annotation
and the facts together. **A row with a genre heading and subject keywords is no longer
uninformative — score it rather than defaulting to 3.** If you have none of the three,
say 3 and move on rather than guessing from the title. A 3 is a useful answer, not a
failure, and it stays the right answer for a row that tells you nothing.

Output one line per row, nothing else, no preamble:

`<id>|<rec>|<score>|<≤6 words why>`

`rec` is 1 if you already knew this specific WORK and 0 if you did not — reasoning
from the annotation or the facts alone is a 0, EXCEPT that recognising the work from
`orig=` is genuine recognition and is a 1. Recognising the author, the series or the
genre is not recognising the work. It does not affect the score; it records what the
score was based on.
