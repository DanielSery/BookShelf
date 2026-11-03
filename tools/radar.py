"""The seven-spoke radar beside every score: the reader's for read books, the shelf's for predictions.

    python tools/radar.py sync                 add an all-null row to book-read-radar.json for every read book without one
    python tools/radar.py check                validate book-read-radar.json and every `radar` in book-estimates.jsonl
    python tools/radar.py xlsx [file]          write a spreadsheet of the read books to rate in (refuses to overwrite)
    python tools/radar.py import [file] [--erase]   copy the spreadsheet's numbers into book-read-radar.json
    python tools/radar.py batches <outdir> [--min 65] [--size 57] [--redo]
        -> calibration.jsonl and batch files of predictions without a radar; one agent per batch file,
           each following tools/radar-prompt.md and writing <outdir>/out/<batch>.jsonl
    python tools/radar.py merge <files...>      write the agents' radars into book-estimates.jsonl

A spoke is a whole number 0-10, 10 the best on every spoke, so safety 10 is clean. null means
not rated yet (a read book) or not settled by the evidence (a prediction), and the viewer draws
it as a gap, never as a 5. The definitions are in book-recommendations.md, "## The radar".
"""
import argparse, io, json, os, re, sys, unicodedata

sys.path.insert(0, "tools")
import readlog

RADAR, EST, XLSX, SHEET = "book-read-radar.json", "book-estimates.jsonl", "book-read-radar.xlsx", "Rate"
SPOKES = ["world", "coherence", "pull", "characters", "heart", "ideas", "safety"]
ISSUE_MAX = 60
ROLLUP = {
    "world": ["worldbuilding", "discovery"],
    "coherence": ["worldbuilding", "prophecy", "unearned-competence"],
    "pull": ["opening", "momentum", "density", "multi-pov", "collection", "verse"],
    "characters": ["protagonist", "motives", "character-differentiation", "life-phase", "childrens"],
    "heart": ["protagonist", "bleakness"],
    "ideas": ["ideas", "short-idea-driven", "memoir-form", "faith"],
    "safety": ["occult", "sexual-content", "sexual-treatment", "sex-portrayal", "infidelity", "same-sex-romance",
               "content"],
}
MEANS = {
    "world": "A fresh setting with new ideas, an unknown worth exploring. For a real-world book: an interesting "
             "place or group seen from inside.",
    "coherence": "The world AND the plot hold up: rules kept, twists that fit what came before, nobody rescued by "
                 "luck. For a real-world book: true to how things really are.",
    "pull": "Clear and gripping from page one, and never drags.",
    "characters": "Inner life and motives on the page, flaws to overcome, a cast who think differently. Ordinary "
                  "is not flat.",
    "heart": "Someone to root for and something good to hold on to: friendship, self-sacrifice, hope. Low: a lead "
             "sliding into evil, bleakness, isolation.",
    "ideas": "Leaves something to think about and grow from, without forcing or mocking it.",
    "safety": "Clean of occult, sex scenes, infidelity and the other content objections. 10 = clean; the worst "
              "issue sets it. Name it in Safety issue.",
}


