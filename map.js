// The Map tab. Loaded before the main script and run against its globals (D, F, esc,
// band, tone, cover, accessLine, LEGEND, render, setView, store, recall,
// candidateFilter, readFilter), all of which exist by the time anything here is called.
// Names are map-prefixed because every top-level declaration shares one scope with
// index.html.

const MAP = {
  opts: null, seeds: [], hover: null, cam: null, built: null, pendingFocus: null,
  ro: null, raf: 0, gen: 0, memo: null,
};

const MAP_BAND_VAR = { 'S+': '--b-S', S: '--b-S', A: '--b-A', B: '--b-B', C: '--b-C', F: '--b-F' };
const MAP_PAD = 28;
const MAP_SHOWN = 40;

function mapOpts() {
  if (!MAP.opts) {
    let saved = {};
    try { saved = JSON.parse(recall('bookshelf.map')) || {}; } catch {}
    MAP.opts = { mode: 'books', minSim: 0.4, unread: true, sameAuthor: false, tags: [], ...saved };
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
  const authors = [];
  sim.authors.forEach(a => {
    const members = a.books.map(i => bySimIdx[i]).filter(Boolean);
    if (!members.length) return;
    const d = new Float32Array(NF);
    members.forEach(m => m.d.forEach((x, f) => { d[f] += x; }));
    const norm = Math.hypot(...d) || 1;
    const read = members.filter(m => m.kind === 'r');
    const live = members.filter(m => m.kind === 'c' && m.score != null);
    const au = {
      name: a.name, x: a.x, y: a.y, members, i: authors.length, ref: 'a' + authors.length, hasRead: read.length > 0,
      d: d.map(x => x / norm),
      score: read.length ? Math.max(...read.map(m => m.score))
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
  MAP.built = { D, NT, books, authors, regions, tagIndex, ids: new Set(books.map(b => b.id)),
                tagIds: sim.tags.map(t => t[0]), tagLabel: sim.tags.map(t => t[1]), tagGroup: sim.tags.map(t => t[3]),
                unmapped: D.books.length + D.read.rows.length - books.length };
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

// With a selection, only it and its listed matches stay opaque and clickable.
const mapFocusSet = B => MAP.seeds.length
  ? new Set([...MAP.seeds, ...mapAbove(B).slice(0, MAP_SHOWN).map(r => r.p)]) : null;

function sharedTags(seeds, p, B, n = 3) {
  return p.sv.filter(([f]) => f < B.NT)
    .map(([f, x]) => [x * Math.min(...seeds.map(s => s.d[f])), f]).filter(([c]) => c > 0)
    .sort((a, b) => b[0] - a[0]).slice(0, n).map(([, f]) => B.tagLabel[f]);
}

function mapScoreText(p) {
  if (p.members) {
    if (p.score == null) return 'blocked only';
    return p.hasRead ? `read · best ${p.score}` : `best prediction ${Math.round(p.score)}`;
  }
  if (p.kind === 'r') return `read · ${p.score}`;
  return p.row.est ? `predicted ${p.row.est[0]}–${p.row.est[1]}` : 'blocked';
}

const mapLetter = p => p.score == null ? '—' : band(p.score);
const mapTone = p => p.score == null ? 'bN' : tone(p.score);
const mapCount = (n, word) => `${n} ${word}${n === 1 ? '' : 's'}`;
const mapLabel = p => p.members ? p.name : p.title;

// The first verified route only: the full access line is in the panel head once a
// book is selected.
function mapRowLink(p) {
  if (p.members || p.kind !== 'c') return '';
  const b = p.row, part = b.hasEn && (b.en.parts || [])[0];
  if (b.hasCz && b.cz.recordUrl) return `<a class="rowlink" href="${esc(b.cz.recordUrl)}" target="_blank" rel="noreferrer"
    title="Borrow — Czech print: open the catalogue record at Městská knihovna Valašské Meziříčí">Borrow ↗</a>`;
  if (part) return `<a class="rowlink" href="${esc(part.url)}" target="_blank" rel="noreferrer"
    title="Free English audio">▶ Listen</a>`;
  return '';
}

function mapRow(p, B, r) {
  const sub = p.members ? mapCount(p.members.length, 'book') : p.author;
  const why = r ? sharedTags(MAP.seeds, p, B) : [];
  const per = r && r.per.length > 1
    ? ` title="${esc(MAP.seeds.map((s, i) => `${mapLabel(s)}: ${Math.round(r.per[i] * 100)} %`).join('\n'))}"` : '';
  const added = MAP.seeds.includes(p), sameKind = !!p.members === (MAP.opts.mode === 'authors');
  return `<li class="prow"><button type="button" class="pick ${mapTone(p)}" data-pick="${p.ref}">
      <span class="pl">${mapLetter(p)}</span>
      <span class="pt"><b>${esc(mapLabel(p))}</b><br><span class="ps">${esc(sub)} · ${esc(mapScoreText(p))}</span>
        ${why.length ? `<br><span class="pw">${esc(why.join(' · '))}</span>` : ''}</span>
      ${r ? `<span class="pp"${per}>${Math.round(r.sim * 100)} %<span class="pbar"><i style="width:${Math.round(r.sim * 100)}%"></i></span></span>` : ''}
    </button><span class="pacts">${sameKind ? `<button type="button" class="addseed" data-add="${p.ref}"
      title="${added ? 'Remove from the selection' : 'Add to the selection — find titles close to all of it'}">${added ? '−' : '+'}</button>` : ''}${
      mapRowLink(p)}</span></li>`;
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
  return `<div class="sidehead">${cover(sel.row.media || {}, sel.author)}
      <div><div class="bk-title">${esc(sel.title)}</div>
        ${sel.alt ? `<div class="bk-alt">${esc(sel.alt)}</div>` : ''}
        <div class="bk-author">${sel.authorRef
          ? `<button type="button" class="linkish" data-pick="${sel.authorRef.ref}" title="Show the author on the authors map">${esc(sel.author)}</button>`
          : esc(sel.author)}</div>
        <div class="scorerow ${mapTone(sel)}"><span class="bandletter small">${mapLetter(sel)}</span>
          <span class="scorelabel">${esc(mapScoreText(sel))}</span></div></div>${close}</div>
    ${mapWhy(sel)}
    ${sel.kind === 'c' ? `<div class="access">${accessLine(sel.row)}</div>` : ''}
    <div class="badges">${mapChips(sel, B)}</div>`;
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
  if (!MAP.seeds.length) {
    const anchors = (MAP.opts.mode === 'authors' ? B.authors.filter(a => a.hasRead) : B.books.filter(p => p.kind === 'r'))
      .filter(p => p.on).sort((a, b) => b.score - a.score).slice(0, 15);
    return `<p class="mapnote">Click a point to see what is closest to it in content: a similar world, kind,
      themes and tone. Shift+click, or <b>+</b> in a list, adds more to the selection, and the list then
      shows titles close to <i>all</i> of them. While something is selected, only it and its matches
      stay clickable; click empty space to clear. Near on the map means similar; distance across the
      whole map means nothing.</p>
      ${anchors.length ? `<h4>Start from what you know</h4>${mapList(anchors, B)}` : ''}`;
  }
  const o = MAP.opts;
  return `<div id="maphead">${mapHead(B)}</div>
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
    <span>· ${o.mode === 'authors' ? '◆ an author you have read · ● candidates only' : '◆ read · ● candidate'}
    · colour, size and stacking follow the score, real for read books, predicted for the rest
    · a line to a match is thicker the closer it is</span></div>
    ${o.tags.length ? `<div class="tagfilters">Only ${o.mode === 'authors' ? 'authors with books' : 'titles'} tagged:
      ${o.tags.map(t => `<button type="button" class="badge tagbtn on" data-untag="${esc(t)}" title="Remove this tag">${
        esc(B.tagLabel[B.tagIndex[t]])} ×</button>`).join('')}
      <button type="button" class="linkish" data-untag="*">clear all</button></div>` : ''}
    <div class="mapwrap">
      <div class="mapstage" id="mapstage">
        <canvas id="mapc" aria-label="Similarity map of ${what}"></canvas>
        <div class="mapmode" role="group" aria-label="What the map shows">
          <button type="button" data-mode="books" aria-pressed="${o.mode === 'books'}">Books</button>
          <button type="button" data-mode="authors" aria-pressed="${o.mode === 'authors'}">Authors</button>
        </div>
        <div class="maptools">
          <button type="button" data-mz="in" title="Zoom in">+</button>
          <button type="button" data-mz="out" title="Zoom out">−</button>
          <button type="button" data-mz="fit">Fit</button>
        </div>
        <div class="maptip" id="maptip" hidden></div>
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
  const res = seeds.length ? mapAbove(B).slice(0, MAP_SHOWN) : [];
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
    } else ctx.arc(p.sx, p.sy, r, 0, Math.PI * 2);
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
  const taken = [[0, 0, 170, 46], [W - 140, 0, W, 46]];
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
  if (MAP.seeds.length && !MAP.seeds.includes(p)) {
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

function mapSetSeeds(seeds, focus) {
  MAP.seeds = seeds;
  const side = F('mapside');
  if (side) { side.innerHTML = mapSide(mapBuild()); side.scrollTop = 0; }
  if (seeds.length > 1) mapFrame([...seeds, ...mapAbove(mapBuild()).slice(0, 15).map(r => r.p)]);
  else if (focus) mapFocus(focus);
  else mapRedraw();
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
      else mapSetSeeds(p ? [p] : []);
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

function mapOpen(p, mode) {
  mapOpts().mode = mode;
  mapSaveOpts();
  MAP.seeds = p ? [p] : [];
  MAP.pendingFocus = p;
  MAP.memo = null;
  if (MAP.cam) MAP.cam.mode = null;
}

document.addEventListener('click', e => {
  const to = e.target.closest('[data-tomap]');
  if (to) {
    const p = mapBuild().books.find(b => b.id === to.dataset.tomap);
    if (!p) return;
    mapOpen(p, 'books');
    setView('map');
    scrollTo(0, 0);
    return;
  }
  if (!F('mapstage')) return;
  const B = mapBuild();
  const mode = e.target.closest('[data-mode]');
  if (mode) {
    if (mode.dataset.mode !== MAP.opts.mode) { mapOpen(null, mode.dataset.mode); render(); }
    return;
  }
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
  const pick = e.target.closest('[data-pick]');
  if (pick) {
    const p = mapByRef(B, pick.dataset.pick), mode = pick.dataset.pick[0] === 'a' ? 'authors' : 'books';
    if (mode === MAP.opts.mode) { mapSetSeeds([p], p); return; }
    mapOpen(p, mode);
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

new MutationObserver(mapRedraw).observe(document.documentElement, { attributes: true, attributeFilter: ['data-theme'] });
matchMedia('(prefers-color-scheme: dark)').addEventListener('change', mapRedraw);
