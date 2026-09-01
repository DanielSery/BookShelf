"""Cheap-model ranking for ONE triage slice, under a variant prompt.

Why this exists (2026-08-27): `ai_rank.py` is the right tool for the default
queue and structurally cannot rank a slice the default queue drops. Its
`DROP_CLS` never sends the `childrens` class to a model, and
`tools/ai-rank-prompt.md` scores children's rows a 1 — both correct as policy, both
fatal to a deliberate children's-crossover screen, which would come back all 1s.
Editing the live prompt to fix one slice would have invalidated all 11,611 stored
verdicts, so this runs a variant prompt over a named `src` instead.

Verdicts land in the SAME store, `book-ai-rank.jsonl`, so the no-repeat guarantee
still holds — but each carries `pv` (the variant name) and the digest of the
variant prompt. The main ranker therefore treats them as foreign and re-ranks
nothing, and `seal` still works on them because `done` is a fact about the work.

    python tools/ai_rank_scoped.py batches <outdir> --src kids-heading \
        --prompt tools/ai-rank-crossover-prompt.md --pv crossover-v1 [--size 500]
    python tools/ai_rank_scoped.py merge <outdir>/*.txt --prompt ... --pv ... --at YYYY-MM-DD
    python tools/ai_rank_scoped.py status --src ... --prompt ... --pv ...

Class exclusions are per-run and deliberate: on a slice the default classifier
calls `childrens` wholesale, its class column carries no signal, so the drops that
survive are only the ones a *different* filter established (already-read,
rejected, detective, and the sweep's own mechanical format/audio drop recorded in
`dropWhy`).
"""
import io, json, os, re, sys, hashlib, collections

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ai_rank

TRIAGE, STORE, ANNOT = ai_rank.TRIAGE, ai_rank.STORE, ai_rank.ANNOT
MODEL = ai_rank.MODEL
ANNOT_MAX = ai_rank.ANNOT_MAX

# A row is not sent when a filter OTHER than the children's classifier put it there.
DROP_CLS = ("already-read", "rejected", "detective", "manga", "romance-hi",
            "edition-audio", "edition-ebook", "edition-foreign")
DROP_WHY = ("format", "edition-audio", "taste")


def digest(prompt_path):
    txt = io.open(prompt_path, encoding="utf-8").read()
    body = txt.split("\n---\n", 1)[-1]
    return hashlib.sha256(body.encode()).hexdigest()[:12]


def load_works(src):
    rows = [json.loads(l) for l in io.open(TRIAGE, encoding="utf-8")][1:]
    works = {}
    for r in rows:
        if r.get("src") != src:
            continue
        k = ai_rank.workkey(r["t"], r["a"])
        w = works.setdefault(k, {"k": k, "t": r["t"], "a": r["a"], "p": r["p"],
                                 "y": r["y"], "skip": True})
        # One usable edition rescues a work whose other record was dropped.
        usable = (r.get("next") != "promoted" and r["cls"] not in DROP_CLS
                  and r.get("dropWhy") not in DROP_WHY)
        if usable:
            w["skip"] = False
            w.update(p=r["p"], y=r["y"])
    return works


def load_annots():
    out = {}
    if not os.path.exists(ANNOT):
        return out
    for l in io.open(ANNOT, encoding="utf-8"):
        if not l.strip():
            continue
        r = json.loads(l)
        if "_readme" in r:
            continue
        a = re.sub(r"[|\r\n\t]+", " ", r.get("a") or "").strip()
        if a:
            out[r["k"]] = a[:ANNOT_MAX]
    return out


def todo_list(src, pd, pv):
    works, store = load_works(src), ai_rank.load_store()
    out = []
    for k, w in works.items():
        if w["skip"]:
            continue
        s = store.get(k, {})
        if s.get("done"):
            continue
        if s.get("pd") == pd and s.get("pv") == pv:
            continue
        out.append(w)
    out.sort(key=lambda w: w["k"])
    return works, out