def slug(s):
    s = "".join(c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")[:60]


def risk_spokes(risks):
    axes = {a.removeprefix("axis:") for a in risks or []}
    return [s for s in SPOKES if axes & set(ROLLUP[s])]


def problems(r, read=False, risks=None):
    if not isinstance(r, dict):
        return ["not an object"]
    out = [f"missing spoke {s}" for s in SPOKES if s not in r]
    extra = {"safetyIssue"} | ({"predicted"} if read else set())
    out += [f"unknown key {k!r}" for k in r if k not in SPOKES and k not in extra]
    for s in SPOKES:
        v = r.get(s)
        if v is not None and (type(v) is not int or not 0 <= v <= 10):
            out.append(f"{s} must be a whole number 0-10 or null, got {v!r}")
    issue = r.get("safetyIssue")
    if issue is not None and (not isinstance(issue, str) or not 0 < len(issue) <= ISSUE_MAX):
        out.append(f"safetyIssue must be short text, up to {ISSUE_MAX} characters")
    if not read and type(r.get("safety")) is int and r["safety"] < 10 and not issue:
        out.append("safety below 10 needs a safetyIssue naming what lowered it")
    out += [f"{s} must be null: an axis it rolls up is in risks" for s in risk_spokes(risks) if r.get(s) is not None]
    if read and r.get("predicted") is not None:
        out += ["predicted: " + p for p in problems(r["predicted"])]
    return out


def load():
    try:
        return json.load(io.open(RADAR, encoding="utf-8"))
    except FileNotFoundError:
        return {"radar": {}}


def dump(doc):
    out = ["{"]
    out += [f" {json.dumps(k)}: {json.dumps(v, ensure_ascii=False)}," for k, v in doc.items() if k != "radar"]
    rows = [f"  {json.dumps(k)}: {json.dumps(v, ensure_ascii=False)}" for k, v in doc["radar"].items()]
    out += [' "radar": {', ",\n".join(rows), " }", "}"]
    io.open(RADAR, "w", encoding="utf-8", newline="\n").write("\n".join(out) + "\n")


def sync():
    doc = load()
    old = doc["radar"]
    keys = [slug(r["title"]) for r in readlog.rows()]
    new = {k: old.get(k) or {s: None for s in SPOKES} for k in keys}
    orphans = [k for k in old if k not in new]
    new.update({k: old[k] for k in orphans})
    added = [k for k in keys if k not in old]
    doc["radar"] = new
    dump(doc)
    print(f"{len(added)} row(s) added" + "".join(f"\n  + {k}" for k in added))
    for k in orphans:
        print(f"  orphan {k}: no books-read.md row has this title; rename the key or delete the row")
    return 0


def check():
    bad = []
    radar = load()["radar"]
    keys = {slug(r["title"]) for r in readlog.rows()}
    bad += [f"{RADAR}: no row for read book {k} (run sync)" for k in sorted(keys - set(radar))]
    bad += [f"{RADAR}: orphan {k}" for k in sorted(set(radar) - keys)]
    for k, r in radar.items():
        bad += [f"{RADAR}: {k}: {p}" for p in problems(r, read=True)]
    rated = sum(1 for r in radar.values() if any(r.get(s) is not None for s in SPOKES))
    lines = io.open(EST, encoding="utf-8").read().splitlines()[1:]
    predicted = 0
    for line in filter(str.strip, lines):
        e = json.loads(line)
        if "radar" not in e:
            continue
        predicted += 1
        if e.get("blocked"):
            bad.append(f"{EST}: {e['key']}: a blocked book has no radar")
        bad += [f"{EST}: {e['key']}: {p}" for p in problems(e["radar"], risks=e.get("risks"))]
    for b in bad:
        print(b)
    print(f"read books rated: {rated} of {len(keys)} · predictions with a radar: {predicted}")
    return 1 if bad else 0


def label(s):
    return s.capitalize()


def xlsx(path):
    from openpyxl import Workbook
    from openpyxl.comments import Comment
    from openpyxl.formatting.rule import ColorScaleRule
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.utils import get_column_letter as col
    from openpyxl.worksheet.datavalidation import DataValidation

    if os.path.exists(path):
        print(f"{path} exists and may hold numbers not yet imported. Import it, or delete it, first.")
        return 1
    radar = load()["radar"]
    rows = readlog.rows()
    rated = sum(1 for r in rows if any((radar.get(slug(r["title"])) or {}).get(s) is not None for s in SPOKES))
    wb = Workbook()
    ws = wb.active
    ws.title = SHEET
    head = ["Book", "Author", "Score"] + [label(s) for s in SPOKES] + ["Safety issue", "Notes", "key"]
    ws.append(head)
    for r in rows:
        k = slug(r["title"])
        v = radar.get(k) or {}
        score = round(r["score"] / 10) if r["score"] is not None else "not finished"
        ws.append([r["title"], r["author"], score] + [v.get(s) for s in SPOKES]
                  + [v.get("safetyIssue"), r["notes"], k])

    last, first_spoke = len(rows) + 1, 4
    spoke_cols = [col(first_spoke + i) for i in range(len(SPOKES))]
    issue_col, notes_col, key_col = (col(first_spoke + len(SPOKES) + i) for i in range(3))
    center = Alignment(horizontal="center")
    ws.freeze_panes = "D2"
    ws.auto_filter.ref = f"A1:{key_col}{last}"
    for c in ws[1]:
        c.font = Font(bold=True)
        c.fill = PatternFill("solid", fgColor="E7E6E6")
        c.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
    for letter, width in {"A": 42, "B": 22, "C": 9, issue_col: 22, notes_col: 90}.items():
        ws.column_dimensions[letter].width = width
    ws.column_dimensions[key_col].hidden = True
    for row in ws.iter_rows(min_row=2, max_row=last):
        row[2].alignment = center
        row[2].font = Font(color="808080", italic=not isinstance(row[2].value, int))
        for c in row[first_spoke - 1:first_spoke - 1 + len(SPOKES)]:
            c.alignment = center
        row[len(head) - 2].font = Font(color="808080", size=9)
    for s, letter in zip(SPOKES, spoke_cols):
        ws.column_dimensions[letter].width = 11
        ws[f"{letter}1"].comment = Comment(MEANS[s], "Book shelf", width=260, height=110)
        dv = DataValidation(type="whole", operator="between", formula1="0", formula2="10", allow_blank=True,
                            showInputMessage=True, promptTitle=label(s), prompt=MEANS[s],
                            showErrorMessage=True, errorTitle="0-10 only",
                            error="A whole number 0-10, 10 the best. Leave it empty if you cannot judge it.")
        dv.add(f"{letter}2:{letter}{last}")
        ws.add_data_validation(dv)
    ws.conditional_formatting.add(f"{spoke_cols[0]}2:{spoke_cols[-1]}{last}", ColorScaleRule(
        start_type="num", start_value=0, start_color="F8CBAD", mid_type="num", mid_value=5, mid_color="FFFFFF",
        end_type="num", end_value=10, end_color="9BC2E6"))

    ax = wb.create_sheet("Axes")
    ax.append(["Axis", "10 means"])
    for s in SPOKES:
        ax.append([label(s), MEANS[s]])
    ax.append([])
    for line in ("Whole numbers 0-10, 10 the best on every axis, so Safety 10 means clean.",
                 "Leave a cell empty when you cannot judge it, for example on a book you did not finish.",
                 "The axes never compute the score: one low axis may sink a book that is fine everywhere else.",
                 f"When done, save and run: python tools/radar.py import {path}"):
        ax.append([line])
    ax.column_dimensions["A"].width = 14
    ax.column_dimensions["B"].width = 110
    for c in ax[1]:
        c.font = Font(bold=True)
    wb.save(path)
    print(f"{path}: {len(rows)} books, {rated} already rated")
    return 0


def import_xlsx(path, erase):
    from openpyxl import load_workbook

    ws = load_workbook(path, data_only=True)[SHEET]
    it = ws.iter_rows(values_only=True)
    head = [str(h).strip() if h is not None else "" for h in next(it)]
    at = {h: i for i, h in enumerate(head)}
    missing = [h for h in ["Book"] + [label(s) for s in SPOKES] if h not in at]
    if missing:
        print(f"{path}: sheet {SHEET!r} has no column {', '.join(missing)}")
        return 1
    doc = load()
    radar = doc["radar"]
    bad, erased, changed = [], [], 0
    for n, row in enumerate(it, 2):
        title = row[at["Book"]]
        if not title:
            continue
        k = (row[at["key"]] if "key" in at else None) or slug(str(title))
        if k not in radar:
            bad.append(f"row {n} {title}: no row in {RADAR}; run sync first")
            continue
        new = dict(radar[k])
        for s in SPOKES:
            v = row[at[label(s)]]
            if v is None or (isinstance(v, str) and not v.strip()):
                if new.get(s) is not None:
                    erased.append(f"row {n} {title}: {label(s)} {new[s]}")
                new[s] = None
                continue
            try:
                f = float(str(v).replace(",", "."))
            except ValueError:
                f = -1
            if not (f.is_integer() and 0 <= f <= 10):
                bad.append(f"row {n} {title}: {label(s)} {v!r} is not a whole number 0-10")
                continue
            new[s] = int(f)
        issue = row[at["Safety issue"]] if "Safety issue" in at else None
        if issue is not None and str(issue).strip():
            new["safetyIssue"] = str(issue).strip()
        else:
            new.pop("safetyIssue", None)
        bad += [f"row {n} {title}: {p}" for p in problems(new, read=True)]
        if new != radar[k]:
            radar[k] = new
            changed += 1
    if erased and not erase:
        bad += [e + " would be erased by an empty cell (pass --erase if that is intended)" for e in erased]
    for b in bad:
        print(b)
    if bad:
        print(f"nothing written: {len(bad)} problem(s)")
        return 1
    dump(doc)
    print(f"{changed} book(s) updated in {RADAR}")
    return 0


def estimate_lines():
    text = io.open(EST, encoding="utf-8", newline="").read()
    nl = "\r\n" if "\r\n" in text else "\n"
    return text.split(nl), nl


def batches(outdir, lowest, size, redo):
    rows = readlog.rows()
    radar = load()["radar"]
    calib = [{"title": r["title"], "score": round(r["score"] / 10), "radar": {s: radar[k][s] for s in SPOKES}}
             for r in rows if r["score"] is not None
             for k in [slug(r["title"])] if k in radar and all(radar[k][s] is not None for s in SPOKES)]
    cache = {b["key"]: b for b in json.load(io.open("book-cache.json", encoding="utf-8"))["books"]}
    media = json.load(io.open("book-media.json", encoding="utf-8")).get("media", {})
    deep = {}
    for line in io.open("book-deep.jsonl", encoding="utf-8").read().splitlines():
        if line.startswith('{"key"'):
            d = json.loads(line)
            deep[d["key"]] = {ax: [v.get("v"), v.get("note")] for ax, v in d.get("axes", {}).items()}
    lines, _ = estimate_lines()
    todo = []
    for line in lines[1:]:
        if not line.strip():
            continue
        e = json.loads(line)
        if e.get("blocked") or not e.get("est") or sum(e["est"]) / 2 < lowest or ("radar" in e and not redo):
            continue
        b = cache.get(e["key"], {})
        item = {"key": e["key"], "title": e["t"], "author": b.get("author"), "series": b.get("series"),
                "genre": b.get("genre"), "form": b.get("form"), "est": e["est"], "leanedOn": e.get("leanedOn"),
                "risks": e.get("risks"), "why": e["why"], "blurb": media.get(e["key"], {}).get("blurb")}
        if e["key"] in deep:
            item["dossier"] = deep[e["key"]]
        todo.append(item)
    os.makedirs(os.path.join(outdir, "out"), exist_ok=True)
    with io.open(os.path.join(outdir, "calibration.jsonl"), "w", encoding="utf-8", newline="\n") as f:
        f.writelines(json.dumps(c, ensure_ascii=False) + "\n" for c in calib)
    for i in range(0, len(todo), size):
        name = os.path.join(outdir, f"batch-{i // size + 1:02d}.jsonl")
        with io.open(name, "w", encoding="utf-8", newline="\n") as f:
            f.writelines(json.dumps(t, ensure_ascii=False) + "\n" for t in todo[i:i + size])
        print(name, len(todo[i:i + size]))
    print(f"{len(todo)} predictions in {-(-len(todo) // size)} batch(es); calibration: {len(calib)} read books")
    return 0


def merge(files):
    lines, nl = estimate_lines()
    index = {json.loads(l)["key"]: i for i, l in enumerate(lines) if l.startswith('{"key"')}
    got, bad, unset = {}, [], 0
    for p in files:
        for n, line in enumerate(io.open(p, encoding="utf-8").read().splitlines(), 1):
            if not line.strip():
                continue
            try:
                d = json.loads(line)
            except ValueError:
                bad.append(f"{p}:{n}: not JSON")
                continue
            k = d.get("key")
            if k not in index:
                bad.append(f"{p}:{n}: unknown key {k!r}")
            elif json.loads(lines[index[k]]).get("blocked"):
                bad.append(f"{p}:{n}: {k} is blocked, so it has no radar")
            elif k in got:
                bad.append(f"{p}:{n}: {k} given twice")
            else:
                r, risks = d.get("radar"), json.loads(lines[index[k]]).get("risks")
                if isinstance(r, dict):
                    for s in risk_spokes(risks):
                        unset += r.get(s) is not None
                        r[s] = None
                    if r.get("safety") is None:
                        r.pop("safetyIssue", None)
                bad += [f"{p}:{n}: {k}: {x}" for x in problems(r, risks=risks)]
                got[k] = r
    for b in bad:
        print(b)
    if bad:
        print(f"nothing written: {len(bad)} problem(s)")
        return 1
    for k, r in got.items():
        e = json.loads(lines[index[k]])
        out = {}
        for f, v in e.items():
            if f != "radar":
                out[f] = v
            if f == "est":
                out["radar"] = r
        lines[index[k]] = json.dumps(out, ensure_ascii=False)
    io.open(EST, "w", encoding="utf-8", newline="").write(nl.join(lines))
    nulls = {s: sum(1 for r in got.values() if r[s] is None) for s in SPOKES}
    print(f"{len(got)} predictions given a radar; {unset} spoke(s) set unknown because an axis they roll up is a "
          f"listed risk; unknown spokes now: " + ", ".join(f"{s} {n}" for s, n in nulls.items()))
    return 0


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("sync")
    sub.add_parser("check")
    s = sub.add_parser("xlsx")
    s.add_argument("file", nargs="?", default=XLSX)
    s = sub.add_parser("import")
    s.add_argument("file", nargs="?", default=XLSX)
    s.add_argument("--erase", action="store_true")
    s = sub.add_parser("batches")
    s.add_argument("outdir")
    s.add_argument("--min", type=float, default=65, help="lowest predicted midpoint, 0-100")
    s.add_argument("--size", type=int, default=57)
    s.add_argument("--redo", action="store_true", help="include predictions that already have a radar")
    s = sub.add_parser("merge")
    s.add_argument("files", nargs="+")
    a = p.parse_args()
    if a.cmd == "xlsx":
        return xlsx(a.file)
    if a.cmd == "import":
        return import_xlsx(a.file, a.erase)
    if a.cmd == "batches":
        return batches(a.outdir, a.min, a.size, a.redo)
    if a.cmd == "merge":
        return merge(a.files)
    return sync() if a.cmd == "sync" else check()


if __name__ == "__main__":
    sys.exit(main())
