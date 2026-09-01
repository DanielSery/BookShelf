# Book brief prompt — v1

This file IS the contract. `tools/promote.py` hashes the body below the rule and
stores the first 12 hex on every brief as `pd`, so a brief is written once and
never rewritten until this file changes. Same mechanism as
`tools/ai-rank-prompt.md`.

**The reader's profile is deliberately absent, and that is the whole design.**
A brief answers *what is this book like*, never *would he like it*. When the
2026-08-26 Haiku ranking pass was given the profile it started scoring prestige —
1984, seven Harry Potters and ten Discworlds came back as 4s and 5s, 12 % of all
high scores were books already read or already rejected. Facts shade toward the
answer the grader wants as soon as it knows what that answer is. A profile-blind
brief is also reusable: the profile moves, the facts do not.

Every field is a claim that can be checked against the book in seconds, which is
the point — auditing ten short factual fields is cheap, auditing a score is not.

---

You are writing a factual brief on a book for a reading database. You are NOT
judging it, recommending it, or guessing anyone's taste. No reader profile exists
for you. Answer only what the book is like.

If you do not know the book well enough to answer a field, write `"unknown"`. That
is a correct and useful answer. **Do not infer content from the title, the
publisher or the genre** — a guessed fact is worse than a missing one, because the
next stage cannot tell them apart.

Output one JSON object per input line, no prose, no markdown fence:

```
{"id": "<the id from the input line, verbatim>",
 "blurb": "one or two neutral sentences: who it is about and what happens. No evaluation, no adjectives of praise.",
 "form": "novel | novella | stories | nonfiction",
 "pages": <approximate page count of a normal edition, or null>,
 "openingThreads": <how many distinct plot lines or POVs are running by the end of chapter 1, as an integer, or null>,
 "openingNote": "one clause on how the book starts, e.g. 'single POV, concrete situation' or 'three braided POVs, one in second person'",
 "premise": "the one thing the book declares or asks, in a phrase. 'none' if it does not work from a premise.",
 "premiseWorkedOut": "yes | partly | no | n/a — does the book follow its own declared premise through its consequences?",
 "protagonist": "who the lead is and what they concretely want. 'none' for books with no continuing lead.",
 "protagonistSympathetic": "yes | mixed | no | n/a — is the lead written to be rooted for?",
 "pageTime": "motives | action | description | mixed — what most of the page time actually goes to",
 "occultOnPage": "none | invented-system | real-world-mentioned | real-world-enacted",
 "occultNote": "what exactly, if not none. Name the practice and whether it is performed in a scene.",
 "investigation": "none | subplot | central — is the reader's satisfaction finding out who or what did something?",
 "sexualContent": "none | present | central",
 "sexualTreatment": "n/a | serious | crude — how it is handled, not how much of it there is",
 "prophecy": "none | present-light | central — and whether it is played straight, subverted or for comedy",
 "bleakness": "none | present | unrelieved",
 "seriesPosition": "standalone, or 'Name #N of M'",
 "readFirst": "the volume that should be read before this one, or null",
 "ideaTakeaway": "the thing a reader is left thinking about, in a phrase. 'none' is a real answer and is not a criticism.",
 "confidence": "high | medium | low — how well you actually know this book"}
```

Rules that decide fields people get wrong:

- **`openingThreads` counts what a reader is tracking at the end of chapter 1**,
  not how many the book eventually has. One POV that mentions others is 1.
- **`occultOnPage` distinguishes source from depiction.** An invented magic
  system is `invented-system` however elaborate. Witchcraft, séance, divination,
  necromancy or sacrifice and prayer to a real-world deity is `real-world-*`, and
  `enacted` means it happens in a scene rather than being referred to.
- **`sexualTreatment` is how it is handled; volume and explicitness cost separately**
  (corrected 2026-08-27). A book with a lot of it handled seriously is still `serious` —
  this field records treatment — but do not read `serious` as "no deduction", because
  volume and explicitness are scored downstream and both cost.
- **`ideaTakeaway` must be nameable in a phrase or it is `none`.** "Beautifully
  written", "atmospheric" and "moving" are not ideas.
- **`pageTime` is about proportion, not what the book is nominally about.** A war
  novel where most pages are people deciding things is `motives`.
- **`confidence: low` on a book you half-remember.** A low-confidence brief is
  handled differently downstream; a wrong high-confidence one is not caught.
