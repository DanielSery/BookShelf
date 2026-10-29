"""Which read-book scores each prediction's range is set against, so a changed score in
books-read.md moves the ranges built on it without rereading every `why`.

A `why` cites read books with their score ("the Narnia 67 position", "unlike Já, robot 55").
The number in the text IS the score the range was derived under. A citation whose number no
longer matches the log is out of date, and how it is fixed depends on its role, kept per
line in `anchors` as {read title: role}:

    level     the range is set relative to that score: it moves by the same amount when
              the score sits inside the range, and by half when it sits just outside,
              where the citation is usually a neighbour or the size of one deduction
    contrast  cited for one trait, as an analogy or a counter-example: only the number
              in the text is rewritten

Several level citations on one line move it by the mean of their shifts.

A changed citation with no role yet is classified by distance when it sits more than
MARGIN points outside the range (a contrast); one inside that band needs a reader.

    python tools/anchors.py todo <out.jsonl> [--all]
        -> near, unclassified citations whose score changed (--all: changed or not),
           one line per estimate with only the sentences that cite them
    python tools/anchors.py roles <files...>     # {key: {title: "level"|"contrast"}}
    python tools/anchors.py rescore [--dry]      # shift, rewrite the numbers, stamp `at`
"""
import argparse
import datetime
import io
import json
import re
import sys

import readlog

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8")
    except AttributeError:
        pass

EST, SERIES = "book-estimates.jsonl", "book-series.json"
MARGIN = 6
ROLES = {"level", "contrast"}

# Read title, or "series:<book-series.json id>" for a citation of a whole series, which
# stands for the mean of that series' scored rows.
ALIASES = [
    ("Ozvěna věcí budoucích (An Echo of Things to Come)", r"Ozv[ěe]n[aě]?(?: v[ěe]c[íi] budouc[íi]ch)?|An Echo of Things to Come"),
    ("Project Hail Mary", r"Project Hail Mary|PHM"),
    ("Seeking Allah, Finding Jesus", r"Seeking Allah(?:,? Finding Jesus)?"),
    ("Světlo věcí konečných (The Light of All That Falls)", r"Sv[ěe]tlo v[ěe]c[íi] kone[čc]n[ýy]ch|The Light of All That Falls"),
    ("Red Rising", r"Red Rising"),
    ("Stín věcí ztracených (The Shadow of What Was Lost)", r"St[íi]n v[ěe]c[íi] ztracen[ýy]ch|The Shadow of What Was Lost"),
    ("Golden Son (Red Rising #2)", r"Golden Son"),
    ("Mockingjay (Hunger Games #3)", r"Mockingjay"),
    ("Speaker for the Dead (Ender #2)", r"Speaker(?: for the Dead)?"),
    ("The Hunger Games", r"(?:The )?Hunger Games"),
    ("Sunrise on the Reaping", r"Sunrise(?: on the Reaping)?"),
    ("Válka starého muže (Old Man's War)", r"V[áa]lka star[ée]ho mu[žz]e|Old Man'?s War|VSM"),
    ("Ender's Game", r"Ender'?s Game"),
    ("The Hobbit", r"(?:The )?Hobbit"),
    ("The Lord of the Rings (series)", r"(?:The )?Lord of the Rings|LOTR|P[áa]n prsten[ůu]"),
    ("Catching Fire (Hunger Games #2)", r"Catching Fire"),
    ("The Hitchhiker's Guide to the Galaxy", r"(?:The )?Hitchhiker'?s(?: Guide(?: to the Galaxy)?)?"),
    ("Mort (Discworld #4)", r"Mort|Smr[ťt]"),
    ("The Martian", r"(?:The )?Martian|Mar[ťt]an"),
    ("The Little Prince", r"(?:The )?Little Prince|Mal[ýy] princ"),
    ("Ender saga #3-5 (Xenocide onward)", r"(?:Ender )?saga #3-5|Xenocide"),
    ("Počítání hvězd (The Calculating Stars)", r"Po[čc][íi]t[áa]n[íi] hv[ěe]zd|(?:The )?Calculating Stars"),
    ("Ender's Shadow series", r"Ender'?s Shadow(?: series)?"),
    ("Malé ženy (Little Women)", r"Mal[ée] [žz]eny|Little Women"),
    ("Animal Farm", r"Animal Farm|Farma zv[íi][řr]at"),
    ("Les Misérables", r"Les Mis[ée]rables|B[íi]dn[íi]ci"),
    ("The Silmarillion", r"(?:The )?Silmarillion"),
    ("Saturnin", r"Saturnin"),
    ("Pýcha a předsudek (Pride and Prejudice)", r"P[ýy]cha a p[řr]edsudek|Pride and Prejudice"),
    ("series:rangers-apprentice", r"Ranger'?s Apprentice|Hrani[čc][áa][řr][ůu]v u[čc]e[ňn]"),
    ("Labyrint světa a ráj srdce", r"Labyrint(?: sv[ěe]ta(?: a r[áa]j srdce)?)?"),
    ("The Count of Monte Cristo", r"(?:The Count of )?Monte Cristo|Hrab[ěe] Monte Cristo"),
    ("Son of Hamas", r"Son of Hamas"),
    ("Hitchhiker's sequels (#2-5)", r"Hitchhiker'?s? sequels"),
    ("Unfinished Tales", r"Unfinished Tales"),
    ("Artemis", r"Artemis"),
    ("Exodus", r"Exodus"),
    ("The Chronicles of Narnia", r"(?:The )?(?:Chronicles of )?Narni[ae]|Letopisy Narnie"),
    ("Quo Vadis", r"Quo Vadis"),
    ("Percy Jackson (full series)", r"Percy Jackson"),
    ("Čaropisci (Foundryside)", r"[ČC]aropisci|Foundryside"),
    ("The Ballad of Songbirds and Snakes", r"(?:The )?Ballad(?: of Songbirds and Snakes)?"),
    ("1984", r"1984"),
    ("Divergent (series)", r"Divergent"),
    ("Oliver Twist", r"Oliver Twist"),
    ("Já, robot (I, Robot)", r"J[áa],? robot|I, Robot"),
    ("Mortal Engines (Smrtelné stroje)", r"Mortal Engines|Smrteln[ée] stroje"),
    ("Proměna (The Metamorphosis)", r"Prom[ěe]n[aěy]|(?:The )?Metamorphosis|Gregor Samsa"),
    ("Ready Player One", r"Ready Player One"),
    ("The Witcher (series)", r"(?:The )?Witcher|Zakl[íi]na[čc]"),
    ("Harry Potter (series)", r"Harry Potter"),
    ("Havran (The Raven)", r"Havran|The Raven"),
]
# "Narnia 67", "Narnia (67)", "Narnia at 67", "held Narnia to 67". A number that opens a
# span ("83 to 70", "92-96") is not one book's score.
CITE = re.compile(r"(?<![\w-])(?P<name>%s)(?!\w)(?P<sep>\*{0,2}(?:'s)?\*{0,2}(?: \(| (?:at|to|fell to|dropped to|scored) | ))(?P<n>\d{1,3})(?!\d|\.\d|\s*(?:to|-|–|→)\s*\d)"
                  % "|".join("(?:%s)" % p for _, p in ALIASES))
