// The review sheet: the reader scores a book, says which markers moved the score, and the page
// commits the entry to book-reviews.json on main through the GitHub API, then refits in place.
// Runs against the main script's globals; names are rv-prefixed for the shared scope.

const RV_REPO = 'DanielSery/BookShelf', RV_BRANCH = 'main', RV_PATH = 'book-reviews.json';
const RV_TOKEN = 'bookshelf.ghtoken', RV_PENDING = 'bookshelf.rvpending';
// Meanings shortened from _scores in book-reviews.json.
const RV_SCORES = [
  ['endorse', 'Endorse', 'Enjoyed it very much, up to almost a perfect book', 'bS'],
  ['recommend', 'Recommend', 'A nice read, or at least ok to read', 'bA'],
  ['neutral', 'Neutral', 'Not liked much, but not disliked much', 'bB'],
  ['discourage', 'Discourage', 'Did not like it very much', 'bC'],
  ['oppose', 'Oppose', 'Did not like reading it', 'bF'],
  ['', "Didn't finish", 'Put down, never counted as a dislike', 'bN'],
];
const RV_RANK = { endorse: 5, recommend: 4, neutral: 3, discourage: 2, oppose: 1 };
const RV_STRENGTH = ['minor', 'clear', 'central'];
const RV_STEPS = ['Score', 'Markers', 'Notes'];
const RV_PENDING_MS = 3600000;
let RV = null;

const rvCap = w => w[0].toUpperCase() + w.slice(1);
const rvToday = () => new Date().toLocaleDateString('sv');
const rvPending = () => { try { return JSON.parse(recall(RV_PENDING)) || {}; } catch { return {}; } };
const rvWord = score => RV_SCORES.find(s => s[0] === (score || ''));
const rvLogged = v => `${v} / ${+String(v).replace(',', '.') <= 10 ? 10 : 100}`;

const RV_ICON = {
  up: '<svg width="19" height="19" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M7 10v12"/><path d="M15 5.88 14 10h5.83a2 2 0 0 1 1.92 2.56l-2.33 8A2 2 0 0 1 17.5 22H4a2 2 0 0 1-2-2v-8a2 2 0 0 1 2-2h2.76a2 2 0 0 0 1.79-1.11L12 2a3.13 3.13 0 0 1 3 3.88Z"/></svg>',
  down: '<svg width="19" height="19" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M17 14V2"/><path d="M9 18.12 10 14H4.17a2 2 0 0 1-1.92-2.56l2.33-8A2 2 0 0 1 6.5 2H20a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2h-2.76a2 2 0 0 0-1.79 1.11L12 22a3.13 3.13 0 0 1-3-3.88Z"/></svg>',
  x: '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" aria-hidden="true"><path d="M18 6 6 18"/><path d="m6 6 12 12"/></svg>',
  search: '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" aria-hidden="true"><circle cx="11" cy="11" r="7"/><path d="m20 20-3.5-3.5"/></svg>',
};

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

