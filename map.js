// The Map tab. Loaded before the main script and run against its globals (D, F, esc, nice,
// band, tone, ten, rng, cover, accessLine, LIBRARY, LEGEND, render, setView, store, recall,
// candidateFilter, readFilter), all of which exist by the time anything here is called.
// Names are map-prefixed because every top-level declaration shares one scope with
// index.html.

const MAP = {
  opts: null, seeds: [], openBook: null, hover: null, cam: null, built: null, pendingFocus: null,
  ro: null, raf: 0, gen: 0, memo: null, world: null, wix: null,
};

const MAP_BAND_VAR = { 'S+': '--b-S', S: '--b-S', A: '--b-A', B: '--b-B', C: '--b-C', F: '--b-F' };
const MAP_PAD = 28;
const MAP_SHOWN = 40;

function mapOpts() {
  if (!MAP.opts) {
    let saved = {};
    try { saved = JSON.parse(recall('bookshelf.map')) || {}; } catch {}
    // Every visit starts on the maps (reader, 2026-10-29); Similar is a switch, not a place to stay.
    MAP.opts = { mode: 'books', minSim: 0.4, unread: true, sameAuthor: false, tags: [], worldOrder: 'story', ...saved, view: 'map' };
  }
  return MAP.opts;
}
const mapSaveOpts = () => store('bookshelf.map', JSON.stringify(MAP.opts));

function mapBuild() {
  if (MAP.built && MAP.built.D === D) return MAP.built;
  const sim = D.sim, NT = sim.tags.length, NF = NT + sim.facets.length;
  const byKey = Object.fromEntries(D.books.map(b => [b.key, b]));
  const readByKey = Object.fromEntries(D.read.rows.map(r => [r.key, r]));
  const dense = v => { const d = new Float32Array(NF); v.forEach(([f, x]) => { d[f] = x; }); return d; };
  const bySimIdx = [], books = [];
  sim.books.forEach((s, i) => {
    const kind = s.id[0], key = s.id.slice(2);
    const row = kind === 'c' ? byKey[key] : readByKey[key];
    if (!row) return;
    const p = {
      id: s.id, kind, key, row, x: s.x, y: s.y, sv: s.v, d: dense(s.v), i: books.length, ref: 'b' + books.length,
      title: kind === 'c' ? row.cache.czTitle || row.cache.title : row.title,
      alt: kind === 'c' && row.cache.czTitle && row.cache.title !== row.cache.czTitle ? row.cache.title : '',
      author: kind === 'c' ? row.cache.author || '' : row.author,
      score: kind === 'c' ? (row.est ? row.mid : null) : row.score,
    };
    bySimIdx[i] = p;
    books.push(p);
  });
  const profiled = books.length;
  // A series is one point (reader, 2026-10-25: he reads a series whole): its volumes'
  // centroid and summed profile, so it is matched as the one thing he would pick up.
  // Read volumes of one series group apart from its unread ones: a read series is a
  // diamond scored by what he gave it, the unread rest a square scored by prediction.
  const vols = new Map();
  books.forEach(p => {
    const sid = p.kind === 'c' ? D.seriesOf[p.key] : D.readSeriesOf[p.key];
    if (sid) vols.set(p.kind + ':' + sid, [...(vols.get(p.kind + ':' + sid) || []), p]);
  });
  const shown = new Map(), aliases = new Map();
  vols.forEach((ps, g) => {
    const kind = g[0], sid = g.slice(2), read = kind === 'r';
    const d = new Float32Array(NF);
    ps.forEach(m => m.d.forEach((x, f) => { d[f] += x; }));
    const norm = Math.hypot(...d) || 1;
    const row = read ? readSeriesEntry(D.readSeries[sid]) : seriesEntry(D.series[sid]);
    const p = {
      id: (read ? 'rs:' : 's:') + sid, kind, isSeries: true, key: row.key, row, vols: ps,
      x: ps.reduce((t, m) => t + m.x, 0) / ps.length, y: ps.reduce((t, m) => t + m.y, 0) / ps.length,
      d: d.map(x => x / norm), title: row.s.name, alt: row.s.nameEn && row.s.nameEn !== row.s.name ? row.s.nameEn : '',
      author: read ? row.author : row.cache.author, score: read ? row.score : row.est ? row.mid : null,
    };
    p.sv = [...p.d].map((x, f) => [f, x]).filter(([, x]) => x > 0);
    ps.forEach(m => { shown.set(m, p); aliases.set(m.id, p); });
    aliases.set(p.id, p);
  });
  const visible = books.filter(p => !shown.has(p)).concat([...new Set(shown.values())]);
  books.length = 0;
  visible.forEach((p, i) => { p.i = i; p.ref = 'b' + i; books.push(p); aliases.set(p.id, p); });
  const authors = [];
  sim.authors.forEach(a => {
    const members = [...new Set(a.books.map(i => bySimIdx[i]).filter(Boolean).map(m => shown.get(m) || m))];
    if (!members.length) return;
    const d = new Float32Array(NF);
    members.forEach(m => m.d.forEach((x, f) => { d[f] += x; }));
    const norm = Math.hypot(...d) || 1;
    const read = members.filter(m => m.kind === 'r');
    const scored = read.filter(m => m.score != null);
    const live = members.filter(m => m.kind === 'c' && m.score != null);
    const au = {
      name: a.name, x: a.x, y: a.y, members, i: authors.length, ref: 'a' + authors.length, hasRead: read.length > 0, scoredRead: scored.length > 0,
      d: d.map(x => x / norm),
      score: scored.length ? Math.max(...scored.map(m => m.score))
           : live.length ? Math.max(...live.map(m => m.score)) : null,
    };
    au.sv = [...au.d].map((x, f) => [f, x]).filter(([, x]) => x > 0);
    members.forEach(m => { m.authorRef = au; });
    authors.push(au);
  });
  const tagIndex = Object.fromEntries(sim.tags.map(([id], i) => [id, i]));
  const regions = {};
  for (const [mode, list] of Object.entries(sim.regions || {}))
    regions[mode] = list.map(r => ({ x: r.x, y: r.y, label: r.tags.map(t => sim.tags[tagIndex[t]][1]).join(' · ') }));

  const was = MAP.seeds;
  MAP.built = { D, NT, books, authors, regions, tagIndex, ids: new Set(aliases.keys()), byId: aliases,
                tagIds: sim.tags.map(t => t[0]), tagLabel: sim.tags.map(t => t[1]), tagGroup: sim.tags.map(t => t[3]),
                unmapped: D.books.length + D.read.rows.length - profiled };
  MAP.seeds = was.map(s => s.members ? authors.find(a => a.name === s.name) : books.find(b => b.id === s.id)).filter(Boolean);
  MAP.memo = null;
  return MAP.built;
}

const mapHas = id => !!(D && D.sim && mapBuild().ids.has(id));
const mapPoints = B => MAP.opts.mode === 'authors' ? B.authors : B.books;
const mapByRef = (B, ref) => ref[0] === 'a' ? B.authors[+ref.slice(1)] : B.books[+ref.slice(1)];

function mapMatches(B) {
  const cf = candidateFilter(), rf = readFilter();
  const need = MAP.opts.tags.map(t => B.tagIndex[t]).filter(f => f != null);
  B.books.forEach(p => { p.on = (p.kind === 'c' ? cf(p.row) : rf(p.row)) && need.every(f => p.d[f] > 0); });
  B.authors.forEach(a => { a.on = a.members.some(m => m.on); });
  MAP.gen++;
}

function simDot(a, b) {
  let s = 0;
  for (const [f, x] of a.sv) s += x * b.d[f];
  return s;
}

// "Close to all of them" is the weakest link: a book scores its lowest similarity to
// any seed, so a match for one seed alone cannot float to the top of a multi-seed list.
function mapResults(B) {
  const o = MAP.opts, seeds = MAP.seeds;
  const key = [MAP.gen, o.mode, o.unread, o.sameAuthor, ...seeds.map(s => s.ref)].join('|');
  if (MAP.memo && MAP.memo.key === key) return MAP.memo.all;
  let pool;
  if (o.mode === 'authors') pool = B.authors.filter(a => a.on && !seeds.includes(a));
  else {
    // The reader knows a seed's author already, and a long series would otherwise
    // fill the whole list with its own volumes.
    const own = o.sameAuthor ? new Set() : new Set(seeds.map(s => s.authorRef));
    pool = B.books.filter(p => p.on && !seeds.includes(p) && !(o.unread && p.kind === 'r') && !own.has(p.authorRef));
  }
  const all = pool.map(p => { const per = seeds.map(s => simDot(s, p)); return { p, per, sim: Math.min(...per) }; })
    .sort((a, b) => b.sim - a.sim);
  MAP.memo = { key, all };
  return all;
}

const mapAbove = B => mapResults(B).filter(r => r.sim >= MAP.opts.minSim);

const mapSimilar = () => MAP.opts.view === 'similar';

// With a selection, only it and its listed matches stay opaque and clickable.
const mapFocusSet = B => MAP.seeds.length && mapSimilar()
  ? new Set([...MAP.seeds, ...mapAbove(B).slice(0, MAP_SHOWN).map(r => r.p)]) : null;

function sharedTags(seeds, p, B, n = 3) {
  return p.sv.filter(([f]) => f < B.NT)
    .map(([f, x]) => [x * Math.min(...seeds.map(s => s.d[f])), f]).filter(([c]) => c > 0)
    .sort((a, b) => b[0] - a[0]).slice(0, n).map(([, f]) => B.tagLabel[f]);
}