WHICH = [(t, re.compile(r"(?:%s)$" % p)) for t, p in ALIASES]


def current_scores():
    scores = {r["title"]: r["score"] for r in readlog.rows() if r["score"] is not None}
    for sid, s in json.load(io.open(SERIES, encoding="utf-8"))["series"].items():
        vals = [scores[t] for t in s.get("read", []) if t in scores]
        if vals:
            scores["series:" + sid] = round(sum(vals) / len(vals))
    return scores


def title_of(name):
    return next(t for t, rx in WHICH if rx.match(name))


def citations(why, scores):
    """(match, title, cited, current) for every citation of a scored read book."""
    out = []
    for m in CITE.finditer(why or ""):
        t = title_of(m.group("name"))
        n = int(m.group("n"))
        if t in scores and 0 < n <= 100:
            out.append((m, t, n, scores[t]))
    return out


def load():
    raw = io.open(EST, encoding="utf-8", newline="").read()
    nl = "\r\n" if "\r\n" in raw else "\n"
    lines = raw.split(nl)
    return lines, nl


def save(lines, nl):
    io.open(EST, "w", encoding="utf-8", newline="").write(nl.join(lines))


def near(est, n):
    return est[0] - MARGIN <= n <= est[1] + MARGIN


def todo(a):
    scores = current_scores()
    lines, _ = load()
    out, cites = [], 0
    for line in lines[1:]:
        if not line.startswith("{"):
            continue
        e = json.loads(line)
        if not e.get("est"):
            continue
        roles = e.get("anchors") or {}
        need = {}
        for m, t, n, cur in citations(e.get("why"), scores):
            if t not in roles and (a.all or n != cur) and near(e["est"], n):
                need.setdefault(t, n)
        if not need:
            continue
        sentences = [s for s in re.split(r"(?<=[.;!?])\s+", e["why"]) if CITE.search(s)]
        out.append({"key": e["key"], "est": e["est"], "leanedOn": e.get("leanedOn"),
                    "cites": [{"book": t, "score": n} for t, n in need.items()],
                    "text": " ".join(sentences)})
        cites += len(need)
    with io.open(a.out, "w", encoding="utf-8", newline="\n") as f:
        for o in out:
            f.write(json.dumps(o, ensure_ascii=False) + "\n")
    print("%d estimates, %d citations to classify -> %s" % (len(out), cites, a.out))


