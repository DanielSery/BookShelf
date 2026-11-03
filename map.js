// Similar books and authors, and the author map. Loaded before the main script and run against
// its globals (D, F, esc, plural, tone, ten, rng, grid, EMPTY, state, candidateCard, seriesCard,
// readCard, readSeriesCard, markClips, render, setView, setCount, store, recall, candidateFilter,
// readFilter), all of which exist by the time anything here is called. Names are map-prefixed
// because every top-level declaration shares one scope with index.html.

// seeds: what the similar list is close to, in the current mode; bookSeeds keeps the books
// so that switching Authors -> Books returns to them. from: the tab and scroll to go back to.
const MAP = {
  opts: null, seeds: [], bookSeeds: [], from: null, built: null, memo: null, gen: 0,
  wix: null, world: null, hl: null,
};

const MAP_SHOWN = 40;

function mapOpts() {
  if (!MAP.opts) {
    let saved = {};
    try { saved = JSON.parse(recall('bookshelf.similar')) || {}; } catch {}
    MAP.opts = { minSim: 0.4, unread: true, sameAuthor: false, mode: 'books', ...saved };
  }
  return MAP.opts;
}
const mapSaveOpts = () => store('bookshelf.similar', JSON.stringify(MAP.opts));

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
      id: s.id, kind, key, row, sv: s.v, d: dense(s.v), i: books.length, ref: 'b' + books.length,
      title: kind === 'c' ? row.cache.czTitle || row.cache.title : row.title,
      alt: kind === 'c' && row.cache.czTitle && row.cache.title !== row.cache.czTitle ? row.cache.title : '',
      author: kind === 'c' ? row.cache.author || '' : row.author,
      score: kind === 'c' ? (row.est ? row.mid : null) : row.score,
    };
    bySimIdx[i] = p;
    books.push(p);
  });
  const profiled = books.length;
  // A series is one entry (reader, 2026-10-25: he reads a series whole) with its volumes'
  // summed profile, so it is matched as the one thing he would pick up. Read volumes of a
  // series group apart from its unread ones, scored by what he gave them.
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
    const au = { name: a.name, members, i: authors.length, ref: 'a' + authors.length, d: d.map(x => x / norm) };
    au.sv = [...au.d].map((x, f) => [f, x]).filter(([, x]) => x > 0);
    members.forEach(m => { m.authorRef = au; });
    authors.push(au);
  });
  const tagIndex = Object.fromEntries(sim.tags.map(([id], i) => [id, i]));
  MAP.built = { D, NT, books, authors, tagIndex, ids: new Set(aliases.keys()), byId: aliases,
                tagIds: sim.tags.map(t => t[0]), tagLabel: sim.tags.map(t => t[1]), tagGroup: sim.tags.map(t => t[3]),
                unmapped: D.books.length + D.read.rows.length - profiled };
  const again = list => list.map(s => s.members ? authors.find(a => a.name === s.name) : books.find(b => b.id === s.id)).filter(Boolean);
  MAP.seeds = again(MAP.seeds);
  MAP.bookSeeds = again(MAP.bookSeeds);
  MAP.memo = null;
  return MAP.built;
}

const mapHas = id => !!(D && D.sim && mapBuild().ids.has(id));
const mapByRef = (B, ref) => ref[0] === 'a' ? B.authors[+ref.slice(1)] : B.books[+ref.slice(1)];