def cmd_batches(outdir, src, prompt, pv, size):
    pd = digest(prompt)
    works, todo = todo_list(src, pd, pv)
    ann = load_annots()
    os.makedirs(outdir, exist_ok=True)
    n = withann = 0
    for i in range(0, len(todo), size):
        chunk = todo[i:i + size]
        p = os.path.join(outdir, "scoped_%03d.txt" % (i // size))
        with io.open(p, "w", encoding="utf-8", newline="\n") as f:
            for w in chunk:
                a = ann.get(w["k"], "")
                withann += bool(a)
                f.write("%s|%s|%s|%s|%s|%s\n" % (w["k"], w["t"], w["a"], w["p"], w["y"], a))
        n += 1
    print("digest %s | pv %s | src %s" % (pd, pv, src))
    print("works %d | sendable %d | unjudged %d | wrote %d batches of %d"
          % (len(works), sum(1 for w in works.values() if not w["skip"]), len(todo), n, size))
    print("annotations on %d/%d rows (%.0f%%)" % (withann, len(todo),
                                                 withann / max(1, len(todo)) * 100))
    print("  -> %s" % outdir)


def cmd_merge(paths, prompt, pv, at):
    pd, store = digest(prompt), ai_rank.load_store()
    added = skipped = 0
    for p in paths:
        for line in io.open(p, encoding="utf-8"):
            line = line.strip()
            if not line or "|" not in line:
                continue
            parts = line.split("|")
            if len(parts) < 3:
                continue
            k, why = parts[0], parts[-1]
            if "~" not in k:
                skipped += 1
                continue
            mid = [x.strip() for x in parts[1:-1]]
            rec = idea = None
            if len(mid) >= 3 and all(x.isdigit() for x in mid[:3]):
                rec, idea, s = int(mid[0]), int(mid[1]), mid[2]
            elif mid and mid[-1].isdigit():
                s = mid[-1]
            else:
                skipped += 1
                continue
            if not s.isdigit() or not 1 <= int(s) <= 5 or rec not in (None, 0, 1) \
                    or idea not in (None, 0, 1):
                skipped += 1
                continue
            row = {"k": k, "s": int(s), "w": why[:48], "m": MODEL, "pd": pd,
                   "pv": pv, "at": at}
            if rec is not None:
                row["rec"], row["idea"] = rec, idea
            if store.get(k, {}).get("done"):
                row["done"] = store[k]["done"]
            store[k] = row
            added += 1
    ai_rank.save_store(store)
    print("merged %d verdicts (%d unparseable) | store now %d" % (added, skipped, len(store)))
    mine = [r for r in store.values() if r.get("pv") == pv]
    c = collections.Counter(r["s"] for r in mine)
    print("  %s: %d verdicts | scores %s" % (pv, len(mine), sorted(c.items(), reverse=True)))
    print("  recognised %d | nameable idea %d"
          % (sum(r.get("rec", 0) for r in mine), sum(r.get("idea", 0) for r in mine)))


def cmd_status(src, prompt, pv):
    pd = digest(prompt)
    works, todo = todo_list(src, pd, pv)
    store = ai_rank.load_store()
    mine = {k: r for k, r in store.items() if r.get("pv") == pv and r.get("pd") == pd}
    print("digest %s | pv %s | src %s" % (pd, pv, src))
    print("works %d | sendable %d | judged %d | remaining %d"
          % (len(works), sum(1 for w in works.values() if not w["skip"]), len(mine), len(todo)))
    if mine:
        c = collections.Counter(r["s"] for r in mine.values())
        for s in sorted(c, reverse=True):
            print("  %d: %d" % (s, c[s]))


def main():
    a = sys.argv[1:]
    if not a:
        sys.exit(__doc__)
    def opt(name, default=None):
        return a[a.index(name) + 1] if name in a else default
    prompt = opt("--prompt", os.path.join("tools", "ai-rank-crossover-prompt.md"))
    pv = opt("--pv", "crossover-v1")
    src = opt("--src", "kids-heading")
    cmd = a[0]
    if cmd == "batches":
        cmd_batches(a[1], src, prompt, pv, int(opt("--size", 500)))
    elif cmd == "merge":
        paths = [x for x in a[1:] if not x.startswith("--")
                 and x not in (prompt, pv, src, opt("--at", "\0"))]
        at = opt("--at")
        if not at or not re.match(r"^\d{4}-\d{2}-\d{2}$", at):
            sys.exit("pass --at YYYY-MM-DD; this script must not guess the date")
        cmd_merge(paths, prompt, pv, at)
    elif cmd == "status":
        cmd_status(src, prompt, pv)
    else:
        sys.exit(__doc__)


if __name__ == "__main__":
    main()