function mapScoreText(p) {
  if (p.isSeries && p.kind === 'r') return `read series of ${p.row.vols.length} · ` +
    (p.score == null ? 'not finished' : `average ${ten(p.score)}`);
  if (p.isSeries) return `series of ${p.row.vols.length} · ` + (p.row.est ? `predicted ${rng(p.row.est[0], p.row.est[1])}` : 'blocked');
  if (p.members) {
    if (p.score == null) return p.hasRead ? 'read · not finished' : 'blocked only';
    return p.scoredRead ? `read · best ${ten(p.score)}`
      : `${p.hasRead ? 'read, not finished · ' : ''}best prediction ${ten(p.score)}`;
  }
  if (p.kind === 'r') return p.score == null ? 'read · not finished, no score' : `read · ${ten(p.score)}`;
  return p.row.est ? `predicted ${rng(p.row.est[0], p.row.est[1])}` : 'blocked';
}

const mapLetter = p => p.score == null ? '—' : ten(p.score);
const mapTone = p => p.score == null ? 'bN' : tone(p.score);
const mapCount = (n, word) => `${n} ${word}${n === 1 ? '' : 's'}`;
const mapLabel = p => p.members ? p.name : p.title;

// The first verified route only: the full access line is in the panel head once a
// book is selected.
function mapRowLink(p) {
  if (p.members || p.kind !== 'c' || p.isSeries) return '';
  const b = p.row;
  if (b.hasCz && b.cz.recordUrl) return `<a class="rowlink" href="${esc(b.cz.recordUrl)}" target="_blank" rel="noreferrer"
    title="Borrow — Czech print: open the catalogue record at ${esc(LIBRARY[b.lib])}">Borrow ↗</a>`;
  if (b.hasEloan && b.cz.recordUrl) return `<a class="rowlink" href="${esc(b.cz.recordUrl)}" target="_blank" rel="noreferrer"
    title="Borrow — library e-loan: open the e-loan record at Městská knihovna Valašské Meziříčí">E-loan ↗</a>`;
  const ec = b.enGem && b.cache.enCopy;
  if (ec) return `<a class="rowlink" href="${esc(ec.recordUrl)}" target="_blank" rel="noreferrer"
    title="Borrow in English: open the English edition at ${esc(LIBRARY[ec.library])}">EN copy ↗</a>`;
  return '';
}

function mapRow(p, B, r) {
  const sub = p.members ? mapCount(p.members.length, 'book') : p.author;
  const why = r ? sharedTags(MAP.seeds, p, B) : [];
  const per = r && r.per.length > 1
    ? ` title="${esc(MAP.seeds.map((s, i) => `${mapLabel(s)}: ${Math.round(r.per[i] * 100)} %`).join('\n'))}"` : '';
  const added = MAP.seeds.includes(p), sameKind = !!p.members === (MAP.opts.mode === 'authors');
  // A book listed under an author on the authors map opens in place; leaving for the
  // books map is the separate "On map" button, so a glance does not lose the author.
  const open = !sameKind && MAP.openBook === p.ref;
  const main = sameKind ? `data-pick="${p.ref}"` : `data-detail="${p.ref}" aria-expanded="${open}"`;
  return `<li class="prow"><button type="button" class="pick ${mapTone(p)}" ${main}>
      <span class="pl">${mapLetter(p)}</span>
      <span class="pt"><b>${esc(mapLabel(p))}</b><br><span class="ps">${esc(sub)} · ${esc(mapScoreText(p))}</span>
        ${why.length ? `<br><span class="pw">${esc(why.join(' · '))}</span>` : ''}</span>
      ${r ? `<span class="pp"${per}>${Math.round(r.sim * 100)} %<span class="pbar"><i style="width:${Math.round(r.sim * 100)}%"></i></span></span>` : ''}
    </button><span class="pacts">${sameKind ? `<button type="button" class="addseed" data-add="${p.ref}"
      title="${added ? 'Remove from the selection' : 'Add to the selection — find titles close to all of it'}">${added ? '−' : '+'}</button>`
      : `<button type="button" class="rowbtn" data-pick="${p.ref}" title="Open the ${p.members ? 'authors' : 'books'} map with this selected">On map</button>`}${
      mapRowLink(p)}</span>${open ? `<div class="rowdetail">${mapBookDetail(p, B)}</div>` : ''}</li>`;
}

const mapList = (rows, B) => `<ol class="picks">${rows.map(r => r.p ? mapRow(r.p, B, r) : mapRow(r, B, null)).join('')}</ol>`;

const mapTagBtn = (f, B) => `<button type="button" class="badge tagbtn" data-tagfilter="${esc(B.tagIds[f])}"
  title="Show only titles with this tag on the map">${esc(B.tagLabel[f])}</button>`;

function mapChips(p, B, n = 10) {
  return p.sv.filter(([f]) => f < B.NT).sort((a, b) => b[1] - a[1]).slice(0, n).map(([f]) => mapTagBtn(f, B)).join('');
}

function mapCommonChips(seeds, B, n = 8) {
  const common = [];
  for (let f = 0; f < B.NT; f++) {
    const m = Math.min(...seeds.map(s => s.d[f]));
    if (m > 0) common.push([m, f]);
  }
  return common.sort((a, b) => b[0] - a[0]).slice(0, n).map(([, f]) => mapTagBtn(f, B)).join('');
}

// Candidates carry the reader-facing pitch (blurb where none was written); a read book
// has only the reader's own notes, which are long, so they fold away.
function mapWhy(p) {
  if (p.kind === 'c') {
    const m = p.row.media || {};
    return m.pitch ? `<p class="pitch">${esc(m.pitch)}</p>` : m.blurb ? `<p class="blurb">${esc(m.blurb)}</p>` : '';
  }
  if (p.isSeries) return '';
  return p.row.notes ? `<details class="scoring"><summary>Your notes</summary>
    <p class="why">${esc(p.row.notes)}</p></details>` : '';
}

const MAP_GROUPS = [['Kind', 'Kind'], ['Setting', 'Setting'], ['Theme', 'Theme'], ['Tone', 'Tone'],
                    ['Audience', 'Audience'], ['Lead', 'Lead character'], ['Telling', 'Telling']];

function mapFillTags(B) {
  const sel = F('maptag');
  if (!sel || sel.dataset.built === String(B.books.length)) return;
  const n = new Array(B.NT).fill(0);
  B.books.forEach(p => p.sv.forEach(([f]) => { if (f < B.NT) n[f]++; }));
  sel.innerHTML = '<option value="">add a tag…</option>' + MAP_GROUPS.map(([g, label]) =>
    `<optgroup label="${esc(label)}">${B.tagIds.map((t, f) => [t, f]).filter(([, f]) => B.tagGroup[f] === g && n[f])
      .sort((a, b) => B.tagLabel[a[1]].localeCompare(B.tagLabel[b[1]]))
      .map(([t, f]) => `<option value="${esc(t)}">${esc(B.tagLabel[f])} (${n[f]})</option>`).join('')}</optgroup>`).join('');
  sel.dataset.built = String(B.books.length);
}

function mapHead(B) {
  const seeds = MAP.seeds, close = '<button type="button" class="unpick" data-unpick title="Clear the selection">×</button>';
  if (seeds.length > 1) {
    const common = mapCommonChips(seeds, B);
    return `<div class="sidehead"><div><div class="bk-title">Selection: ${mapCount(seeds.length, seeds[0].members ? 'author' : 'title')}</div>
        <div class="bk-meta">showing what is close to all of them at once</div></div>${close}</div>
      <ul class="seeds">${seeds.map(s => `<li class="${mapTone(s)}"><span class="pl">${mapLetter(s)}</span>
        <button type="button" class="linkish" data-focus="${s.ref}">${esc(mapLabel(s))}</button>
        <button type="button" class="unpick" data-unseed="${s.ref}" title="Remove from the selection">×</button></li>`).join('')}</ul>
      ${common ? `<div class="mapnote">Shared:</div><div class="badges">${common}</div>`
               : '<p class="mapnote">The selection shares no tag, so nothing can be close to all of it.</p>'}`;
  }
  const sel = seeds[0];
  if (sel.members) return `<div class="sidehead"><div><div class="bk-title">${esc(sel.name)}</div>
      <div class="bk-meta">${esc(mapCount(sel.members.length, 'book'))} · ${esc(mapScoreText(sel))}</div></div>${close}</div>
    <div class="badges">${mapChips(sel, B)}</div>`;
  return mapBookDetail(sel, B, close, true);
}

function mapBookDetail(p, B, close = '', authorLink = false) {
  return `<div class="sidehead">${cover(p.row.media || {}, p.author)}
      <div><div class="bk-title">${esc(p.title)}</div>
        ${p.alt ? `<div class="bk-alt">${esc(p.alt)}</div>` : ''}
        <div class="bk-author">${authorLink && p.authorRef
          ? `<button type="button" class="linkish" data-pick="${p.authorRef.ref}" title="Show the author on the authors map">${esc(p.author)}</button>`
          : esc(p.author)}</div>
        <div class="scorerow ${mapTone(p)}"><span class="bandletter small">${mapLetter(p)}</span>
          <span class="scorelabel">${esc(mapScoreText(p))}</span></div></div>${close}</div>
    ${mapWhy(p)}
    ${p.isSeries && p.kind === 'r' ? readVolumes(p.row.vols)
      : p.isSeries ? `<ol class="vols">${p.row.s.members.map(m => `<li${m.n ? ` value="${+m.n}"` : ''}>${volumeLine(m.book)}</li>`).join('')}</ol>`
      : p.kind === 'c' ? `<div class="access">${accessLine(p.row)}</div>` : ''}
    <div class="badges">${mapChips(p, B)}</div>`;
}

