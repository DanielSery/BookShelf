# AI triage prompt — v3, RUN AND REVERTED 2026-08-26

**Not the live contract.** `tools/ai-rank-prompt.md` is. This file is kept because
v3 was built, run over the whole 11,025-work corpus (~1.5M tokens, 23 Haiku
agents), measured against a holdout, and found to be **worse than v2 on the only
thing that matters**. Two of its three changes were right. Read the measurement
before writing v4.

## What was measured

Holdout: the 113 tier-2 works, which `seal` had excluded from the run, so the
prompt had genuinely not seen them. Each carries a hand-derived `est` range, and
`est` low ≥ 68 is the propose/record line. 112 usable, 64 proposable, 48
recorded-low.

| | v2 | v3 |
|---|---|---|
| recall at `>=4` | **77 %** | **56 %** |
| queue size | 24 % of corpus | 7.5 % of corpus |
| known-good scored `<=2` | — | **11 of 64 (17 %)** |
| recorded-low also scoring `>=4` | — | 50 % |

The 11 lost outright were *Rebelka* (est 82 — the strongest non-fiction match in
the library), *Půl krále* (78), *Přežila jsem čínský gulag* (76), *Slyším tě všude*
(72), *Jurský park* (72), *Proměna* (70), *Naslouchej noži* (70), *Fantastické
povídky* (70), *Cizinec* (68). A `1` or a `2` is not a queue position; those books
would simply have gone.

Caveat on method: this compares a Haiku triage score against a hand-derived
estimate, which is the same proxy v2's 77 % figure used, but on a different holdout
(64 works against 47). Apples to apples in method, not in sample.

## What was right and must be kept

**1. Feeding the catalogue annotation. Keep this.** Measured over the 10,782 v3
verdicts:

| | with annotation | without |
|---|---|---|
| n | 6,398 | 4,384 |
| scored `>=4` | **11.1 %** | **2.4 %** |
| named an idea | 15.1 % | 6.9 % |
| recognised the work | 7.5 % | 3.7 % |

A row with an annotation is **4.6× more likely** to be flagged worth
investigating. That is the single most useful change available to this step.

**2. The `rec` flag. Keep this.** It exposed something v2 hid entirely: asked
directly, the model recognises only **6 % of the corpus** — while 42 % of v2
verdicts were non-3, which implied recognition. So most of v2's confident scores
were not based on knowing the book. On the known-good holdout `rec` was 34 %
against 6 % corpus-wide, so it does carry signal — but note that is the canonicity
bias in a new dress, since canonical books are both recognisable and good.

## What was wrong

**3. The `idea` flag has zero discriminating power. Drop it.** It was the entire
justification for a binary flag over a longer scale — "auditable, unlike a
7-against-9". Measured on the holdout:

- known-good works: **70 %** had a nameable idea
- recorded-low works: **71 %**

One percentage point in the wrong direction. It does not order the `>=4` bucket
and it must not be quoted as if it does.

**4. The reframing of `3` is the likely cause of the recall collapse.** v3 said
*"a `3` no longer means did not recognise it — use `3` for a book you can see
clearly and simply cannot call"*, and simultaneously asked for an honest `rec`
flag. Everything then collapsed toward the middle: the 3-bucket grew from 58 % to
72 %, `1` and `2` shrank from 3,550 to 2,210, and `>=4` shrank from 1,310 to 813.
Honesty pressure plus a widened middle produced a model unwilling to commit.

## What v4 should be

v2's scoring instructions and v2's scale, unchanged, **plus** the annotation in the
input line and the `rec` flag in the output. No `idea` flag, and no reframing of
what `3` means. Then re-measure against the same 113-work holdout before it goes
anywhere near the live store.

`tools/ai_rank.py` only appends the annotation when the live prompt body contains
the word "annotation", so v4 gets it automatically and v2 does not.

---

You are triaging library catalogue rows for one specific reader. For each row
output a recognition flag, an idea flag and a 1-5 plausibility score. You are NOT
predicting how much he would enjoy the book — another system does that properly.
You are answering: **is this worth twenty minutes of expensive investigation?**

Each input line is:

`<id>|<Czech title>|<author>|<publisher>|<year>|<catalogue annotation, may be empty>`

**The annotation is the library's own summary and is usually the best information
you have.** Trust it for premise, protagonist and setting. Do not trust it for
tone or quality: it is publisher copy and it overclaims. It will not tell you how
the book opens, whether a ritual happens in a scene, or how crudely sex is
handled — where it is silent on one of those, do not assume the answer is
favourable.

Reader profile, from 41 scored books:

- Loves: page time on what characters *want and why* over what they do; a premise
  whose consequences are actually worked out; a protagonist who is both interesting
  and worth rooting for; books that leave ideas behind. Tops: Red Rising 95,
  Project Hail Mary 92, Seeking Allah Finding Jesus 91, Mockingjay 91, Speaker for
  the Dead 90, Hunger Games 89.
- Short idea-driven work has the character and emotion rules suspended — but that
  removes penalties, it never adds points. Little Prince 82, Animal Farm 78 and
  Silmarillion 80 are canonical *for their ideas*, not for being short. "Short,
  clean, allegorical" is not a reason.
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

## The three fields

**`rec` — did you already know this work?** `1` or `0`, and answer it honestly.

- `1` means you know the book itself: you could say what happens in it without the
  annotation.
- `0` means you do not. Recognising the *author*, the series name or the genre is
  **not** recognising the work, and neither is inferring from the title.
- Answer `0` even when the annotation let you score confidently.

**`idea` — can you name what the book leaves a reader thinking about, in a
phrase?** `1` or `0`. **MEASURED USELESS — 70 % on known-good against 71 % on
known-low. Do not carry this field into v4.**

**`score` — 1 to 5.**

- **5** — canonical or award-calibre, idea-driven, clearly his shape
- **4** — plausible fit on a nameable strength, worth investigating
- **3** — nothing to place it either way
- **2** — probably not his kind of book
- **1** — hits a hard exclusion

A `3` no longer means "did not recognise it" — `rec` carries that now. Use `3` for
a book you can see clearly and simply cannot call. **THIS REFRAMING IS THE PRIME
SUSPECT for the recall collapse; do not repeat it.**

Output one line per row, nothing else, no preamble:

`<id>|<rec 0 or 1>|<idea 0 or 1>|<score 1-5>|<≤8 words why>`
