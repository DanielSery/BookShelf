# Radar spokes for a recorded prediction

The shelf has already predicted a score for each book you are given, and argued it in
`why`. You add the seven radar spokes that show **where** that prediction's strengths and
pushbacks sit. You do not change the range, and nothing you write is a recommendation.

## Input

- **`calibration.jsonl` — read it first.** One line per book the reader has read and rated
  himself: its title, his score out of 10, and his seven spokes. **This is the scale.** Read
  off it what a typical 7, 8 and 9 look like on each spoke, the lowest values he actually
  uses, and how rarely Safety drops below 10 and for what. A spoke you give means "as strong
  on this axis as the read books he gave that number".
- **The batch file**, one JSON object per line: `key`, `title`, `author`, `series`,
  `genre`, `form`, `est` (the predicted range on 0-100, his score times ten), `leanedOn`
  (the axes carrying the number), `risks` (axes nobody could settle), `why` (the
  argument), `blurb`, and on a deep-dived book `dossier`: a sourced verdict per axis,
  `[verdict, note]`, where the verdict is `earns`, `clear`, `costs` or `unknown`.

## The spokes

Each is a whole number 0-10, **10 the best on every spoke**, so Safety 10 means clean.

| Spoke | 10 means | Rolls up these axes |
|---|---|---|
| `world` | a fresh setting with new ideas, an unknown worth exploring; for a real-world book, an interesting place or group seen from inside | worldbuilding (how interesting), discovery |
| `coherence` | the world **and the plot** hold up: declared rules kept, twists that fit what came before, nobody rescued by luck; for a real-world book, true to how things really are | worldbuilding (does it hold up), prophecy, unearned-competence |
| `pull` | clear and gripping from page one, and never drags | opening, momentum, density, multi-pov, collection, verse |
| `characters` | inner life and motives on the page, flaws to overcome, a cast who think differently; ordinary is not flat | protagonist (is the lead interesting), motives, character-differentiation, life-phase, childrens |
| `heart` | someone to root for and something good to hold on to: friendship, self-sacrifice, hope. Low: a lead sliding into evil, sustained bleakness, isolation | protagonist (is the lead worth rooting for), bleakness |
| `ideas` | leaves something to think about and grow from, without forcing or mocking it | ideas, short-idea-driven, memoir-form, faith |
| `safety` | clean of graded content: occult, sexual content, infidelity, a same-sex romance thread, a one-sided competence contrast between the sexes. The **worst** one present sets it | occult, sexual-content, sexual-treatment, sex-portrayal, infidelity, same-sex-romance, content |

## Rules

1. **Derive each spoke from what `why` and `dossier` say about the axes it rolls up.** An
   axis priced as earning shows as a high spoke, one priced as a cost as a low one, and
   the size of the cost in `why` sets how low. Where they say nothing, you may use your own
   **confident** knowledge of the book. A book you do not recognise gets only what the
   input supports.
2. **`null` when nothing settles a spoke, never a guessed 5.** A spoke whose deciding axis
   is in `risks` is `null`: the range assumes the risk does not fire, and a number would
   assert what nobody checked. So is Safety when `why` says occult or content was not
   examined and you do not know the book.
3. **The spokes are not computed from the range and need not average to it.** The range is
   the best part minus the problems, so a book predicted 8 can carry Heart 4 when `why`
   says the lead turns cruel. Do not raise or lower a spoke to match the range.
4. **Safety** is 10 when the book is clean of the content in the table. Otherwise the worst
   issue sets the number, calibrated against the read books, and `safetyIssue` names it in
   a few words: `"occult, light"`, `"sexual content, one chapter"`. A Safety below 10 with
   no `safetyIssue` is refused. **Not Safety at all:** violence, torture, swearing, drugs,
   a frightening or bleak ending (that is Heart), a romance that is neither sexual nor
   infidelity nor same-sex, and abuse that is not sexual. The reader named those as no
   objection; they never lower Safety.
5. Never name another book in `safetyIssue`.

## Output

Write **one file only**, at the output path you are given: one JSON object per input
line, same `key`, in input order, and nothing else.

```json
{"key": "ruze-pro-algernon", "radar": {"world": 6, "coherence": 8, "pull": 8, "characters": 9, "heart": null, "ideas": 10, "safety": 8, "safetyIssue": "sexual content, brief"}}
```

All seven spoke keys on every line, each a whole number 0-10 or `null`; add `safetyIssue`
only when safety is below 10. Then reply with how many lines you wrote and how many spokes
you left `null`, nothing more.
