"""Mechanics for the /book-deep skill: pick candidates, brief a dive, record its dossier.

    python tools/deep.py select --genre fantasy --route cz [--limit 15]
    python tools/deep.py payload <outdir> <key> [<key> ...]
    python tools/deep.py record [--check] <dossier.json> [...]

`select` lists undived candidates best-first with their series and prereq, because
whether a volume can be read next is a judgement the cache cannot make on its own:
most rows carry no `prereq`. `payload` writes the per-book brief a dive subagent
reads. `record` validates each returned dossier against the skill's Phase 3 checks
and, only if every file passes, appends it to book-deep.jsonl and rewrites the
book's line in book-estimates.jsonl. Both files keep whatever newline they have on
disk: a checkout with core.autocrlf rewrites them as CRLF.
"""
import argparse, datetime, io, json, sys

EST, DEEP, CACHE, REVS, MEDIA = ("book-estimates.jsonl", "book-deep.jsonl", "book-cache.json",
                                 "book-revs.json", "book-media.json")
MANDATORY = ["axis:opening", "axis:occult", "axis:detective", "axis:worldbuilding",
             "axis:protagonist", "axis:motives"]
TAGS = {"exploration"}
VERDICTS = {"earns", "clear", "costs", "fires", "unknown"}
MIN_WIDTH = 6


def read(p):
    return io.open(p, encoding="utf-8", newline="").read()


def write(p, text):
    io.open(p, "w", encoding="utf-8", newline="").write(text)


def split(text):
    nl = "\r\n" if "\r\n" in text else "\n"
    return text.split(nl), nl


def books():
    return {b["key"]: b for b in json.loads(read(CACHE))["books"]}


def estimates():
    lines, _ = split(read(EST))
    return [json.loads(l) for l in lines[1:] if l.strip()]


def fresh(route, ttl):
    if route.get("state") != "verified" or not route.get("checked"):
        return False
    age = (datetime.date.today() - datetime.date.fromisoformat(route["checked"])).days
    return age <= ttl


def select(a):
    cache = books()
    ttl = json.loads(read(CACHE))["_ttlDays"]
    rows = []
    for e in estimates():
        b = cache.get(e["key"], {})
        if e.get("blocked") or not e.get("est") or e.get("depth"):
            continue
        if a.genre in TAGS and a.genre not in (b.get("tags") or []):
            continue
        genre = None if a.genre in TAGS else a.genre
        if any(v and b.get(f) != v for f, v in (("genre", genre), ("form", a.form), ("audience", a.audience))):
            continue
        cz = fresh(b.get("cz", {}), ttl.get("cz.verified", 180))
        en = fresh(b.get("enAudio", {}), ttl.get("enAudio.verified", 30))
        if not {"cz": cz, "en": en, "either": cz or en}[a.route]:
            continue
        rows.append((sum(e["est"]) / 2, e, b))
    rows.sort(key=lambda r: -r[0])
    for mid, e, b in rows[:a.limit]:
        print(f"{mid:5.1f} {e['est']} {e['key']} | {b.get('czTitle') or b.get('title')} | {b.get('author')}"
              f" | series {b.get('series')} | prereq {b.get('prereq')} | risks {e.get('risks')}")


def payload(a):
    est = {e["key"]: e for e in estimates()}
    cache = books()
    media = json.loads(read(MEDIA)).get("media", {})
    axes = sorted(k for k in json.loads(read(REVS))["revs"] if k.startswith("axis:"))
    for k in a.keys:
        b = cache[k]
        brief = {
            "estimateLine": est[k],
            "cache": {f: b.get(f) for f in ("title", "czTitle", "author", "series", "flags", "prereq",
                                            "genre", "form", "audience")},
            "czEdition": {f: b.get("cz", {}).get(f) for f in ("publisher", "year", "translator")},
            "blurb": media.get(k, {}).get("blurb"),
            "validAxisIds": axes,
        }
        write(f"{a.outdir}/{k}.json", json.dumps(brief, ensure_ascii=False, indent=1))
        print(k, "->", f"{a.outdir}/{k}.json")