function mapMatches(B) {
  const cf = candidateFilter(), rf = readFilter();
  B.books.forEach(p => { p.on = p.kind === 'c' ? cf(p.row) : rf(p.row); });
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

function sharedTags(seeds, p, B, n = 3) {
  return p.sv.filter(([f]) => f < B.NT)
    .map(([f, x]) => [x * Math.min(...seeds.map(s => s.d[f])), f]).filter(([c]) => c > 0)
    .sort((a, b) => b[0] - a[0]).slice(0, n).map(([, f]) => B.tagLabel[f]);
}

const mapTone = p => p.score == null ? 'bN' : tone(p.score);
const mapLabel = p => p.members ? p.name : p.title;

// The same card the Candidates and Read tabs draw, so a book looks the same wherever it is opened.
const mapCard = p => p.kind === 'c' ? (p.isSeries ? seriesCard : candidateCard)(p.row)
  : (p.isSeries ? readSeriesCard : readCard)(p.row);

const MAP_GROUPS = [['Kind', 'Kind'], ['Setting', 'Setting'], ['Theme', 'Theme'], ['Tone', 'Tone'],
                    ['Audience', 'Audience'], ['Lead', 'Lead character'], ['Telling', 'Telling']];

const mapBestFirst = (a, b) => (b.score ?? -1) - (a.score ?? -1);

// The profile tags behind Similar, offered as one more filter on the lists.
function mapFillTags() {
  const sel = F('maptag');
  if (!sel || !D.sim) return;
  const B = mapBuild(), n = new Array(B.NT).fill(0);
  B.books.forEach(p => p.sv.forEach(([f]) => { if (f < B.NT) n[f]++; }));
  sel.innerHTML = '<option value="">Any tag</option>' + MAP_GROUPS.map(([g, label]) =>
    `<optgroup label="${esc(label)}">${B.tagIds.map((t, f) => [t, f]).filter(([, f]) => B.tagGroup[f] === g && n[f])
      .sort((a, b) => B.tagLabel[a[1]].localeCompare(B.tagLabel[b[1]]))
      .map(([t, f]) => `<option value="${esc(t)}">${esc(B.tagLabel[f])} (${n[f]})</option>`).join('')}</optgroup>`).join('');
}

// A book with no profile has no tags, so any tag excludes it.
function mapTagged(mapId, tag) {
  if (!D.sim) return false;
  const B = mapBuild(), p = B.byId.get(mapId), f = B.tagIndex[tag];
  return !!p && f != null && p.d[f] > 0;
}

function mapCardLinks(mapId) {
  const au = mapAuthorOf(mapBuild().byId.get(mapId));
  return `<button type="button" class="tomap" data-similar="books:${esc(mapId)}">Similar books</button>${
    au ? `<button type="button" class="tomap" data-similar="authors:${esc(mapId)}">Similar authors</button>` : ''}${
    mapAuthorLink(mapId)}`;
}

function mapStart(mode, mapId) {
  const p = mapBuild().byId.get(mapId);
  if (!p) return;
  mapOpts().mode = mode;
  mapSaveOpts();
  MAP.bookSeeds = [p];
  MAP.seeds = mode === 'authors' ? [mapAuthorOf(p)].filter(Boolean) : [p];
  if (state.view !== 'similar') MAP.from = { view: state.view, y: scrollY };
  mapCloseAuthor();
  setView('similar');
  scrollTo(0, 0);
}

function mapLeave() {
  const from = MAP.from || { view: 'candidates', y: 0 };
  MAP.seeds = [];
  MAP.bookSeeds = [];
  MAP.from = null;
  setView(from.view);
  scrollTo(0, from.y);
}

function mapSetMode(mode) {
  const o = mapOpts();
  if (o.mode === mode) return;
  o.mode = mode;
  mapSaveOpts();
  MAP.seeds = mode === 'authors' ? [...new Set(MAP.bookSeeds.map(mapAuthorOf).filter(Boolean))] : MAP.bookSeeds.slice();
  if (!MAP.seeds.length) { mapLeave(); return; }
  render();
}

function mapSetSeeds(seeds) {
  MAP.seeds = seeds;
  if (mapOpts().mode === 'books') MAP.bookSeeds = seeds.slice();
  if (!seeds.length) { mapLeave(); return; }
  render();
  scrollTo(0, 0);
}

function mapBar() {
  const o = mapOpts();
  const seg = [['books', 'Books'], ['authors', 'Authors']].map(([m, label]) =>
    `<button type="button" data-simmode="${m}" aria-pressed="${o.mode === m}">${label}</button>`).join('');
  return `<div class="simbar">
    <span class="simlabel">Similar to</span>
    ${MAP.seeds.map(s => `<span class="badge seed">${esc(mapLabel(s))}<button type="button" data-simdrop="${s.ref}"
      aria-label="Remove ${esc(mapLabel(s))}">×</button></span>`).join('')}
    <div class="wseg" role="group" aria-label="Show">${seg}</div>
    <label class="range">Min. <b id="minsimval">${Math.round(o.minSim * 100)} %</b>
      <input type="range" min="10" max="90" step="5" value="${Math.round(o.minSim * 100)}" data-mapopt="minSim" aria-label="Minimum similarity"></label>
    <label class="chk"><input type="checkbox" data-mapopt="unread"${o.unread ? ' checked' : ''}> Unread only</label>
    ${o.mode === 'books' ? `<label class="chk"><input type="checkbox" data-mapopt="sameAuthor"${o.sameAuthor ? ' checked' : ''}> Same author too</label>` : ''}
    <button type="button" class="unpick" data-simclose title="Back to the list" aria-label="Back to the list">×</button>
  </div>`;
}

const mapAuthorBooks = a => a.members.filter(m => m.on && !(MAP.opts.unread && m.kind === 'r')).sort(mapBestFirst);

function mapSimLine(r, B) {
  const shared = sharedTags(MAP.seeds, r.p, B);
  return `<div class="simline"><b>${Math.round(r.sim * 100)} %</b>${shared.length ? `<span>${esc(shared.join(' · '))}</span>` : ''}
    <button type="button" class="linkish" data-simadd="${r.p.ref}" title="Find what is close to this too">+ also like this</button></div>`;
}

const mapBookRow = (r, B) => `<div class="simitem">${mapSimLine(r, B)}${mapCard(r.p)}</div>`;

// One tile per author, so authors wrap in the grid like books do: the best book as a card,
// the rest as names that open the author map at that book.
function mapAuthorRow(r, B) {
  const a = r.p, [best, ...rest] = r.books;
  const also = rest.slice(0, 4).map(m => `<button type="button" class="linkish" data-toauthor="${esc(m.id)}">${esc(m.title)}</button>`);
  if (rest.length > 4) also.push(`${rest.length - 4} more`);
  return `<div class="simitem simauthor"><div class="simhead"><span class="simname">${esc(a.name)}</span>${
      mapAuthorMap(a.name).size > 1 ? `<button type="button" class="tomap" data-toauthor="a:${esc(a.name)}">Author map</button>` : ''}</div>
    ${mapSimLine(r, B)}${mapCard(best)}${also.length ? `<p class="mapnote">Also ${also.join(', ')}</p>` : ''}</div>`;
}

function similarView() {
  if (!D.sim || !MAP.seeds.length) return EMPTY;
  const B = mapBuild(), o = mapOpts();
  mapMatches(B);
  const authors = o.mode === 'authors';
  const rows = authors ? mapAbove(B).map(r => ({ ...r, books: mapAuthorBooks(r.p) })).filter(r => r.books.length) : mapAbove(B);
  setCount(plural(rows.length, authors ? 'author' : 'book'));
  if (!rows.length) return `<div class="empty">Nothing above ${Math.round(o.minSim * 100)} % with these filters</div>`;
  const shown = rows.slice(0, MAP_SHOWN);
  return grid(shown.map(r => (authors ? mapAuthorRow : mapBookRow)(r, B))) +
    (rows.length > shown.length ? `<p class="mapnote">The closest ${MAP_SHOWN} of ${rows.length}</p>` : '');
}

// The author map: every book of an author as a reading graph, one box per series or shared
// world. book-worlds.json holds the researched worlds and their recommended reading order;
// any other series is drawn from book-series.json, which knows only the shelf, the read rows
// and a volume count.

const MAP_G = { box: 200, lane: 236, h: 40, row: 72, top: 30, head: 36, wrap: 6 };

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

function mapWorldIdOf(p) {
  if (!p || p.members || !D.worlds) return null;
  const X = mapWorldIndex();
  if (p.isSeries) {
    const sid = p.id.replace(/^r?s:/, '');
    return X.ofLine[sid] || (D.seriesDoc[sid] ? 's:' + sid : null);
  }
  return (p.kind === 'c' ? X.ofKey[p.key] : X.ofRead[p.row.title]) || null;
}

const mapAuthorOf = p => p ? (p.members ? p : p.authorRef || null) : null;

function mapAuthorLink(mapId) {
  const au = mapHas(mapId) && mapAuthorOf(mapBuild().byId.get(mapId));
  return au && mapAuthorMap(au.name).size > 1
    ? `<button type="button" class="tomap" data-toauthor="${esc(mapId)}">Author map</button>` : '';
}

// One box per world, so boxes never connect to each other; books in no series share one
// box of standalones.
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
  const m = { name, au, blocks, size: blocks.reduce((t, w) => t + w.nodes.reduce((s, n) => s + mapNodeSize(n), 0), 0) };
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

const mapNodeSize = n => n.count || 1;

// The recommended order where research recorded one; otherwise each series in its own
// numbering, starting at its first volume. A researched world's unnumbered books are
// companions read after their series; on a shelf-only series their place is unknown, so
// they get no arrow at all.
function mapReading(w) {
  const ids = new Set(w.nodes.map(n => n.id)), r = w.reading, edges = [], starts = [];
  if (r) {
    (r.chains || []).forEach(c => c.slice(1).forEach((id, i) => edges.push([c[i], id, false])));
    (r.after || []).forEach(([a, b]) => edges.push([a, b, true]));
    starts.push(...(r.starts || []));
  } else w.lines.forEach(l => {
    const list = w.nodes.filter(n => n.line === l.id);
    if (l.standalone) { starts.push(...list.filter(n => !n.gap).map(n => n.id)); return; }
    const num = list.filter(n => n.n != null).sort((a, b) => a.n - b.n);
    num.slice(1).forEach((n, i) => edges.push([num[i].id, n.id, false]));
    if (!num.length) return;
    starts.push(num[0].id);
    if (!w.synthetic) list.filter(n => n.n == null).forEach(n => edges.push([num[num.length - 1].id, n.id, true]));
  });
  return { edges: edges.filter(([a, b]) => ids.has(a) && ids.has(b)), starts: new Set(starts.filter(i => ids.has(i))) };
}

// One column per series (a long list of standalones wraps into several). Books are placed in
// reading order, each on the first row below every book it follows and below the previous
// book of its column, so series read side by side share rows.
function mapGraphLayout(w, R, heads) {
  const cols = [], colOf = {};
  w.lines.forEach(l => {
    const list = w.nodes.filter(n => n.line === l.id);
    if (!list.length) return;
    const k = l.standalone ? Math.ceil(list.length / MAP_G.wrap) : 1, first = cols.length;
    for (let j = 0; j < k; j++) cols.push({ line: l, head: j === 0 });
    list.forEach((n, i) => { colOf[n.id] = first + (l.standalone ? Math.floor(i / MAP_G.wrap) : 0); });
  });
  const inc = Object.fromEntries(w.nodes.map(n => [n.id, []]));
  R.edges.forEach(([a, b]) => inc[b].push(a));
  const rank = n => colOf[n.id] * 1e4 + (n.n ?? 5e3);
  const pending = w.nodes.slice().sort((a, b) => rank(a) - rank(b));
  const row = {}, next = cols.map(() => 0);
  while (pending.length) {
    let i = pending.findIndex(n => inc[n.id].every(p => p in row));
    if (i < 0) i = 0;
    const n = pending.splice(i, 1)[0], c = colOf[n.id];
    row[n.id] = Math.max(next[c], ...inc[n.id].filter(p => p in row).map(p => row[p] + 1));
    next[c] = row[n.id] + 1;
  }
  const top = MAP_G.top + (heads ? MAP_G.head : 0), at = {};
  w.nodes.forEach(n => { at[n.id] = { x: colOf[n.id] * MAP_G.lane, y: top + row[n.id] * MAP_G.row, col: colOf[n.id], row: row[n.id] }; });
  const rows = Math.max(0, ...Object.values(row)) + 1;
  return { cols, at, W: cols.length * MAP_G.lane + 30, H: top + rows * MAP_G.row - (MAP_G.row - MAP_G.h) + 12 };
}

function mapGraphSvg(L, R) {
  const { box, h } = MAP_G, cx = p => p.x + box / 2, out = [];
  R.edges.forEach(([a, b, soft]) => {
    const A = L.at[a], Bp = L.at[b];
    if (!A || !Bp) return;
    const cls = soft ? 'wsoft' : 'wnext', mk = soft ? 'wahs' : 'wahn';
    let d;
    if (A.col === Bp.col && Bp.row === A.row + 1) d = `M${cx(A)},${A.y + h} L${cx(Bp)},${Bp.y - 1}`;
    else if (A.col === Bp.col) {
      // Skipping rows within a column would run through the boxes between, so go round the right.
      const x = A.x + box, x2 = Bp.x + box;
      d = `M${x},${A.y + h / 2} C${x + 44},${A.y + h / 2} ${x2 + 44},${Bp.y + h / 2} ${x2 + 1},${Bp.y + h / 2}`;
    } else {
      const dy = Math.max(20, (Bp.y - A.y - h) / 2);
      d = `M${cx(A)},${A.y + h} C${cx(A)},${A.y + h + dy} ${cx(Bp)},${Bp.y - dy} ${cx(Bp)},${Bp.y - 1}`;
    }
    out.push(`<path class="${cls}" marker-end="url(#${mk})" d="${d}"/>`);
  });
  R.starts.forEach(id => {
    const p = L.at[id];
    if (!p) return;
    out.push(`<g class="wstart"><rect x="${p.x + 4}" y="${p.y - 27}" width="38" height="15" rx="7.5"/>
      <text x="${p.x + 23}" y="${p.y - 16}">start</text>
      <path marker-end="url(#wahg)" d="M${p.x + 23},${p.y - 12} L${p.x + 23},${p.y - 2}"/></g>`);
  });
  return `<svg width="${L.W}" height="${L.H}" aria-hidden="true">${out.join('')}</svg>`;
}

function mapWorldNodeHtml(n, at, B) {
  const p = n.ref && B.byId.get(n.ref), hl = MAP.hl && mapByRef(B, MAP.hl);
  const value = n.state === 'read' ? (n.score == null ? '—' : ten(n.score))
    : n.state === 'shelf' && n.est ? rng(n.est[0], n.est[1]) : '';
  const tone = n.score == null ? 'bN' : mapTone(n);
  const sub = [n.word, n.alt, n.year].filter(Boolean).join(' · ');
  const tip = [n.title, n.alt, n.year, n.word, n.note].filter(Boolean).join('\n');
  const link = n.href && n.state !== 'read'
    ? `<a href="${esc(n.href)}" target="_blank" rel="noreferrer" title="Open the catalogue record">Borrow ↗</a>` : '';
  return `<div class="wnode ${n.state} ${tone}${p && p === hl ? ' sel' : ''}" title="${esc(tip)}"
      style="left:${at.x}px;top:${at.y}px;width:${MAP_G.box}px;height:${MAP_G.h}px"${
      p ? ` data-mark="${p.ref}" tabindex="0" role="button"` : ''}>
    <span class="wm ${n.state}"></span>
    <span style="min-width:0"><span class="wt">${n.n != null && !n.gap ? `<i>${esc(n.n)}</i>` : ''}${esc(n.title)}</span>
      <span class="ws">${esc(sub)}</span></span>
    ${value ? `<span class="wv">${esc(value)}</span>` : link}</div>`;
}

const MAP_W_DEFS = `<svg width="0" height="0" style="position:absolute" aria-hidden="true"><defs>${
  [['wahn', 'wah'], ['wahs', 'wah soft'], ['wahg', 'wah go']].map(([id, cls]) => `<marker id="${id}" viewBox="0 0 8 8" refX="7" refY="4"
    markerWidth="7" markerHeight="7" orient="auto"><path class="${cls}" d="M0,0 L8,4 L0,8 z"/></marker>`).join('')}</defs></svg>`;

function mapTally(nodes) {
  const LABEL = { read: 'read', shelf: 'on the shelf', library: 'in the library', rejected: 'rejected',
                  gap: 'not on the shelf' };
  const tally = new Map(Object.values(LABEL).map(k => [k, 0]));
  nodes.forEach(n => { const k = LABEL[n.state] || n.word; tally.set(k, (tally.get(k) || 0) + mapNodeSize(n)); });
  const total = nodes.reduce((t, n) => t + mapNodeSize(n), 0);
  return `${plural(total, 'book')} · ${[...tally].filter(([, k]) => k).map(([label, k]) => `${k} ${label}`).join(', ')}`;
}

// Why the boxes are ordered as they are, and what links the series, folded under each box.
function mapWorldNotes(w) {
  const byId = Object.fromEntries(w.nodes.map(n => [n.id, n]));
  const name = id => byId[id] ? byId[id].title : (w.lines.find(l => l.id === id) || {}).name || id;
  const KIND = { then: 'continues in', prequel: 'prequel to', crossover: 'crossover with' };
  const items = [
    ...(w.links || []).map(k => `<li><span class="wk">${KIND[k.kind] || k.kind}</span><b>${esc(name(k.from))}</b> → <b>${
      esc(name(k.to))}</b>${k.note ? ' — ' + esc(k.note) : ''}</li>`),
    ...w.lines.filter(l => l.note).map(l => `<li><b>${esc(l.name)}</b> — ${esc(l.note)}</li>`),
    ...(w.arcs || []).filter(a => a.note).map(a => `<li><b>${esc(a.name)}</b> — ${esc(a.note)}</li>`),
  ];
  const src = [...new Set([...(w.reading && w.reading.sources || []), ...(w.sources || [])])]
    .map((u, i) => `<a href="${esc(u)}" target="_blank" rel="noopener">${i + 1}</a>`).join(' ');
  const why = w.reading && w.reading.note;
  if (!why && !items.length && !w.checked) return '';
  return `<details class="wbnotes"><summary>${w.reading ? 'Why this order' : 'Notes'}</summary>
    ${why ? `<p class="wbwhy">${esc(why)}</p>` : ''}
    ${items.length ? `<ul class="wplinks">${items.join('')}</ul>` : ''}
    ${w.checked ? `<p class="mapnote">Researched ${esc(w.checked)}${w.libChecked ? `, library checked ${esc(w.libChecked)}` : ''}${
      src ? ` · sources ${src}` : ''}</p>` : ''}</details>`;
}

function mapGraph(w, B) {
  const R = mapReading(w), heads = w.lines.filter(l => w.nodes.some(n => n.line === l.id)).length > 1;
  const L = mapGraphLayout(w, R, heads);
  return `<div class="wpgraph" style="width:${L.W}px;height:${L.H}px">${mapGraphSvg(L, R)}
    ${heads ? L.cols.map((c, i) => c.head ? `<div class="wlane" style="left:${i * MAP_G.lane}px;top:4px;width:${MAP_G.lane - 12}px" title="${
      esc(c.line.note || '')}"><b>${esc(c.line.name)}</b><span>${esc(c.line.nameEn && c.line.nameEn !== c.line.name ? c.line.nameEn : '')}</span></div>` : '').join('') : ''}
    ${w.nodes.map(n => mapWorldNodeHtml(n, L.at[n.id], B)).join('')}
  </div>`;
}

function mapAuthorHtml(m, B) {
  const head = w => w.solo ? '<b>Standalone books</b>'
    : `<b>${esc(w.name)}</b>${w.nameEn ? ` <span class="bk-alt">${esc(w.nameEn)}</span>` : ''}`;
  const many = m.blocks.length > 1;
  return `<div class="wphead">
      <div><div class="bk-title">${esc(m.name)}</div>
        <div class="bk-meta">${esc(mapTally(m.blocks.flatMap(w => w.nodes)))}</div></div>
      <button type="button" class="unpick" data-world-close title="Close (Esc)" aria-label="Close">×</button>
    </div>
    <div class="wpbody">${MAP_W_DEFS}
      <div class="wblocks">${m.blocks.map(w => `<section class="wblock"><div class="wbhead">${head(w)}
          ${many ? `<div class="bk-meta">${esc(mapTally(w.nodes))}</div>` : ''}${mapWorldNotes(w)}</div>
        ${mapGraph(w, B)}</section>`).join('')}</div>
    </div>`;
}

// v is a book's map id, which also marks that book, or 'a:' + an author's name.
function mapOpenAuthor(v) {
  const B = mapBuild(), p = v.startsWith('a:') ? null : B.byId.get(v);
  const au = p ? mapAuthorOf(p) : B.authors.find(a => a.name === v.slice(2));
  if (!au) return;
  MAP.world = 'a:' + au.name;
  MAP.hl = p ? p.ref : null;
  mapSheetRender(true);
}

function mapCloseAuthor() {
  MAP.world = null;
  MAP.hl = null;
  mapSheetRender();
}

function mapSheetRender(fresh = false) {
  const el = F('authorsheet');
  if (!el) return;
  const id = MAP.world, m = id && mapAuthorMap(id.slice(2));
  el.hidden = !m;
  document.body.classList.toggle('sheet-open', !!m);
  if (!m) { el.innerHTML = ''; delete el.dataset.world; return; }
  const B = mapBuild(), body = el.querySelector('.wpbody');
  const keep = !fresh && body && el.dataset.world === id ? [body.scrollLeft, body.scrollTop] : null;
  const hl = MAP.hl && mapByRef(B, MAP.hl);
  el.innerHTML = `<div class="sheetpanel" role="dialog" aria-modal="true" aria-label="${esc('Author map: ' + m.name)}">
    ${mapAuthorHtml(m, B)}
    <aside class="sheetside">${hl ? mapCard(hl) : '<p class="mapnote">Click a book to see its card.</p>'}</aside></div>`;
  el.dataset.world = id;
  const nb = el.querySelector('.wpbody'), sel = el.querySelector('.wnode.sel');
  if (keep) [nb.scrollLeft, nb.scrollTop] = keep;
  else if (sel) {
    nb.scrollTop = Math.max(0, sel.offsetTop + sel.closest('.wblock').offsetTop - nb.clientHeight / 3);
    nb.scrollLeft = Math.max(0, sel.offsetLeft + sel.closest('.wblock').offsetLeft - nb.clientWidth / 3);
  }
  markClips();
}

document.addEventListener('click', e => {
  const sim = e.target.closest('[data-similar]');
  if (sim) {
    const v = sim.dataset.similar, at = v.indexOf(':');
    mapStart(v.slice(0, at), v.slice(at + 1));
    return;
  }
  const to = e.target.closest('[data-toauthor]');
  if (to) { mapOpenAuthor(to.dataset.toauthor); return; }
  const sheet = F('authorsheet');
  if (sheet && !sheet.hidden) {
    if (e.target === sheet || e.target.closest('[data-world-close]')) { mapCloseAuthor(); return; }
    const mark = !e.target.closest('#authorsheet a') && e.target.closest('[data-mark]');
    if (mark) { MAP.hl = MAP.hl === mark.dataset.mark ? null : mark.dataset.mark; mapSheetRender(); return; }
  }
  if (state.view !== 'similar') return;
  const B = mapBuild();
  const mode = e.target.closest('[data-simmode]');
  if (mode) { mapSetMode(mode.dataset.simmode); return; }
  if (e.target.closest('[data-simclose]')) { mapLeave(); return; }
  const add = e.target.closest('[data-simadd]'), p = add && mapByRef(B, add.dataset.simadd);
  if (p) { if (!MAP.seeds.includes(p)) mapSetSeeds([...MAP.seeds, p]); return; }
  const drop = e.target.closest('[data-simdrop]');
  if (drop) mapSetSeeds(MAP.seeds.filter(s => s.ref !== drop.dataset.simdrop));
});

// The slider redraws only the list: redrawing the bar would replace the slider mid-drag.
document.addEventListener('input', e => {
  const opt = e.target.closest('[data-mapopt]');
  if (!opt) return;
  const o = mapOpts(), name = opt.dataset.mapopt;
  if (name === 'minSim') {
    o.minSim = +opt.value / 100;
    F('minsimval').textContent = opt.value + ' %';
  } else o[name] = opt.checked;
  mapSaveOpts();
  F('view').innerHTML = similarView();
  markClips();
});

document.addEventListener('keydown', e => {
  if (e.key === 'Escape' && MAP.world) { mapCloseAuthor(); return; }
  const node = (e.key === 'Enter' || e.key === ' ') && e.target.closest && e.target.closest('.wnode[data-mark]');
  if (node) { e.preventDefault(); node.click(); }
});
