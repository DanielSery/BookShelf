"""Score every tier-1 triage row so promotion effort can be spent top-down.

Zero LLM tokens. Every term below is computed from data already in the pulled
catalogue record, so a rerun is free and deterministic.

The point is NOT to predict the reader's score — book-estimates.jsonl does that,
expensively, for promoted titles only. The point is to order 9,000 rows so the
good ones are near the top, and to make "where do I stop reading the list?" an
explicit threshold instead of a vibe.

Validate before trusting: `--validate` checks where the already-promoted titles
land. A scorer that cannot rank the known-good titles highly is worthless, and
that check is cheaper than finding out later.

Run:  python tools/rank.py <scratchdir> [--validate]
"""
import json, io, os, re, sys, collections, unicodedata

# Publisher tiers. Curated lists first — these imprints choose few books and
# translate canon; the commercial houses publish by the metre.
TIER = {
    3: ("host", "argo", "odeon", "torst", "atlantis", "paseka", "prostor", "academia",
        "triton", "planeta9", "laser", "polaris", "plus", "vyšehrad", "pistorius",
        "mervart", "malvern", "dauphin", "druhé město", "volvox", "větrné mlýny",
        "labyrint", "kniha zlin", "brokilon", "straky", "gnóm", "gnom", "maraton"),
    2: ("talpress", "baronet", "epocha", "jota", "slovart", "euromedia", "knižní klub",
        "mladá fronta", "fantom print", "classic", "návrat", "zoner", "beta", "garamond",
        "supraphon", "melantrich", "svoboda", "lidové nakladatelství", "čs. spisovatel",
        "československý spisovatel", "snklhu", "práce", "wales", "perseus"),
    1: ("moba", "ikar", "motto", "alpress", "cosmopolis", "dobrovský", "metafora",
        "domino", "víkend", "levné knihy", "xyz", "brána", "fortuna libri", "pointa"),
}
ELIGIBLE_CLS = ("sf-fantasy", "litfic", "short-idea", "testimony-allegory")
# An Odeon / Světová knihovna-era translation is itself a canon signal in Czech
# publishing: those houses were the state literary imprints and picked accordingly.
CANON_ERA_PUB = ("odeon", "melantrich", "snklhu", "čs. spisovatel", "československý spisovatel",
                 "lidové nakladatelství", "svoboda", "mladá fronta")


def strip(s):
    s = unicodedata.normalize("NFKD", s or "")
    return "".join(c for c in s if not unicodedata.combining(c)).lower()


def pub_tier(pub):
    # strip() both sides: the needles were written with diacritics and the haystack
    # arrives without them, so mlada fronta, knizni klub, dobrovsky, lidove
    # nakladatelstvi and cs. spisovatel never matched before 2026-08-26 — and the
    # canon-era bonus below was dead for all but four imprints.
    p = strip(pub)
    for t in (3, 2, 1):
        if any(strip(k) in p for k in TIER[t]):
            return t
    return 0


def load_raw(scratch):
    """Re-read the pulls for fields triage truncated: full responsibility statement."""
    raw = {}
    for f in ("full.jsonl", "cat.jsonl", "pov.jsonl", "proza.jsonl", "cz.jsonl",
              "sweep.jsonl", "sw2.jsonl"):
        p = os.path.join(scratch, f)
        if not os.path.exists(p):
            continue
        for line in io.open(p, encoding="utf-8"):
            r = json.loads(line)
            raw.setdefault((r["name"], r.get("yr", "")), r.get("rs", ""))
    return raw


ORIG = re.compile(r"origin[áa]lu\s+(.+?)\s*(?:\.\.\.|,|;|\s+p[řr]elo[žz]|$)", re.I)


