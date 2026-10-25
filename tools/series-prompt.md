# Series assigner — which shelf books belong to one series

The reader does not read single titles out of a series: he reads a series whole, so
the viewer and `/book-suggest` propose a series as ONE entry (ruled 2026-10-25). Your
job is to say which books on the shelf belong together, and in what order.

## Input

A batch file, one JSON object per line, one line per **author group**:

- `author` — the group's author surname, normalised.
- `shelf` — that author's unread candidates: `key`, `title` (original), `czTitle`,
  `author` (full), `series` (the raw value already recorded — unreliable, see below),
  `year`.
- `read` — rows of the reader's read log that may be by this author (title, author,
  score). The surname join is loose, so a different author with the same surname can
  appear here: ignore those.
- `rejected` — reject rows that may be by this author (entity, author, filter).

## Output

JSONL to the path you are given, one object per series or universe you identify:

```
{"id": "licanius", "name": "Licanius", "nameEn": "Licanius", "kind": "series",
 "members": [{"key": "stin-veci-ztracenych", "n": 1}],
 "read": ["Stín věcí ztracených (The Shadow of What Was Lost)"],
 "rejected": [], "volumes": 3, "note": ""}
```

- `id`: lowercase ascii slug of the English series name. Unique.
- `name`: the Czech series name when the Czech editions have one, else the original.
  `nameEn`: the original-language name.
- `kind`:
  - `series` — a continuing story, or one lead carried across books, meant to be
    read in order: trilogies, sagas, Hunger Games, Red Rising, Cato and Macro,
    Raven's Shadow, Silo. **This is what the viewer groups.**
  - `universe` — a shared world of novels that stand alone, with different leads:
    Discworld as a whole, the Hainish cycle, Asimov's Galactic Empire novels,
    Star Wars and other franchise tie-ins. Not grouped. **A universe's real
    sub-series are `series` of their own**: Discworld's City Watch, Death, Witches,
    Rincewind, Moist von Lipwig, Tiffany Aching and Industrial Revolution books.
- `members`: shelf keys from this batch only, each with `n`, its number in the
  series' reading order (publication order unless the author says otherwise). A key
  belongs to at most one series; a sub-series member is not also listed in its
  universe.
- `read` / `rejected`: copy the matching strings from the input — only those that
  really are volumes of this series.
- `volumes`: how many volumes the series has in total, if you know it; else null.
- `readWhole` (only on hand-written records): one `books-read.md` row that logs a whole
  series ("Harry Potter (series)"). The Read tab labels it as read whole.
- `note`: one short line only when something is non-obvious (a prequel written
  later, a volume the library holds only as an omnibus, a disputed order). Usually
  empty.

**Do not output** a record for a book that is not in a series. Standalones are the
default; say nothing about them.

## Traps

- **The raw `series` value is often a publisher's line, not a series**: Fantastika,
  SF, Světový bestseller, Klokan, Monada, Disney, Brokilon alternativa, Host
  „edice", a numbered imprint. Those are not series — ignore them.
- **A first volume often has no `series` value** while its sequels do (Silo, Skyward).
  Put it in.
- **Same surname, different author** (Frank vs Brian Herbert, Suzanne vs Bridget
  Collins, Agatha vs Michael Christie): only the real author's books are a series —
  though a series continued by another author (Brian Herbert's Dune prequels) is a
  separate `series` of its own, not part of the original.
- Czech-original series: trust the titles and the raw `series` value; a numbered
  cycle in the catalogue ("Z cyklu: …") is usually a real series.
- Use what you know. Search the web only when you cannot tell whether a book is a
  series volume or which number it is, and then at most a few searches per batch.

Your final message: one line — how many series and universes you wrote, and the
output path.