function mapResultsHtml(B) {
  const above = mapAbove(B), seeds = MAP.seeds;
  const what = MAP.opts.mode === 'authors' ? 'authors' : 'titles';
  let out = above.length
    ? `<h4>${seeds.length > 1 ? 'Close to all selected' : 'Most similar'}
         <span class="sub">${above.length} ${what} above the threshold${above.length > MAP_SHOWN ? `, showing ${MAP_SHOWN}` : ''}</span></h4>
       ${mapList(above.slice(0, MAP_SHOWN), B)}`
    : `<p class="mapnote">Nothing is above ${Math.round(MAP.opts.minSim * 100)} %. Lower the threshold or loosen the filters above.</p>`;
  if (seeds.length === 1 && seeds[0].members) {
    const own = seeds[0].members.slice().sort((a, b) => (b.score ?? -1) - (a.score ?? -1));
    out = `<h4>Books by this author</h4>${mapList(own, B)}` + out;
  } else if (seeds.length === 1 && seeds[0].authorRef) {
    const same = seeds[0].authorRef.members.filter(p => p !== seeds[0]);
    if (same.length) out += `<h4>By the same author</h4>${mapList(same, B)}`;
  }
  return out;
}

function mapSide(B) {
  const o = MAP.opts, authors = o.mode === 'authors', similar = o.view === 'similar';
  if (!MAP.seeds.length) {
    const anchors = (authors ? B.authors.filter(a => a.hasRead) : B.books.filter(p => p.kind === 'r'))
      .filter(p => p.on).sort((a, b) => b.score - a.score).slice(0, 15);
    const how = similar
      ? `Click a point to see what is closest to it in content: a similar world, kind, themes and tone.
        Shift+click, or <b>+</b> in a list, adds more to the selection, and the list then shows titles close
        to <i>all</i> of them. While something is selected, only it and its matches stay clickable; click empty
        space to clear. Near on the map means similar; distance across the whole map means nothing.`
      : authors
        ? `Click an author to open their author map: every book, grouped by series and world, and which of
          them connect. Switch to <b>Similar authors</b> above the map to find authors close in content.`
        : `Click a series or a book to open its series map: every volume, read or not, how the series connect
          and the reading order. A book outside any series opens its author's map. Switch to
          <b>Similar books</b> above the map to find what is close in content.`;
    return `<p class="mapnote">${how}</p>${anchors.length ? `<h4>Start from what you know</h4>${mapList(anchors, B)}` : ''}`;
  }
  const ctx = MAP.seeds.length === 1 && mapContextOf(MAP.seeds[0]);
  const open = ctx ? `<button type="button" class="worldbtn" data-world-open="${esc(ctx)}">${ctx.startsWith('a:')
      ? 'Open the author map<span>every book, grouped by series and world</span>'
      : `Open the ${mapWorldWord(mapWorld(ctx))} map<span>every volume, read or not, and the reading order</span>`}</button>` : '';
  if (!similar) {
    const sel = MAP.seeds[0], own = MAP.seeds.length === 1 && sel.members
      ? `<h4>Books by this author</h4>${mapList(sel.members.slice().sort((a, b) => (b.score ?? -1) - (a.score ?? -1)), B)}` : '';
    return `<div id="maphead">${mapHead(B)}</div>${open}
      <button type="button" class="tomap" data-mapkind="${o.mode}:similar">Find similar ${authors ? 'authors' : 'books'} instead</button>${own}`;
  }
  return `<div id="maphead">${mapHead(B)}</div>
    ${open}
    <div class="mapopts">
      <label class="range">Min. similarity <b id="minsimval">${Math.round(o.minSim * 100)} %</b>
        <input type="range" min="10" max="90" step="5" value="${Math.round(o.minSim * 100)}" data-mapopt="minSim"></label>
      ${o.mode === 'books' ? `
      <label class="chk"><input type="checkbox" data-mapopt="unread"${o.unread ? ' checked' : ''}> unread only</label>
      <label class="chk"><input type="checkbox" data-mapopt="sameAuthor"${o.sameAuthor ? ' checked' : ''}> include same author</label>` : ''}
    </div>
    <div id="mapres">${mapResultsHtml(B)}</div>`;
}

function mapView() {
  if (!D.sim) return `<div class="empty">The map has no data yet. Build it with <code>python tools/similarity.py</code>:
    <code>batches</code> → an agent following <code>tools/similarity-prompt.md</code> → <code>merge</code> → <code>build</code>.</div>`;
  const o = mapOpts(), B = mapBuild();
  mapFillTags(B);
  // The select only adds: what is active lives in opts.tags and shows as chips.
  const picked = F('maptag') && F('maptag').value;
  if (picked) {
    if (!o.tags.includes(picked)) o.tags.push(picked);
    F('maptag').value = '';
    mapSaveOpts();
  }
  o.tags = o.tags.filter(t => t in B.tagIndex);
  mapMatches(B);
  const pts = mapPoints(B), on = pts.filter(p => p.on).length;
  const what = o.mode === 'authors' ? 'authors' : 'books';
  return `<div class="grouphead">${on} of ${pts.length} ${what} match the filters${
      B.unmapped ? ` · ${mapCount(B.unmapped, 'book')} not profiled yet, missing from the map` : ''} ${LEGEND}
    <span>· ${o.mode === 'authors' ? '◆ an author you have read · ● candidates only' : '◆ read · ● candidate · ■ unread series · a series is one mark'}
    · colour, size and stacking follow the score, real for read books, predicted for the rest
    · a line to a match is thicker the closer it is</span></div>
    ${o.tags.length ? `<div class="tagfilters">Only ${o.mode === 'authors' ? 'authors with books' : 'titles'} tagged:
      ${o.tags.map(t => `<button type="button" class="badge tagbtn on" data-untag="${esc(t)}" title="Remove this tag">${
        esc(B.tagLabel[B.tagIndex[t]])} ×</button>`).join('')}
      <button type="button" class="linkish" data-untag="*">clear all</button></div>` : ''}
    <div class="mapwrap">
      <div class="mapstage" id="mapstage">
        <canvas id="mapc" aria-label="Similarity map of ${what}"></canvas>
        <div class="mapmodes">${mapViewSeg()}</div>
        <div class="maptools">
          <button type="button" data-mz="in" title="Zoom in">+</button>
          <button type="button" data-mz="out" title="Zoom out">−</button>
          <button type="button" data-mz="fit">Fit</button>
        </div>
        <div class="maptip" id="maptip" hidden></div>
        <div class="worldpane" id="worldpane" hidden></div>
      </div>
      <aside class="mapside" id="mapside">${mapSide(B)}</aside>
    </div>`;
}

function mapFit(pts, W, H) {
  const xs = pts.map(p => p.x), ys = pts.map(p => p.y);
  const x0 = Math.min(...xs), x1 = Math.max(...xs), y0 = Math.min(...ys), y1 = Math.max(...ys);
  const s0 = Math.min((W - 2 * MAP_PAD) / (x1 - x0 || 1), (H - 2 * MAP_PAD) / (y1 - y0 || 1));
  return { cx: (x0 + x1) / 2, cy: (y0 + y1) / 2, k: 1, s0, mode: MAP.opts.mode };
}

function mountMap() {
  const c = F('mapc');
  if (!c) return;
  const stage = F('mapstage');
  if (MAP.ro) MAP.ro.disconnect();
  MAP.ro = new ResizeObserver(() => {
    const W = stage.clientWidth, H = stage.clientHeight, dpr = devicePixelRatio || 1;
    c.width = W * dpr; c.height = H * dpr; c.style.width = W + 'px'; c.style.height = H + 'px';
    const fit = mapFit(mapPoints(mapBuild()), W, H);
    if (!MAP.cam || MAP.cam.mode !== MAP.opts.mode) MAP.cam = fit;
    else MAP.cam.s0 = fit.s0;
    if (MAP.pendingFocus) { mapFocus(MAP.pendingFocus, 3, false); MAP.pendingFocus = null; }
    drawMap();
  });
  MAP.ro.observe(stage);
  mapWire(c);
  mapWorldRender();
}

const mapScreen = (p, W, H) => [W / 2 + (p.x - MAP.cam.cx) * MAP.cam.s0 * MAP.cam.k,
                                H / 2 + (p.y - MAP.cam.cy) * MAP.cam.s0 * MAP.cam.k];

// Size and stacking both follow the score - the predicted midpoint for a candidate, the
// real one for a read book, the best of their books for an author - so the strongest
// titles are the biggest marks and are never buried under weaker neighbours.
const mapRadius = p => p.score == null ? 2.5 : 2.5 + Math.max(0, p.score - 50) * 0.11;
const mapByScore = (a, b) => (a.score ?? 0) - (b.score ?? 0);

function mapRedraw() {
  if (MAP.raf) return;
  MAP.raf = requestAnimationFrame(() => { MAP.raf = 0; drawMap(); });
}

