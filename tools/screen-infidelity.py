"""Shortlist works whose infidelity content needs a judgement, by searching text we
already have. No model, no network, runs in about a second.

    python tools/screen-infidelity.py                # report
    python tools/screen-infidelity.py --out FILE     # also write the shortlist

WHAT IT SEARCHES. `book-annotations.jsonl` (11,625 Czech catalogue annotations, MARC
520) plus the work titles, and separately the English blurbs of the books already
absorbed into `book-cache.json`. Both are on disk already, which is the point: the
2026-08-27 ruling made premise-level infidelity a hard reject, and re-promoting the
corpus to find it would cost millions of tokens for a question a lexicon can shortlist.

WHAT IT CANNOT DO, and this is the whole caveat: **it cannot decide `premise` versus
`subplot`.** That is the distinction the reject turns on, and publisher copy is written
to sell rather than to disclose structure. So this produces a RANKED SHORTLIST and
nothing more - the tiers below are confidence that infidelity is *present*, never that
it is the premise. Two known error directions:

  * false positive - `milenka` means mistress OR simply "lover", and a courtesan in a
    historical novel is not a betrayed marriage. `Milenka Slunce` is a Montespan
    novel; the title alone cannot tell you whether a spouse exists.
  * false negative - an annotation that never mentions the marriage. Coverage of
    annotations is 91% of works to begin with, so a silent miss is guaranteed.

TIERS. `strong` needles bind to a marriage on their own (nevera, cizolozstvi,
mimomanzelsky, zahyba). `medium` needles need a marriage word within the same
annotation, because they are ambiguous alone (milenec, pomer s, tajny vztah).
`premise` is a separate flag, not a tier: set when a strong or medium hit lands in the
FIRST SENTENCE, or the annotation frames the book around it ("roman o nevere", "osou
romanu je"). It raises a candidate up the list; it does not settle anything.
"""
import io, json, os, re, sys, unicodedata, collections

ANN, CACHE, MEDIA = "book-annotations.jsonl", "book-cache.json", "book-media.json"

# Needles are matched against DE-ACCENTED lowercase text, so they carry no diacritics.
# That is the same lesson as the catalogue query: accented needles against a
# de-accented haystack silently never fire, which cost 26 dead tokens in triage.py.
STRONG = re.compile(r"nevery|nevera|neveru|neverou|nevern|cizolozs|cizolozn|"
                    r"mimomanzelsk|zahyba|zahybal|podvedeny manzel|podvedena manzelk|"
                    r"manzelska nevera|dvoji zivot|milostny trojuhelnik")
MEDIUM = re.compile(r"milenec|milenk|milence|milenci|pomer s |tajny vztah|tajna laska|"
                    r"laska mimo|svadi|zamiluje se do zenat|zamiluje se do vdan|"
                    r"vdan[ea]|zenat[yeh]|nemanzelsk")
MARRIED = re.compile(r"manzel|manzelk|manzelstv|chot |snoubenec|snoubenk|svatb|"
                     r"vdana|zenaty|zenateho|rodinn")
PREMISE = re.compile(r"roman o nevere|pribeh o nevere|osou roman|osou pribehu|"
                     r"hlavnim tematem|je pribehem|vypravi o nevere|"
                     r"kronika manzelstv|rozpad manzelstv")

# English, for the blurbs of books already on the shelf.
# `infidel` alone is a NON-BELIEVER, not an adulterer: it matched Hirsi Ali's memoir
# *Infidel* on the first run, a book about Islam and forced marriage. Only the
# `infidelit-` stem means the thing this axis is about.
EN_STRONG = re.compile(r"\baffair\b|adulter|infidelit|unfaithful|extramarital|"
                       r"cheat(?:s|ing|ed)? on (?:his|her|their)")
EN_MEDIUM = re.compile(r"\bmistress\b|\blover\b|another man|another woman|"
                       r"married (?:man|woman)")
EN_MARRIED = re.compile(r"\bmarri|\bhusband|\bwife\b|\bwives\b|\bspouse|engaged to")
# `affair` is also "the Dreyfus affair", "a family affair", "state affairs" - that
# false positive is already in the shelf data, so it is excluded explicitly.
EN_NOT = re.compile(r"dreyfus affair|state affairs|current affairs|family affair|"
                    r"foreign affairs|affairs of state|love affair with (?:the|a) (?:city|sea|language|idea)")


def flat(s):
    s = unicodedata.normalize("NFKD", s or "")
    return "".join(c for c in s if not unicodedata.combining(c)).lower()


def first_sentence(t):
    m = re.search(r"^(.{0,220}?[.!?])(?:\s|$)", t)
    return m.group(1) if m else t[:220]


