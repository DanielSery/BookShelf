"""Auto-reject works the CATALOGUER classed detective, crime or erotic.

The corpus half of the heading veto: `ai_rank.HEADING_VETO` owns the stems and the
reasoning, `ai_rank.py veto` downgrades verdicts already written, `cmd_batches` stops
new ones being bought, and this writes the reject rows that keep the work out of every
queue by name. Ruled by the reader 2026-08-28.

Only the genre heading is ever read, never a subject keyword: the same stems over `kw`
take Jane Eyre, Dostoyevsky's `Krotkaja` and `Cold Mountain`. `milostn` and `thriller`
are both out - see the note on `ai_rank.HEADING_VETO`, which owns that decision.

    python tools/screen-headings.py            # dry run, prints what it would write
    python tools/screen-headings.py --write
    python tools/screen-headings.py --shelf [--write]   # retract them from the shelf too
"""
import io, json, os, sys, collections

sys.path.insert(0, "tools")
import ai_rank as A
import promote as P

REJECTS = "book-rejects.jsonl"
TODAY = os.environ.get("BOOK_TODAY", "2026-08-28")


def main(write):
    wk, hdgs = A.load_works(), A.load_headings()
    store = A.load_store()
    decided = P.already_decided()
    rows, skipped = [], collections.Counter()
    for k, w in wk.items():
        gf = hdgs.get(k, [])
        hit = A.heading_veto(gf)
        if not hit:
            continue
        h = " ".join(gf).lower()
        skipped["carry a matching heading"] += 1
        if w["skip"]:
            skipped["  already dropped in triage"] += 1
            continue
        if P._decided(w, *decided):
            skipped["  already estimated or rejected"] += 1
            continue
        term = next(x for x in h.split() if any(rx.search(x) for rx, _ in A.HEADING_VETO))
        rows.append({"entity": P.deacc(w["t"]), "key": P.slug(w["t"])[:44],
                     "level": "title", "author": w["a"],
                     "filter": hit,
                     "why": f"Catalogue genre heading: {term}. Auto-rejected on the "
                            f"heading alone, never read by a model.",
                     "at": TODAY, "source": "catalogue-heading"})
    for k, v in skipped.items():
        print(f"{v:6d}  {k}")
    print(f"{len(rows):6d}  TO REJECT")
    by = collections.Counter(r["filter"] for r in rows)
    print("        " + ", ".join(f"{v} {k}" for k, v in by.most_common()))
    # What this actually saves TODAY is small and worth stating plainly: only a verdict
    # of 4 reaches a promotion queue, and 11 of these sit there. The rest is durability -
    # a recorded decision with an axis on it, which survives a cutoff change.
    at4 = 0
    for k, w in wk.items():
        v = store.get(k)
        if not v or v.get("s") != 4 or w["skip"] or P._decided(w, *decided):
            continue
        at4 += bool(A.heading_veto(hdgs.get(k, [])))
    print(f"        of these, {at4} carry a verdict of 4 - the only ones a promotion "
          f"queue would have reached")
    if not write:
        print("\ndry run. Rerun with --write to append them to " + REJECTS)
        for r in rows[:10]:
            print(f"   {r['filter'].replace('axis:',''):16s} {r['entity'][:44]:46s} {r['why'][:46]}")
        return
    with io.open(REJECTS, "a", encoding="utf-8", newline="\n") as fh:
        for r in rows:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(f"\nappended {len(rows)} rows to {REJECTS}")
    print("They are excluded from every future queue by promote.already_decided().")


def shelf(write):
    """Retract shelf entries whose catalogue GENRE HEADING already decides the filter.

    The join is (title, author) and never title alone: `Cizinec` is Camus on the shelf
    and Harlan Coben in the catalogue, and a bare-title match moved Coben's
    `detektivni romany` onto Camus - which nearly cost a [68, 78] proposal on
    2026-08-28. A shelf book whose author string does not match is left alone; missing
    a retraction is recoverable and deleting the wrong book is not.
    """
    wk, hdgs = A.load_works(), A.load_headings()
    ent = collections.defaultdict(list)
    for k, w in wk.items():
        ent[(P.deacc(w["t"]).strip().lower(), P.authorid(w["a"]))].append(k)
    cache = json.load(io.open(P.CACHE, encoding="utf-8"))
    media = json.load(io.open(P.MEDIA, encoding="utf-8"))
    est = P.load_jsonl(P.EST)
    hits = []
    for b in cache["books"]:
        t = P.deacc(b.get("czTitle") or b.get("title"))
        ks = ent.get((t.strip().lower(), P.authorid(b.get("author") or "")))
        gf = hdgs.get(ks[0], []) if ks else []
        axis = A.heading_veto(gf)
        if not axis:
            continue
        h = " ".join(gf).lower()
        term = next(x for x in h.split() if any(rx.search(x) for rx, _ in A.HEADING_VETO))
        hits.append((b, term, axis))
    for b, term, axis in hits:
        e = [r for r in est if r.get("key") == b["key"]]
        print(f"   {str(e[0]['est']) if e else '-':10s} {(b.get('czTitle') or b['title'])[:34]:36s} "
              f"{term:14s} {axis}")
    print(f"{len(hits)} shelf entries to retract")
    if not write:
        print("dry run. Rerun with --shelf --write")
        return
    keys = {b["key"] for b, _, _ in hits}
    cache["books"] = [b for b in cache["books"] if b["key"] not in keys]
    for k in keys:
        media.get("media", {}).pop(k, None)
    json.dump(cache, io.open(P.CACHE, "w", encoding="utf-8", newline="\n"),
              ensure_ascii=False, indent=1)
    json.dump(media, io.open(P.MEDIA, "w", encoding="utf-8", newline="\n"),
              ensure_ascii=False, indent=1)
    hdr = io.open(P.EST, encoding="utf-8").readline()
    with io.open(P.EST, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(hdr)
        for r in est:
            if r.get("key") not in keys:
                fh.write(json.dumps(r, ensure_ascii=False) + "\n")
    with io.open(REJECTS, "a", encoding="utf-8", newline="\n") as fh:
        for b, term, axis in hits:
            fh.write(json.dumps({
                "entity": P.deacc(b.get("czTitle") or b["title"]), "key": b["key"],
                "level": "title", "author": b.get("author") or "",
                "filter": axis,
                "why": f"Catalogue genre heading: {term}. Retracted from the shelf on "
                       f"the heading alone.",
                "at": TODAY, "source": "catalogue-heading-retro"}, ensure_ascii=False) + "\n")
    print(f"retracted {len(hits)} from the shelf, estimates and blurbs; reject rows appended")


if __name__ == "__main__":
    if "--shelf" in sys.argv:
        shelf("--write" in sys.argv)
    else:
        main("--write" in sys.argv)