function drawMap() {
  const c = F('mapc');
  if (!c || !MAP.cam) return;
  const B = mapBuild(), pts = mapPoints(B), seeds = MAP.seeds;
  const css = getComputedStyle(document.documentElement), v = n => css.getPropertyValue(n).trim();
  const dpr = devicePixelRatio || 1, W = c.width / dpr, H = c.height / dpr;
  const ctx = c.getContext('2d');
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  const surface = v('--surface'), muted = v('--ink-muted'), accent = v('--band-mid');
  ctx.fillStyle = surface;
  ctx.fillRect(0, 0, W, H);
  const k = MAP.cam.k;
  pts.forEach(p => { [p.sx, p.sy] = mapScreen(p, W, H); });

  // Line weight and opacity carry the similarity, scaled across the band above the
  // threshold so that a low threshold still shows its loosest matches as hairlines.
  const res = seeds.length && mapSimilar() ? mapAbove(B).slice(0, MAP_SHOWN) : [];
  if (res.length) {
    const lo = MAP.opts.minSim;
    ctx.save();
    ctx.strokeStyle = accent;
    res.slice().reverse().forEach(r => seeds.forEach((s, i) => {
      const t = Math.max(0, Math.min(1, (r.per[i] - lo) / (1 - lo)));
      ctx.globalAlpha = 0.2 + 0.55 * t;
      ctx.lineWidth = 0.6 + 3.4 * t;
      ctx.beginPath(); ctx.moveTo(s.sx, s.sy); ctx.lineTo(r.p.sx, r.p.sy); ctx.stroke();
    }));
    ctx.restore();
  }

  const diamond = p => p.members ? p.hasRead : p.kind === 'r';
  const mark = (p, fill) => {
    const r = mapRadius(p);
    ctx.beginPath();
    if (diamond(p)) {
      const d = r * 1.25;
      ctx.moveTo(p.sx, p.sy - d); ctx.lineTo(p.sx + d, p.sy); ctx.lineTo(p.sx, p.sy + d); ctx.lineTo(p.sx - d, p.sy);
      ctx.closePath();
    } else if (p.isSeries) ctx.rect(p.sx - r, p.sy - r, 2 * r, 2 * r);
    else ctx.arc(p.sx, p.sy, r, 0, Math.PI * 2);
    ctx.fillStyle = fill; ctx.fill();
    ctx.lineWidth = 2; ctx.strokeStyle = surface; ctx.stroke();
  };
  const inView = p => p.sx > -20 && p.sy > -20 && p.sx < W + 20 && p.sy < H + 20;

  const lit = pts.filter(p => p.on && inView(p)).sort(mapByScore);
  const focus = mapFocusSet(B);
  const colour = p => p.score == null ? muted : v(MAP_BAND_VAR[band(p.score)]);
  if (focus) {
    ctx.globalAlpha = 0.15;
    lit.filter(p => !focus.has(p)).forEach(p => mark(p, colour(p)));
    ctx.globalAlpha = 1;
    [...focus].filter(inView).sort(mapByScore).forEach(p => mark(p, colour(p)));
  } else lit.forEach(p => mark(p, colour(p)));

  if (MAP.hover && !seeds.includes(MAP.hover)) mapRing(ctx, MAP.hover, mapRadius(MAP.hover) + 4, muted);
  res.forEach(r => mapRing(ctx, r.p, mapRadius(r.p) + 3, accent));
  seeds.forEach(s => mapRing(ctx, s, mapRadius(s) + 5, v('--ink')));

  // Region names orient the overview and fade out as you zoom in. Without a selection
  // they outrank book labels; with one they step back so its matches stay legible.
  const taken = [[0, 0, 480, 46], [W - 140, 0, W, 46]];
  const regionAlpha = Math.max(0, Math.min(0.9, 1.9 - k * 0.65)) * (seeds.length ? 0.5 : 1);
  if (regionAlpha > 0.05) {
    ctx.save();
    ctx.globalAlpha = regionAlpha;
    ctx.font = '600 12.5px system-ui, -apple-system, "Segoe UI", sans-serif';
    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';
    ctx.lineJoin = 'round';
    (B.regions[MAP.opts.mode] || []).forEach(r => {
      const [x, y] = mapScreen(r, W, H), w = ctx.measureText(r.label).width;
      ctx.lineWidth = 4; ctx.strokeStyle = surface; ctx.strokeText(r.label, x, y);
      ctx.fillStyle = muted; ctx.fillText(r.label, x, y);
      if (!seeds.length) taken.push([x - w / 2 - 3, y - 9, x + w / 2 + 3, y + 9]);
    });
    ctx.restore();
  }

  const labelled = [...seeds, ...res.slice(0, 15).map(r => r.p)];
  if (!focus) {
    lit.filter(diamond).reverse().forEach(p => labelled.push(p));
    if (k >= 2.2) lit.filter(p => !diamond(p)).reverse().forEach(p => labelled.push(p));
  }
  mapLabels(ctx, [...new Set(labelled)].filter(inView), v('--ink-2'), surface, W, H, taken);
}

function mapRing(ctx, p, r, color) {
  ctx.beginPath();
  ctx.arc(p.sx, p.sy, r, 0, Math.PI * 2);
  ctx.lineWidth = 2; ctx.strokeStyle = color; ctx.stroke();
}

function mapLabels(ctx, list, color, halo, W, H, taken) {
  ctx.font = '500 11.5px system-ui, -apple-system, "Segoe UI", sans-serif';
  ctx.textBaseline = 'middle';
  ctx.textAlign = 'left';
  ctx.lineJoin = 'round';
  const boxes = taken.slice();
  for (const p of list) {
    if (boxes.length - taken.length >= 70) break;
    let t = mapLabel(p);
    if (t.length > 30) t = t.slice(0, 28) + '…';
    const w = ctx.measureText(t).width, x = p.sx + mapRadius(p) + 5, y = p.sy;
    const box = [x - 2, y - 8, x + w + 2, y + 8];
    if (box[2] > W || box[1] < 0 || box[3] > H) continue;
    if (boxes.some(b => box[0] < b[2] && box[2] > b[0] && box[1] < b[3] && box[3] > b[1])) continue;
    boxes.push(box);
    ctx.lineWidth = 3; ctx.strokeStyle = halo; ctx.strokeText(t, x, y);
    ctx.fillStyle = color; ctx.fillText(t, x, y);
  }
}

// Nearest point within 14px rather than an exact hit: small marks are packed tight.
function mapNearest(mx, my) {
  const B = mapBuild(), focus = mapFocusSet(B);
  let best = null, bd = 14 * 14;
  for (const p of focus || mapPoints(B).filter(q => q.on)) {
    if (p.sx == null) continue;
    const d = (p.sx - mx) ** 2 + (p.sy - my) ** 2;
    if (d < bd) { bd = d; best = p; }
  }
  return best;
}

function mapTip(p, mx, my) {
  const tip = F('maptip');
  if (!tip) return;
  if (!p) { tip.hidden = true; return; }
  const line = (tag, text, cls) => { const el = document.createElement(tag); el.textContent = text; if (cls) el.className = cls; return el; };
  tip.replaceChildren(
    line('b', mapLetter(p) + ' · ' + mapScoreText(p)),
    line('div', mapLabel(p)));
  if (!p.members) tip.append(line('div', p.author, 'bk-meta'));
  const ctx = !mapSimilar() && mapContextOf(p);
  if (ctx) tip.append(line('div', `click: ${ctx.startsWith('a:') ? 'author' : mapWorldWord(mapWorld(ctx))} map`, 'bk-meta'));
  if (mapSimilar() && MAP.seeds.length && !MAP.seeds.includes(p)) {
    const s = Math.min(...MAP.seeds.map(q => simDot(q, p)));
    tip.append(line('div', `similarity to the selection ${Math.round(s * 100)} %`, 'bk-meta'));
  }
  tip.hidden = false;
  const stage = F('mapstage');
  tip.style.left = Math.max(6, Math.min(mx + 14, stage.clientWidth - tip.offsetWidth - 6)) + 'px';
  tip.style.top = Math.max(6, my - tip.offsetHeight - 10) + 'px';
}

function mapZoom(f, mx, my) {
  const c = F('mapc'), W = c.clientWidth, H = c.clientHeight, cam = MAP.cam;
  const k2 = Math.max(0.7, Math.min(40, cam.k * f));
  const s1 = cam.s0 * cam.k, s2 = cam.s0 * k2;
  cam.cx += (mx - W / 2) / s1 - (mx - W / 2) / s2;
  cam.cy += (my - H / 2) / s1 - (my - H / 2) / s2;
  cam.k = k2;
  mapRedraw();
}

function mapFocus(p, minK = 2.5, animate = true) {
  if (!MAP.cam) { MAP.pendingFocus = p; return; }
  mapFlyTo({ cx: p.x, cy: p.y, k: Math.max(MAP.cam.k, minK) }, animate);
}

function mapFrame(pts) {
  const c = F('mapc');
  if (!c || !MAP.cam) return;
  const fit = mapFit(pts, c.clientWidth, c.clientHeight);
  mapFlyTo({ cx: fit.cx, cy: fit.cy, k: Math.max(0.7, Math.min(8, fit.s0 / MAP.cam.s0 * 0.85)) });
}

