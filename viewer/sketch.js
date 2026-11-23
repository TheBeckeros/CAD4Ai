// Sketch pad: an infinite canvas with pressure-sensitive ink (Pointer Events: Apple Pencil draws, fingers pan / zoom),
// highlighter, stroke eraser, lasso, text, images, shapes, and the Snap tool (the AI redraws one boxed region, you accept
// or reject). Items sync through /api/sketch (long-poll + per-item ops). Geometry lives in ink.js (global Ink).
/* global Ink */
const $ = id => document.getElementById(id);
const cvB = $('base'), cvT = $('top'), bctx = cvB.getContext('2d'), tctx = cvT.getContext('2d');
const FONT = 'ui-sans-serif, system-ui, -apple-system, "Segoe UI", sans-serif';
const SIZES = { pen: [1.5, 3, 6], hl: [12, 20, 32], eraser: [10, 20, 40], text: [14, 20, 32], shape: [1.5, 3, 6] }; // screen px
const COLORS = ['ink', '#e5484d', '#3e8ed0', '#30a46c', '#f08c00', '#8e4ec6'];
const HL = ['#ffd60a', '#7cd992', '#ff8fb1', '#7fc8ff'];
const HINTS = {
  pen: 'Pencil or mouse draws · fingers pan, pinch zooms', hl: 'Marker draws under the ink', eraser: 'Touch strokes to remove them',
  lasso: 'Circle items to select · drag inside to move · Delete removes', text: 'Tap to type · tap a text to edit it',
  shape: 'Drag to draw', snap: 'Drag a box around what should change · nothing outside it is touched',
};
const r2 = v => Math.round(v * 100) / 100;
const clamp = (v, a, b) => Math.max(a, Math.min(b, v));
const sleep = ms => new Promise(ok => setTimeout(ok, ms));

// ---------------------------------------------------------------- prefs
const S = { tool: 'pen', color: { pen: 'ink', hl: HL[0], text: 'ink', shape: 'ink' }, size: { pen: 1, hl: 1, eraser: 1, text: 1, shape: 1 }, shape: 'rect', bg: 'dots', theme: 'auto', finger: false, view: null };
try { const p = JSON.parse(localStorage.getItem('cad-sketch') || '{}'); for (const k in S) if (k in p) S[k] = typeof S[k] === 'object' && S[k] && p[k] ? { ...S[k], ...p[k] } : p[k]; } catch { /* private mode */ }
let view = S.view && S.view.z > 0 ? { ...S.view } : { x: -60, y: -60, z: 1 };
let saveT = 0;
const savePrefs = () => { clearTimeout(saveT); saveT = setTimeout(() => { try { localStorage.setItem('cad-sketch', JSON.stringify({ ...S, view })); } catch { /* ignore */ } }, 300); };

// ---------------------------------------------------------------- document + sync
const items = {}, snaps = {};
let rev = 0, api = false, loaded = false;
const me = Math.random().toString(36).slice(2, 8);
let seq = 0;
const newId = () => `${me}${Date.now().toString(36)}${(seq++).toString(36)}`;
const nextZ = () => Date.now() + (seq++ % 1000) / 1000;
const undos = [], redos = [], outbox = [];
const hidden = new Set(), sel = new Set();