def main(scratch, validate=False):
    rows = [json.loads(l) for l in io.open("book-triage.jsonl", encoding="utf-8")]
    hdr, rows = rows[0], rows[1:]
    raw = load_raw(scratch)

    # --- collapse RECORDS into WORKS before scoring. One work = one decision.
    # Scoring records ranked Ja, robot at both +53 (Triton print) and -24
    # (OneHotBook audio); the audio edition buried the work. Take the best
    # edition's evidence and count the rest as printings.
    CLS_RANK = {c: 2 for c in ELIGIBLE_CLS}
    CLS_RANK["unknown"] = 1
    works = collections.defaultdict(
        lambda: {"recs": [], "tier": 0, "cls": None, "known": False})
    for r in rows:
        w = works[(strip(r["t"]), strip(r["a"]))]
        w["recs"].append(r)
        w["tier"] = max(w["tier"], pub_tier(r["p"]))
        if CLS_RANK.get(r["cls"], 0) > CLS_RANK.get(w["cls"], 0):
            w["cls"] = r["cls"]
        w["known"] |= bool(r.get("knownAuthor"))
    adult_by_author = collections.Counter()
    for w in works.values():
        if w["tier"] >= 2 and w["cls"] in ELIGIBLE_CLS:
            adult_by_author[strip(w["recs"][0]["a"])] += 1
    printings = {k: len(w["recs"]) for k, w in works.items()}
    workof = {id(r): works[(strip(r["t"]), strip(r["a"]))] for r in rows}

    for r in rows:
        if r.get("next") == "promoted":
            r["rank"] = None
            continue
        w = workof[id(r)]
        t = w["tier"]
        s = 0
        why = []
        s += t * 8
        if t:
            why.append(f"pub-tier{t}:+{t * 8}")
        if w["cls"] in ELIGIBLE_CLS:
            s += 10
            why.append("eligible-cls:+10")
        elif w["cls"] == "unknown":
            s += 2
            why.append("unknown-cls:+2")
        else:
            s -= 40
            why.append("dropped-cls:-40")
        n = adult_by_author[strip(r["a"])]
        if n >= 2:
            b = min(12, 3 * n)
            s += b
            why.append(f"author-adult-holdings{n}:+{b}")
        pr = printings[(strip(r["t"]), strip(r["a"]))]
        if pr >= 2:
            b = min(10, 4 * (pr - 1))
            s += b
            why.append(f"printings{pr}:+{b}")
        if any(strip(k) in strip(x["p"]) for x in w["recs"] for k in CANON_ERA_PUB):
            s += 6
            why.append("canon-era-imprint:+6")
        if w["known"]:
            s += 15
            why.append("known-author:+15")
        rs = raw.get((r["t"], r["y"]), "")
        m = ORIG.search(rs)
        if m:
            r["orig"] = m.group(1)[:60]
            s += 3
            why.append("orig-title-known:+3")
        r["rank"] = s
        r["rankWhy"] = " ".join(why)

    with io.open("book-triage.jsonl", "w", encoding="utf-8", newline="\n") as f:
        hdr["_rank"] = ("Deterministic priority score from tools/rank.py — zero LLM cost. "
                        "Orders the review queue; it is NOT a predicted reader score and "
                        "must never be shown as one. Terms: publisher tier, eligible class, "
                        "author's adult-imprint holdings, reprint count, canon-era imprint, "
                        "author already known to the database, original title recoverable. "
                        "`rankWhy` shows the arithmetic so a bad ordering is debuggable.")
        hdr["_rankThreshold"] = ("Promote top-down and stop at the agreed cutoff; see the "
                                 "distribution printed by tools/rank.py. Everything below "
                                 "the cutoff stays on disk and costs nothing.")
        hdr["_rankBacktest"] = (
            "MEASURED 2026-08-26, not assumed. Holdout: score the already-promoted works "
            "as if unseen and see where they land among 15,346 works. Latest run, 113 "
            "holdout titles: median rank 1955 = top 12.7%; top 1000 captures 31%, top "
            "2500 54%, top 4000 67%. Three fixes got it there: collapse records into "
            "works (19.9% -> 14.6%), stop letting broad trade houses set a dropping class "
            "(Baronet and Dobrovsky publish both romance and Crichton; that scored Jursky "
            "park and Promena at -40), and de-accent the publisher needles (14.6% -> "
            "12.7%; mlada fronta, knizni klub, dobrovsky, lidove nakladatelstvi, cs. "
            "spisovatel and the whole canon-era bonus had never matched anything). IT "
            "PLATEAUS AROUND HERE - catalogue metadata does not encode quality, so do NOT "
            "tune this further expecting much. Its job is only to decide how large a "
            "slice deserves an LLM pass.")
        f.write(json.dumps(hdr, ensure_ascii=False) + "\n")
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    scored = [r for r in rows if r.get("rank") is not None]
    scored.sort(key=lambda r: -r["rank"])
    print(f"scored {len(scored)} rows\n")
    buckets = collections.Counter()
    for r in scored:
        buckets[min(60, 10 * (r["rank"] // 10))] += 1
    run = 0
    print(f"{'score':>7} {'rows':>7} {'cumulative':>11}")
    for b in sorted(buckets, reverse=True):
        run += buckets[b]
        print(f"{'>=' + str(b):>7} {buckets[b]:>7} {run:>11}")

    if validate:
        print("\n--- validation: where would the already-found good titles rank?")
        want = ("Výdech", "Příběhy vašeho života", "Levá ruka tmy", "Děti času", "Hana",
                "Čaropisci", "Den trifidů", "Europeana", "Silo", "Dárce", "Nadace",
                "Já, robot", "Marťanská kronika", "Síň slávy mistrů SF")
        by_t = {r["t"]: r for r in rows}
        for w in want:
            r = by_t.get(w)
            if not r:
                print(f"   {w:28s} NOT IN TRIAGE")
            elif r.get("rank") is None:
                print(f"   {w:28s} already tier-2")
            else:
                pos = 1 + sum(1 for x in scored if x["rank"] > r["rank"])
                print(f"   {w:28s} score {r['rank']:3d}  ~rank {pos:5d}/{len(scored)}  {r['rankWhy']}")


if __name__ == "__main__":
    a = [x for x in sys.argv[1:] if not x.startswith("--")]
    main(a[0] if a else ".", "--validate" in sys.argv)