function mapFlyTo(to, animate = true) {
  const cam = MAP.cam, from = { cx: cam.cx, cy: cam.cy, k: cam.k };
  if (!animate) { Object.assign(cam, to); return; }
  const t0 = performance.now();
  const step = now => {
    const t = Math.min(1, (now - t0) / 320), e = 1 - (1 - t) ** 3;
    cam.cx = from.cx + (to.cx - from.cx) * e;
    cam.cy = from.cy + (to.cy - from.cy) * e;
    cam.k = from.k + (to.k - from.k) * e;
    drawMap();
    if (t < 1) requestAnimationFrame(step);
  };
  requestAnimationFrame(step);
}

// In map view a single pick opens its series, world or author map; any other change of
// selection shows the canvas.
function mapSetSeeds(seeds, focus, openWorld = false) {
  MAP.seeds = seeds;
  MAP.openBook = null;
  MAP.world = openWorld && seeds.length === 1 ? mapContextOf(seeds[0]) : null;
  const side = F('mapside');
  if (side) { side.innerHTML = mapSide(mapBuild()); side.scrollTop = 0; }
  if (seeds.length > 1) mapFrame([...seeds, ...(mapSimilar() ? mapAbove(mapBuild()).slice(0, 15).map(r => r.p) : [])]);
  else if (focus) mapFocus(focus);
  else mapRedraw();
  mapWorldRender();
}

const mapToggleSeed = p => MAP.seeds.includes(p)
  ? mapSetSeeds(MAP.seeds.filter(s => s !== p))
  : mapSetSeeds([...MAP.seeds, p]);

function mapRefreshResults() {
  const res = F('mapres');
  if (res) res.innerHTML = mapResultsHtml(mapBuild());
  mapRedraw();
}

function mapWire(c) {
  const ptrs = new Map();
  let drag = null, pinch = null;
  const at = e => { const r = c.getBoundingClientRect(); return [e.clientX - r.left, e.clientY - r.top]; };
  c.addEventListener('pointerdown', e => {
    c.setPointerCapture(e.pointerId);
    ptrs.set(e.pointerId, at(e));
    if (ptrs.size === 2) {
      const [a, b] = [...ptrs.values()];
      pinch = { d: Math.hypot(a[0] - b[0], a[1] - b[1]), k: MAP.cam.k };
      drag = null;
    } else drag = { start: at(e), last: at(e), moved: false };
  });
  c.addEventListener('pointermove', e => {
    const [mx, my] = at(e);
    if (ptrs.has(e.pointerId)) ptrs.set(e.pointerId, [mx, my]);
    if (pinch && ptrs.size === 2) {
      const [a, b] = [...ptrs.values()];
      mapZoom(Math.hypot(a[0] - b[0], a[1] - b[1]) / pinch.d * pinch.k / MAP.cam.k, (a[0] + b[0]) / 2, (a[1] + b[1]) / 2);
      return;
    }
    if (drag) {
      if (!drag.moved && Math.hypot(mx - drag.start[0], my - drag.start[1]) > 4) drag.moved = true;
      if (drag.moved) {
        const s = MAP.cam.s0 * MAP.cam.k;
        MAP.cam.cx -= (mx - drag.last[0]) / s;
        MAP.cam.cy -= (my - drag.last[1]) / s;
        drag.last = [mx, my];
        mapTip(null);
        mapRedraw();
        return;
      }
    }
    const p = mapNearest(mx, my);
    c.style.cursor = p ? 'pointer' : 'grab';
    if (p !== MAP.hover) { MAP.hover = p; mapRedraw(); }
    mapTip(p, mx, my);
  });
  const end = e => {
    ptrs.delete(e.pointerId);
    if (ptrs.size < 2) pinch = null;
    if (drag && !drag.moved && e.type === 'pointerup') {
      const [mx, my] = at(e), p = mapNearest(mx, my);
      if (e.shiftKey || e.ctrlKey || e.metaKey) { if (p) mapToggleSeed(p); }
      else mapSetSeeds(p ? [p] : [], null, !mapSimilar());
    }
    drag = null;
  };
  c.addEventListener('pointerup', end);
  c.addEventListener('pointercancel', end);
  c.addEventListener('pointerleave', () => { MAP.hover = null; mapTip(null); mapRedraw(); });
  c.addEventListener('wheel', e => {
    e.preventDefault();
    const [mx, my] = at(e);
    mapZoom(Math.exp(-e.deltaY * 0.0015), mx, my);
  }, { passive: false });
  c.addEventListener('dblclick', e => { const [mx, my] = at(e); mapZoom(2, mx, my); });
}

// The series map: every volume of a series or shared world, one row each in reading order,
// one lane per series. book-worlds.json holds the researched worlds; any other series is
// drawn from book-series.json, which knows only the shelf, the read rows and a volume count.

const MAP_W = { row: 46, box: 232, lane: 276, top: 44, arc: 20, h: 38 };

function mapWorldIndex() {
  if (MAP.wix && MAP.wix.D === D) return MAP.wix;
  const ofLine = {}, ofKey = {}, ofRead = {};
  Object.entries(D.worlds).forEach(([id, w]) => {
    w.lines.forEach(l => { ofLine[l.id] = id; });
    w.books.forEach(b => { if (b.key) ofKey[b.key] = id; if (b.read) ofRead[b.read] = id; });
  });
  Object.entries(D.seriesDoc).forEach(([sid, s]) => {
    if (ofLine[sid]) return;
    (s.members || []).forEach(m => { ofKey[m.key] ??= 's:' + sid; });
    (s.read || []).forEach(t => { ofRead[t] ??= 's:' + sid; });
  });
  MAP.wix = {
    D, ofLine, ofKey, ofRead, worlds: new Map(), authors: new Map(),
    cand: Object.fromEntries(D.books.map(b => [b.key, b])),
    read: Object.fromEntries(D.read.rows.map(r => [r.title, r])),
    rej: Object.fromEntries(D.rejects.map(r => [r.entity, r])),
  };
  return MAP.wix;
}

const mapWorldWord = w => w.lines.length > 1 || w.universe ? 'world' : 'series';

function mapWorldLink(mapId) {
  const id = mapHas(mapId) && mapWorldOf(mapBuild().byId.get(mapId));
  return id ? `<button type="button" class="tomap" data-toworld="${esc(mapId)}">${
    mapWorldWord(mapWorld(id)) === 'world' ? 'World' : 'Series'} map</button>` : '';
}

function mapWorldIdOf(p) {
  if (!p || p.members || !D.worlds) return null;
  const X = mapWorldIndex();
  if (p.isSeries) {
    const sid = p.id.replace(/^r?s:/, '');
    return X.ofLine[sid] || (D.seriesDoc[sid] ? 's:' + sid : null);
  }
  return (p.kind === 'c' ? X.ofKey[p.key] : X.ofRead[p.row.title]) || null;
}

// A world of one known book has nothing to map, so it does not open.
function mapWorldOf(p) {
  const id = mapWorldIdOf(p);
  return id && mapWorld(id).nodes.length > 1 ? id : null;
}

// What a click opens in map view: an author's map for an author, a book's series or world,
// and for a book outside any series its author's map.
function mapContextOf(p) {
  if (!p) return null;
  const own = !p.members && mapWorldOf(p), au = p.members ? p : p.authorRef;
  if (own) return own;
  return au && mapAuthorMap(au.name).size > 1 ? 'a:' + au.name : null;
}

// An author's map is one block per world, so blocks never connect to each other; books in
// no series share one block of standalones.
function mapAuthorMap(name) {
  const X = mapWorldIndex();
  if (X.authors.has(name)) return X.authors.get(name);
  const au = mapBuild().authors.find(a => a.name === name);
  const ids = new Set(), solo = [];
  (au ? au.members : []).forEach(m => { const id = mapWorldIdOf(m); if (id) ids.add(id); else solo.push(m); });
  Object.entries(D.worlds).forEach(([id, w]) => { if (w.author === name) ids.add(id); });
  const blocks = [...ids].map(mapWorld);
  if (solo.length) {
    solo.sort((a, b) => (b.kind === 'r') - (a.kind === 'r') || (b.score ?? -1) - (a.score ?? -1));
    const raw = {
      name: 'Standalone books', lines: [{ id: 'solo', name: 'Standalone books', standalone: true }], links: [], arcs: [],
      books: solo.map(m => m.kind === 'c' ? { id: 'k:' + m.key, line: 'solo', n: null, key: m.key }
                                          : { id: 'r:' + m.row.title, line: 'solo', n: null, read: m.row.title }),
    };
    blocks.push({ ...raw, id: 'solo', solo: true, nodes: raw.books.map(b => mapWorldNode(b, raw, X)) });
  }
  const read = w => w.nodes.filter(n => n.state === 'read').length;
  blocks.sort((a, b) => !!a.solo - !!b.solo || read(b) - read(a) || b.nodes.length - a.nodes.length);
  const m = { name, au, blocks, size: blocks.reduce((t, w) => t + w.nodes.reduce((s, n) => s + (n.count || 1), 0), 0) };
  X.authors.set(name, m);
  return m;
}