def problems(d, revs, est_keys, dived):
    out = []
    axes = d.get("axes", {})
    for ax, v in axes.items():
        if ax not in revs:
            out.append(f"unknown axis id {ax}")
        if v.get("v") not in VERDICTS:
            out.append(f"{ax}: bad verdict {v.get('v')!r}")
        if not v.get("note"):
            out.append(f"{ax}: no note")
    out += [f"mandatory {ax} missing" for ax in MANDATORY if ax not in axes]
    fired = [ax for ax, v in axes.items() if v.get("v") == "fires"]
    if fired and not d.get("blocked"):
        out.append(f"fires without blocked: {fired}")
    if d.get("blocked"):
        if d.get("est") is not None:
            out.append("blocked but est set")
        if d["blocked"] not in fired:
            out.append("blocked axis has no fires verdict")
    else:
        e = d.get("est")
        if not (isinstance(e, list) and len(e) == 2 and e[0] <= e[1]):
            out.append(f"bad est {e}")
        elif e[1] - e[0] < MIN_WIDTH:
            out.append(f"range narrower than {MIN_WIDTH}: {e}")
    out += [f"risk {r} is not an unknown verdict" for r in d.get("risks", [])
            if axes.get(r, {}).get("v") != "unknown"]
    out += [f"leanedOn {ax} has no verdict" for ax in d.get("leanedOn", []) if ax not in axes]
    if not 400 <= len(d.get("why", "")) <= 1800:
        out.append(f"why length {len(d.get('why', ''))}")
    if d.get("key") not in est_keys:
        out.append("no estimate line")
    if d.get("key") in dived:
        out.append("already dived")
    return out


def record(a):
    today = datetime.date.today().isoformat()
    revs = json.loads(read(REVS))["revs"]
    lines, nl = split(read(EST))
    index = {json.loads(l)["key"]: i for i, l in enumerate(lines) if l.startswith('{"key"')}
    deep_text = read(DEEP)
    deep_lines, dnl = split(deep_text)
    dived = {json.loads(l)["key"] for l in deep_lines if l.startswith('{"key"')}
    dossiers = [json.loads(read(p)) for p in a.files]
    bad = False
    for d in dossiers:
        pr = problems(d, revs, index, dived)
        print(d.get("key"), "OK" if not pr else pr)
        bad = bad or bool(pr)
    if bad or a.check:
        return 1 if bad else 0

    added = []
    for d in dossiers:
        i = index[d["key"]]
        old = json.loads(lines[i])
        deps = {k: revs[k] for k in old["deps"] if not k.startswith("axis:")}
        deps.update({ax: revs[ax] for ax in d["axes"]})
        line = {"key": old["key"], "t": old["t"], "est": d.get("est")}
        if d.get("blocked"):
            line["blocked"] = d["blocked"]
        line.update({"leanedOn": d["leanedOn"], "risks": d["risks"], "at": today, "why": d["why"],
                     "deps": deps, "depth": "deep"})
        lines[i] = json.dumps(line, ensure_ascii=False)
        dossier = {"key": d["key"], "at": today,
                   "pre": {"est": old.get("est"), "leanedOn": old.get("leanedOn", []),
                           "risks": old.get("risks", [])},
                   "est": d.get("est")}
        if d.get("blocked"):
            dossier["blocked"] = d["blocked"]
        dossier.update({"readingOrder": d.get("readingOrder"), "axes": d["axes"]})
        added.append(json.dumps(dossier, ensure_ascii=False))
        print(d["key"], old.get("est"), "->", d.get("est") or "blocked " + d["blocked"], "| risks", d["risks"])

    write(EST, nl.join(lines))
    write(DEEP, deep_text.rstrip("\r\n") + dnl + dnl.join(added) + dnl)
    return 0


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("select")
    s.add_argument("--genre"), s.add_argument("--form"), s.add_argument("--audience")
    s.add_argument("--route", choices=["cz", "en", "either"], default="either")
    s.add_argument("--limit", type=int, default=15)
    s.set_defaults(fn=select)
    s = sub.add_parser("payload")
    s.add_argument("outdir"), s.add_argument("keys", nargs="+")
    s.set_defaults(fn=payload)
    s = sub.add_parser("record")
    s.add_argument("--check", action="store_true"), s.add_argument("files", nargs="+")
    s.set_defaults(fn=record)
    a = p.parse_args()
    return a.fn(a) or 0


if __name__ == "__main__":
    sys.exit(main())