def roles(a):
    got = {}
    for p in a.files:
        for k, v in json.load(io.open(p, encoding="utf-8")).items():
            bad = {t: r for t, r in v.items() if r not in ROLES}
            if bad:
                sys.exit("%s: %s has roles outside %s: %s" % (p, k, sorted(ROLES), bad))
            got.setdefault(k, {}).update(v)
    lines, nl = load()
    n = 0
    for i, line in enumerate(lines):
        if not line.startswith('{"key"'):
            continue
        e = json.loads(line)
        if e["key"] in got:
            r = dict(e.get("anchors") or {})
            for t, role in got.pop(e["key"]).items():
                r[t] = "level" if "level" in (role, r.get(t)) else role
            e["anchors"] = dict(sorted(r.items()))
            lines[i] = json.dumps(e, ensure_ascii=False)
            n += 1
    if got:
        sys.exit("no estimate line for: %s" % ", ".join(sorted(got)))
    save(lines, nl)
    print("roles recorded on %d estimates" % n)


def rescore(a):
    scores = current_scores()
    lines, nl = load()
    today = datetime.date.today().isoformat()
    moved, text_only, unresolved, sizes = 0, 0, [], {}
    for i, line in enumerate(lines):
        if not line.startswith('{"key"'):
            continue
        e = json.loads(line)
        cs = [c for c in citations(e.get("why"), scores) if c[2] != c[3]]
        if not cs:
            continue
        r = dict(e.get("anchors") or {})
        for _, t, n, _ in cs:
            if t not in r and (not e.get("est") or not near(e["est"], n)):
                r[t] = "contrast"
        open_ = sorted({t for _, t, _, _ in cs if t not in r})
        if open_:
            unresolved.append((e["key"], open_))
            continue
        deltas = {(t, n): (cur - n) * (1 if e.get("est") and e["est"][0] <= n <= e["est"][1] else 0.5)
                  for _, t, n, cur in cs if r[t] == "level"}
        if deltas and e.get("est"):
            d = round(sum(deltas.values()) / len(deltas))
            e["est"] = [min(100, max(0, x + d)) for x in e["est"]]
            sizes[d] = sizes.get(d, 0) + 1
            moved += 1
        else:
            text_only += 1
        e["why"] = CITE.sub(lambda m: m.group("name") + m.group("sep") + str(
            scores.get(title_of(m.group("name")), int(m.group("n")))
            if 0 < int(m.group("n")) <= 100 else m.group("n")), e["why"])
        e["anchors"] = dict(sorted(r.items()))
        e["at"] = today
        lines[i] = json.dumps(e, ensure_ascii=False)
    print("%d ranges shifted, %d with only the cited numbers rewritten, %d left unresolved"
          % (moved, text_only, len(unresolved)))
    print("shift sizes:", ", ".join("%+d x%d" % kv for kv in sorted(sizes.items())))
    for k, t in unresolved[:20]:
        print("  unresolved", k, t)
    if unresolved:
        print("Classify those first: python tools/anchors.py todo <out.jsonl>")
    if not a.dry:
        save(lines, nl)


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("todo")
    p.add_argument("out")
    p.add_argument("--all", action="store_true")
    p.set_defaults(fn=todo)
    p = sub.add_parser("roles")
    p.add_argument("files", nargs="+")
    p.set_defaults(fn=roles)
    p = sub.add_parser("rescore")
    p.add_argument("--dry", action="store_true")
    p.set_defaults(fn=rescore)
    a = ap.parse_args()
    a.fn(a)


if __name__ == "__main__":
    main()
