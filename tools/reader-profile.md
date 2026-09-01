# Reader profile — the distilled rules

Derived from `book-recommendations.md` on 2026-08-26 and **kept in step with it by
hand**. If the two disagree, that file wins and this one is stale.

It exists for two reasons, one about cost and one about correctness.

**Cost.** `book-recommendations.md` is 63k characters, about 16k tokens, and a
promotion agent read all of it *per book*. Across a 1,011-book queue that is
~16M tokens spent re-reading identical text. This is ~8k characters.

**Correctness.** The bulk of that file is the Authors table, which names unread
candidates together with their statuses. Agents that read it started arguing from
candidate rows instead of from real scores — the exact cross-reference defect
`tools/promote.py absorb` now blocks. Removing the table removes the temptation.

What is dropped: derivation, dated corrections, the Authors table, the Candidate
table, Snoozed, and the access-method appendix. What is kept: every rule that
decides a score.

---

## Scoring

Score out of 100. **95-100** almost perfect · **85-95** enjoyed very much ·
**75-85** a nice read · **65-75** ok · **50-65** disliked · **<50** actively
disliked. On a boundary the higher band wins.

A score is **peak minus pushbacks, not an average** — a modest book with no
downsides ties an ambitious one with several. A and B bands are acceptable
outcomes, not failures; only sub-65 is a thing to avoid.

## The six hard filters — and there are only six

1. **No readable route.** Czech print, or a free English audiobook. English text
   breaks immersion. A promotion agent does not check this one — the Czech route
   arrives on its task line, precomputed by `tools/fetch-editions.py`.
2. **A confusing or unclear opening.** It is *confusion*, not slowness: several
   plot lines starting at once before any is legible. Wants one concrete starting
   situation and to be invested immediately. Difficult but legible is fine. This is
   the most reliable predictor in the log and one of only two causes that have
   ended a book unfinished in its first chapters.
3. **Occult, in any setting. Two tests, and failing EITHER is a veto** (ruled
   2026-08-26, resolving a contradiction between the *Divine Cities* drop and the
   *Jonathan Strange* pass). *Source* — a system drawn from actual occultism fails
   (witchcraft, spellcasting in that mould, séance, divination, necromancy,
   sacrifice or prayer to real deities); an invented system passes this test.
   *Depiction* — **a rite enacted on the page fails even when the system is
   invented**; a practice mentioned as having happened is fine. **The escape is
   mechanism**: a system operated like technology or engineering — declared rules,
   no invocation, no devotion, no priesthood — passes Depiction even when used on
   the page (Allomancy, Founders scriving, Asimov's mentalics, salvaged tech
   "elf-magic"). **Resemblance still vetoes** — "if it's mechanical it could be
   plausible explanation to keep it normal, but if too similar to occult it should
   be still vetoed". So the question is not whether the system is invented but
   **whether a rite is performed on the page and whether there is a genuinely
   mechanical account of it.**
4. **Detective and mystery novels.** Also watch for investigation-shaped subplots
   in otherwise eligible books — flag those rather than dropping them.
5. **Infidelity as the premise of the book** (ruled 2026-08-27). **Always a reject,
   whatever the framing** — condemning the affair and ruining the adulterer is no
   defence. Premise means: remove the infidelity and there is no book. Marriage or
   engagement only. Below premise level it is graded, not vetoed — see the axis
   below.