// Read rows carry a volume number only when it follows the series' own name:
// "Hraničářův učeň #1-4" is volumes 1-4, "Guards! Guards! (Discworld #8)" in the City
// Watch sub-series is not volume 8 of it. Once any entry has no number, which numbers are
// missing is unknown, so the shortfall becomes one untitled entry at the end.
function mapWorldFromSeries(sid) {
  const s = D.seriesDoc[sid], uni = s.kind === 'universe', books = [];
  const own = [s.name, s.nameEn].filter(Boolean).map(t => t.toLowerCase());
  (s.members || []).forEach(m => books.push({ id: 'k:' + m.key, line: sid, n: uni ? null : m.n, key: m.key }));
  (s.read || []).forEach(t => {
    const m = /^(.*?)\s*#(\d+)(?:\s*[-–]\s*(\d+))?/.exec(t);
    if (uni || !m || !own.includes(m[1].toLowerCase())) return books.push({ id: 'r:' + t, line: sid, n: null, read: t });
    for (let n = +m[2]; n <= +(m[3] || m[2]); n++) books.push({ id: `r${n}:${t}`, line: sid, n, read: t });
  });
  (s.rejected || []).forEach(t => books.push({ id: 'x:' + t, line: sid, n: null, rejectedText: t }));
  if (!uni && books.some(b => b.n == null)) {
    const more = (s.volumes || 0) - books.length;
    if (more > 0) books.push({ id: 'g', line: sid, n: null, count: more, gap: true });
  } else if (!uni) {
    const have = new Set(books.map(b => b.n));
    const last = Math.max(s.volumes || 0, ...have);
    for (let n = 1; n <= last; n++) {
      if (have.has(n)) continue;
      let to = n;
      while (to < last && !have.has(to + 1)) to++;
      books.push({ id: `g:${n}`, line: sid, n, n2: to, count: to - n + 1, gap: true });
      n = to;
    }
  }
  return { name: s.name, nameEn: s.nameEn && s.nameEn !== s.name ? s.nameEn : '', note: s.note, synthetic: true,
           universe: uni, volumes: s.volumes, lines: [{ id: sid, name: s.name, nameEn: s.nameEn, standalone: uni }],
           books, links: [], arcs: [] };
}

function mapWorld(id) {
  const X = mapWorldIndex();
  if (X.worlds.has(id)) return X.worlds.get(id);
  const raw = id.startsWith('s:') ? mapWorldFromSeries(id.slice(2)) : D.worlds[id];
  const w = { ...raw, id, nodes: raw.books.map(b => mapWorldNode(b, raw, X)) };
  w.author ||= (w.nodes.find(n => n.author) || {}).author || '';
  X.worlds.set(id, w);
  return w;
}

function mapWorldNode(b, w, X) {
  const cand = b.key && X.cand[b.key], row = b.read && X.read[b.read];
  const rt = b.rejected || b.rejectedText;
  const rej = rt ? X.rej[rt] || X.rej[rt.replace(/\s*\(.*\)$/, '')] : null;
  const n = { ...b, title: b.cz || b.en || '', alt: b.cz && b.en && b.cz !== b.en ? b.en : '', href: b.recordUrl || '' };
  if (row) {
    Object.assign(n, { state: 'read', score: row.score, author: row.author, ref: 'r:' + row.key,
                       word: row.score == null ? 'read, not finished' : 'read' });
    n.title ||= row.title;
  } else if (cand) {
    Object.assign(n, { state: 'shelf', score: cand.est ? cand.mid : null, est: cand.est, author: cand.cache.author, ref: 'c:' + cand.key,
                       word: cand.blocked ? `on the shelf, blocked · ${nice(cand.blocked)}` : 'on the shelf' });
    n.title ||= cand.cache.czTitle || cand.cache.title;
    n.alt ||= cand.cache.czTitle && cand.cache.title !== cand.cache.czTitle ? cand.cache.title : '';
    if (cand.hasCz && cand.cz.recordUrl) n.href = cand.cz.recordUrl;
  } else if (rt) {
    Object.assign(n, { state: 'rejected', word: 'rejected' + (rej ? ` · ${nice(rej.filter)}` : '') });
    n.title ||= rt;
  } else if (b.gap) {
    const k = b.count;
    Object.assign(n, { state: 'gap', word: 'title not recorded', title: b.n == null
      ? `${k} more volume${k === 1 ? '' : 's'} not on the shelf`
      : `${k === 1 ? 'Volume' : 'Volumes'} ${b.n}${k > 1 ? '–' + b.n2 : ''} not on the shelf` });
  } else if (b.lib) Object.assign(n, { state: 'library', word: 'in the library' });
  else Object.assign(n, { state: 'absent', word: !b.cz ? 'no Czech edition' : w.libChecked ? 'not in the library' : 'not on the shelf' });
  return n;
}

// Rows follow the chosen order. Publication order is by year written, so a volume the Czech
// edition renumbered into story order (Výkupné za Eraka, written seventh, numbered fifth)
// shows out of its numbering there. A book with no year keeps its place after the volume
// before it, which is all an untitled gap or a shelf-only series has.
function mapWorldLayout(w, story, top = MAP_W.top) {
  const lanes = w.lines.filter(l => w.nodes.some(n => n.line === l.id));
  const laneOf = Object.fromEntries(lanes.map((l, i) => [l.id, i]));
  const perLane = lanes.map(l => w.nodes.filter(n => n.line === l.id).sort((a, b) => (a.n ?? 1e9) - (b.n ?? 1e9)));
  let seq;
  if (story) {
    const pos = Object.fromEntries(w.story.map((id, i) => [id, i]));
    seq = w.nodes.slice().sort((a, b) => (pos[a.id] ?? 1e9) - (pos[b.id] ?? 1e9));
  } else {
    const key = new Map();
    perLane.forEach((list, li) => {
      let y = -Infinity;
      list.forEach((n, i) => { y = n.year ?? y; key.set(n, [y, li, i]); });
    });
    seq = w.nodes.slice().sort((a, b) => {
      const [ya, la, ia] = key.get(a), [yb, lb, ib] = key.get(b);
      return ya - yb || la - lb || ia - ib;
    });
  }
  const arcStart = new Map((w.arcs || []).map(a => [perLane[laneOf[a.line]]?.find(n => n.n === a.from), a]));
  const at = {}, captions = [];
  let y = top;
  seq.forEach(n => {
    const a = arcStart.get(n);
    if (a) { y += MAP_W.arc; captions.push({ a, x: laneOf[n.line] * MAP_W.lane + 4, y: y - MAP_W.arc + 2 }); }
    at[n.id] = { x: laneOf[n.line] * MAP_W.lane, y, lane: laneOf[n.line] };
    y += MAP_W.row;
  });
  return { lanes, laneOf, perLane, at, captions, W: lanes.length * MAP_W.lane + 24, H: y };
}

function mapWorldSvg(w, L) {
  const { box, h } = MAP_W, mid = p => p.y + h / 2, mx = p => p.x + 13;
  const ttl = t => t ? `<title>${esc(t)}</title>` : '';
  const out = [];
  L.perLane.forEach((list, li) => !L.lanes[li].standalone && list.slice(1).forEach((n, i) => {
    const a = L.at[list[i].id], b = L.at[n.id];
    out.push(`<path class="wsq" d="M${mx(a)},${mid(a)} L${mx(b)},${mid(b)}"/>`);
  }));
  (w.arcs || []).forEach(a => {
    const ys = (L.perLane[L.laneOf[a.line]] || []).filter(n => n.n >= a.from && n.n <= a.to).map(n => L.at[n.id]);
    if (!ys.length) return;
    const x = ys[0].x + box + 6, y0 = Math.min(...ys.map(p => p.y)), y1 = Math.max(...ys.map(p => p.y)) + h;
    out.push(`<path class="warc" d="M${x - 4},${y0} H${x} V${y1} H${x - 4}">${ttl(a.name + (a.note ? ' — ' + a.note : ''))}</path>`);
  });
  (w.links || []).forEach(k => {
    const a = L.at[k.from];
    if (!a) return;
    if (k.kind === 'crossover') {
      const lane = L.laneOf[k.to];
      if (lane == null) return;
      const tx = lane * MAP_W.lane + 13, sx = lane < a.lane ? a.x : a.x + box;
      out.push(`<path class="wx" d="M${sx},${mid(a)} H${tx}">${ttl(k.note)}</path><circle class="wxdot" cx="${tx}" cy="${mid(a)}" r="3.5"/>`);
      return;
    }
    const b = L.at[k.to];
    if (!b) return;
    // Leave and enter through the facing box edges, so the curve runs in the gutter between lanes.
    let sx, ex, c1, c2;
    if (b.lane > a.lane) { sx = a.x + box; ex = b.x + 3; c1 = sx + 34; c2 = ex - 34; }
    else if (b.lane < a.lane) { sx = a.x; ex = b.x + box; c1 = sx - 34; c2 = ex + 34; }
    else { sx = a.x + box; ex = b.x + box; c1 = sx + 46; c2 = ex + 46; }
    out.push(`<path class="${k.kind === 'prequel' ? 'wpre' : 'wthen'}" marker-end="url(#wah)"
      d="M${sx},${mid(a)} C${c1},${mid(a)} ${c2},${mid(b)} ${ex},${mid(b)}">${ttl(k.note)}</path>`);
  });
  return `<svg width="${L.W}" height="${L.H}" aria-hidden="true">${out.join('')}</svg>`;
}

