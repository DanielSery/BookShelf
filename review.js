// The review sheet: the reader scores a book, says which markers moved the score, and the page
// commits the entry to book-reviews.json on main through the GitHub API, then refits in place.
// Runs against the main script's globals; names are rv-prefixed for the shared scope.

const RV_REPO = 'DanielSery/BookShelf', RV_BRANCH = 'main', RV_PATH = 'book-reviews.json';
const RV_TOKEN = 'bookshelf.ghtoken', RV_PENDING = 'bookshelf.rvpending';
const RV_WORDS = ['endorse', 'recommend', 'neutral', 'discourage', 'oppose'];
const RV_SIDES = [['helped', 'Helped'], ['', 'No effect'], ['hurt', 'Hurt'], ['removed', 'Not in it']];
const RV_PENDING_MS = 3600000;
let RV = null;

const rvCap = w => w[0].toUpperCase() + w.slice(1);
const rvToday = () => new Date().toLocaleDateString('sv');
const rvPending = () => { try { return JSON.parse(recall(RV_PENDING)) || {}; } catch { return {}; } };

// Pages keeps serving the old file for a few minutes after a save, so until the fetched file
// carries an entry this browser saved, the browser shows its own copy of it.
function rvApplyPending(doc) {
  const pend = rvPending(), reviews = doc.reviews = doc.reviews || {};
  Object.entries(pend).forEach(([id, p]) => {
    if (JSON.stringify(reviews[id] ?? null) === JSON.stringify(p.e) || Date.now() - p.t > RV_PENDING_MS) delete pend[id];
    else if (p.e) reviews[id] = p.e;
    else delete reviews[id];
  });
  store(RV_PENDING, JSON.stringify(pend));
  return doc;
}

function rvOpen(key) {
  const b = D.books.find(x => x.key === key);
  if (!b || !D.taste) return;
  const id = 'c:' + key, rv = D.taste.model.reviews[id] || {}, ticks = {};
  ['helped', 'hurt', 'removed'].forEach(side => (rv[side] || []).forEach(t => { ticks[t] = side; }));
  RV = { b, id, editing: !!rv.at, score: rv.at ? rv.score : undefined, notes: rv.notes || '', ticks,
         added: { ...(rv.added || {}) }, token: '', busy: false, msg: '', err: false };
  rvRender();
  F('reviewsheet').querySelector('.rvpanel').focus();
}

function rvClose() {
  RV = null;
  const el = F('reviewsheet');
  el.hidden = true;
  el.innerHTML = '';
  document.body.classList.remove('rv-open');
}

function rvMarkerRows() {
  const { model, fit } = D.taste, m = model.taste[RV.id] || {};
  const ids = [...new Set([...Object.keys(m), ...Object.keys(RV.added)])].filter(t => model.byId[t]);
  const strength = t => Math.max(m[t] || 0, RV.added[t] || 0);
  const effect = t => model.byId[t].kind === 'veto' ? null : ((fit && fit.w[t]) || 0) * tasteValue(model, t, strength(t));
  const rank = t => effect(t) == null ? Infinity : Math.abs(effect(t));
  return ids.sort((a, b) => rank(b) - rank(a)).map(t => {
    const mk = model.byId[t], fx = effect(t), own = t in RV.added && !(t in m);
    const val = fx == null ? '<span class="v costs">veto</span>'
      : Math.round(fx) ? `<span class="v ${fx < 0 ? 'costs' : 'earns'}">${fx < 0 ? '−' : '+'}${Math.abs(Math.round(fx))}</span>` : '<span class="v">0</span>';
    const sides = RV_SIDES.filter(([side]) => !(own && side === 'removed')).map(([side, label]) =>
      `<button type="button" data-rv-tick="${esc(t)}|${side}" aria-pressed="${(RV.ticks[t] || '') === side}">${label}</button>`).join('');
    return `<li><div class="rvname">${val} ${esc(mk.label)} <span class="bk-meta">${strength(t)}/3${own ? ' · added' : ''}</span>${
        own ? ` <button type="button" class="unpick" data-rv-drop="${esc(t)}" aria-label="Remove ${esc(mk.label)}">×</button>` : ''}</div>
      <div class="wseg" role="group" aria-label="${esc(mk.label)}">${sides}</div></li>`;
  }).join('');
}

function rvAddOptions() {
  const { model } = D.taste, have = { ...(model.taste[RV.id] || {}), ...RV.added };
  const group = (kind, label) => `<optgroup label="${label}">${model.markers.filter(mk => mk.kind === kind && !(mk.id in have))
    .sort((a, b) => a.label.localeCompare(b.label))
    .map(mk => `<option value="${esc(mk.id)}">${esc(mk.label)}</option>`).join('')}</optgroup>`;
  return `<option value="">Add a marker the book has…</option>${group('graded', 'Graded')}${group('veto', 'Vetoes')}`;
}

