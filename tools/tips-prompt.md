# The treasure and how to read it — analyse the book, then write two sentences

You write two lines the viewer shows on a card, each exactly one sentence:

- **The treasure**: why this book is special, the best thing in it, the reason to read it.
- **How to read it**: the reading style that gets the most from it.

The reader asked for both on 2026-11-03, for every card, read books included. What started
it: *Výdech* works best one story per sitting with a pause to think, while *Stín věcí
ztracených* rewards sinking into the world for long stretches. His instruction for this
work: **"do not just copy it, analyze it and propose your own style."** So the job is not to
fill a template. Work out how **this** book is built and what is best in it, then write
both lines in words meant for this book alone.

## Input

A batch file, one JSON object per line, with an `id`, a `kind` and `want`, the list of
lines this card still needs. **Write only the lines in `want`.** A line the card already has
arrives as `has_treasure` or `has_howto`; don't repeat its content in the other line.

- **`book`**, a candidate he has not read: `title`, `alt` (English title), `author`,
  `genre`, `form`, `tags`, `pitch` (what the card already says) and `notes`. The notes are
  the scoring notes and your main source of facts. They also hold deductions, reviewer
  complaints and often the ending, so mine them for what the book does well and how it is
  built, and never echo their machinery.
- **`read`**, a book he has read: `title`, `author`, `genre`, `form`, `score` (his, out of
  10; `null` means not finished and left unscored) and `notes`, his own log entry: what he
  liked and what stopped him.
- **`series`**, a series shown as one card: `title`, `alt`, `author` and `volumes` in
  order. A volume he has read carries `read: true`, his score and his notes; the rest
  carry scoring notes.

## Analyse first

For each book, answer these for yourself before writing anything. The analysis stays in
your head; only the sentences it leads to are written.

1. **How is it built?** One thread or many; told by whom; standalone pieces or one arc;
   episodes, letters, a frame, time jumps, a puzzle, an argument, a life told in order.
2. **What is the best thing in it?** The one element that sets this book apart from others
   like it: a character, a friendship, the central invention, an idea pushed to its end,
   the voice, a kind of scene it does better than anyone. Name it concretely.
3. **What does it ask of the person reading?** Patience with a slow or confusing stretch,
   pauses to think, momentum, background knowledge, tolerance for side-tracks, keeping
   track of a large cast.
4. **Where would the wrong mode hurt?** Bingeing what should be savoured, sipping what
   runs on pull, chasing plot in a book whose plot is not the point, giving up on an
   opening that only makes sense later.

Different books should come out different, because they are built differently. If two
books in your batch get the same line, ask whether they really share that.

## What he is like, where it bears on the lines

- He reads in Czech print, and reads a series whole.
- He loves uncovering a mystery or a hidden past, a world whose rules hold, a lead worth
  rooting for who has flaws to overcome, ideas taken seriously, and friendship and hope.
- He gives up early when an opening starts many threads at once and nothing is clear yet.
  Knowing the setup beforehand got him through a book he had once abandoned in chapter one.
- He puts a collection down at a weak story instead of skipping it.
- He dislikes digression and padding. Length itself is never the problem.

## What you write

Both lines are **exactly one sentence, 50-220 characters**. The merge refuses a second
sentence.

- **`treasure`**: the best thing in this book and what it gives you, from answer 2. Not the
  setup, which the pitch carries, and not a list of strengths: one thing, said concretely.
  For a **`read`** book, use what his notes say he loved when they say it, in plain words;
  when he disliked the book or did not finish it, name what the book does best anyway,
  without arguing with his verdict. For a **`series`**, the best thing across the volumes.
- **`howto`**: the reading style you propose, as a plain instruction or to "you", from
  answers 1, 3 and 4. A tip that would fit a book built differently is the wrong tip. For
  a **`read`** book, write for a re-read or for seeing how it works best; where his notes
  say what stopped him, aim at that, never as "you should have". For a **`series`**, how to
  read the volumes as a whole.

## Never

- **No copied wording.** Don't reuse a phrase across cards, and don't borrow wording from
  this prompt or from the card's pitch. The merge lists every five-word phrase that recurs
  on several cards, and those cards are rewritten.
- **No spoilers** past the opening setup, even when the notes state them: no twists,
  reveals, deaths, who someone really is, or how it ends. If the best thing is a mystery,
  name the question and never the answer.
- **No scores**, nothing that looks like one, and no ranges. Write numbers as words.
  None of these words: score, deduction, axis, filter, estimate, predicted, rating, tier,
  premise, declared, rootable, legible, interiority, "the reader".
- **No empty praise.** Not "a masterpiece", "unforgettable", "a must-read", "beautifully
  written". The treasure earns its place by being specific. No warnings that a book is weak.
- **No stock advice** that fits any book ("take your time", "enjoy the journey", "keep an
  open mind").
- **No invented facts.** Use the notes or your own confident knowledge of the book. If the
  notes are thin and you don't know the book, keep the line modest, or write `null` for it
  if not even that is safe.
- **Comparisons:** at most one per line, and only to a book he has read, which in the notes
  are the titles carrying a number. Echo the title without the number.

## Output

Write **one file only**, at the output path you are given: one JSON object per input
line, same `id`, in input order, with only the fields in that line's `want`, and nothing
else.

```json
{"id": "<id from the input>", "treasure": "<the best thing>", "howto": "<your proposed style>"}
```

Then reply with how many lines you wrote and how many fields you left `null`, nothing more.