// One arrowhead for every graph in the pane: an author map holds several, and ids must be unique.
const MAP_W_DEFS = `<svg width="0" height="0" style="position:absolute" aria-hidden="true"><defs><marker id="wah"
  viewBox="0 0 8 8" refX="7" refY="4" markerWidth="7" markerHeight="7" orient="auto"><path class="wah" d="M0,0 L8,4 L0,8 z"/></marker></defs></svg>`;

function mapWorldNodeHtml(n, at, B) {
  const p = n.ref && B.byId.get(n.ref);
  const value = n.state === 'read' ? (n.score == null ? '—' : ten(n.score))
    : n.state === 'shelf' && n.est ? rng(n.est[0], n.est[1]) : '';
  const tone = n.score == null ? 'bN' : mapTone(n);
  const sub = [n.word, n.alt, n.year].filter(Boolean).join(' · ');
  const tip = [n.title, n.alt, n.year, n.word, n.note].filter(Boolean).join('\n');
  const link = n.href && n.state !== 'read'
    ? `<a href="${esc(n.href)}" target="_blank" rel="noreferrer" title="Open the catalogue record">Borrow ↗</a>` : '';
  return `<div class="wnode ${n.state} ${tone}${p && MAP.seeds.includes(p) ? ' sel' : ''}" title="${esc(tip)}"
      style="left:${at.x}px;top:${at.y}px;width:${MAP_W.box}px;height:${MAP_W.h}px"${
      p ? ` data-wpick="${p.ref}" tabindex="0" role="button"` : ''}>
    <span class="wm ${n.state}"></span>
    <span style="min-width:0"><span class="wt">${n.n != null && !n.gap ? `<i>${esc(n.n)}</i>` : ''}${esc(n.title)}</span>
      <span class="ws">${esc(sub)}</span></span>
    ${value ? `<span class="wv">${esc(value)}</span>` : link}</div>`;
}

const MAP_W_LEGEND = `<div class="wplegend">
  <span><span class="wm read"></span>read, your score</span>
  <span><span class="wm"></span>on the shelf, predicted</span>
  <span><span class="wm library"></span>in the library, not screened yet</span>
  <span><span class="wm absent"></span>not in the library, or no Czech edition</span>
  <span><span class="wm gap"></span>volume not on the shelf, title unknown</span>
  <span><svg width="22" height="8"><path class="wsq" d="M0,4 H22"/></svg>next volume</span>
  <span><svg width="22" height="8"><path class="wthen" d="M0,4 H18"/><path class="wah" d="M16,1 L22,4 L16,7 z"/></svg>continues in</span>
  <span><svg width="22" height="8"><path class="wpre" d="M0,4 H18"/><path class="wah" d="M16,1 L22,4 L16,7 z"/></svg>prequel, written later</span>
  <span><svg width="22" height="8"><path class="wx" d="M0,4 H22"/></svg>crossover</span></div>`;

const mapStoryOrder = w => !!(w.story && w.story.length) && MAP.opts.worldOrder !== 'pub';
const mapNodeSize = n => n.count || 1;

function mapTally(nodes) {
  const LABEL = { read: 'read', shelf: 'on the shelf', library: 'in the library, not screened yet', rejected: 'rejected',
                  gap: 'not on the shelf' };
  const tally = new Map(Object.values(LABEL).map(k => [k, 0]));
  nodes.forEach(n => { const k = LABEL[n.state] || n.word; tally.set(k, (tally.get(k) || 0) + mapNodeSize(n)); });
  const total = nodes.reduce((t, n) => t + mapNodeSize(n), 0);
  return `${mapCount(total, 'book')}: ${[...tally].filter(([, k]) => k).map(([label, k]) => `${k} ${label}`).join(', ')}`;
}

// A one-lane block in an author map already names its series in the block head.
function mapWorldGraph(w, B, laneHeads = true) {
  const L = mapWorldLayout(w, mapStoryOrder(w), laneHeads ? MAP_W.top : 4);
  return `<div class="wpgraph" style="width:${L.W}px;height:${L.H}px">${mapWorldSvg(w, L)}
    ${laneHeads ? L.lanes.map((l, i) => `<div class="wlane" style="left:${i * MAP_W.lane}px;top:6px;width:${MAP_W.box}px" title="${esc(l.note || '')}">
      <b>${esc(l.name)}</b><span>${esc([l.nameEn && l.nameEn !== l.name ? l.nameEn : '',
        mapCount(L.perLane[i].reduce((t, n) => t + mapNodeSize(n), 0), 'book')].filter(Boolean).join(' · '))}</span></div>`).join('') : ''}
    ${L.captions.map(c => `<div class="warcname" style="left:${c.x}px;top:${c.y}px" title="${esc(c.a.note || '')}">${esc(c.a.name)}${
      c.a.nameEn && c.a.nameEn !== c.a.name ? ` · ${esc(c.a.nameEn)}` : ''}</div>`).join('')}
    ${w.nodes.map(n => mapWorldNodeHtml(n, L.at[n.id], B)).join('')}
  </div>`;
}

// One control for both choices, shown on the canvas and in every open map's header: an open
// map covers the canvas, so a control left only there could not be reached.
const MAP_KINDS = [
  ['books', 'map', 'Series maps', 'A click opens the series or world: every volume and the reading order'],
  ['authors', 'map', 'Author maps', "A click opens the author's books, grouped by series and world"],
  ['books', 'similar', 'Similar books', 'A click lists the books closest in content'],
  ['authors', 'similar', 'Similar authors', 'A click lists the authors closest in content'],
];

function mapViewSeg() {
  const o = MAP.opts;
  return `<div class="wseg" role="group" aria-label="What the map shows">${MAP_KINDS.map(([mode, view, label, tip]) =>
    `<button type="button" data-mapkind="${mode}:${view}" aria-pressed="${o.mode === mode && o.view === view}"
      title="${esc(tip)}">${label}</button>`).join('')}</div>`;
}

// The selection follows the switch where it can: a book becomes its author on the authors
// side; an author has no single book to become, so the books side starts unselected.
function mapSwitch(mode, view) {
  const sel = MAP.seeds.length === 1 ? MAP.seeds[0] : null;
  const p = !sel ? null : mode === 'authors' ? (sel.members ? sel : sel.authorRef || null) : sel.members ? null : sel;
  MAP.opts.view = view;
  if (mode !== MAP.opts.mode) mapOpen(p, mode);
  else MAP.seeds = p ? [p] : [];
  MAP.openBook = null;
  MAP.world = view === 'map' && p ? mapContextOf(p) : null;
  mapSaveOpts();
  render();
}

function mapPaneControls(withOrder) {
  const story = MAP.opts.worldOrder !== 'pub';
  return `<div class="wpctl">${withOrder ? `<div class="wseg" role="group" aria-label="Row order">
      <button type="button" data-worder="story" aria-pressed="${story}" title="Rows in the order the story happens">Story order</button>
      <button type="button" data-worder="pub" aria-pressed="${!story}" title="Each series in its own numbering, the series interleaved by year written">Publication</button></div>` : ''}
    ${mapViewSeg()}
    <button type="button" class="unpick" data-world-close title="Close (Esc)">×</button></div>`;
}

function mapAuthorButton(name, B) {
  return B.authors.some(a => a.name === name)
    ? `<button type="button" class="linkish" data-author-map="${esc(name)}" title="All of this author's books, by series and world">${esc(name)}</button>`
    : esc(name);
}

function mapAuthorHtml(m, B) {
  const worlds = m.blocks.filter(w => !w.solo), solo = m.blocks.find(w => w.solo);
  const lines = worlds.reduce((t, w) => t + w.lines.length, 0);
  const shape = [worlds.length ? `${lines} series in ${mapCount(worlds.length, 'world')}` : '',
                 solo ? `${solo.nodes.length} standalone` : ''].filter(Boolean).join(' · ');
  const head = w => w.solo ? `<b>Standalone books</b><div class="bk-meta">not part of any series · ${esc(mapTally(w.nodes))}</div>`
    : `<button type="button" class="linkish wbname" data-world-open="${esc(w.id)}" title="Open this ${mapWorldWord(w)} map with its connections and sources">${esc(w.name)}</button>${
        w.nameEn ? ` <span class="bk-alt">${esc(w.nameEn)}</span>` : ''}
      <div class="bk-meta">${w.lines.length > 1 ? `${w.lines.length} series, connected` : w.universe || w.lines[0].standalone ? 'standalone novels in one world' : 'one series'}
        · ${esc(mapTally(w.nodes))}</div>`;
  return `<div class="wphead">
      <div><div class="bk-title">${esc(m.name)}</div>
        <div class="bk-meta">${esc(mapTally(m.blocks.flatMap(w => w.nodes)))}${shape ? ' · ' + esc(shape) : ''}</div></div>
      ${mapPaneControls(worlds.some(w => w.story && w.story.length))}
    </div>
    <div class="wpbody">${MAP_W_DEFS}
      <p class="mapnote" style="margin:10px 0 0">${worlds.length > 1 || (worlds.length && solo)
        ? 'Each box is one series or shared world: the series inside a box connect, the boxes do not connect to each other.'
        : worlds.length ? 'Everything here belongs to one world.' : 'None of these books belongs to a series.'}</p>
      <div class="wblocks">${m.blocks.map(w => `<section class="wblock"><div class="wbhead">${head(w)}</div>
        ${mapWorldGraph(w, B, w.lines.length > 1)}</section>`).join('')}</div>
      ${MAP_W_LEGEND}
      <p class="mapnote" style="margin-top:10px">Series without a researched bibliography show only what the shelf knows;
        books by this author that are on no list here are not recorded.</p>
    </div>`;
}