function rvRender() {
  const el = F('reviewsheet'), b = RV.b;
  const title = b.cache.czTitle || b.cache.title || b.key, alt = b.cache.czTitle && b.cache.title !== b.cache.czTitle ? b.cache.title : '';
  const marked = !!D.taste.model.taste[RV.id];
  const scores = [...RV_WORDS.map(w => [w, rvCap(w)]), ['', 'Not finished']].map(([w, label]) =>
    `<button type="button" data-rv-score="${w}" aria-pressed="${RV.score !== undefined && (RV.score || '') === w}">${label}</button>`).join('');
  const token = recall(RV_TOKEN)
    ? `<p class="bk-meta rvtok">Saves to GitHub with the token in this browser · <button type="button" class="linkish" data-rv-forget>Forget it</button></p>`
    : `<label class="rvlabel" for="rvtoken">GitHub token</label>
       <input id="rvtoken" type="password" autocomplete="off" spellcheck="false" placeholder="github_pat_…" value="${esc(RV.token)}">
       <p class="bk-meta">A fine-grained token with Contents read and write on ${RV_REPO} and nothing else: it stays
       in this browser, where every page on ${esc(location.hostname)} can read it.</p>`;
  el.innerHTML = `<div class="rvpanel" role="dialog" aria-modal="true" aria-label="${esc('Review: ' + title)}" tabindex="-1">
    <div class="wphead"><div><div class="bk-title">${esc(title)}${alt ? ` <span class="bk-alt">(${esc(alt)})</span>` : ''}</div>
      <div class="bk-author">${esc(b.cache.author || '')}</div></div>
      <button type="button" class="unpick" data-rv-close aria-label="Close">×</button></div>
    <div class="rvbody">
      <div class="rvlabel">Score</div>
      <div class="wseg rvscore" role="group" aria-label="Score">${scores}</div>
      <label class="rvlabel" for="rvnotes">Notes</label>
      <textarea id="rvnotes" rows="4">${esc(RV.notes)}</textarea>
      <div class="rvlabel">Markers <span class="bk-meta">· which of them moved your score</span></div>
      ${marked ? '' : '<p class="bk-meta">Screening has not marked this book: add the markers it has, or the review cannot teach the estimate.</p>'}
      <ul class="rvmarks">${rvMarkerRows()}</ul>
      <div class="rvadd">
        <select id="rvaddid" aria-label="Marker to add">${rvAddOptions()}</select>
        <select id="rvadds" aria-label="Strength"><option value="1">1 · minor</option><option value="2" selected>2 · clear</option><option value="3">3 · central</option></select>
        <button type="button" class="rvbtn" data-rv-add>Add</button>
      </div>
      <p class="bk-meta rvuse" id="rvuse"></p>
      ${token}
    </div>
    <div class="rvfoot">
      <span class="rvmsg${RV.err ? ' err' : ''}" role="status">${esc(RV.msg)}</span>
      ${RV.editing ? `<button type="button" class="rvbtn" data-rv-delete${RV.busy ? ' disabled' : ''}>Delete review</button>` : ''}
      <button type="button" class="rvbtn primary" data-rv-save${RV.busy ? ' disabled' : ''}>Save</button>
    </div></div>`;
  el.hidden = false;
  document.body.classList.add('rv-open');
}

function rvSay(msg, err = false) {
  RV.msg = msg;
  RV.err = err;
  rvRender();
}

function rvEntry() {
  const side = s => Object.keys(RV.ticks).filter(t => RV.ticks[t] === s).sort();
  return { score: RV.score, notes: RV.notes.trim(), at: rvToday(), helped: side('helped'), hurt: side('hurt'),
           removed: side('removed'), added: Object.fromEntries(Object.entries(RV.added).sort()) };
}

const rvDecode = b64 => new TextDecoder().decode(Uint8Array.from(atob(b64.replace(/\s/g, '')), c => c.charCodeAt(0)));
function rvEncode(text) {
  const bytes = new TextEncoder().encode(text);
  let s = '';
  for (let i = 0; i < bytes.length; i += 0x8000) s += String.fromCharCode(...bytes.subarray(i, i + 0x8000));
  return btoa(s);
}

function rvRefusal(status) {
  if (status === 401) return 'GitHub refused the token (401): it is mistyped, expired or revoked.';
  if (status === 403 || status === 404) return `The token cannot write to ${RV_REPO} (${status}): it needs Contents read and write on that repository.`;
  return `GitHub answered ${status}; nothing was saved.`;
}

