# AI triage prompt — v6 (LIVE since 2026-08-28)

**The body below is NO LONGER byte-identical to `tools/ai-rank-prompt-v4.md`, so the
v4 holdout measured a different prompt and its recall/precision numbers do not
transfer.** v6 = v4 plus two 2026-08-28 changes: children's books stop being a hard
exclusion, and a CALIBRATION paragraph, added because fifteen graders running the same
7,353 rows admitted between 2% and 74% of them at the `>=4` cutoff. `tools/ai_rank.py`
hashes the text after the `---` rule and stores the first 12 hex on each verdict as
`pd`, so this edit invalidated every stored verdict; `ai_rank.py restamp` carried
forward the 12,230 the children's rule could not have touched.

**A grader that reports having read `ai-rank-prompt-v4.md` has read the wrong file** —
the versioned copies beside this one are archives, and this preamble used to point at
v4 as the live body, which is exactly the confusion that produces a stale verdict.

**v4 = v2's body and scale verbatim, plus two things: the catalogue annotation in
the input, and a `rec` flag in the output.** No `idea` flag and no reframing of what
a `3` means — those were v3's two losing changes. v2 is preserved verbatim at
`tools/ai-rank-prompt-v2.md`; v3 and its measurement are at
`tools/ai-rank-prompt-v3.md`.

## The holdout, run BEFORE promotion (2026-08-27)

264 tier-2 works with a hand-derived `est` and a joinable annotation, scored blind by
one Haiku agent. Every one already carried a v2 verdict on disk, so the same works
were measured under both prompts with one variable changed. Ground truth: `est` low
>= 68 means the book was judged worth proposing.

|                     | v2 (was live) | v4 (now live) |
|---------------------|---------------|---------------|
| recall at >=4       | **85 %**      | 44 %          |
| false positive >=4  | 92 %          | **24 %**      |
| precision at >=4    | 35 %          | **51 %**      |
| precision at >=5    | 53 %          | **71 %**      |
| false positive >=5  | 20 %          | **2 %**       |
| good/low mean spread| +0.12         | **+0.26**     |
| known-good lost to a 1-2 | 2        | 2             |

**v4 failed the pre-registered gate — beat v2's recall at >=4 — and was promoted
anyway, deliberately, because the same run showed the gate was measuring the wrong
thing.** v2's 85 % recall comes with a 92 % false-positive rate and a good-vs-low
mean spread of +0.12: at `>=4` it is very nearly "score everything 4", which is the
mechanism behind an `>=4` bucket of 857 works that nobody was ever going to work
through. A shortlist that contains almost everything is not a shortlist.

**Why recall fell, and why that is not simply a loss.** The annotation removes a free
ride. v2's recall is substantially an artefact of rewarding canonicity with no
information, and the known-good set is heavily canonical *because* it was promoted.
Give the model the library's own plot summary and it stops guessing high on a
famous-sounding row and starts reading the premise — which for a mediocre book
reveals mediocrity. False positives 92 % -> 24 % and recall 85 % -> 44 % are the same
effect seen from two sides.

**What this costs, stated plainly:** at `>=4`, roughly half the genuinely good books
now land at 3 instead. The `>=5` bucket is the one to work from — 71 % precision at a
2 % false-positive rate — and a 3 remains "the model could not call it", never a no.

**The annotation effect is confirmed and larger than v3 measured it:** of holdout
rows with an annotation 37 % scored >=4, against 6 % of rows without — 6.2x, where
v3 measured 4.6x. `tools/ai_rank.py` appends it only when this body contains the
word "annotation", which it now does.

**v4 does NOT reproduce the v3 collapse.** v3 lost 11 of 64 known-good works to a 1
or a 2; v4 loses 2 of 96, exactly as many as v2. Dropping the `idea` flag and keeping
v2's framing of a 3 fixed it, so the v3 post-mortem's diagnosis was right.

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
  lines starting at once.
- **A children's book is NOT an exclusion** (ruled 2026-08-28; it was one until that
  date, so ignore any instinct that it still is). It is graded like anything else, on
  the same question: can you name what the book leaves a reader thinking about?
  - **A TOPIC IS NOT AN IDEA.** "Christmas", "friendship", "an adventure", "humour and
    a message", "dragons" are subjects, not ideas, and none of them earns a 4. The test
    is whether you can finish the sentence *"this book leaves you thinking about ..."*
    with something a reader could disagree with.
  - **Do not write "canonical work" unless you can name the canon.** Recognising a
    title is `rec`, not a score. A book you have merely heard of is a 3.
  - Anchors from the reader's own log: *Hobbit* 84 and *The Little Prince* 82 cost
    nothing at all for being for children, *Ranger's Apprentice* 74 and Narnia 67 cost
    a little, a picture book or early reader lands in the 30s or 40s. So: a children's
    book carrying a real idea is a 4; a competent story with no idea you can name is a
    3; a picture book, an early reader, a licensed tie-in or a gamebook is a 2. Being
    for children is never by itself the reason for a 1.

**CALIBRATION — read this before you start scoring.** On a typical slice of this
catalogue **about one row in six earns a 4 or 5**. Fifteen graders ran the same 7,353
rows on 2026-08-28 and admitted between 2% and 49% of them, which is why this paragraph
exists: the score is worthless if it means something different per batch. If you are
marking a third of your rows 4, you are scoring topics and titles you recognise rather
than ideas — go back and demand the sentence above. If you are marking almost nothing,
check you are not treating "I do not know this book" as a reason to withhold a 4 from
one whose annotation plainly describes a worked-out premise.
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