function mapWorldHtml(w, B) {
  const total = w.nodes.reduce((t, n) => t + mapNodeSize(n), 0);
  const known = w.universe && w.volumes > total ? ` · ${w.volumes} books in the whole world, only these are recorded` : '';
  const byId = Object.fromEntries(w.nodes.map(n => [n.id, n]));
  const lineName = id => (w.lines.find(l => l.id === id) || {}).name || id;
  const end = id => byId[id] ? `<b>${esc(byId[id].title)}</b>` : `<b>${esc(lineName(id))}</b>`;
  const KIND = { then: 'continues in', prequel: 'prequel to', crossover: 'crossover with' };
  const notes = [
    ...(w.links || []).map(k => `<li><span class="wk">${KIND[k.kind] || k.kind}</span>${end(k.from)} → ${end(k.to)}${
      k.note ? ' — ' + esc(k.note) : ''}</li>`),
    ...w.lines.filter(l => l.note).map(l => `<li><b>${esc(l.name)}</b> — ${esc(l.note)}</li>`),
    ...(w.arcs || []).filter(a => a.note).map(a => `<li><b>${esc(a.name)}</b> — ${esc(a.note)}</li>`),
    ...(w.synthetic && w.note ? [`<li>${esc(w.note)}</li>`] : []),
  ];
  const src = (w.sources || []).map((u, i) => `<a href="${esc(u)}" target="_blank" rel="noopener">${i + 1}</a>`).join(' ');
  return `<div class="wphead">
      <div><div class="bk-title">${esc(w.name)}${w.nameEn ? ` <span class="bk-alt">(${esc(w.nameEn)})</span>` : ''}</div>
        <div class="bk-meta">${w.author ? mapAuthorButton(w.author, B) + ' · ' : ''}${esc([w.lines.length > 1 ? `${w.lines.length} series` : '',
          mapTally(w.nodes)].filter(Boolean).join(' · '))}${esc(known)}</div></div>
      ${mapPaneControls(!!(w.story && w.story.length))}
    </div>
    <div class="wpbody">${MAP_W_DEFS}
      ${mapWorldGraph(w, B)}
      ${MAP_W_LEGEND}
      ${notes.length ? `<h4>How it connects</h4><ul class="wplinks">${notes.join('')}</ul>` : ''}
      <p class="mapnote" style="margin-top:10px">${w.synthetic
        ? 'Drawn from the shelf alone: titles of volumes that are not on the shelf, and links to other series, are not recorded yet.'
        : `Researched ${esc(w.checked || '')}${w.libChecked ? `, library holdings checked ${esc(w.libChecked)}` : ''}${src ? ` · sources ${src}` : ''}`}</p>
    </div>`;
}

function mapWorldRender(fresh = false) {
  const pane = F('worldpane');
  if (!pane) return;
  const id = MAP.world, author = id && id.startsWith('a:');
  const w = id && (author ? mapAuthorMap(id.slice(2)) : mapWorld(id));
  pane.hidden = !w;
  if (!w) { pane.innerHTML = ''; delete pane.dataset.world; return; }
  const body = pane.querySelector('.wpbody');
  const keep = !fresh && body && pane.dataset.world === MAP.world ? [body.scrollLeft, body.scrollTop] : null;
  pane.innerHTML = author ? mapAuthorHtml(w, mapBuild()) : mapWorldHtml(w, mapBuild());
  pane.dataset.world = MAP.world;
  const nb = pane.querySelector('.wpbody'), sel = pane.querySelector('.wnode.sel');
  if (keep) [nb.scrollLeft, nb.scrollTop] = keep;
  else if (sel) nb.scrollTop = Math.max(0, sel.offsetTop - nb.clientHeight / 3);
}

function mapOpen(p, mode) {
  mapOpts().mode = mode;
  mapSaveOpts();
  MAP.seeds = p ? [p] : [];
  MAP.openBook = null;
  MAP.world = null;
  MAP.pendingFocus = p;
  MAP.memo = null;
  if (MAP.cam) MAP.cam.mode = null;
}

document.addEventListener('click', e => {
  const to = e.target.closest('[data-tomap], [data-toworld]');
  if (to) {
    const p = mapBuild().byId.get(to.dataset.tomap || to.dataset.toworld);
    if (!p) return;
    mapOpen(p, 'books');
    MAP.opts.view = to.dataset.tomap ? 'similar' : 'map';
    mapSaveOpts();
    MAP.world = to.dataset.toworld ? mapContextOf(p) : null;
    setView('map');
    scrollTo(0, 0);
    return;
  }
  if (!F('mapstage')) return;
  const B = mapBuild();
  if (e.target.closest('#worldpane a')) return;
  // A book picked inside an author map, or an author named in a series map, belongs to the
  // other kind of map, so the map switches kind with it.
  const pickIn = (p, open) => {
    const mode = p.members ? 'authors' : 'books';
    if (mode === MAP.opts.mode) { mapSetSeeds([p], null, open); return; }
    mapOpen(p, mode);
    MAP.world = open ? mapContextOf(p) : null;
    render();
  };
  const wpick = e.target.closest('[data-wpick]');
  if (wpick) { pickIn(mapByRef(B, wpick.dataset.wpick), true); return; }
  const amap = e.target.closest('[data-author-map]');
  if (amap) {
    const au = B.authors.find(a => a.name === amap.dataset.authorMap);
    if (!au) return;
    MAP.opts.view = 'map';
    mapSaveOpts();
    pickIn(au, true);
    return;
  }
  const kind = e.target.closest('[data-mapkind]');
  if (kind) { mapSwitch(...kind.dataset.mapkind.split(':')); return; }
  const wopen = e.target.closest('[data-world-open]');
  if (wopen) { MAP.world = wopen.dataset.worldOpen; mapWorldRender(true); return; }
  if (e.target.closest('[data-world-close]')) { MAP.world = null; mapWorldRender(); return; }
  const worder = e.target.closest('[data-worder]');
  if (worder) { MAP.opts.worldOrder = worder.dataset.worder; mapSaveOpts(); mapWorldRender(true); return; }
  const tagf = e.target.closest('[data-tagfilter]');
  if (tagf) {
    if (!MAP.opts.tags.includes(tagf.dataset.tagfilter)) MAP.opts.tags.push(tagf.dataset.tagfilter);
    mapSaveOpts();
    render();
    return;
  }
  const untag = e.target.closest('[data-untag]');
  if (untag) {
    MAP.opts.tags = untag.dataset.untag === '*' ? [] : MAP.opts.tags.filter(t => t !== untag.dataset.untag);
    mapSaveOpts();
    render();
    return;
  }
  const add = e.target.closest('[data-add]');
  if (add) { mapToggleSeed(mapByRef(B, add.dataset.add)); return; }
  const unseed = e.target.closest('[data-unseed]');
  if (unseed) { mapToggleSeed(mapByRef(B, unseed.dataset.unseed)); return; }
  const foc = e.target.closest('[data-focus]');
  if (foc) { mapFocus(mapByRef(B, foc.dataset.focus)); return; }
  const detail = e.target.closest('[data-detail]');
  if (detail) {
    MAP.openBook = MAP.openBook === detail.dataset.detail ? null : detail.dataset.detail;
    mapRefreshResults();
    return;
  }
  const pick = e.target.closest('[data-pick]');
  if (pick) {
    const p = mapByRef(B, pick.dataset.pick), mode = pick.dataset.pick[0] === 'a' ? 'authors' : 'books';
    if (mode === MAP.opts.mode) { mapSetSeeds([p], p, !mapSimilar()); return; }
    mapOpen(p, mode);
    if (!mapSimilar()) MAP.world = mapContextOf(p);
    render();
    return;
  }
  if (e.target.closest('[data-unpick]')) { mapSetSeeds([]); return; }
  const z = e.target.closest('[data-mz]');
  if (z && MAP.cam) {
    const c = F('mapc');
    if (z.dataset.mz === 'fit') { MAP.cam = mapFit(mapPoints(B), c.clientWidth, c.clientHeight); mapRedraw(); }
    else mapZoom(z.dataset.mz === 'in' ? 1.6 : 1 / 1.6, c.clientWidth / 2, c.clientHeight / 2);
  }
});

// The slider re-renders only the result list: replacing the panel would destroy the
// slider under the pointer mid-drag.
document.addEventListener('input', e => {
  const opt = e.target.closest('[data-mapopt]');
  if (!opt) return;
  const o = mapOpts(), name = opt.dataset.mapopt;
  if (name === 'minSim') {
    o.minSim = +opt.value / 100;
    F('minsimval').textContent = opt.value + ' %';
  } else o[name] = opt.checked;
  mapSaveOpts();
  mapRefreshResults();
});

document.addEventListener('keydown', e => {
  if (e.key === 'Escape' && MAP.world && F('worldpane')) { MAP.world = null; mapWorldRender(); return; }
  const node = (e.key === 'Enter' || e.key === ' ') && e.target.closest && e.target.closest('[data-wpick]');
  if (node) { e.preventDefault(); node.click(); }
});

new MutationObserver(mapRedraw).observe(document.documentElement, { attributes: true, attributeFilter: ['data-theme'] });
matchMedia('(prefers-color-scheme: dark)').addEventListener('change', mapRedraw);