async function call(url, body) {
  const r = await fetch(url, body === undefined ? {} : { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
  const j = await r.json().catch(() => ({}));
  if (!r.ok) throw Object.assign(new Error(j.error || `HTTP ${r.status}`), { status: r.status });
  return j;
}
function apply({ put = [], del = [] }) {
  for (const id of del) { delete items[id]; sel.delete(id); }
  for (const it of put) items[it.id] = it;
  dirty();
}
function commit(put, del, undo, snapsUp) {
  const op = { put, del };
  apply(op);
  undos.push({ op, undo });
  if (undos.length > 300) undos.shift();
  redos.length = 0;
  send({ ...op, snaps: snapsUp });
}
function undo() { const u = undos.pop(); if (u) { apply(u.undo); redos.push(u); send(u.undo); } }
function redo() { const u = redos.pop(); if (u) { apply(u.op); undos.push(u); send(u.op); } }
function send(op) {
  if (!op.put?.length && !op.del?.length && !op.snaps?.length) return;
  outbox.push(op);
  flush();
}
let flushing = false;
async function flush() {
  if (flushing) return;
  flushing = true;
  while (outbox.length) {
    try { await call('/api/sketch/ops', { ...outbox[0], by: me }); outbox.shift(); setSync(true); }
    catch (e) {
      if (e.status === 400) { outbox.shift(); toast(`Not saved: ${e.message}`, true); continue; }
      setSync(false); await sleep(2000);
    }
  }
  flushing = false;
}
async function poll() {
  for (;;) {
    try {
      const since = rev, r = await call(`/api/sketch?since=${since}&wait=${since ? 25 : 0}`);
      if (r.rev < since) { for (const k in items) delete items[k]; for (const k in snaps) delete snaps[k]; rev = 0; continue; } // server was reset
      for (const it of r.items) {
        if (since && it.by === me) continue; // our own change coming back; local state is newer or equal
        if (it.deleted) { delete items[it.id]; sel.delete(it.id); } else items[it.id] = it;
      }
      for (const s of r.snaps) snaps[s.id] = s;
      rev = r.rev; api = r.api; setSync(true);
      if (!loaded) { loaded = true; if (!S.view) fit(); }
      dirty(); renderSnaps();
    } catch { setSync(false); await sleep(3000); }
  }
}
function setSync(ok) { const el = $('sync'); el.textContent = ok ? (outbox.length ? 'saving…' : 'synced') : 'offline, retrying…'; el.className = ok ? '' : 'off'; }

// ---------------------------------------------------------------- view + theme
let dpr = 1, W = 0, H = 0, needB = true, needT = true, theme = {};
const dirty = (b = true) => { if (b) needB = true; needT = true; };
const toWorld = (sx, sy) => [sx / view.z + view.x, sy / view.z + view.y];
const toScreen = (x, y) => [(x - view.x) * view.z, (y - view.y) * view.z];
const viewRect = () => [view.x, view.y, W / view.z, H / view.z];
function resize() {
  const r = $('wrap').getBoundingClientRect();
  dpr = window.devicePixelRatio || 1; W = r.width; H = r.height;
  for (const c of [cvB, cvT]) { c.width = Math.max(1, Math.round(W * dpr)); c.height = Math.max(1, Math.round(H * dpr)); }
  dirty();
}
new ResizeObserver(resize).observe($('wrap'));
function readTheme() {
  if (S.theme === 'auto') delete document.documentElement.dataset.theme; else document.documentElement.dataset.theme = S.theme;
  const cs = getComputedStyle(document.documentElement), v = n => cs.getPropertyValue(n).trim();
  theme = { ink: v('--text'), paper: v('--bg'), grid: v('--line'), grid2: v('--line2'), accent: v('--accent'), bad: v('--bad'), faint: v('--faint') };
  dirty();
}
matchMedia('(prefers-color-scheme: light)').addEventListener('change', readTheme);
function zoomAt(sx, sy, f) {
  const z = clamp(view.z * f, 0.05, 20), w = toWorld(sx, sy);
  view = { z, x: w[0] - sx / z, y: w[1] - sy / z };
  viewChanged();
}
function viewChanged() { $('zoom').textContent = `${Math.round(view.z * 100)} %`; savePrefs(); dirty(); }
function fit() {
  const b = Ink.union(Object.values(items).map(bounds));
  if (!b) view = { x: -W / 2, y: -H / 2, z: 1 };
  else { const z = clamp(Math.min(W / (b[2] + 80), H / (b[3] + 80)), 0.05, 4); view = { z, x: b[0] + b[2] / 2 - W / 2 / z, y: b[1] + b[3] / 2 - H / 2 / z }; }
  viewChanged();
}

// ---------------------------------------------------------------- drawing
const pathCache = new WeakMap(), boundCache = new WeakMap(), imgCache = new Map(), ghostCache = new WeakMap();
function bounds(it) { let b = boundCache.get(it); if (!b) { b = Ink.bounds(it); boundCache.set(it, b); } return b; }
function polyPath(p, poly) { // points are dense and already smoothed on input, so straight edges look smooth
  p.moveTo(poly[0][0], poly[0][1]);
  for (let i = 1; i < poly.length; i++) p.lineTo(poly[i][0], poly[i][1]);
  p.closePath();
}
function strokePath(it, cache = true) {
  let p = cache && pathCache.get(it);
  if (p) return p;
  p = new Path2D();
  const pr = it.tool !== 'hl', poly = Ink.outline(it.pts, it.w, pr);
  if (poly) polyPath(p, poly);
  else { const q = it.pts[0]; p.arc(q[0], q[1], Ink.radius(it.w, q[2], pr), 0, Math.PI * 2); }
  if (cache) pathCache.set(it, p);
  return p;
}
function image(src) {
  let im = imgCache.get(src);
  if (!im) { im = new Image(); im.onload = () => dirty(); im.src = src; imgCache.set(src, im); }
  return im;
}
function drawItem(c, it, ink, cache = true) {
  const col = !it.color || it.color === 'ink' ? ink : it.color;
  if (it.t === 'stroke') {
    c.fillStyle = col;
    c.globalAlpha = it.tool === 'hl' ? 0.38 : 1;
    c.fill(strokePath(it, cache));
    c.globalAlpha = 1;
  } else if (it.t === 'text') {
    c.fillStyle = col; c.font = `${it.size}px ${FONT}`; c.textBaseline = 'top';
    String(it.s).split('\n').forEach((l, i) => c.fillText(l, it.x, it.y + i * it.size * 1.25));
  } else if (it.t === 'image') {
    const im = image(it.src);
    if (im.complete && im.naturalWidth) c.drawImage(im, it.x, it.y, it.w, it.h);
    else { c.strokeStyle = theme.grid2; c.lineWidth = 1 / view.z; c.strokeRect(it.x, it.y, it.w, it.h); }
  }
}
const rank = it => (it.t === 'image' ? 0 : it.tool === 'hl' ? 1 : 2);
const sorted = () => Object.values(items).sort((a, b) => rank(a) - rank(b) || a.z - b.z);
const worldTf = c => c.setTransform(dpr * view.z, 0, 0, dpr * view.z, -view.x * view.z * dpr, -view.y * view.z * dpr);
function drawGrid(c) {
  if (S.bg === 'none') return;
  let g = 24;
  while (g * view.z < 14) g *= 4;
  const [x, y, w, h] = viewRect(), x0 = Math.floor(x / g) * g, y0 = Math.floor(y / g) * g;
  if (S.bg === 'dots') {
    c.fillStyle = theme.grid2; const d = 1.6 / view.z;
    for (let X = x0; X < x + w; X += g) for (let Y = y0; Y < y + h; Y += g) c.fillRect(X - d / 2, Y - d / 2, d, d);
  } else {
    c.strokeStyle = theme.grid; c.lineWidth = 1 / view.z; c.beginPath();
    for (let X = x0; X < x + w; X += g) { c.moveTo(X, y); c.lineTo(X, y + h); }
    for (let Y = y0; Y < y + h; Y += g) { c.moveTo(x, Y); c.lineTo(x + w, Y); }
    c.stroke();
  }
}
function drawBase() {
  const c = bctx;
  c.setTransform(1, 0, 0, 1, 0, 0); c.fillStyle = theme.paper; c.fillRect(0, 0, cvB.width, cvB.height);
  worldTf(c); drawGrid(c);
  const vr = viewRect(), off = g?.kind === 'movesel' ? g.off : null;
  for (const it of sorted()) {
    if (hidden.has(it.id)) continue;
    const b = bounds(it), moving = off && sel.has(it.id);
    if (!moving && !Ink.overlap(b, vr)) continue;
    if (moving) { c.save(); c.translate(off[0], off[1]); drawItem(c, it, theme.ink); c.restore(); } else drawItem(c, it, theme.ink);
  }
  $('count').textContent = `${Object.keys(items).length} items`;
}
function ghost(s) { let gh = ghostCache.get(s); if (!gh) { gh = Ink.clipProposal(s.proposal, s.rect); ghostCache.set(s, gh); } return gh; }
function drawTop() {
  const c = tctx, z = view.z;
  c.setTransform(1, 0, 0, 1, 0, 0); c.clearRect(0, 0, cvT.width, cvT.height); worldTf(c);
  for (const s of Object.values(snaps)) {
    if (!['pending', 'proposed', 'error'].includes(s.status)) continue;
    const [x, y, w, h] = s.rect;
    if (s.status === 'proposed' && !peek.has(s.id)) {
      c.save(); c.beginPath(); c.rect(x, y, w, h); c.clip();
      c.globalAlpha = 0.86; c.fillStyle = theme.paper; c.fillRect(x, y, w, h); c.globalAlpha = 1;
      for (const it of ghost(s)) drawItem(c, it, theme.ink);
      c.restore();
    }
    c.setLineDash([6 / z, 4 / z]); c.lineWidth = 1.5 / z; c.strokeStyle = s.status === 'error' ? theme.bad : theme.accent; c.strokeRect(x, y, w, h); c.setLineDash([]);
  }
  if (!g) { if (S.tool === 'eraser' && hover) ring(c, hover, SIZES.eraser[S.size.eraser] / 2 / z); }
  else if (g.kind === 'draw') drawItem(c, { t: 'stroke', tool: g.tool, color: g.color, w: g.w, pts: g.pts.concat(g.pred || []) }, theme.ink, false);
  else if (g.kind === 'erase' && hover) ring(c, hover, SIZES.eraser[S.size.eraser] / 2 / z);
  else if (g.kind === 'lasso') { c.setLineDash([5 / z, 4 / z]); c.lineWidth = 1.2 / z; c.strokeStyle = theme.accent; c.beginPath(); g.poly.forEach((p, i) => (i ? c.lineTo(p[0], p[1]) : c.moveTo(p[0], p[1]))); c.stroke(); c.setLineDash([]); }
  else if (g.kind === 'shape' && g.moved) drawItem(c, { t: 'stroke', tool: 'pen', color: S.color.shape, w: SIZES.shape[S.size.shape] / z, pts: Ink.shapePts(S.shape, g.a, g.b) }, theme.ink, false);
  else if (g.kind === 'snap') { const r = rectOf(g.a, g.b); c.fillStyle = theme.accent; c.globalAlpha = 0.08; c.fillRect(...r); c.globalAlpha = 1; c.setLineDash([6 / z, 4 / z]); c.lineWidth = 1.5 / z; c.strokeStyle = theme.accent; c.strokeRect(...r); c.setLineDash([]); }
  const sb = selBounds();
  if (sb) { const o = g?.kind === 'movesel' ? g.off : [0, 0]; c.setLineDash([4 / z, 3 / z]); c.lineWidth = 1 / z; c.strokeStyle = theme.accent; c.strokeRect(sb[0] + o[0] - 4 / z, sb[1] + o[1] - 4 / z, sb[2] + 8 / z, sb[3] + 8 / z); c.setLineDash([]); }
  if (editing) placeEditor();
  placeSnaps();
}
function ring(c, p, r) { c.lineWidth = 1 / view.z; c.strokeStyle = theme.faint || theme.grid2; c.beginPath(); c.arc(p[0], p[1], r, 0, Math.PI * 2); c.stroke(); }
const rectOf = (a, b) => [Math.min(a[0], b[0]), Math.min(a[1], b[1]), Math.abs(b[0] - a[0]), Math.abs(b[1] - a[1])];
function selBounds() { const its = [...sel].map(id => items[id]).filter(Boolean); return its.length ? Ink.union(its.map(bounds)) : null; }
function frame() {
  if (needB) { needB = false; drawBase(); }
  if (needT) { needT = false; drawTop(); }
  requestAnimationFrame(frame);
}

// ---------------------------------------------------------------- input (Pointer Events)
let g = null, hover = null, penDown = false, penAt = 0, penSeen = false, spaceDown = false;
const ptrs = new Map();
const pos = e => { const r = cvT.getBoundingClientRect(); return [e.clientX - r.left, e.clientY - r.top]; };
const samples = e => (e.getCoalescedEvents ? e.getCoalescedEvents() : null)?.length ? e.getCoalescedEvents() : [e];
const capture = e => { try { cvT.setPointerCapture(e.pointerId); } catch { /* pointer already gone */ } };
const pressure = (e, pen) => (pen ? clamp(e.pressure || 0.5, 0.05, 1) : 0.5);

cvT.addEventListener('pointerdown', e => {
  const sp = pos(e);
  if (e.pointerType === 'touch') {
    // palm rejection: no touches while the Pencil is down or was just used, and no palm-sized contacts
    if (penDown || performance.now() - penAt < 500 || (e.width > 60 && e.height > 60)) return;
    capture(e);
    ptrs.set(e.pointerId, sp);
    if (ptrs.size === 2) { abort(); startPinch(); } else if (ptrs.size === 1) { if (S.finger && !penSeen) begin(e, sp, true); else startPan(sp, e.pointerId); }
    return;
  }
  if (e.pointerType === 'pen') { penDown = true; penSeen = true; penAt = performance.now(); if (g && (g.touch || g.finger)) abort(); ptrs.clear(); }
  capture(e);
  if (e.pointerType === 'mouse' && (e.button === 1 || e.button === 2 || spaceDown)) { startPan(sp, e.pointerId); return; }
  if (e.button !== 0 && !(e.buttons & 32)) return;
  begin(e, sp, false);
});
cvT.addEventListener('pointermove', e => {
  const sp = pos(e);
  if (e.pointerType === 'touch') {
    if (!ptrs.has(e.pointerId)) return;
    ptrs.set(e.pointerId, sp);
    if (g?.kind === 'pinch') pinchMove(); else if (g?.kind === 'pan' && g.id === e.pointerId) panMove(sp); else if (g?.finger && g.id === e.pointerId) move(e);
    return;
  }
  if (e.pointerType === 'pen') penAt = performance.now();
  hover = toWorld(...sp);
  if (!g) { if (S.tool === 'eraser') dirty(false); return; }
  if (g.id !== e.pointerId) return;
  if (g.kind === 'pan') panMove(sp); else move(e);
});
const up = e => {
  if (e.pointerType === 'pen') { penDown = false; penAt = performance.now(); }
  if (e.pointerType === 'touch') {
    if (!ptrs.delete(e.pointerId)) return;
    if (g?.kind === 'pinch') { if (ptrs.size === 1) { const [id, p] = [...ptrs][0]; startPan(p, id); } else g = null; return; }
    if (g?.kind === 'pan' && g.id === e.pointerId) { g = null; return; }
  }
  if (g && g.id === e.pointerId) end(e);
};
cvT.addEventListener('pointerup', up);
cvT.addEventListener('pointercancel', up); // Safari cancels a Pencil stroke at times: keep what was drawn
cvT.addEventListener('pointerleave', () => { if (!g) { hover = null; dirty(false); } });
cvT.addEventListener('contextmenu', e => e.preventDefault());
for (const ev of ['gesturestart', 'gesturechange']) document.addEventListener(ev, e => e.preventDefault());
document.addEventListener('touchmove', e => { if (e.target === cvT) e.preventDefault(); }, { passive: false });

function startPan(sp, id) { endEdit(); g = { kind: 'pan', id, touch: true, s0: sp, v0: { ...view } }; }
function panMove(sp) { view = { ...g.v0, x: g.v0.x - (sp[0] - g.s0[0]) / g.v0.z, y: g.v0.y - (sp[1] - g.s0[1]) / g.v0.z }; viewChanged(); }
function startPinch() {
  endEdit();
  const [a, b] = [...ptrs.values()];
  g = { kind: 'pinch', touch: true, d0: Math.hypot(b[0] - a[0], b[1] - a[1]) || 1, m0: [(a[0] + b[0]) / 2, (a[1] + b[1]) / 2], v0: { ...view } };
}
function pinchMove() {
  const [a, b] = [...ptrs.values()], d = Math.hypot(b[0] - a[0], b[1] - a[1]), m = [(a[0] + b[0]) / 2, (a[1] + b[1]) / 2];
  const z = clamp((g.v0.z * d) / g.d0, 0.05, 20), w = [g.m0[0] / g.v0.z + g.v0.x, g.m0[1] / g.v0.z + g.v0.y];
  view = { z, x: w[0] - m[0] / z, y: w[1] - m[1] / z };
  viewChanged();
}
function abort() {
  if (g?.kind === 'erase') { for (const id of g.gone.keys()) hidden.delete(id); }
  g = null; dirty();
}

function begin(e, sp, finger) {
  const w = toWorld(...sp), pen = e.pointerType === 'pen', tool = e.buttons & 32 ? 'eraser' : S.tool, id = e.pointerId;
  if (tool !== 'text') endEdit();
  if (tool === 'pen' || tool === 'hl') {
    const p = [w[0], w[1], pressure(e, pen)];
    g = { kind: 'draw', id, finger, pen, tool, color: S.color[tool], w: SIZES[tool][S.size[tool]] / view.z, pts: [p], last: p, raw: p, k: pen ? 0.3 : 0.5 };
  } else if (tool === 'eraser') { g = { kind: 'erase', id, finger, gone: new Map() }; hover = w; eraseAt(w); }
  else if (tool === 'lasso') {
    const sb = selBounds();
    if (sb && Ink.inRect(w, [sb[0] - 8 / view.z, sb[1] - 8 / view.z, sb[2] + 16 / view.z, sb[3] + 16 / view.z])) g = { kind: 'movesel', id, finger, a: w, off: [0, 0] };
    else { sel.clear(); g = { kind: 'lasso', id, finger, poly: [w] }; buildCtx(); }
  } else g = { kind: tool, id, finger, a: w, b: w, moved: false, wasEditing: !!editing };
  dirty(false);
}
function move(e) {
  if (g.kind === 'draw') {
    for (const ev of samples(e)) {
      const w = toWorld(...pos(ev)), raw = [w[0], w[1], pressure(ev, g.pen)], q = Ink.step(g.last, raw, g.k), L = g.pts[g.pts.length - 1];
      g.last = q; g.raw = raw;
      if (Math.hypot(q[0] - L[0], q[1] - L[1]) * view.z > 0.6) g.pts.push(q);
    }
    g.pred = (e.getPredictedEvents?.() || []).slice(0, 2).map(ev => { const w = toWorld(...pos(ev)); return [w[0], w[1], g.last[2]]; });
    dirty(false);
    return;
  }
  const w = toWorld(...pos(e));
  if (g.kind === 'erase') { for (const ev of samples(e)) eraseAt(toWorld(...pos(ev))); hover = w; }
  else if (g.kind === 'lasso') { const L = g.poly[g.poly.length - 1]; if (Math.hypot(w[0] - L[0], w[1] - L[1]) * view.z > 3) g.poly.push(w); }
  else if (g.kind === 'movesel') { g.off = [w[0] - g.a[0], w[1] - g.a[1]]; dirty(); return; }
  else { g.b = w; if (Math.hypot(w[0] - g.a[0], w[1] - g.a[1]) * view.z > 6) g.moved = true; }
  dirty(false);
}
function eraseAt(w) {
  const r = SIZES.eraser[S.size.eraser] / 2 / view.z, box = [w[0] - r, w[1] - r, 2 * r, 2 * r];
  for (const it of Object.values(items)) {
    if (hidden.has(it.id) || !Ink.overlap(bounds(it), box) || !Ink.hit(it, w, r)) continue;
    g.gone.set(it.id, it); hidden.add(it.id); dirty();
  }
}
const moveItem = (it, dx, dy) => (it.t === 'stroke' ? { ...it, pts: it.pts.map(p => [r2(p[0] + dx), r2(p[1] + dy), p[2]]) } : { ...it, x: r2(it.x + dx), y: r2(it.y + dy) });
function end() {
  const k = g; g = null;
  if (k.kind === 'draw') {
    const pts = Ink.simplify([...k.pts, k.raw], 0.3 / view.z).map(p => [r2(p[0]), r2(p[1]), r2(p[2])]);
    const it = { id: newId(), t: 'stroke', tool: k.tool, color: k.color, w: r2(k.w), z: nextZ(), pts };
    commit([it], [], { del: [it.id] });
  } else if (k.kind === 'erase') {
    const gone = [...k.gone.values()];
    for (const it of gone) hidden.delete(it.id);
    if (gone.length) commit([], gone.map(i => i.id), { put: gone });
  } else if (k.kind === 'lasso') {
    if (k.poly.length > 2) Ink.lasso(Object.values(items), k.poly).forEach(it => sel.add(it.id));
    buildCtx();
  } else if (k.kind === 'movesel') {
    const [dx, dy] = k.off;
    if (Math.hypot(dx, dy) * view.z > 1) { const old = [...sel].map(id => items[id]).filter(Boolean); commit(old.map(it => moveItem(it, dx, dy)), [], { put: old }); }
  } else if (k.kind === 'text' && !k.wasEditing) { // a tap while typing only ends the typing
    const hitT = Object.values(items).filter(it => it.t === 'text' && Ink.hit(it, k.a, 4 / view.z)).sort((a, b) => b.z - a.z)[0];
    editText(hitT || { id: newId(), t: 'text', x: r2(k.a[0]), y: r2(k.a[1] - (SIZES.text[S.size.text] / view.z) * 0.6), s: '', size: r2(SIZES.text[S.size.text] / view.z), color: S.color.text, z: nextZ() });
  } else if (k.kind === 'shape' && k.moved) {
    const it = { id: newId(), t: 'stroke', tool: 'pen', color: S.color.shape, w: r2(SIZES.shape[S.size.shape] / view.z), z: nextZ(), pts: Ink.shapePts(S.shape, k.a, k.b).map(p => [r2(p[0]), r2(p[1]), p[2]]) };
    commit([it], [], { del: [it.id] });
  } else if (k.kind === 'snap' && k.moved) openSnap(rectOf(k.a, k.b).map(r2));
  dirty();
}
cvT.addEventListener('wheel', e => {
  e.preventDefault();
  const sp = pos(e);
  if (e.ctrlKey || e.metaKey) zoomAt(sp[0], sp[1], Math.exp(-e.deltaY * (e.deltaMode ? 0.05 : 0.01)));
  else { const k = e.deltaMode ? 30 : 1, dx = e.shiftKey ? e.deltaY : e.deltaX, dy = e.shiftKey ? 0 : e.deltaY; view = { ...view, x: view.x + (dx * k) / view.z, y: view.y + (dy * k) / view.z }; viewChanged(); }
}, { passive: false });

// ---------------------------------------------------------------- text editor
let editing = null;
const ed = $('ed');
function editText(it) {
  editing = it; hidden.add(it.id);
  ed.value = it.s; ed.style.display = 'block'; ed.style.color = !it.color || it.color === 'ink' ? theme.ink : it.color;
  placeEditor(); sizeEditor();
  setTimeout(() => ed.focus(), 0);
  dirty();
}
function placeEditor() {
  const [x, y] = toScreen(editing.x, editing.y);
  Object.assign(ed.style, { left: `${x - 2}px`, top: `${y - 2}px`, fontSize: `${editing.size * view.z}px` });
}
function sizeEditor() { ed.style.width = '0px'; ed.style.height = '0px'; ed.style.width = `${ed.scrollWidth + 12}px`; ed.style.height = `${ed.scrollHeight + 4}px`; }
function endEdit() {
  const it = editing;
  if (!it) return;
  editing = null; hidden.delete(it.id); ed.style.display = 'none';
  const s = ed.value.replace(/\s+$/, ''), old = items[it.id];
  if (!s) { if (old) commit([], [it.id], { put: [old] }); }
  else if (!old || old.s !== s) commit([{ ...it, s }], [], old ? { put: [old] } : { del: [it.id] });
  dirty();
}
ed.addEventListener('input', sizeEditor);
ed.addEventListener('blur', endEdit);
ed.addEventListener('keydown', e => { if (e.key === 'Escape' || (e.key === 'Enter' && (e.ctrlKey || e.metaKey))) { e.preventDefault(); ed.blur(); } });

// ---------------------------------------------------------------- snap tool
let snapDraft = null;
const peek = new Set();
function openSnap(rect, text = '', replaces = null) {
  snapDraft = { rect, replaces };
  const pop = $('snapPop'), [x, y] = toScreen(rect[0], rect[1] + rect[3]);
  pop.classList.add('open');
  pop.style.left = `${clamp(x, 8, W - pop.offsetWidth - 8)}px`;
  pop.style.top = `${clamp(y + 8, 8, H - pop.offsetHeight - 8)}px`;
  $('snapText').value = text;
  $('snapDirectRow').style.visibility = api ? 'visible' : 'hidden';
  try { $('snapDirect').checked = api && localStorage.getItem('cad-sketch-direct') === '1'; } catch { /* ignore */ }
  setTimeout(() => $('snapText').focus(), 0);
}
function closeSnap() { snapDraft = null; $('snapPop').classList.remove('open'); }
function renderPng(r, scale, bg = '#ffffff', ink = '#1f1e1d') {
  const c = document.createElement('canvas');
  c.width = Math.max(1, Math.round(r[2] * scale)); c.height = Math.max(1, Math.round(r[3] * scale));
  const x = c.getContext('2d');
  x.fillStyle = bg; x.fillRect(0, 0, c.width, c.height);
  x.setTransform(scale, 0, 0, scale, -r[0] * scale, -r[1] * scale);
  for (const it of sorted()) if (Ink.overlap(bounds(it), r)) drawItem(x, it, ink);
  return c.toDataURL('image/png');
}
async function sendSnap() {
  const text = $('snapText').value.trim();
  if (!snapDraft || !text) return;
  const { rect, replaces } = snapDraft, direct = $('snapDirect').checked && api;
  try { localStorage.setItem('cad-sketch-direct', direct ? '1' : '0'); } catch { /* ignore */ }
  const live = Object.values(items), ids = Ink.regionIds(live, rect), idset = new Set(ids);
  const scale = r2(clamp(1024 / Math.max(rect[2], rect[3]), 0.25, 4));
  const near = [rect[0] - rect[2], rect[1] - rect[3], rect[2] * 3, rect[3] * 3];
  const outside = live.filter(it => !idset.has(it.id)).map(bounds).filter(b => Ink.overlap(b, near)).slice(0, 200).map(b => b.map(v => Math.round(v)));
  closeSnap();
  if (replaces) send({ snaps: [{ id: replaces, status: 'rejected' }] });
  try {
    await call('/api/sketch/snap', { rect, text, ids, image: renderPng(rect, scale), scale, outside, direct });
    toast(direct ? 'Asked the AI, the proposal shows up in the box…' : 'Snap request added to your Claude message: send it there.');
  } catch (e) { toast(`Snap failed: ${e.message}`, true); }
}
$('snapSend').onclick = sendSnap;
$('snapCancel').onclick = closeSnap;
$('snapText').addEventListener('keydown', e => { if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) sendSnap(); if (e.key === 'Escape') closeSnap(); });
function setSnap(id, status) { if (snaps[id]) snaps[id] = { ...snaps[id], status }; send({ snaps: [{ id, status }] }); renderSnaps(); dirty(); }
function acceptSnap(s) {
  const a = Ink.accept(items, s, newId);
  commit(a.put, a.del, a.undo, [{ id: s.id, status: 'accepted' }]);
  snaps[s.id] = { ...s, status: 'accepted' };
  peek.delete(s.id); renderSnaps();
  toast(`Accepted: ${a.del.length} replaced, ${a.put.length} new · Ctrl+Z undoes it`);
}
function renderSnaps() {
  const box = $('snaps'), live = Object.values(snaps).filter(s => ['pending', 'proposed', 'error'].includes(s.status));
  for (const el of [...box.children]) if (!snaps[el.dataset.id] || !live.includes(snaps[el.dataset.id])) el.remove();
  for (const s of live) {
    let el = box.querySelector(`[data-id="${s.id}"]`);
    if (el && el.dataset.st === s.status + s.rev) continue;
    if (!el) { el = document.createElement('div'); el.dataset.id = s.id; box.appendChild(el); }
    el.dataset.st = s.status + s.rev;
    el.className = `snapbar${s.status === 'error' ? ' err' : ''}`;
    const b = (label, fn, cls = '') => { const x = document.createElement('button'); x.textContent = label; x.className = cls; x.onclick = fn; return x; };
    const t = document.createElement('span'); t.className = 't';
    el.replaceChildren(t);
    if (s.status === 'pending') {
      t.textContent = `✦ Waiting for Claude… "${s.text}"`;
      el.append(b('Cancel', () => setSnap(s.id, 'rejected'), 'ghost'));
    } else if (s.status === 'proposed') {
      t.textContent = `✦ ${s.note || `Proposal: ${s.text}`}`; t.title = s.note || s.text;
      const pk = b('Show old', () => { if (peek.has(s.id)) peek.delete(s.id); else peek.add(s.id); pk.classList.toggle('on', peek.has(s.id)); dirty(false); }, 'ghost');
      pk.classList.toggle('on', peek.has(s.id));
      el.append(pk, b('Edit…', () => openSnap(s.rect, s.text, s.id), 'ghost'), b('Reject', () => setSnap(s.id, 'rejected'), 'ghost danger'), b('Accept', () => acceptSnap(s), 'primary'));
    } else {
      t.textContent = s.note || 'The AI call failed'; t.title = t.textContent;
      el.append(b('Edit…', () => openSnap(s.rect, s.text, s.id), 'ghost'), b('Dismiss', () => setSnap(s.id, 'rejected'), 'ghost'));
    }
  }
  placeSnaps();
}
function placeSnaps() {
  for (const el of $('snaps').children) {
    const s = snaps[el.dataset.id];
    if (!s) continue;
    const [x, y] = toScreen(s.rect[0], s.rect[1] + s.rect[3]);
    el.style.left = `${clamp(x, 8, Math.max(8, W - el.offsetWidth - 8))}px`;
    el.style.top = `${clamp(y + 6, 8, Math.max(8, H - el.offsetHeight - 8))}px`;
  }
}

// ---------------------------------------------------------------- send whole canvas
let sendData = null;
$('bSend').onclick = () => {
  const b = Ink.union(Object.values(items).map(bounds));
  if (!b) return toast('The canvas is empty.', true);
  const r = [b[0] - 20, b[1] - 20, b[2] + 40, b[3] + 40];
  sendData = renderPng(r, clamp(1600 / Math.max(r[2], r[3]), 0.1, 2));
  $('sendImg').src = sendData; $('sendText').value = '';
  $('modal').classList.add('open');
};
$('sendCancel').onclick = () => $('modal').classList.remove('open');
$('sendGo').onclick = async () => {
  $('modal').classList.remove('open');
  try { await call('/api/sketch/send', { image: sendData, text: $('sendText').value.trim() }); toast('Added to your Claude message: send it there.'); }
  catch (e) { toast(`Send failed: ${e.message}`, true); }
};

// ---------------------------------------------------------------- images, paste, drop
const fileUrl = f => new Promise((ok, no) => { const r = new FileReader(); r.onload = () => ok(r.result); r.onerror = no; r.readAsDataURL(f); });
const loadImg = url => new Promise((ok, no) => { const im = new Image(); im.onload = () => ok(im); im.onerror = () => no(new Error('cannot read the image')); im.src = url; });
async function addImage(file, at) {
  try {
    let url = await fileUrl(file), im = await loadImg(url);
    const m = Math.max(im.naturalWidth, im.naturalHeight);
    if (m > 2048 || !/^data:image\/(png|jpeg|webp)/.test(url)) {
      const k = Math.min(1, 2048 / m), c = document.createElement('canvas');
      c.width = Math.round(im.naturalWidth * k); c.height = Math.round(im.naturalHeight * k);
      c.getContext('2d').drawImage(im, 0, 0, c.width, c.height);
      url = c.toDataURL(file.type === 'image/jpeg' ? 'image/jpeg' : 'image/png', 0.9);
      im = await loadImg(url);
    }
    const { src } = await call('/api/sketch/image', { image: url });
    imgCache.set(src, im);
    let w = im.naturalWidth / view.z, h = im.naturalHeight / view.z;
    const f = Math.min(1, (W * 0.6) / view.z / w, (H * 0.6) / view.z / h);
    w *= f; h *= f;
    const it = { id: newId(), t: 'image', src, x: r2(at[0] - w / 2), y: r2(at[1] - h / 2), w: r2(w), h: r2(h), z: nextZ() };
    commit([it], [], { del: [it.id] });
  } catch (e) { toast(`Image: ${e.message}`, true); }
}
const center = () => toWorld(W / 2, H / 2);
$('bImage').onclick = () => $('file').click();
$('file').onchange = () => { for (const f of $('file').files) addImage(f, center()); $('file').value = ''; };
document.addEventListener('paste', e => {
  if (e.target.closest?.('textarea,input')) return;
  const files = [...(e.clipboardData?.files || [])].filter(f => f.type.startsWith('image/'));
  if (files.length) { e.preventDefault(); files.forEach(f => addImage(f, center())); return; }
  const s = e.clipboardData?.getData('text/plain');
  if (s) { const [x, y] = center(), size = r2(SIZES.text[S.size.text] / view.z); const id = newId(); commit([{ id, t: 'text', x: r2(x), y: r2(y), s: s.slice(0, 5000), size, color: S.color.text, z: nextZ() }], [], { del: [id] }); }
});
$('wrap').addEventListener('dragover', e => e.preventDefault());
$('wrap').addEventListener('drop', e => {
  e.preventDefault();
  const at = toWorld(...pos(e));
  [...(e.dataTransfer?.files || [])].filter(f => f.type.startsWith('image/')).forEach(f => addImage(f, at));
});

// ---------------------------------------------------------------- toolbar
function setTool(t) {
  endEdit();
  if (t !== 'lasso') sel.clear();
  S.tool = t; savePrefs();
  for (const b of document.querySelectorAll('#tools button')) b.classList.toggle('on', b.dataset.tool === t);
  cvT.style.cursor = t === 'text' ? 'text' : 'crosshair';
  buildCtx(); dirty();
}
function buildCtx() {
  const box = $('ctx'), t = S.tool, kids = [];
  const btn = (html, title, on, fn, cls = '') => { const b = document.createElement('button'); b.innerHTML = html; b.title = title; b.className = cls + (on ? ' on' : ''); b.onclick = () => { fn(); buildCtx(); }; kids.push(b); return b; };
  if (t === 'shape') for (const [k, ic] of [['line', '<path d="M2.5 13.5l11-11"/>'], ['rect', '<rect x="2" y="3.5" width="12" height="9" rx="1"/>'], ['ellipse', '<ellipse cx="8" cy="8" rx="6" ry="4.5"/>']])
    btn(`<svg viewBox="0 0 16 16">${ic}</svg>`, k, S.shape === k, () => { S.shape = k; savePrefs(); }, 'icon');
  if (S.color[t] !== undefined) for (const c of t === 'hl' ? HL : COLORS) {
    const b = btn('', c === 'ink' ? 'Ink (follows the theme)' : c, S.color[t] === c, () => { S.color[t] = c; savePrefs(); }, 'sw');
    b.style.background = c === 'ink' ? 'var(--text)' : c;
  }
  if (SIZES[t]) SIZES[t].forEach((s, i) => { const d = Math.round(clamp(t === 'hl' || t === 'eraser' ? s / 3 : s * 1.6, 3, 14)); btn(`<i style="width:${d}px;height:${d}px"></i>`, `${s}px`, S.size[t] === i, () => { S.size[t] = i; savePrefs(); }, 'sz'); });
  if (t === 'lasso') {
    if (sel.size) btn(`Delete ${sel.size}`, 'Delete the selection (Del)', false, delSel, 'danger');
    else { const m = document.createElement('span'); m.className = 'muted'; m.style.padding = '0 6px'; m.textContent = 'Circle items to select'; kids.push(m); }
  }
  if (t === 'snap') { const m = document.createElement('span'); m.className = 'muted'; m.style.padding = '0 6px'; m.textContent = 'Box what should change'; kids.push(m); }
  box.replaceChildren(...kids);
  box.style.display = kids.length ? '' : 'none';
  $('hint').textContent = HINTS[t] || '';
}
function delSel() { const old = [...sel].map(id => items[id]).filter(Boolean); sel.clear(); if (old.length) commit([], old.map(i => i.id), { put: old }); buildCtx(); }
for (const b of document.querySelectorAll('#tools button')) b.onclick = () => setTool(b.dataset.tool);
$('bUndo').onclick = undo; $('bRedo').onclick = redo; $('bFit').onclick = fit;
$('zoom').onclick = () => zoomAt(W / 2, H / 2, 1 / view.z);
$('bViewMenu').onclick = e => { e.stopPropagation(); $('menuView').classList.toggle('open'); };
document.addEventListener('pointerdown', e => { if (!e.target.closest('.dd')) $('menuView').classList.remove('open'); });
const segs = () => {
  for (const b of document.querySelectorAll('#bgSeg button')) b.classList.toggle('on', b.dataset.bg === S.bg);
  for (const b of document.querySelectorAll('#themeSeg button')) b.classList.toggle('on', b.dataset.th === S.theme);
  $('optFinger').checked = S.finger;
};
for (const b of document.querySelectorAll('#bgSeg button')) b.onclick = () => { S.bg = b.dataset.bg; savePrefs(); segs(); dirty(); };
for (const b of document.querySelectorAll('#themeSeg button')) b.onclick = () => { S.theme = b.dataset.th; savePrefs(); segs(); readTheme(); };
$('optFinger').onchange = () => { S.finger = $('optFinger').checked; penSeen = false; savePrefs(); };
addEventListener('keydown', e => {
  if (e.target.closest?.('textarea,input')) return;
  const k = e.key.toLowerCase(), mod = e.ctrlKey || e.metaKey;
  if (mod && k === 'z') { e.preventDefault(); if (e.shiftKey) redo(); else undo(); return; }
  if (mod && k === 'y') { e.preventDefault(); redo(); return; }
  if (mod || e.altKey) return;
  if (k === ' ') { spaceDown = true; cvT.style.cursor = 'grab'; e.preventDefault(); return; }
  const tools = { p: 'pen', h: 'hl', e: 'eraser', l: 'lasso', t: 'text', s: 'shape', a: 'snap' };
  if (tools[k]) setTool(tools[k]);
  else if (k === 'f') fit();
  else if ((k === 'delete' || k === 'backspace') && sel.size) delSel();
  else if (k === 'escape') { sel.clear(); abort(); closeSnap(); buildCtx(); }
});
addEventListener('keyup', e => { if (e.key === ' ') { spaceDown = false; cvT.style.cursor = S.tool === 'text' ? 'text' : 'crosshair'; } });
let toastT = 0;
function toast(msg, err = false) { const el = $('toast'); el.textContent = msg; el.className = err ? 'err' : ''; el.style.display = 'block'; clearTimeout(toastT); toastT = setTimeout(() => { el.style.display = 'none'; }, 3500); }

segs(); readTheme(); resize(); setTool(S.tool); viewChanged(); poll(); frame();
window.__sketch = { items, snaps, get view() { return view; } }; // for checks from the browser console