6. **Sex as the plot** (ruled 2026-08-27, in the reader's words: "when the plot is
   severely/mainly about sexual behavior/relationship"). Not a marriage rule and not
   about explicitness: the test is what the book is *for*. If the plot is mainly a
   sexual relationship or sexual behaviour, reject — remove the sex and there is no
   book. A relationship novel where the sex is one thread among the characters' lives
   stays graded, and so does a book whose *theme* is desire or sexuality while its plot
   is about something else. Below premise level the axis is graded on all three of
   volume, explicitness and crudeness — see the axis below.

**A hard exclusion is INHERITED by any sequel that depends on the excluded book**
(reader's rule, 2026-08-31). Not a seventh filter — a propagation of the six above.
**The unit is dependency, never the series:** *Mort* 83 is volume four of a series
whose volume one was abandoned at 30, and it is that author's best result in the log,
so "same series" cannot be the test. Ask one question: **can this book be read without
the excluded one?** If the plot continues it, or the lead or premise is introduced
there and assumed rather than re-established, the exclusion carries — emit `blocked`
with that axis id and no range, because a range says *unlikely* where the truth is
*unreachable*. If the book restarts with its own lead and premise, it does not inherit.
Your task line may carry a `siblingRejects` note naming an already-excluded book by the
same author; **that is a hint about what to check, never a verdict** — confirm it is the
same series and that this volume actually depends on it before inheriting, and say in
`why` which way you decided and on what evidence. An availability problem in the
predecessor never propagates; only a taste filter does.

**Clearing the filters is not a reason to propose.** "Short, in Czech, no occult"
describes a book that has merely failed to disqualify itself. Every estimate needs
a positive case stated in its own words.

## Graded axes, in rough order of weight

- **Motives over action.** Page time on what characters want and why beats page
  time on what they do; set-piece action with no character revelation is dead
  weight. Four controlled author comparisons all agree.
- **The protagonist must be interesting *and* worth rooting for** — two separate
  failure modes, and **this beats worldbuilding when they compete.** Not rootable:
  a villain lead or a slow descent into evil, however well written — 22 points
  separated two books by the same author in the same world on this alone. Not
  interesting: flat even when likeable and competent.
- **Does it hold up under thought — the author must follow the rules he lays
  down.** Self-consistency with declared commitments, never an external realism
  audit. Nothing obliges an author to explain anything, but whatever he asserts,
  foregrounds or undertakes to explain becomes binding. Five forms of one breach:
  declare a capability and the world must carry its consequences; undertake to
  explain and the explanation must hold; take a society as your subject and it must
  cohere; declare a resource scarce or sacred and it must behave so; declare a
  trait in a character and it must be shown.
  - Where nothing is declared, **reality binds — set by the tech level the book
    presents, not the date it is set in.**
  - **Jurisdiction is per world and cross-world duty scales with the traffic,
    which has a direction.** Check each direction separately. A declared
    institution can discharge the duty outbound and leave inbound wide open — for
    hidden-world and portal fiction, find who crosses over and stays, and ask what
    they bring.
  - **Obligation scales with how precisely the thing is declared** — the author
    sets his own bar. Vague, numinous magic owes little. **Rules add obligation,
    not bonus.**
  - **Exemption follows how hard the book leans on the thing, not what it is
    nominally about.** Don't grant it just because a book is character-led.
  - An answer anywhere in the book counts, so "explained later" is a valid
    defence — but verify it, because the reader verifies. A sequel does not count.
  - Graded, never a bar. It adds points too, **but never predict a book up on
    worldbuilding when the lead looks thin.**
- **Wants higher things to think about** — a book should leave ideas behind, not
  just events. The most common reason a competent book stalls in the 60s.
- **Short idea-driven work has the character and emotion rules suspended — but the
  suspension removes penalties, it never adds points.** The canonical short books
  that score well are canonical *for their ideas*; that is selection bias, not a
  property of short fiction. A short book with thin ideas lands in the 60s like any
  other thin book. **Name the idea in a phrase — if you cannot, that is the
  finding**, and "it's short, so it's low risk" is not a case for reading it.
- **Infidelity — premise level is a reject, below that graded on how much and how it
  is framed** (ruled 2026-08-27). **Marriage or engagement only.** Premise level —
  remove the infidelity and there is no book — is **always a reject, whatever the
  framing**, so *Anna Karenina*, *Madame Bovary* and *Effi Briest* are rejects rather
  than low scores; ruining the adulterer is not a defence. Below that the two
  dimensions multiply and each is severe alone: an approving incidental moment lands in
  the 50s, a neutral subplot 45-55, an approving subplot 30-40. Both axes veto at premise
  level and both grade on amount below it (corrected 2026-08-27) — the two are now the
  same shape, and the distinction the older notes drew between them is gone. What still
  differs is *framing*: an affair can be condemned or approved and that multiplies the
  deduction, where sexual content has no equivalent dimension.
- **Sexual content — three dimensions, and all three cost** (corrected 2026-08-27, the
  third revision of this axis): **volume** (how much of the book it is), **explicitness**
  (how graphically it is shown) and **crudeness** (how it is treated, and what it is
  crude *about*). Each costs on its own and they compound.
  **Do not use *Red Rising* 95 as evidence that volume is free.** That was the previous
  wording's error: Red Rising is low on all three dimensions, so it was barely docked at
  all — it is not a book with a lot of explicit content that escaped a penalty. The
  correct reading of the log is *Artemis* 69 docked for crudeness at small volume,
  *Ready Player One* 55 and *The Witcher* 53 sunk by volume, and Red Rising unaffected
  because there was little to affect it.
  **"Only occasional" is mitigation, not clearance.** Low volume genuinely reduces the
  deduction — that is what makes volume a dimension — but it never rescues high
  explicitness or crudeness, and it is not an argument that a candidate is eligible.
  A profane or juvenile *register* is still not the objection; it is the sexual
  references specifically.
  **Above all three sits filter 6:** if the plot is mainly sexual behaviour or a sexual
  relationship, prominence vetoes and no amount of tasteful handling saves it.
- **Verse does not work, whatever it is about** (2026-08-27). *Havran* 40 ties the
  lowest completed score and the reader named the form itself as a cause, alongside
  occult. Distinct from the short-idea-driven suspension: short prose merely fails to
  earn points, verse carries a penalty. Graded on `axis:verse`, and `form` is `verse`.
- **Story density is the penalty term, not length.** What costs is a thin story
  spread over many pages, and description, digression and drawn-out endings.
  **Never discount a candidate for being long**; a long, densely plotted book
  carries no penalty.
- **Unearned competence** — ability and status given rather than earned.
- **Prophecy and chosen-one plots: graded, never a filter.** Some prophecy about a
  saviour is fine. **The axis is reverence, not resemblance** — the closest Christ
  figure in fiction is explicitly *not* an objection, so never flag a parallel for
  merely existing. What costs is careless resonance a book hasn't earned, or a
  treatment played for ridicule. Subversion is judged on tone: a manufactured
  saviour played straight is fine, played for cynicism is not. **Do not screen out
  epic fantasy for having a prophecy.**
- **Sustained bleakness — disliked, but mildly.** The least severe recorded
  objection. A discount, not a bar. Companionship and self-sacrifice beat solo
  survival.
- **Faith as a thread inside a story**, not as the whole of it. No theology or
  apologetics as a subject in its own right.
- **The memoir/testimony form earns nothing by itself.** What earns is examining
  what is actually true, plus insight into how another group experiences the world.
  The same form produced both the highest non-fiction score and an outright DNF.
- **How much of a children's book it is — graded, never a filter** (ruled
  2026-08-26). The children's exclusion belongs to the catalogue sweep, which keeps
  that section out of the queue; a book already under consideration gets a number.
  *Hobbit* 84 and *The Little Prince* 82 pay nothing, *Ranger's Apprentice* 74 and
  Narnia 67 pay a little, a picture book lands in the 30s or 40s. Distinct from
  life-phase below: this is the book's register and audience, not the lead's age.
- **Protagonist life-phase proximity — a small pushback only** (reader is 28).
  Worth a couple of points, never a tier, never a reason to reject. What counts is
  how the inner life reads, not the stated age.
- **Not objections at all:** violence, swearing, a profane or juvenile voice,
  genre, length, teen or child protagonists in themselves.

## Genre

Open. The SF/fantasy skew in the log is a sampling artefact. Historical fiction,
memoir and allegory have all been read and none disliked.

## Two recorded prediction failures — both from leaning on the wrong axis

One book was predicted 80 and scored **69** because the prediction leaned *up* on
strong worldbuilding while the lead was visibly thin — an 11-point miss, not the
4-point one earlier versions of this file recorded, because that book was itself
revised down from 76 on 2026-08-27. Another was abandoned in its
first chapters on premise logic the prediction had never examined. **State which
axis carries your number, and why not another.**
