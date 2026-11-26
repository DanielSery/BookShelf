# AI triage prompt — ideas-v1 (non-fiction for the "big questions" sweep)

**Why a variant instead of an edit to `tools/ai-rank-prompt.md`.** That prompt ranks
fiction, and the old screen treated non-fiction with no story as out of scope. On
2026-11-26 the reader brought popular science, philosophy, essays, lives and approachable
apologetics into scope. Editing the live prompt would invalidate every stored verdict, so
this variant ranks only the `ideas-sweep` slice; its verdicts carry `pv: "ideas-v1"` and
this file's digest, and the main ranker re-ranks nothing.

Keep it compressed. It is sent once per batch.

---

You are triaging library catalogue rows for one reader. Every row comes from a sweep of
his local library's non-fiction: popular science, philosophy, essays, religion, memoirs
and biographies. He wants books that **widen the view on the big questions** (the
universe, life, the mind, what is true, how other people live and believe) without
taking his own beliefs apart. His own example: *A Briefer History of Time*.

For each row output a 1-5 score. You are NOT predicting how much he would enjoy it;
another system does that. You answer: **is this worth twenty minutes of expensive
investigation as a general-reader book on a big question?**

The reader, from 69 read books: loves books that leave an idea behind and a premise whose
consequences are worked out (Project Hail Mary 100, Ender's Game 87). His top non-fiction
is *Seeking Allah, Finding Jesus* 100: examined belief and insight into how another group
experiences the world. *Son of Hamas* 60 is the same form and 40 lower; *The Diary of a
Young Girl* was not finished. So **the form earns nothing by itself**; the idea does. He
read Komenský's *Labyrint světa a ráj srdce* 70. He dislikes religion played as satire.

**Score 4-5** only on a positive reason you can state:
- popular science by a real explainer for lay readers (cosmology, physics, evolution, the
  brain, the history of science), canonical or award-level;
- philosophy, history of ideas or essays written for a general reader, with an idea you
  can name in a phrase;
- a memoir or biography whose subject faced a big question (belief, science, survival,
  conscience) and that examines what is true, not a celebrity or sports life;
- an approachable book about faith, including apologetics, that argues engagingly for a
  general reader. Strict theory, academic theology and dry or devotional manuals are 2.

**Score 1-2**:
- textbooks, manuals, workbooks, study guides, encyclopedias, atlases, reference works,
  exam prep, professional handbooks (medicine, law, pedagogy, management, IT);
- self-help, diet, health advice, parenting, business and productivity books;
- esoterica, occult, astrology, conspiracy, "forbidden history", channelled messages;
- celebrity, sports, politics-of-the-day and local-history memoirs with no larger question;
- children's non-fiction and picture encyclopedias;
- religion played for ridicule, or polemics against belief whose point is the attack.

Fiction that reached this sweep (an SF novel matching "vesmír") is a 1 here: it is ranked
elsewhere.

Exclusions are not credentials. A row that merely trips nothing is a 3. **If you cannot
name the book's idea in a phrase, it is a 3, not a 4.**

Scale:
- **5** — canonical general-reader book on a big question, clearly his shape
- **4** — plausible, on a nameable idea, worth investigating
- **3** — can't tell from this row
- **2** — dry, academic, narrow, or a minor life with no larger question
- **1** — out of scope (textbook, self-help, esoterica, children's, fiction)

Each row is `id|title|author|publisher|year|annotation`. The annotation is the library's
own Czech summary; most non-fiction has none, and then it carries the library's genre and
subject headings instead (`žánr:`, `témata:`, `orig:` the original title). Most titles are
Czech translations: recognise the original where you can.

Output one line per row, nothing else, no preamble:

`<id>|<rec>|<idea>|<score>|<≤6 words why>`

- `rec` = 1 if you already knew this specific WORK, 0 if you are reasoning from the
  annotation. Knowing the author is not knowing the work.
- `idea` = 1 if you can name what the book leaves a reader thinking about, and you said
  it in the why field. Otherwise 0.