function rvOpen(ref) {
  if (!D.taste) return;
  const id = ref.startsWith('r:') ? ref : 'c:' + ref, rv = D.taste.model.reviews[id] || {}, ticks = {};
  let who;
  if (id.startsWith('r:')) {
    if (!('score' in rv) || rv.withdrawn) return;
    const row = D.read.rows.find(r => r.key === id.slice(2));
    who = { title: rv.title, alt: '', author: rv.author || '', media: row ? row.media : {}, predicted: null };
  } else {
    const b = D.books.find(x => x.key === ref);
    if (!b) return;
    const c = b.cache;
    who = { title: c.czTitle || c.title || b.key, alt: c.czTitle && c.title !== c.czTitle ? c.title : '', author: c.author || '',
            media: b.media, predicted: b.est ? band(b.mid).toLowerCase() : null };
  }
  ['helped', 'hurt', 'removed'].forEach(side => (rv[side] || []).forEach(t => { ticks[t] = side; }));
  const editing = 'score' in rv;
  RV = { id, ...who, editing, score: editing ? rv.score : undefined, was: rv.score, logged: rv.logged, at: rv.at,
         notes: rv.notes || '', ticks, added: { ...(rv.added || {}) }, token: '', busy: false, msg: '', err: false,
         sure: false, step: 1, query: '' };
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

function rvCompare(short) {
  if (RV.score === undefined) return short ? '' : 'Pick a score to go on.';
  const [, , meaning] = rvWord(RV.score);
  const d = RV.score && RV.predicted ? RV_RANK[RV.score] - RV_RANK[RV.predicted] : null;
  const rel = d == null ? '' : d ? `${d > 0 ? 'above' : 'below'} the prediction` : 'same as predicted';
  if (short) return !RV.score ? 'not finished' : rel;
  return meaning + (rel ? ', ' + rel : '') + '.';
}

// rvEntry keeps `logged` and `at` only while the word is the one the review was saved with.
function rvKeepNote() {
  if (!RV.editing || RV.score === RV.was) {
    return RV.logged != null ? `Keeping ${rvWord(RV.was)[1]} keeps the logged ${rvLogged(RV.logged)}. A new word replaces it and dates the review today.` : '';
  }
  return RV.logged != null ? `A new word: the logged ${rvLogged(RV.logged)} is dropped and the review is dated today.`
    : 'A new word dates the review today.';
}

function rvStepSubs() {
  const n = side => Object.values(RV.ticks).filter(v => v === side).length;
  const h = n('helped'), u = n('hurt'), a = Object.keys(RV.added).length;
  return [
    RV.score === undefined ? 'Not picked' : rvWord(RV.score)[1],
    [h && h + ' helped', u && u + ' hurt', a && a + ' added'].filter(Boolean).join(' · ') || 'None marked',
    RV.notes.trim() ? 'Written' : 'Optional',
  ];
}

function rvScoreStep() {
  const pred = RV.predicted && rvWord(RV.predicted), keep = rvKeepNote();
  const buttons = RV_SCORES.map(([w, label, meaning, tone]) =>
    `<button type="button" class="rvword ${tone}" data-rv-score="${w}" aria-pressed="${RV.score !== undefined && (RV.score || '') === w}">
      <span class="dot" aria-hidden="true"></span><b>${label}</b><span>${meaning}</span></button>`).join('');
  return `<div class="rvh"><h2 id="rvhow">How was it?</h2>${pred
      ? `<span class="rvpred ${pred[3]}"><span class="dot" aria-hidden="true"></span>Predicted <b>${pred[1]}</b></span>` : ''}</div>
    <div class="rvwords" role="group" aria-labelledby="rvhow">${buttons}</div>
    <p class="rvnote">${esc(rvCompare())}</p>
    ${keep ? `<p class="rvkeep${RV.score === RV.was ? '' : ' warn'}">${esc(keep)}</p>` : ''}`;
}

function rvMarkerRows() {
  const { model, fit } = D.taste, m = model.taste[RV.id] || {};
  const ids = [...new Set([...Object.keys(m), ...Object.keys(RV.added)])].filter(t => model.byId[t]);
  const strength = t => Math.max(m[t] || 0, RV.added[t] || 0);
  const effect = t => model.byId[t].kind === 'veto' ? null : ((fit && fit.w[t]) || 0) * tasteValue(model, t, strength(t));
  const rank = t => effect(t) == null ? Infinity : Math.abs(effect(t));
  return ids.sort((a, b) => rank(b) - rank(a)).map(t => {
    const mk = model.byId[t], fx = effect(t), own = t in RV.added && !(t in m), tick = RV.ticks[t] || '';
    const pts = fx == null ? '<span class="v costs">veto</span>'
      : Math.round(fx) ? `<span class="v ${fx < 0 ? 'costs' : 'earns'}">${fx < 0 ? '−' : '+'}${Math.abs(Math.round(fx))}</span>` : '<span class="v">0</span>';
    const meta = [`${strength(t)}/3 · ${RV_STRENGTH[strength(t) - 1]}`, own && 'you added it', tick === 'removed' && 'not in this book'];
    const btn = (side, cls, label, icon) =>
      `<button type="button" class="${cls}" data-rv-tick="${esc(t)}|${side}" aria-pressed="${tick === side}" aria-label="${label}" title="${label}">${icon}</button>`;
    return `<li class="${tick === 'removed' ? 'out' : ''}">${pts}
      <div class="rvmkname"><div>${esc(mk.label)}</div><div class="bk-meta">${meta.filter(Boolean).join(' · ')}</div></div>
      <div class="rvicons" role="group" aria-label="${esc(mk.label)}">${btn('helped', 'up', 'Helped', RV_ICON.up)}${btn('hurt', 'down', 'Hurt', RV_ICON.down)}${
        own ? `<button type="button" class="out" data-rv-drop="${esc(t)}" aria-label="Remove" title="Remove">${RV_ICON.x}</button>`
          : btn('removed', 'out', 'Not in this book', RV_ICON.x)}</div></li>`;
  }).join('');
}

function rvSuggestions() {
  const q = RV.query.trim().toLowerCase();
  if (!q) return '';
  const { model, fit } = D.taste, have = { ...(model.taste[RV.id] || {}), ...RV.added };
  const named = mk => mk.label.toLowerCase().includes(q) || mk.id.includes(q);
  const hits = model.markers.filter(mk => !(mk.id in have) && (named(mk) || (mk.use || '').toLowerCase().includes(q)))
    .sort((a, b) => named(b) - named(a) || a.label.localeCompare(b.label)).slice(0, 6);
  if (!hits.length) return `<p class="bk-meta">No marker matches “${esc(RV.query.trim())}”.</p>`;
  const note = mk => {
    if (mk.kind === 'veto') return '<span class="costs">Veto: blocks books that have it</span>';
    const w = Math.round(((fit && fit.w[mk.id]) || 0) * tasteValue(model, mk.id, 3));
    return w ? `${w > 0 ? 'Adds up to +' : 'Costs up to −'}${Math.abs(w)}` : 'No effect in your reviews yet';
  };
  return `<ul class="rvsugg">${hits.map(mk => `<li title="${esc(mk.use || '')}"><div class="rvmkname"><div>${esc(mk.label)}</div>
      <div class="bk-meta">${note(mk)}</div></div>
      <div class="wseg" role="group" aria-label="${esc('Add ' + mk.label + ' at strength')}">${[1, 2, 3].map(s =>
        `<button type="button" data-rv-add="${esc(mk.id)}|${s}" aria-label="Add as ${RV_STRENGTH[s - 1]}">${s}</button>`).join('')}</div></li>`).join('')}</ul>
    <p class="bk-meta">1 minor · 2 clear · 3 central to the book</p>`;
}

function rvMarkerStep() {
  const marked = !!D.taste.model.taste[RV.id];
  return `<div class="rvh"><h2>What moved your score?</h2></div>
    <p class="rvnote">Points are what each marker adds to the prediction. Mark the ones that helped or hurt; leave the rest.</p>
    ${marked ? '' : '<p class="rvnote">Screening has not marked this book: add the markers it has, or the review cannot teach the estimate.</p>'}
    <ul class="rvmarks">${rvMarkerRows()}</ul>
    <label class="rvsub" for="rvq">Add a marker the book has</label>
    <div class="rvsearch">${RV_ICON.search}<input id="rvq" type="search" autocomplete="off" spellcheck="false"
      placeholder="Search markers, e.g. lead or opening" value="${esc(RV.query)}"></div>
    <div id="rvsugg">${rvSuggestions()}</div>`;
}

function rvSummary() {
  const { byId } = D.taste.model, side = s => Object.keys(RV.ticks).filter(t => RV.ticks[t] === s && byId[t]).map(t => byId[t].label);
  const word = RV.score === undefined ? null : rvWord(RV.score), rel = rvCompare(true);
  const rows = [['Helped', side('helped').join(', ')], ['Hurt', side('hurt').join(', ')],
    ['Added', Object.entries(RV.added).filter(([t]) => byId[t]).map(([t, s]) => `${byId[t].label} ${s}/3`).join(', ')],
    ['Not in it', side('removed').join(', ')]].filter(([, v]) => v);
  return `<div class="rvsum"><div class="${word ? word[3] : 'bN'}"><span class="dot" aria-hidden="true"></span>
      <b>${word ? word[1] : 'No score yet'}</b>${rel ? ' · ' + esc(rel) : ''}</div>
    ${rows.map(([k, v]) => `<div><b>${k}</b> ${esc(v)}</div>`).join('')}</div>`;
}

function rvNotesStep() {
  const token = recall(RV_TOKEN)
    ? `<p class="bk-meta">Saves to your log on GitHub with the token in this browser · <button type="button" class="linkish" data-rv-forget>Forget it</button></p>`
    : `<label class="rvsub" for="rvtoken">GitHub token</label>
       <input id="rvtoken" type="password" autocomplete="off" spellcheck="false" placeholder="github_pat_…" value="${esc(RV.token)}">
       <p class="bk-meta">A fine-grained token with Contents read and write on ${RV_REPO} and nothing else: it stays
       in this browser, where every page on ${esc(location.hostname)} can read it.</p>`;
  return `<label class="rvh" for="rvnotes"><h2>Anything to remember?</h2></label>
    <textarea id="rvnotes" rows="6" placeholder="What worked, and what didn't">${esc(RV.notes)}</textarea>
    ${rvSummary()}
    ${token}`;
}

function rvFoot() {
  const off = RV.busy ? ' disabled' : '', last = RV.step === 3;
  const back = RV.step > 1 ? `<button type="button" class="rvbtn rvback" data-rv-back${off}>Back</button>` : '';
  if (!RV.editing) {
    return `${back}<span class="spacer"></span>${last
      ? `<button type="button" class="rvbtn primary" data-rv-save${off}>Save review</button>`
      : `<button type="button" class="rvbtn primary" data-rv-next>Next</button>`}`;
  }
  return `<button type="button" class="rvbtn danger" data-rv-delete${off}>${RV.sure ? 'Delete for good' : 'Delete review'}</button>
    <span class="spacer"></span>${back}${last ? '' : '<button type="button" class="rvbtn" data-rv-next>Next</button>'}
    <button type="button" class="rvbtn primary" data-rv-save${off}>Save changes</button>`;
}

// Keyboard focus and the scroll position survive a re-render; the selector names the control
// by the data attribute it carries.
function rvFocusKey(el) {
  if (!el || !el.attributes) return null;
  if (el.id) return '#' + CSS.escape(el.id);
  const a = [...el.attributes].find(x => x.name.startsWith('data-rv-'));
  return a ? `[${a.name}="${CSS.escape(a.value)}"]` : null;
}

// The header is drawn once per sheet: redrawing it would reload the cover on every tap.
function rvShell() {
  const { title, alt } = RV;
  const chips = RV.id.startsWith('r:')
    ? `<div class="rvchips"><span>Read before the review page</span>${RV.logged != null ? `<span>Logged as ${esc(rvLogged(RV.logged))}</span>` : ''}</div>` : '';
  return `<div class="rvpanel" data-id="${esc(RV.id)}" role="dialog" aria-modal="true" aria-label="${esc('Review: ' + title)}" tabindex="-1">
    <div class="rvgrab" aria-hidden="true"></div>
    <div class="rvhead"><div class="rvthumb">${cover(RV.media || {}, '')}</div>
      <div class="rvwho"><div class="bk-title">${esc(title)}${alt ? ` <span class="bk-alt">(${esc(alt)})</span>` : ''}</div>
        <div class="bk-author">${esc(RV.author)}</div>${chips}</div>
      <button type="button" class="rvclose" data-rv-close aria-label="Close">${RV_ICON.x}</button></div>
    <nav class="rvsteps" aria-label="Steps"></nav><div class="rvbody"></div><div class="rvfoot"></div></div>`;
}

function rvRender() {
  const el = F('reviewsheet');
  if (!el.querySelector(`.rvpanel[data-id="${CSS.escape(RV.id)}"]`)) el.innerHTML = rvShell();
  const body = el.querySelector('.rvbody'), scroll = +body.dataset.step === RV.step ? body.scrollTop : 0;
  const focus = el.contains(document.activeElement) ? rvFocusKey(document.activeElement) : null;
  const subs = rvStepSubs();
  el.querySelector('.rvsteps').innerHTML = RV_STEPS.map((label, i) =>
    `<button type="button" data-rv-step="${i + 1}"${i + 1 === RV.step ? ' aria-current="step"' : ''} class="${i + 1 <= RV.step ? 'done' : ''}">
      <span class="bar" aria-hidden="true"></span><b>${i + 1} ${label}</b><span class="sub" id="rvsub${i + 1}">${esc(subs[i])}</span></button>`).join('');
  body.dataset.step = RV.step;
  body.innerHTML = [rvScoreStep, rvMarkerStep, rvNotesStep][RV.step - 1]();
  el.querySelector('.rvfoot').innerHTML = (RV.msg ? `<p class="rvmsg${RV.err ? ' err' : ''}" role="status">${esc(RV.msg)}</p>` : '') + rvFoot();
  body.scrollTop = scroll;
  const back = focus && el.querySelector(focus);
  if (back) back.focus({ preventScroll: true });
  el.hidden = false;
  document.body.classList.add('rv-open');
}

function rvSay(msg, err = false) {
  RV.msg = msg;
  RV.err = err;
  rvRender();
}

function rvGo(step) {
  Object.assign(RV, { step, msg: '', err: false, sure: false });
  rvRender();
  F('reviewsheet').querySelector('.rvpanel').focus({ preventScroll: true });
}

// Updates the sheet in place: a full render would take the caret out of the notes.
function rvDisarm() {
  if (!RV.sure) return;
  Object.assign(RV, { sure: false, msg: '', err: false });
  const sheet = F('reviewsheet'), msg = sheet.querySelector('.rvmsg');
  sheet.querySelector('[data-rv-delete]').textContent = 'Delete review';
  if (msg) msg.remove();
}

function rvEntry() {
  const side = s => Object.keys(RV.ticks).filter(t => RV.ticks[t] === s).sort();
  // An unchanged word keeps the number an old read was logged with, and the day it was given.
  const same = RV.score === RV.was, logged = same && RV.logged != null ? { logged: RV.logged } : {};
  const at = same ? RV.at : rvToday();
  return { title: RV.title, author: RV.author, score: RV.score, ...logged, notes: RV.notes.trim(), ...(at ? { at } : {}),
           helped: side('helped'), hurt: side('hurt'), removed: side('removed'),
           added: Object.fromEntries(Object.entries(RV.added).sort()) };
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
  if (!remove && RV.score === undefined) { RV.step = 1; return rvSay("Pick a score, or Didn't finish.", true); }
  const token = recall(RV_TOKEN) || RV.token.trim();
  if (!token) { RV.step = 3; return rvSay('Paste a GitHub token below to save.', true); }
  const at = RV, entry = remove ? null : rvEntry(), title = at.title;
  at.busy = true;
  rvSay(remove ? 'Deleting…' : 'Saving…');
  try {
    await rvCommit(token, at.id, entry, `${remove ? 'Review deleted' : 'Review'}: ${title}`);
  } catch (e) {
    const refused = /\(401\)/.test(e.message);
    if (refused) store(RV_TOKEN, '');
    at.busy = false;
    if (RV === at) {
      if (refused) RV.step = 3;
      rvSay(e instanceof TypeError ? 'Could not reach GitHub; nothing was saved.' : e.message, true);
    }
    return;
  }
  store(RV_TOKEN, token);
  store(RV_PENDING, JSON.stringify({ ...rvPending(), [at.id]: { e: entry, t: Date.now() } }));
  const reviews = D.taste.model.reviews;
  if (entry) reviews[at.id] = entry; else delete reviews[at.id];
  if (at.id.startsWith('r:')) readSync(at.id, entry);
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
  if (e.target.closest('[data-rv-score], [data-rv-tick], [data-rv-drop], [data-rv-add]')) rvDisarm();
  const step = e.target.closest('[data-rv-step]');
  if (step) { rvGo(+step.dataset.rvStep); return; }
  if (e.target.closest('[data-rv-back]')) { rvGo(RV.step - 1); return; }
  if (e.target.closest('[data-rv-next]')) {
    if (RV.step === 1 && RV.score === undefined) rvSay("Pick a score, or Didn't finish.", true);
    else rvGo(RV.step + 1);
    return;
  }
  const score = e.target.closest('[data-rv-score]');
  if (score) { RV.score = score.dataset.rvScore || null; RV.msg = ''; rvRender(); return; }
  const tick = e.target.closest('[data-rv-tick]');
  if (tick) {
    const [t, side] = tick.dataset.rvTick.split('|');
    if (RV.ticks[t] === side) delete RV.ticks[t]; else RV.ticks[t] = side;
    rvRender();
    return;
  }
  const drop = e.target.closest('[data-rv-drop]');
  if (drop) { delete RV.added[drop.dataset.rvDrop]; delete RV.ticks[drop.dataset.rvDrop]; rvRender(); return; }
  const add = e.target.closest('[data-rv-add]');
  if (add) {
    const [t, s] = add.dataset.rvAdd.split('|');
    RV.added[t] = +s;
    RV.query = '';
    rvRender();
    F('rvq').focus({ preventScroll: true });
    return;
  }
  if (e.target.closest('[data-rv-forget]')) { store(RV_TOKEN, ''); rvRender(); return; }
  if (e.target.closest('[data-rv-save]')) rvSave(false);
  else if (e.target.closest('[data-rv-delete]')) {
    // An old read's notes exist nowhere else.
    if (RV.id.startsWith('r:') && !RV.sure) {
      RV.sure = true;
      rvSay('Deleting removes this book and its notes from your log. Press Delete for good to confirm.', true);
    } else rvSave(true);
  }
});

document.addEventListener('input', e => {
  if (!RV) return;
  if (e.target.id === 'rvnotes') {
    RV.notes = e.target.value;
    F('rvsub3').textContent = rvStepSubs()[2];
    rvDisarm();
  } else if (e.target.id === 'rvtoken') RV.token = e.target.value;
  else if (e.target.id === 'rvq') { RV.query = e.target.value; F('rvsugg').innerHTML = rvSuggestions(); }
});

document.addEventListener('keydown', e => {
  if (e.key === 'Escape' && RV) { e.stopImmediatePropagation(); if (!RV.busy) rvClose(); }
}, true);
