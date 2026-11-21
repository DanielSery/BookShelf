// The no-agent estimate: a baseline plus each taste marker's effect, fitted from the read books'
// scores and pulled toward the rulebook priors in book-markers.json. A port of solve() in
// tools/taste.py; the constants below must match its chosen settings. Loaded before the main
// script and run against its globals (jsonl); names are taste-prefixed because every top-level
// declaration shares one scope with index.html.

const TASTE_LAM = 10, TASTE_LAM_TAGS = 50, TASTE_RELAX = 1;
const TASTE_SHAPE = [0.33, 0.67, 1];

function tasteModel(markersDoc, tasteText, reviewsDoc, profilesText) {
  const markers = markersDoc.markers || [];
  return {
    markers,
    byId: Object.fromEntries(markers.map(m => [m.id, m])),
    taste: Object.fromEntries(jsonl(tasteText).slice(1).filter(t => t.id).map(t => [t.id, t.m || {}])),
    tags: Object.fromEntries(jsonl(profilesText).slice(1).filter(p => p.id).map(p => [p.id, p.tags || {}])),
    reviews: reviewsDoc.reviews || {},
  };
}

// What training sees: screening's markers, corrected by the reader's review.
function tasteSeen(model, id) {
  const rv = model.reviews[id] || {}, m = { ...(model.taste[id] || {}) };
  Object.entries(rv.added || {}).forEach(([t, s]) => { m[t] = Math.max(s, m[t] || 0); });
  (rv.removed || []).forEach(t => { delete m[t]; });
  return m;
}

const tasteMarked = (model, id) => !!model.taste[id] || Object.keys((model.reviews[id] || {}).added || {}).length > 0;

const tasteVeto = (model, m) => Object.keys(m).find(t => (model.byId[t] || {}).kind === 'veto') || null;
const tasteValue = (model, t, s) => (model.byId[t].shape || TASTE_SHAPE)[s - 1];

function tasteSolve(M, v) {
  const n = v.length;
  for (let c = 0; c < n; c++) {
    let p = c;
    for (let r = c + 1; r < n; r++) if (Math.abs(M[r][c]) > Math.abs(M[p][c])) p = r;
    [M[c], M[p]] = [M[p], M[c]];
    [v[c], v[p]] = [v[p], v[c]];
    for (let r = c + 1; r < n; r++) {
      const f = M[r][c] / M[c][c];
      if (!f) continue;
      for (let k = c; k < n; k++) M[r][k] -= f * M[c][k];
      v[r] -= f * v[c];
    }
  }
  const x = new Float64Array(n);
  for (let r = n - 1; r >= 0; r--) {
    let s = v[r];
    for (let k = r + 1; k < n; k++) s -= M[r][k] * x[k];
    x[r] = s / M[r][r];
  }
  return x;
}

// scored: [{id, score}] for the books the reader has scored. A book his review vetoes is left out:
// its score is the veto's doing, and no weight should learn from it. null when no book is left,
// since the baseline is then unknown.
function tasteFit(model, scored) {
  const graded = model.markers.filter(m => m.kind === 'graded');
  const rows = scored.filter(r => r.score != null && tasteMarked(model, r.id))
    .map(r => ({ ...r, m: tasteSeen(model, r.id), t: model.tags[r.id] || {} }))
    .filter(r => !tasteVeto(model, r.m));
  if (!rows.length) return null;
  const tagIds = [...new Set(rows.flatMap(r => Object.keys(r.t)))].sort();
  const cols = [...graded.map(m => m.id), ...tagIds.map(t => 'tag:' + t)];
  const P = cols.length + 1;
  const prior = [0, ...graded.map(m => m.prior), ...tagIds.map(() => 0)];
  const ticked = new Array(P).fill(0);
  rows.forEach(r => {
    const rv = model.reviews[r.id] || {};
    new Set([...(rv.helped || []), ...(rv.hurt || [])]).forEach(t => {
      const c = cols.indexOf(t);
      if (c >= 0) ticked[c + 1]++;
    });
  });
  const lam = [0, ...graded.map(() => TASTE_LAM), ...tagIds.map(() => TASTE_LAM_TAGS)]
    .map((l, i) => l / (1 + TASTE_RELAX * ticked[i]));
  const row = r => [1, ...graded.map(m => r.m[m.id] ? tasteValue(model, m.id, r.m[m.id]) : 0),
                    ...tagIds.map(t => (r.t[t] || 0) / 3)];
  const A = rows.map(row);
  const AtA = Array.from({ length: P }, (_, i) => Float64Array.from({ length: P }, (_, j) =>
    A.reduce((s, a) => s + a[i] * a[j], 0)));
  const Aty = Float64Array.from({ length: P }, (_, i) => A.reduce((s, a, k) => s + a[i] * rows[k].score, 0));

  // Each weight stays on its prior's side of zero: a weight that crosses is pinned at 0 and the
  // rest refitted, so a marker the rulebook calls a plus can fade but never turn into a minus.
  const lock = prior.map(Math.sign);
  const pinned = new Array(P).fill(false);
  let theta = null;
  for (let it = 0; it < P; it++) {
    const M = AtA.map((r, i) => { const c = Float64Array.from(r); c[i] += pinned[i] ? 1e9 : lam[i]; return c; });
    const v = Float64Array.from(Aty, (x, i) => x + (pinned[i] ? 0 : lam[i] * prior[i]));
    theta = tasteSolve(M, v);
    let more = false;
    for (let i = 0; i < P; i++) if (!pinned[i] && lock[i] * theta[i] < 0) { pinned[i] = more = true; }
    if (!more) break;
  }
  const w = {}, wt = {};
  cols.forEach((c, i) => { if (c.startsWith('tag:')) wt[c.slice(4)] = theta[i + 1]; else w[c] = theta[i + 1]; });
  return { base: theta[0], w, wt, n: rows.length, ticked: Object.fromEntries(cols.map((c, i) => [c, ticked[i + 1]])) };
}

// null when screening has not marked the book, or marked nothing because it did not know it:
// an empty set is no evidence, and would otherwise come out at the baseline as a confident average.
function tasteEstimate(model, fit, id) {
  const m = model.taste[id];
  if (!m || !Object.keys(m).length) return null;
  const veto = tasteVeto(model, m);
  if (veto) return { veto };
  const all = Object.entries(m).filter(([t]) => fit.w[t] != null)
    .map(([t, s]) => ({ id: t, label: model.byId[t].label, s, points: fit.w[t] * tasteValue(model, t, s) }));
  const parts = all.filter(p => Math.abs(p.points) >= 0.5).sort((a, b) => Math.abs(b.points) - Math.abs(a.points));
  const tagPoints = Object.entries(model.tags[id] || {})
    .reduce((s, [t, x]) => s + (fit.wt[t] || 0) * x / 3, 0);
  const raw = fit.base + all.reduce((s, p) => s + p.points, 0) + tagPoints;
  return { points: Math.max(0, Math.min(100, Math.round(raw))), parts, tagPoints, base: fit.base };
}