def classify(text, strong, medium, married, premise=None, nots=None):
    """-> (tier, premise_flag, matched needle) or (None, ...)."""
    t = flat(text)
    if nots and nots.search(t):
        blanked = nots.sub(" ", t)
        if not (strong.search(blanked) or medium.search(blanked)):
            return None, False, None
        t = blanked
    ms, mm = strong.search(t), medium.search(t)
    if not ms and not mm:
        return None, False, None
    tier = "strong" if ms else ("medium" if married.search(t) else "weak")
    hit = (ms or mm)
    at = hit.start()
    prem = at < len(flat(first_sentence(text))) or bool(premise and premise.search(t))
    return tier, prem, hit.group(0)


def main(out=None):
    rows = []
    for l in io.open(ANN, encoding="utf-8"):
        if l.strip():
            r = json.loads(l)
            if "_readme" not in r:
                rows.append(r)
    title = {r["k"]: r["k"].split("~")[0].replace("-", " ") for r in rows}

    found = []
    for r in rows:
        text = (r.get("a") or "") + " " + title[r["k"]]
        tier, prem, hit = classify(text, STRONG, MEDIUM, MARRIED, PREMISE)
        if tier:
            found.append({"k": r["k"], "tier": tier, "premise": prem, "hit": hit,
                          "src": "annotation", "text": (r.get("a") or "")[:200]})

    print(f"CATALOGUE CORPUS — {len(rows)} works with an annotation")
    c = collections.Counter((f["tier"], f["premise"]) for f in found)
    for tier in ("strong", "medium", "weak"):
        n = sum(v for (t, _), v in c.items() if t == tier)
        p = c.get((tier, True), 0)
        print(f"  {tier:7s} {n:4d}   of which premise-shaped {p}")
    print(f"  total shortlisted {len(found)} ({len(found) * 100 / max(1, len(rows)):.1f}%)")

    # already-absorbed shelf, English blurbs
    shelf = []
    try:
        books = {b["key"]: b for b in json.load(io.open(CACHE, encoding="utf-8"))["books"]}
        media = (json.load(io.open(MEDIA, encoding="utf-8")) or {}).get("media", {})
    except OSError:
        books, media = {}, {}
    for k, b in books.items():
        m = media.get(k) or {}
        text = " ".join(filter(None, [m.get("blurb") if isinstance(m, dict) else None,
                                      b.get("title"), b.get("czTitle")]))
        tier, prem, hit = classify(text, EN_STRONG, EN_MEDIUM, EN_MARRIED, nots=EN_NOT)
        if tier:
            shelf.append({"k": k, "tier": tier, "premise": prem, "hit": hit,
                          "src": "blurb", "text": (m.get("blurb") or "")[:200]})
    print(f"\nABSORBED SHELF — {len(books)} books, {len(shelf)} shortlisted")
    for f in sorted(shelf, key=lambda x: (x["tier"] != "strong", not x["premise"], x["k"])):
        print(f"  {f['k'][:32]:34s} {f['tier']:7s} "
              f"{'PREMISE-SHAPED' if f['premise'] else '':15s} {f['hit']!r}")
        print(f"      {f['text'][:130]}")

    print("\nQUEUE — shortlisted works that are still unpromoted, premise-shaped first")
    sys.path.insert(0, "tools")
    import ai_rank as A
    wk, store = A.load_works(), A.load_store()
    live = {k for k, w in wk.items()
            if (r := store.get(k)) and not r.get("done") and not w["skip"]
            and r.get("s", 0) >= 4}
    q = [f for f in found if f["k"] in live]
    for f in sorted(q, key=lambda x: (x["tier"] != "strong", not x["premise"]))[:25]:
        print(f"  {wk[f['k']]['t'][:38]:40s} {f['tier']:7s} "
              f"{'PREMISE-SHAPED' if f['premise'] else '':15s} {f['hit']!r}")
    print(f"  {len(q)} of {len(live)} queued works shortlisted "
          f"({len(q) * 100 / max(1, len(live)):.1f}%)")

    if out:
        with io.open(out, "w", encoding="utf-8", newline="\n") as f:
            f.write(json.dumps({
                "_readme": "Infidelity shortlist from tools/screen-infidelity.py. A LEXICON "
                           "HIT, NOT A VERDICT: tiers are confidence that infidelity is "
                           "present, never that it is the premise, and premise vs subplot is "
                           "what the hard reject turns on. Regenerable in ~1s.",
                "schema": 1,
            }, ensure_ascii=False) + "\n")
            for r in sorted(found + shelf, key=lambda x: (x["src"], x["k"])):
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
        print(f"\n-> {out} ({len(found) + len(shelf)} rows)")


if __name__ == "__main__":
    o = sys.argv[sys.argv.index("--out") + 1] if "--out" in sys.argv else None
    main(o)