// Read-modify-write of the whole file: a 409 means another save landed between the read and the
// write, so the read is repeated rather than overwriting that save.
async function rvCommit(token, id, entry, message) {
  const url = `https://api.github.com/repos/${RV_REPO}/contents/${RV_PATH}`;
  const headers = { Authorization: 'Bearer ' + token, Accept: 'application/vnd.github+json', 'X-GitHub-Api-Version': '2022-11-28' };
  for (let attempt = 0; attempt < 3; attempt++) {
    const got = await fetch(`${url}?ref=${RV_BRANCH}&t=${Date.now()}`, { headers, cache: 'no-store' });
    if (!got.ok && got.status !== 404) throw new Error(rvRefusal(got.status));
    const file = got.ok ? await got.json() : null;
    const doc = file ? JSON.parse(rvDecode(file.content)) : { schema: 1, reviews: {} };
    doc.reviews = doc.reviews || {};
    if (entry) doc.reviews[id] = entry; else delete doc.reviews[id];
    const body = { message, branch: RV_BRANCH, content: rvEncode(JSON.stringify(doc, null, 1) + '\n') };
    if (file) body.sha = file.sha;
    const put = await fetch(url, { method: 'PUT', headers, body: JSON.stringify(body) });
    if (put.ok) return;
    if (put.status !== 409) throw new Error(rvRefusal(put.status));
  }
  throw new Error('Other saves kept landing first; nothing was saved. Try again.');
}

async function rvSave(remove) {
  if (!remove && RV.score === undefined) return rvSay('Pick a score, or Not finished.', true);
  const token = recall(RV_TOKEN) || RV.token.trim();
  if (!token) return rvSay('Paste a GitHub token to save.', true);
  const at = RV, entry = remove ? null : rvEntry(), title = at.b.cache.czTitle || at.b.cache.title || at.b.key;
  at.busy = true;
  rvSay(remove ? 'Deleting…' : 'Saving…');
  try {
    await rvCommit(token, at.id, entry, `${remove ? 'Review deleted' : 'Review'}: ${title}`);
  } catch (e) {
    if (/\(401\)/.test(e.message)) store(RV_TOKEN, '');
    at.busy = false;
    if (RV === at) rvSay(e instanceof TypeError ? 'Could not reach GitHub; nothing was saved.' : e.message, true);
    return;
  }
  store(RV_TOKEN, token);
  store(RV_PENDING, JSON.stringify({ ...rvPending(), [at.id]: { e: entry, t: Date.now() } }));
  const reviews = D.taste.model.reviews;
  if (entry) reviews[at.id] = entry; else delete reviews[at.id];
  tasteRefresh();
  rvClose();
  render();
  rvToast(remove ? `Deleted the review of ${title}.`
    : `Saved ${title}: it is on the Read tab now, and on the published site in a few minutes.`);
}

function rvToast(text) {
  let el = F('rvtoast');
  if (!el) {
    document.body.insertAdjacentHTML('beforeend', '<div class="rvtoast" id="rvtoast" role="status" hidden></div>');
    el = F('rvtoast');
  }
  el.textContent = text;
  el.hidden = false;
  clearTimeout(rvToast.timer);
  rvToast.timer = setTimeout(() => { el.hidden = true; }, 6000);
}

document.addEventListener('click', e => {
  const open = e.target.closest('[data-review]');
  // Keyboard focus can still reach the cards behind an open sheet.
  if (open) { if (!RV) rvOpen(open.dataset.review); return; }
  if (!RV) return;
  const sheet = F('reviewsheet');
  if (e.target === sheet || e.target.closest('[data-rv-close]')) { if (!RV.busy) rvClose(); return; }
  if (RV.busy) return;
  const score = e.target.closest('[data-rv-score]');
  if (score) { RV.score = score.dataset.rvScore || null; RV.msg = ''; rvRender(); return; }
  const tick = e.target.closest('[data-rv-tick]');
  if (tick) {
    const [t, side] = tick.dataset.rvTick.split('|');
    if (side) RV.ticks[t] = side; else delete RV.ticks[t];
    rvRender();
    return;
  }
  const drop = e.target.closest('[data-rv-drop]');
  if (drop) { delete RV.added[drop.dataset.rvDrop]; delete RV.ticks[drop.dataset.rvDrop]; rvRender(); return; }
  if (e.target.closest('[data-rv-add]')) {
    const t = F('rvaddid').value;
    if (t) { RV.added[t] = +F('rvadds').value; rvRender(); }
    return;
  }
  if (e.target.closest('[data-rv-forget]')) { store(RV_TOKEN, ''); rvRender(); return; }
  if (e.target.closest('[data-rv-save]')) rvSave(false);
  else if (e.target.closest('[data-rv-delete]')) rvSave(true);
});

document.addEventListener('input', e => {
  if (!RV) return;
  if (e.target.id === 'rvnotes') RV.notes = e.target.value;
  else if (e.target.id === 'rvtoken') RV.token = e.target.value;
});

document.addEventListener('change', e => {
  if (!RV || e.target.id !== 'rvaddid') return;
  const mk = D.taste.model.byId[e.target.value];
  F('rvuse').textContent = mk ? mk.use || '' : '';
});

document.addEventListener('keydown', e => {
  if (e.key === 'Escape' && RV) { e.stopImmediatePropagation(); if (!RV.busy) rvClose(); }
}, true);
