// Construction canvas: infinite canvas for engineers. Free ink + exact geometry (QuickShape+, trim, snap, dimensions),
// layers, a contextual right panel, and the AI loop: send a selection to Claude, answer briefing bubbles pinned to the
// drawing, accept or reject Claude's proposal. Everything local (draw, drag, dimension edit) works without the AI.
// Objects sync through /api/canvas (canvas.py). Geometry lives in geo.js (global Geo) and ink.js (global Ink).
/* global Ink, Geo */
const $ = id => document.getElementById(id);
const cvB = $('base'), cvT = $('top'), bctx = cvB.getContext('2d'), tctx = cvT.getContext('2d');
const FONT = 'ui-sans-serif, system-ui, -apple-system, "Segoe UI", sans-serif';
const COLORS = ['ink', '#e5484d', '#3e8ed0', '#30a46c', '#f08c00', '#8e4ec6'];
const HL = ['#ffd60a', '#7cd992', '#ff8fb1', '#7fc8ff'];
const GEO_TOOLS = ['line', 'circle', 'arc', 'arc3', 'rect', 'ellipse'];
const KEYS = { v: 'edit', p: 'pen', h: 'hl', e: 'eraser', t: 'text', l: 'lasso', b: 'box', 1: 'line', 2: 'circle', 3: 'arc3', o: 'arc', 4: 'rect', 5: 'ellipse', x: 'trim', s: 'split', w: 'extend', d: 'dim' };
const HINTS = {
  pen: 'Kresli · podrž konec tahu = rozpoznání tvaru · čmárání přes čáru ji smaže', hl: 'Zvýrazňovač', eraser: 'Guma maže celé objekty, přes které přejedeš (tahy, čáry, kružnice, kóty, text) · jen úsek mezi průsečíky smaže Trim',
  edit: 'Klikni na tvar: táhni za body (konce, střed, poloměr), tah po tvaru ho přesune · dvojklik na kótu = nová hodnota',
  lasso: 'Laso: obkroužení vybere · tah uvnitř výběru přesouvá (Ctrl = kopie) · dvojklik edituje', box: 'Obdélníkový výběr', text: 'Klikni a piš',
  line: 'Táhni, nebo klikni dva body', circle: 'Střed, pak poloměr', arc: 'Klikni: střed, začátek, konec', arc3: 'Klikni začátek a konec (nebo táhni), pak bod, kudy má oblouk vést', rect: 'Dva protilehlé rohy', ellipse: 'Dva rohy opsaného obdélníku',
  trim: 'Klikni na úsek mezi průsečíky', split: 'Klikni do místa dělení', extend: 'Klikni na konec čáry, prodlouží se k nejbližšímu objektu',
  dim: 'Klikni na čáru, hranu obdélníku, kružnici nebo oblouk, pak kam kótu dát · do prázdna = volná kóta ze dvou bodů · klik na kótu = nová hodnota',
};
const LABEL = { pending: 'Analyzuji', asking: 'Čekám na upřesnění', drafting: 'Vytvářím návrh', proposed: 'Připraveno ke schválení', applied: 'Použito', rejected: 'Zamítnuto', closed: 'Uzavřeno' };
// A request shows (region, ghosts, bubbles, bar) only while it is open: not once it is applied / rejected / closed, not when
// dismissed here, and not when everything it was about has been deleted meanwhile (an abandoned request).
const FINAL = ['applied', 'rejected', 'closed'];
const openReq = q => !!q && !FINAL.includes(q.status) && !dismissed.has(q.id) && (q.status === 'proposed' || !q.ids?.length || q.ids.some(id => objs[id]));
const seenOpen = new Set(), appliedAt = {}; // request id -> when this tab saw it applied: the bar offers Vrátit for a few seconds, then it all goes
const r2 = v => Math.round(v * 100) / 100;
const clamp = (v, a, b) => Math.max(a, Math.min(b, v));
const sleep = ms => new Promise(ok => setTimeout(ok, ms));
const hyp = Math.hypot;
const h = (tag, a = {}, ...kids) => {
  const el = document.createElement(tag);
  for (const k in a) { if (k === 'on') for (const ev in a.on) el.addEventListener(ev, a.on[ev]); else if (k in el && k !== 'style') el[k] = a[k]; else el.setAttribute(k, a[k]); }
  el.append(...kids.flat().filter(x => x != null && x !== false));
  return el;
};

// ---------------------------------------------------------------- prefs
const S = {
  tool: 'pen', prev: 'lasso', pen: { color: 'ink', w: 1.5, alpha: 1, smooth: 0.35 }, hl: { color: HL[0], w: 8, alpha: 0.4 }, quick: true, hold: 450, tol: 0.06, scribble: true, align: true,
  finger: false, snap: false, snapGrid: false, cons: false, bg: 'dots', gridI: 0.7, axes: false, theme: 'auto', layer: 1, hid: [], side: true, mini: false, view: null, ctx: 'selection', aut: 'propose',
};
try { const p = JSON.parse(localStorage.getItem('cad-canvas') || '{}'); for (const k in S) if (k in p) S[k] = typeof S[k] === 'object' && S[k] && !Array.isArray(S[k]) && p[k] ? { ...S[k], ...p[k] } : p[k]; } catch { /* private mode */ }
let view = S.view && S.view.z > 0 ? { ...S.view } : { x: -80, y: -60, z: 2 };
let saveT = 0;
const savePrefs = () => { clearTimeout(saveT); saveT = setTimeout(() => { try { localStorage.setItem('cad-canvas', JSON.stringify({ ...S, view })); } catch { /* ignore */ } }, 300); };

// ---------------------------------------------------------------- document + sync
const objs = {}, briefs = {}, reqs = {}, sel = new Set(), ovr = {}, dismissed = new Set(), hiddenProp = new Set();
let layers = Array.from({ length: 9 }, (_, i) => ({ n: i + 1, name: `Hladina ${i + 1}`, vis: true, lock: false, op: 1 }));
let regions = [], snaps = [], rev = 0, loaded = false;
const me = Math.random().toString(36).slice(2, 8);
let seq = 0;
const newId = () => `${me}${Date.now().toString(36)}${(seq++).toString(36)}`;
const nextZ = () => Date.now() + (seq++ % 1000) / 1000;
const undos = [], redos = [], outbox = [];

async function call(url, body) {
  const r = await fetch(url, body === undefined ? {} : { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
  const j = await r.json().catch(() => ({}));
  if (!r.ok) throw Object.assign(new Error(j.error || `HTTP ${r.status}`), { status: r.status, body: j });
  return j;
}
function apply({ put = [], del = [] }) {
  for (const id of del) { delete objs[id]; sel.delete(id); }
  for (const o of put) objs[o.id] = o;
  dirty(); sideDirty = true;
  if (del.length) renderAI();
}
function commit(put, del = []) {
  const back = [], created = [];
  for (const o of put) (objs[o.id] ? back : created).push(objs[o.id] ?? o.id);
  for (const id of del) if (objs[id]) back.push(objs[id]);
  const op = { put, del }, undo = { put: back, del: created };
  apply(op);
  undos.push({ op, undo }); if (undos.length > 300) undos.shift();
  redos.length = 0;
  send(op);
}
const undo = () => { const u = undos.pop(); if (u) { apply(u.undo); redos.push(u); send(u.undo); } };
const redo = () => { const u = redos.pop(); if (u) { apply(u.op); undos.push(u); send(u.op); } };
function send(op) {
  if (!op.put?.length && !op.del?.length && !op.layers?.length && !op.regions) return;
  outbox.push(op); flush();
}
let flushing = false;
async function flush() {
  if (flushing) return;
  flushing = true;
  while (outbox.length) {
    try { await call('/api/canvas/ops', { ...outbox[0], by: me }); outbox.shift(); setSync(true); }
    catch (e) {
      if (e.status === 400) { outbox.shift(); toast(`Neuloženo: ${e.message}`, true); continue; }
      setSync(false); await sleep(2000);
    }
  }
  flushing = false;
}
async function poll() {
  for (;;) {
    try {
      const since = rev, r = await call(`/api/canvas?since=${since}&wait=${since ? 25 : 0}`);
      if (r.rev < since) { for (const k in objs) delete objs[k]; rev = 0; continue; } // server was reset
      for (const o of r.objs) {
        if (since && o.by === me) continue; // our own change coming back
        if (o.deleted) { delete objs[o.id]; sel.delete(o.id); } else objs[o.id] = o;
      }
      layers = r.layers; applyVis(); regions = r.regions; snaps = r.snaps;
      for (const b of r.briefs) briefs[b.id] = b;
      for (const q of r.reqs) reqs[q.id] = q;
      rev = r.rev; setSync(true);
      if (!loaded) { loaded = true; if (!S.view) fit(); }
      dirty(); sideDirty = true; renderAI(); renderBubbles();
    } catch { setSync(false); await sleep(3000); }
  }
}
function setSync(ok) { const el = $('sync'); el.textContent = ok ? (outbox.length ? 'ukládám…' : 'synchronizováno') : 'offline, zkouším znovu…'; el.className = ok ? '' : 'off'; }
// Visibility is a per-device view setting (kept here, not on the server), so hiding a layer on the tablet does not hide it on the PC
// and a slow sync cannot flip it back.
function applyVis() { for (const l of layers) l.vis = !S.hid.includes(l.n); }
function setLayer(n, patch) {
  if ('vis' in patch) { S.hid = S.hid.filter(x => x !== n); if (!patch.vis) S.hid.push(n); applyVis(); savePrefs(); const { vis, ...rest } = patch; patch = rest; }
  Object.assign(layers[n - 1], patch); dirty(); sideDirty = true; renderBubbles();
  if (Object.keys(patch).length) send({ layers: [{ n, ...patch }] });
}

// ---------------------------------------------------------------- view + theme
let dpr = 1, W = 0, H = 0, needB = true, needT = true, sideDirty = true, order = [], orderDirty = true, theme = {};
const dirty = (b = true) => { if (b) { needB = true; orderDirty = true; } needT = true; };
const toWorld = (sx, sy) => [sx / view.z + view.x, sy / view.z + view.y];
const toScreen = (x, y) => [(x - view.x) * view.z, (y - view.y) * view.z];
const viewRect = () => [view.x, view.y, W / view.z, H / view.z];
function resize() {
  const r = $('wrap').getBoundingClientRect(), oW = W, oH = H;
  dpr = window.devicePixelRatio || 1; W = r.width; H = r.height;
  if (oW && oH && W && H && (oW !== W || oH !== H)) { view.x += (oW - W) / 2 / view.z; view.y += (oH - H) / 2 / view.z; savePrefs(); drawMini(); }
  for (const c of [cvB, cvT]) { c.width = Math.max(1, Math.round(W * dpr)); c.height = Math.max(1, Math.round(H * dpr)); }
  dirty(); layoutBubbles();
}
new ResizeObserver(resize).observe($('wrap'));
function readTheme() {
  if (S.theme === 'auto') delete document.documentElement.dataset.theme; else document.documentElement.dataset.theme = S.theme;
  const cs = getComputedStyle(document.documentElement), v = n => cs.getPropertyValue(n).trim(), dark = S.bg === 'dark';
  theme = { ink: dark ? '#faf9f5' : v('--text'), paper: dark ? '#171615' : v('--bg'), grid: dark ? '#3d3c38' : v('--line'), grid2: dark ? '#55534d' : v('--line2'), accent: v('--accent'), blue: v('--accent2'), bad: v('--bad'), ok: v('--ok'), faint: v('--faint') };
  dirty();
}
matchMedia('(prefers-color-scheme: light)').addEventListener('change', readTheme);
function zoomAt(sx, sy, f) { const z = clamp(view.z * f, 0.03, 60), w = toWorld(sx, sy); view = { z, x: w[0] - sx / z, y: w[1] - sy / z }; viewChanged(); }
function viewChanged() { $('zoom').textContent = `${Math.round(view.z * 100)} %`; savePrefs(); dirty(); layoutBubbles(); drawMini(); }
function fit() {
  const b = unionB(Object.values(objs).map(bnd));
  if (!b) view = { x: -W / 4, y: -H / 4, z: 2 };
  else { const z = clamp(Math.min(W / (b[2] + 80), H / (b[3] + 80)), 0.03, 20); view = { z, x: b[0] + b[2] / 2 - W / 2 / z, y: b[1] + b[3] / 2 - H / 2 / z }; }
  viewChanged();
}
const unionB = bs => Ink.union(bs.filter(Boolean));
const bCache = new WeakMap();
function bnd(o) { let b = bCache.get(o); if (!b) { b = o.t === 'stroke' ? Ink.bounds(o) : Geo.bounds(o); if (o.t !== 'dim' && o.t !== 'mech') bCache.set(o, b); } return b; }
const getOrder = () => { if (orderDirty) { order = Object.values(objs).sort((a, b) => a.layer - b.layer || a.z - b.z); orderDirty = false; } return order; };
const lay = o => layers[o.layer - 1] || layers[0];
const visible = o => lay(o).vis;
const selectable = o => visible(o) && !lay(o).lock;

// ---------------------------------------------------------------- drawing
const pathCache = new WeakMap();
function strokePath(o) {
  let p = pathCache.get(o);
  if (p) return p;
  p = new Path2D();
  const pr = o.tool !== 'hl', poly = Ink.outline(o.pts, o.w, pr);
  if (poly) { p.moveTo(poly[0][0], poly[0][1]); for (let i = 1; i < poly.length; i++) p.lineTo(poly[i][0], poly[i][1]); p.closePath(); } else { const q = o.pts[0]; p.arc(q[0], q[1], Ink.radius(o.w, q[2], pr), 0, Math.PI * 2); }
  pathCache.set(o, p);
  return p;
}
function head(c, tip, from, size) {
  const a = Math.atan2(tip[1] - from[1], tip[0] - from[0]);
  c.beginPath(); c.moveTo(tip[0], tip[1]);
  c.lineTo(tip[0] - size * Math.cos(a - 0.4), tip[1] - size * Math.sin(a - 0.4)); c.lineTo(tip[0] - size * Math.cos(a + 0.4), tip[1] - size * Math.sin(a + 0.4)); c.closePath(); c.fill();
}
/** Draw one object. px = world size of a screen pixel (for dashes); col overrides the colour (ghosts, export). */
function drawObj(c, o, ink, px, col) {
  const k = col || (!o.color || o.color === 'ink' ? ink : o.color);
  c.strokeStyle = k; c.fillStyle = k; c.lineWidth = o.w; c.lineCap = 'round'; c.lineJoin = 'round';
  if (o.cons) { c.setLineDash([7 * px, 4 * px]); if (!col) c.strokeStyle = theme.blue; }
  switch (o.t) {
    case 'stroke': c.globalAlpha *= o.tool === 'hl' ? o.alpha ?? 0.4 : o.alpha ?? 1; c.fill(strokePath(o)); break;
    case 'line': c.beginPath(); c.moveTo(o.a[0], o.a[1]); c.lineTo(o.b[0], o.b[1]); c.stroke(); if (o.arrow) head(c, o.b, o.a, 5 + o.w * 2); break;
    case 'circle': c.beginPath(); c.arc(o.c[0], o.c[1], o.r, 0, Math.PI * 2); c.stroke(); break;
    case 'arc': c.beginPath(); c.arc(o.c[0], o.c[1], o.r, o.a0, o.a0 + Geo.arcSpan(o)); c.stroke(); break;
    case 'rect': c.strokeRect(Math.min(o.p[0], o.q[0]), Math.min(o.p[1], o.q[1]), Math.abs(o.q[0] - o.p[0]), Math.abs(o.q[1] - o.p[1])); break;
    case 'ellipse': c.beginPath(); c.ellipse(o.c[0], o.c[1], o.rx, o.ry, 0, 0, Math.PI * 2); c.stroke(); break;
    case 'text': c.font = `${o.size}px ${FONT}`; c.textBaseline = 'top'; String(o.s).split('\n').forEach((l, i) => c.fillText(l, o.x, o.y + i * o.size * 1.25)); break;
    case 'dim': drawDim(c, o); break;
    case 'mech': drawMech(c, o, px); break;
    default: break;
  }
  c.setLineDash([]);
}
function drawDim(c, o) {
  const d = Geo.dimGeom(o);
  if (!(d.len > 0)) return;
  c.lineWidth = Math.max(0.3, Math.min(o.w * 0.6, d.size * 0.08));
  const lin = d.kind === 'lin', ux = (d.b2[0] - d.a2[0]) / d.len, uy = (d.b2[1] - d.a2[1]) / d.len;
  c.beginPath();
  if (lin) { c.moveTo(d.a[0], d.a[1]); c.lineTo(d.a2[0] + d.n[0] * d.size * 0.2 * Math.sign(o.off ?? 1), d.a2[1] + d.n[1] * d.size * 0.2 * Math.sign(o.off ?? 1)); c.moveTo(d.b[0], d.b[1]); c.lineTo(d.b2[0] + d.n[0] * d.size * 0.2 * Math.sign(o.off ?? 1), d.b2[1] + d.n[1] * d.size * 0.2 * Math.sign(o.off ?? 1)); }
  c.moveTo(d.a2[0], d.a2[1]); c.lineTo(d.b2[0], d.b2[1]); c.stroke();
  const s = d.size * 0.4;
  if (lin || d.kind === 'dia') { head(c, d.a2, d.b2, s); }
  head(c, d.b2, d.a2, s);
  const ang = Math.atan2(uy, ux), flip = Math.abs(ang) > Math.PI / 2;
  c.save(); c.translate(d.label[0], d.label[1]);
  if (lin) { c.rotate(flip ? ang + Math.PI : ang); c.textAlign = 'center'; c.textBaseline = 'bottom'; c.font = `${d.size}px ${FONT}`; c.fillText(d.txt, 0, -d.size * 0.15); } else { c.textAlign = 'left'; c.textBaseline = 'middle'; c.font = `${d.size}px ${FONT}`; c.fillText(d.txt, 0, 0); }
  c.restore();
}
const worldTf = c => c.setTransform(dpr * view.z, 0, 0, dpr * view.z, -view.x * view.z * dpr, -view.y * view.z * dpr);
function gridStep() { for (let k = 0.1; ; k *= 10) for (const m of [1, 2, 5]) if (m * k * view.z >= 14) return m * k; }
function drawGrid(c) {
  const [x, y, w, hh] = viewRect(), g = gridStep();
  c.globalAlpha = S.gridI;
  if (S.bg === 'dots' || S.bg === 'dark') {
    c.fillStyle = theme.grid2; const d = 1.6 / view.z;
    for (let X = Math.floor(x / g) * g; X < x + w; X += g) for (let Y = Math.floor(y / g) * g; Y < y + hh; Y += g) c.fillRect(X - d / 2, Y - d / 2, d, d);
  } else if (S.bg === 'grid') {
    c.strokeStyle = theme.grid; c.lineWidth = 1 / view.z; c.beginPath();
    for (let X = Math.floor(x / g) * g; X < x + w; X += g) { c.moveTo(X, y); c.lineTo(X, y + hh); }
    for (let Y = Math.floor(y / g) * g; Y < y + hh; Y += g) { c.moveTo(x, Y); c.lineTo(x + w, Y); }
    c.stroke();
  }
  if (S.axes) { c.strokeStyle = theme.blue; c.lineWidth = 1.2 / view.z; c.globalAlpha = 0.7; c.beginPath(); c.moveTo(x, 0); c.lineTo(x + w, 0); c.moveTo(0, y); c.lineTo(0, y + hh); c.stroke(); }
  c.globalAlpha = 1;
}
function drawBase() {
  const c = bctx;
  c.setTransform(1, 0, 0, 1, 0, 0); c.fillStyle = theme.paper; c.fillRect(0, 0, cvB.width, cvB.height);
  worldTf(c); drawGrid(c);
  Geo.ctx.byId = Object.keys(ovr).length ? { ...objs, ...ovr } : objs;
  const vr = viewRect(), px = 1 / view.z, hide = g?.kind === 'erase' ? g.removed : null;
  for (const o0 of getOrder()) {
    const o = ovr[o0.id] || o0;
    if (!visible(o) || hide?.has(o.id)) continue;
    if (o.t !== 'dim' && !Ink.overlap(bnd(o), vr)) continue;
    c.globalAlpha = lay(o).op; drawObj(c, o, theme.ink, px); c.globalAlpha = 1;
  }
  drawTraces(c);
  $('count').textContent = `${Object.keys(objs).length} objektů`;
}
const selB = () => unionB([...sel].map(id => objs[id] && bnd(ovr[id] || objs[id])));
function handlesOf(o) {
  switch (o.t) {
    case 'line': return [{ k: 'a', p: o.a }, { k: 'b', p: o.b }];
    case 'circle': return [{ k: 'c', p: o.c }, { k: 'r', p: [o.c[0] + o.r, o.c[1]] }];
    case 'ellipse': return [{ k: 'c', p: o.c }, { k: 'rx', p: [o.c[0] + o.rx, o.c[1]] }, { k: 'ry', p: [o.c[0], o.c[1] + o.ry] }];
    case 'arc': return [{ k: 'c', p: o.c }, { k: 'a0', p: Geo.arcPt(o, 0) }, { k: 'a1', p: Geo.arcPt(o, 1) }];
    case 'rect': return [{ k: 'p', p: o.p }, { k: 'q', p: o.q }, { k: 'c1', p: [o.q[0], o.p[1]] }, { k: 'c2', p: [o.p[0], o.q[1]] }];
    case 'mech': return mechSt[o.id]?.playing ? [] : o.joints.map(j => ({ k: `j:${j.id}`, p: Geo.mechPts(o)[j.id] }));
    case 'dim': { const d = Geo.dimGeom(o); return d.kind === 'lin' ? [{ k: 'off', p: d.label }] : [{ k: 'ang', p: d.b }]; }
    default: return [];
  }
}
function applyHandle(o, k, p) {
  if (k.startsWith('j:')) return moveJoint(o, k.slice(2), p);
  const n = { ...o }, ang = () => Math.atan2(p[1] - o.c[1], p[0] - o.c[0]);
  switch (k) {
    case 'a': case 'b': n[k] = p; break;
    case 'c': n.c = p; break;
    case 'r': n.r = Math.max(0.01, Geo.dist(o.c, p)); break;
    case 'rx': n.rx = Math.max(0.01, Math.abs(p[0] - o.c[0])); break;
    case 'ry': n.ry = Math.max(0.01, Math.abs(p[1] - o.c[1])); break;
    case 'a0': n.a0 = ang(); n.r = Math.max(0.01, Geo.dist(o.c, p)); break;
    case 'a1': n.a1 = ang(); break;
    case 'p': case 'q': n[k] = p; break;
    case 'c1': n.q = [p[0], o.q[1]]; n.p = [o.p[0], p[1]]; break;
    case 'c2': n.p = [p[0], o.p[1]]; n.q = [o.q[0], p[1]]; break;
    case 'off': { const d = Geo.dimGeom(o); n.off = (p[0] - d.a[0]) * d.n[0] + (p[1] - d.a[1]) * d.n[1]; break; }
    case 'ang': { const r = objs[o.ref]; if (r) n.ang = Math.atan2(p[1] - r.c[1], p[0] - r.c[0]); break; }
    default: break;
  }
  return n;
}
function drawTop() {
  const c = tctx, z = view.z, px = 1 / z;
  c.setTransform(1, 0, 0, 1, 0, 0); c.clearRect(0, 0, cvT.width, cvT.height); worldTf(c);
  const ghostCol = { add: theme.ok, mod: '#f08c00', del: theme.bad };
  for (const q of Object.values(reqs)) { // AI work: region, proposal ghosts
    if (!openReq(q)) continue;
    c.strokeStyle = theme.accent; c.lineWidth = 1.5 * px; c.setLineDash([6 * px, 4 * px]); c.strokeRect(...q.rect); c.setLineDash([]);
    c.fillStyle = theme.accent; c.font = `${11 * px}px ${FONT}`; c.textBaseline = 'bottom'; c.fillText(LABEL[q.status] || q.status, q.rect[0], q.rect[1] - 3 * px);
    if (q.status === 'proposed' && q.proposal && !hiddenProp.has(q.id)) {
      for (const id of q.proposal.del) if (objs[id]) { c.globalAlpha = 0.55; drawObj(c, objs[id], theme.ink, px, ghostCol.del); c.globalAlpha = 1; }
      for (const o of q.proposal.put) {
        const old = objs[o.id];
        if (old) { c.globalAlpha = 0.45; drawObj(c, old, theme.ink, px, ghostCol.del); }
        c.globalAlpha = 0.75; drawObj(c, o, theme.ink, px, old ? ghostCol.mod : ghostCol.add); c.globalAlpha = 1;
      }
    }
  }
  // selection
  const sb = selB();
  if (sb && g?.kind !== 'handle') {
    c.strokeStyle = theme.accent; c.lineWidth = 1 * px; c.setLineDash([4 * px, 3 * px]); c.strokeRect(sb[0] - 3 * px, sb[1] - 3 * px, sb[2] + 6 * px, sb[3] + 6 * px); c.setLineDash([]);
  }
  const one = sel.size === 1 ? ovr[[...sel][0]] || objs[[...sel][0]] : null;
  if (one && selectable(one)) for (const hd of handlesOf(one)) { c.fillStyle = theme.paper; c.strokeStyle = theme.accent; c.lineWidth = 1.5 * px; c.beginPath(); c.arc(hd.p[0], hd.p[1], 4.5 * px, 0, Math.PI * 2); c.fill(); c.stroke(); }
  if (g?.copies) for (const o of g.copies) { c.globalAlpha = 0.6; drawObj(c, o, theme.ink, px); c.globalAlpha = 1; }
  // gestures
  if (g?.kind === 'ink') {
    const t = g.tool, col = t === 'hl' ? S.hl.color : S.pen.color;
    if (g.live) drawObj(c, { ...g.live, w: sw('pen'), color: S.pen.color }, theme.ink, px, theme.accent);
    else drawObj(c, { t: 'stroke', pts: g.pts, w: sw(t), tool: t, alpha: S[t].alpha, color: col }, theme.ink, px);
  } else if (g?.kind === 'lasso') {
    c.strokeStyle = theme.accent; c.lineWidth = 1.2 * px; c.setLineDash([5 * px, 4 * px]); c.beginPath(); g.pts.forEach((p, i) => (i ? c.lineTo(p[0], p[1]) : c.moveTo(p[0], p[1]))); c.closePath(); c.stroke(); c.setLineDash([]);
  } else if (g?.kind === 'snip') {
    const b = boxOf(g.p0, g.p1); c.fillStyle = theme.accent; c.globalAlpha = 0.08; c.fillRect(...b); c.globalAlpha = 1;
    c.strokeStyle = theme.accent; c.lineWidth = 1.5 * px; c.setLineDash([6 * px, 4 * px]); c.strokeRect(...b); c.setLineDash([]);
  } else if (g?.kind === 'boxsel') {
    c.strokeStyle = theme.accent; c.lineWidth = 1.2 * px; c.setLineDash([5 * px, 4 * px]); c.strokeRect(...boxOf(g.p0, g.p1)); c.setLineDash([]);
  } else if (g?.kind === 'erase') {
    c.strokeStyle = theme.faint; c.lineWidth = px; c.beginPath(); c.arc(g.at[0], g.at[1], 10 * px, 0, Math.PI * 2); c.stroke();
  }
  const pv = previewObj();
  if (pv) drawObj(c, pv, theme.ink, px, theme.accent);
  if (hover.snap) { c.strokeStyle = theme.accent; c.lineWidth = 1.5 * px; const [x, y] = hover.snap.p, s = 5 * px; c.beginPath(); if (hover.snap.kind === 'cross') { c.moveTo(x - s, y - s); c.lineTo(x + s, y + s); c.moveTo(x - s, y + s); c.lineTo(x + s, y - s); } else if (hover.snap.kind === 'mid') { c.moveTo(x - s, y + s); c.lineTo(x, y - s); c.lineTo(x + s, y + s); c.closePath(); } else c.rect(x - s, y - s, 2 * s, 2 * s); c.stroke(); }
  // briefing leader lines
  c.setTransform(dpr, 0, 0, dpr, 0, 0);
  c.strokeStyle = theme.accent; c.lineWidth = 1.2;
  for (const b of Object.values(briefs)) { const bp = bubblePos(b); if (!bp) continue; c.globalAlpha = b.state === 'open' ? 0.9 : 0.5; c.beginPath(); c.moveTo(bp.ax, bp.ay); c.lineTo(bp.x, bp.y); c.stroke(); c.beginPath(); c.arc(bp.ax, bp.ay, 2.5, 0, Math.PI * 2); c.fillStyle = theme.accent; c.fill(); }
  c.globalAlpha = 1;
}
function frame() {
  tickMechs();
  if (needB) { needB = false; drawBase(); syncMechs(); }
  if (needT) { needT = false; drawTop(); }
  if (sideDirty && !$('side').contains(document.activeElement?.closest('input[type=text],input[type=number],input[type=range],textarea,select'))) { sideDirty = false; renderSide(); updateBar(); }
  requestAnimationFrame(frame);
}

// ---------------------------------------------------------------- hit tests + selection
const hover = { snap: null, p: null };
function pick(p, tol = 7 / view.z) {
  const o = getOrder();
  for (let i = o.length - 1; i >= 0; i--) { const x = o[i]; if (selectable(x) && Geo.distTo(x, p) <= tol + (x.t === 'stroke' ? 0 : x.w / 2)) return x; }
  return null;
}
const boxOf = (a, b) => [Math.min(a[0], b[0]), Math.min(a[1], b[1]), Math.abs(a[0] - b[0]), Math.abs(a[1] - b[1])];
function withGroups(ids) { const gs = new Set(ids.map(i => objs[i]?.g).filter(Boolean)); if (gs.size) for (const o of Object.values(objs)) if (gs.has(o.g) && selectable(o)) ids.push(o.id); return [...new Set(ids)]; }
function select(ids, add = false) { if (!add) sel.clear(); for (const id of withGroups([...ids])) sel.add(id); needT = true; sideDirty = true; }
function selectIn(poly, add) {
  const ids = getOrder().filter(o => selectable(o) && (() => { const s = o.t === 'stroke' ? o.pts : Geo.samples(o); return s.filter(p => Ink.inPoly(p, poly)).length >= Math.max(1, s.length * 0.6); })()).map(o => o.id);
  select(ids, add);
}
const selObjs = () => [...sel].map(id => objs[id]).filter(Boolean);

// ---------------------------------------------------------------- snapping
function snapPt(p, shift) {
  hover.snap = null;
  if (!S.snap) return p;
  const s = Geo.snap(p, getOrder().filter(visible), 10 / view.z, { grid: S.snapGrid ? gridStep() : 0 });
  hover.snap = s;
  if (s) return s.p;
  return p;
}

// ---------------------------------------------------------------- transform helpers
function xf(o, d) { // d = {dx, dy, rot, s, about}
  const [ax, ay] = d.about || [0, 0], cs = Math.cos(d.rot || 0), sn = Math.sin(d.rot || 0), s = d.s ?? 1;
  const P = p => { const x = (p[0] - ax) * s, y = (p[1] - ay) * s; return [ax + x * cs - y * sn + (d.dx || 0), ay + x * sn + y * cs + (d.dy || 0), ...p.slice(2)]; };
  const n = { ...o };
  for (const k of ['a', 'b', 'c', 'p', 'q']) if (o[k] && !(o.t === 'dim' && o.ref)) n[k] = P(o[k]);
  if (o.pts) n.pts = o.pts.map(P);
  if (o.t === 'text') { const q = P([o.x, o.y]); n.x = q[0]; n.y = q[1]; n.size = o.size * s; }
  for (const k of ['r', 'rx', 'ry']) if (o[k] != null) n[k] = o[k] * s;
  if (o.t === 'arc') { n.a0 = o.a0 + (d.rot || 0); n.a1 = o.a1 + (d.rot || 0); }
  if (o.t === 'rect' && d.rot && Math.abs(Math.sin(d.rot * 2)) > 1e-6) return Geo.rectEdges(o).map(e => ({ ...xf(e, d), id: newId(), z: o.z }));
  if (o.t === 'rect' && d.rot) { const a = P(o.p), b = P(o.q); n.p = a; n.q = b; }
  if (o.t === 'dim' && o.off != null) n.off = o.off * s;
  if (o.t === 'mech') { n.joints = o.joints.map(j => ({ ...j, p: P(j.p).slice(0, 2) })); n.sliders = (o.sliders || []).map(q => ({ ...q, a: P(q.a).slice(0, 2), b: P(q.b).slice(0, 2) })); if (o.len) n.len = o.len.map(v => v * s); delete n.cur; }
  return n;
}
const moveAll = (list, dx, dy) => list.flatMap(o => [xf(o, { dx, dy })].flat());

// ---------------------------------------------------------------- pointer input
let g = null, pend = null, spaceDown = false, penAt = 0, shiftNow = false;
const ptrs = new Map();
const capture = e => { try { cvT.setPointerCapture(e.pointerId); } catch { /* synthetic or finished pointer */ } };
const spOf = e => { const r = cvT.getBoundingClientRect(); return [e.clientX - r.left, e.clientY - r.top]; };
const pressure = () => 0.5; // pen pressure is ignored on purpose: the line has one width (Apple Pencil included)
const sw = k => S[k].w; // pen / highlighter width is in canvas units: the same on the sheet at any zoom, so it scales with the view
function setTool(t) {
  if (t !== S.tool) S.prev = S.tool;
  if (snipping) cancelSnip();
  S.tool = t; pend = null; hover.snap = null; endEdit(); chip(null);
  for (const b of document.querySelectorAll('[data-tool]')) b.classList.toggle('on', b.dataset.tool === t);
  $('tool').textContent = (document.querySelector(`[data-tool="${t}"]`)?.title || '').split(':')[0];
  $('hint').textContent = HINTS[t] || ''; savePrefs(); needT = true;
}
cvT.addEventListener('pointerdown', e => {
  const sp = spOf(e); shiftNow = e.shiftKey;
  if (e.pointerType === 'touch' && !S.finger) { // fingers pan and pinch; the Pencil draws
    if (performance.now() - penAt < 1200) return;
    ptrs.set(e.pointerId, sp); capture(e);
    if (ptrs.size === 2) { const [a, b] = [...ptrs.values()]; g = { kind: 'pinch', d0: hyp(b[0] - a[0], b[1] - a[1]) || 1, m0: [(a[0] + b[0]) / 2, (a[1] + b[1]) / 2], v0: { ...view } }; } else if (ptrs.size === 1) g = { kind: 'pan', s0: sp, v0: { ...view } };
    return;
  }
  if (e.pointerType === 'pen') { penAt = performance.now(); ptrs.clear(); }
  capture(e);
  if (e.button === 1 || (e.button === 0 && spaceDown)) { e.preventDefault(); g = { kind: 'pan', s0: sp, v0: { ...view }, id: e.pointerId }; return; }
  if (e.button !== 0) return;
  endEdit(); chip(null);
  if (snipping) { const p = toWorld(...sp); g = { kind: 'snip', p0: p, p1: p }; return; }
  down(e, sp, toWorld(...sp));
});
cvT.addEventListener('pointermove', e => {
  const sp = spOf(e), p = toWorld(...sp); shiftNow = e.shiftKey;
  $('coords').textContent = `${r2(p[0])}, ${r2(p[1])}`;
  if (e.pointerType === 'touch' && !S.finger) {
    if (!ptrs.has(e.pointerId)) return;
    ptrs.set(e.pointerId, sp);
    if (g?.kind === 'pinch' && ptrs.size >= 2) { const [a, b] = [...ptrs.values()], d = hyp(b[0] - a[0], b[1] - a[1]) || 1, m = [(a[0] + b[0]) / 2, (a[1] + b[1]) / 2], z = clamp(g.v0.z * d / g.d0, 0.03, 60), w0 = [g.m0[0] / g.v0.z + g.v0.x, g.m0[1] / g.v0.z + g.v0.y]; view = { z, x: w0[0] - m[0] / z, y: w0[1] - m[1] / z }; viewChanged(); } else if (g?.kind === 'pan') panTo(sp);
    return;
  }
  if (g) move(e, sp, p); else hoverMove(sp, p);
});
const up = e => {
  if (e.pointerType === 'touch' && !S.finger) { ptrs.delete(e.pointerId); if (!ptrs.size) g = null; else if (g?.kind === 'pinch') g = { kind: 'pan', s0: [...ptrs.values()][0], v0: { ...view } }; return; }
  if (!g) return;
  const sp = spOf(e), p = toWorld(...sp);
  if (['ink', 'erase', 'lasso', 'boxsel', 'snip', 'move', 'handle'].includes(g.kind) && hyp(sp[0] - (g.lastSp?.[0] ?? -1e9), sp[1] - (g.lastSp?.[1] ?? -1e9)) > 0.5) move(e, sp, p); // the release point counts even without a move event before it
  const gg = g;
  g = null;
  finish(gg, e, sp, p);
  dirty(); sideDirty = true;
};
cvT.addEventListener('pointerup', up);
cvT.addEventListener('pointercancel', e => { if (e.pointerType === 'touch') { ptrs.delete(e.pointerId); g = null; } else { g = null; dirty(); } });
document.addEventListener('touchmove', e => { if (e.target === cvT) e.preventDefault(); }, { passive: false });
cvT.addEventListener('contextmenu', e => e.preventDefault());
const panTo = sp => { view = { z: g.v0.z, x: g.v0.x - (sp[0] - g.s0[0]) / g.v0.z, y: g.v0.y - (sp[1] - g.s0[1]) / g.v0.z }; viewChanged(); };
cvT.addEventListener('wheel', e => { // small steps, centred on the cursor
  e.preventDefault();
  const sp = spOf(e), dy = e.deltaMode === 1 ? e.deltaY * 16 : e.deltaY;
  zoomAt(sp[0], sp[1], Math.exp(-dy * (e.ctrlKey ? 0.01 : 0.0015)));
}, { passive: false });
cvT.addEventListener('dblclick', e => {
  const p = toWorld(...spOf(e)), o = pick(p);
  if (o?.t === 'text') editText(o); else if (o?.t === 'dim') editDim(o);
});

function down(e, sp, p) {
  const t = S.tool;
  if (t === 'pen' || t === 'hl') {
    const sm = t === 'pen' ? S.pen.smooth : 0.1, q = [p[0], p[1], pressure(e)];
    g = { kind: 'ink', tool: t, pts: [q], sm: q, smooth: sm, t0: performance.now(), last: performance.now(), lastSp: sp, live: null, tried: false };
  } else if (t === 'eraser') { g = { kind: 'erase', removed: new Set(), at: p }; eraseAt(p); }
  else if (t === 'lasso' || t === 'box' || t === 'edit') {
    const hd = handleAt(sp);
    if (hd) { g = { kind: 'handle', ...hd, p0: p }; return; }
    const b = selB(), o = pick(p);
    const inSel = sel.size && ((o && sel.has(o.id)) || (b && Ink.inRect(p, b) && !o));
    if (inSel) g = { kind: 'move', p0: p, copy: e.ctrlKey || e.metaKey, moved: false };
    else if (o) { select([o.id], e.shiftKey); g = { kind: 'move', p0: p, copy: false, moved: false, clicked: o.id }; }
    else { if (!e.shiftKey) select([]); g = t === 'lasso' ? { kind: 'lasso', pts: [p], add: e.shiftKey } : { kind: 'boxsel', p0: p, p1: p, add: e.shiftKey }; }
  } else if (t === 'text') { const o = pick(p); if (o?.t === 'text') editText(o); else editText(null, p); }
  else if (GEO_TOOLS.includes(t) || t === 'dim') {
    const hd = t !== 'dim' && !pend && handleAt(sp); // fix what was just drawn without switching tools
    if (hd) g = { kind: 'handle', ...hd, p0: p }; else clickDraw(e, sp, p);
  }
  else if (t === 'trim' || t === 'split' || t === 'extend') editTool(t, p);
}
function move(e, sp, p) {
  const gk = g.kind;
  if (gk === 'pan') return panTo(sp);
  if (gk === 'ink') {
    const evs = e.getCoalescedEvents ? e.getCoalescedEvents() : [e];
    for (const ev of evs.length ? evs : [e]) {
      const q = toWorld(...spOf(ev)), pr = pressure(ev);
      if (g.live) { liveMove(snapPt(q)); continue; }
      g.sm = Ink.step(g.sm, [q[0], q[1], pr], g.smooth); g.pts.push(g.sm.slice());
    }
    if (hyp(sp[0] - g.lastSp[0], sp[1] - g.lastSp[1]) > 2.5) { g.last = performance.now(); g.lastSp = sp; g.tried = false; }
    needT = true;
  } else if (gk === 'erase') { // sample the whole path, a fast swipe must not jump over a thin line
    const n = Math.ceil(Geo.dist(g.at, p) / (4 / view.z));
    for (let i = 1; i <= n; i++) eraseAt(Geo.lerp(g.at, p, i / n));
    g.at = p; needB = true; needT = true;
  }
  else if (gk === 'lasso') { g.pts.push(p); needT = true; }
  else if (gk === 'boxsel' || gk === 'snip') { g.p1 = p; needT = true; }
  else if (gk === 'move') {
    let dx = p[0] - g.p0[0], dy = p[1] - g.p0[1];
    if (!g.moved && hyp(dx, dy) * view.z < 3) return;
    g.moved = true;
    if (e.shiftKey) { if (Math.abs(dx) > Math.abs(dy)) dy = 0; else dx = 0; }
    const list = selObjs().filter(o => selectable(o));
    for (const k in ovr) delete ovr[k];
    if (g.copy) g.copies = moveAll(list, dx, dy).map(o => ({ ...o, id: newId() }));
    else for (const o of list) { const n = xf(o, { dx, dy }); if (!Array.isArray(n)) ovr[o.id] = n; }
    g.d = [dx, dy]; dirty();
  } else if (gk === 'handle') {
    const q = snapPt(p), o = objs[g.id];
    ovr[g.id] = applyHandle(o, g.k, q); dirty();
  } else if (gk === 'dragdraw') { hoverMove(sp, p); }
}
function finish(gg, e, sp, p) {
  const gk = gg.kind;
  if (gk === 'ink') return finishInk(gg);
  if (gk === 'erase') { if (gg.removed.size) commit([], withDims([...gg.removed])); return; }
  if (gk === 'snip') {
    cancelSnip();
    const b = boxOf(gg.p0, gg.p1);
    if (b[2] * view.z < 8 || b[3] * view.z < 8) { toast('Oblast je moc malá, klikni na Odeslat do AI a táhni znovu'); return; }
    sendRegion(b.map(r2), getOrder().filter(o => visible(o) && (o.t === 'dim' || Ink.overlap(bnd(o), b))).map(o => o.id));
    return;
  }
  if (gk === 'lasso') { if (gg.pts.length > 2) selectIn(gg.pts, gg.add); needT = true; return; }
  if (gk === 'boxsel') { const b = boxOf(gg.p0, gg.p1); if (b[2] * view.z > 3 || b[3] * view.z > 3) selectIn([[b[0], b[1]], [b[0] + b[2], b[1]], [b[0] + b[2], b[1] + b[3]], [b[0], b[1] + b[3]]], gg.add); return; }
  if (gk === 'move') {
    for (const k in ovr) delete ovr[k];
    if (!gg.moved) { const o = objs[gg.clicked]; if (o?.t === 'dim' && sel.size === 1) editDim(o); return; }
    const list = selObjs().filter(selectable);
    if (gg.copy) { const cp = gg.copies || []; commit(cp); select(cp.map(o => o.id)); } else commit(moveAll(list, gg.d[0], gg.d[1]).filter(o => o));
    return;
  }
  if (gk === 'handle') { const n = ovr[gg.id]; delete ovr[gg.id]; if (n) { commit([n]); offerAlign(n); } return; }
  if (gk === 'dragdraw') dragEnd(gg, sp, p);
}

// ---- free ink: smoothing, QuickShape+, scribble erase
function finishInk(gg) {
  const pts = Ink.simplify(gg.pts, 0.35 / view.z);
  if (gg.live) { const o = shapeObj(gg.live); commit([o]); select([o.id]); offerAlign(o); return; }
  if (gg.tool === 'pen' && S.scribble && Geo.isScribble(gg.pts.map(q => q.slice(0, 2)), performance.now() - gg.t0)) {
    const r = scribbleErase(gg.pts);
    if (r) { commit(r.put, r.del); toast('Smazáno čmáráním · Ctrl+Z vrátí', false); return; }
  }
  const col = gg.tool === 'hl' ? S.hl.color : S.pen.color;
  commit([{ id: newId(), t: 'stroke', layer: S.layer, z: nextZ(), color: col, w: sw(gg.tool), alpha: S[gg.tool].alpha, tool: gg.tool, pts: pts.map(q => [r2(q[0]), r2(q[1]), r2(q[2] ?? 0.5)]) }]);
}
setInterval(() => { // QuickShape+: hold the end of the stroke
  if (g?.kind !== 'ink' || g.tool !== 'pen' || !S.quick || g.live || g.tried || g.pts.length < 6) return;
  if (performance.now() - g.last < S.hold) return;
  g.tried = true;
  const sh = Geo.recognize(g.pts.map(q => q.slice(0, 2)), S.tol);
  if (!sh) return;
  const p = g.pts[g.pts.length - 1];
  g.live = { ...sh };
  if (sh.t === 'rect') { const cs = [sh.p, [sh.q[0], sh.p[1]], sh.q, [sh.p[0], sh.q[1]]]; g.fixed = cs.reduce((m, q) => (Geo.dist(q, p) > Geo.dist(m, p) ? q : m)); }
  needT = true; toast(`Tvar: ${{ line: 'úsečka', circle: 'kružnice', arc: 'oblouk', rect: 'obdélník', ellipse: 'elipsa' }[sh.t]} · táhni pro úpravu, pusť pro potvrzení`, false, 1500);
}, 40);
function liveMove(p) {
  const l = g.live;
  if (l.t === 'line') l.b = p; else if (l.t === 'circle') l.r = Math.max(0.01, Geo.dist(l.c, p));
  else if (l.t === 'rect') { l.p = g.fixed; l.q = p; } else if (l.t === 'ellipse') { l.rx = Math.max(0.01, Math.abs(p[0] - l.c[0])); l.ry = Math.max(0.01, Math.abs(p[1] - l.c[1])); }
  needT = true;
}
function shapeObj(s) {
  const o = { id: newId(), layer: S.cons ? 5 : S.layer, z: nextZ(), color: S.pen.color, w: sw('pen'), ...(S.cons ? { cons: true } : {}), ...s };
  for (const k of ['a', 'b', 'c', 'p', 'q']) if (o[k]) o[k] = [r2(o[k][0]), r2(o[k][1])];
  for (const k of ['r', 'rx', 'ry', 'a0', 'a1']) if (o[k] != null) o[k] = Math.round(o[k] * 1000) / 1000;
  return o;
}
function scribbleErase(pts) {
  const tol = 8 / view.z, put = [], del = [], bb = Ink.union(pts.map(q => [q[0], q[1], 0, 0]));
  const box = [bb[0] - tol, bb[1] - tol, bb[2] + 2 * tol, bb[3] + 2 * tol];
  for (const o of getOrder()) {
    if (!selectable(o) || o.t === 'dim') continue;
    const near = pts.filter(q => Geo.distTo(o, q) <= tol + (o.t === 'stroke' ? 0 : o.w / 2));
    if (near.length < 3) continue;
    del.push(o.id);
    if (o.t === 'stroke') {
      let run = [];
      const flush = () => { if (run.length > 1) put.push({ ...o, id: newId(), pts: run }); run = []; };
      for (const q of o.pts) { if (Ink.inRect(q, box)) flush(); else run.push(q); }
      flush();
    } else if (Geo.GEO.has(o.t)) {
      const mid = [near.reduce((s, q) => s + q[0], 0) / near.length, near.reduce((s, q) => s + q[1], 0) / near.length];
      for (const r of Geo.trim(o, mid, getOrder().filter(x => x.id !== o.id && visible(x)))) put.push({ ...r, id: newId(), z: o.z });
    }
  }
  return del.length ? { put, del } : null;
}
function eraseAt(p) {
  const r = 10 / view.z;
  for (const o of getOrder()) if (selectable(o) && !g.removed.has(o.id) && (o.t === 'stroke' ? Ink.hit(o, p, r) : Geo.distTo(o, p) <= r + o.w / 2)) g.removed.add(o.id);
}
function handleAt(sp) {
  if (sel.size !== 1) return null;
  const o = objs[[...sel][0]];
  if (!o || !selectable(o)) return null;
  for (const hd of handlesOf(o)) { const q = toScreen(...hd.p); if (hyp(q[0] - sp[0], q[1] - sp[1]) <= 10) return { id: o.id, k: hd.k }; }
  return null;
}

// ---- geometry tools: drag or click-click
function clickDraw(e, sp, p) {
  const t = S.tool, q = snapPt(p);
  if (t === 'dim') return dimClick(e, p, q);
  if (!pend) { pend = { tool: t, pts: [q] }; g = { kind: 'dragdraw', sp0: sp }; hover.p = q; return; }
  pend.pts.push(q);
  if (pend.pts.length >= needPts(t)) completeDraw();
}
function dragEnd(gg, sp, p) {
  if (!pend || hyp(sp[0] - gg.sp0[0], sp[1] - gg.sp0[1]) <= 6) return; // a click: wait for the next one
  pend.pts.push(snapPt(p)); // a drag: the release point is the next point
  if (pend.pts.length >= needPts(pend.tool)) completeDraw();
}
const needPts = t => (t === 'arc' || t === 'arc3' ? 3 : 2);
function completeDraw() {
  const [a, b, c] = pend.pts, t = pend.tool;
  let s = null;
  if (t === 'line') s = { t, a, b }; else if (t === 'circle') s = { t, c: a, r: Geo.dist(a, b) };
  else if (t === 'rect') s = { t, p: a, q: b }; else if (t === 'ellipse') s = { t, c: [(a[0] + b[0]) / 2, (a[1] + b[1]) / 2], rx: Math.abs(b[0] - a[0]) / 2, ry: Math.abs(b[1] - a[1]) / 2 };
  else if (t === 'arc3') s = Geo.arcThrough(a, c, b) || { t: 'line', a, b }; // three points on one line: a straight line
  else if (t === 'arc') { const a0 = Math.atan2(b[1] - a[1], b[0] - a[0]); s = { t, c: a, r: Geo.dist(a, b), a0, a1: Math.atan2(c[1] - a[1], c[0] - a[0]) }; }
  pend = null; hover.snap = null;
  if (!s || (s.r !== undefined && s.r < 0.01) || (s.t === 'line' && Geo.dist(s.a, s.b) < 0.01) || (s.t === 'ellipse' && (s.rx < 0.01 || s.ry < 0.01))) { needT = true; return; }
  const o = shapeObj(s); commit([o]); select([o.id]); offerAlign(o);
}
function previewObj() {
  if (!pend || !hover.p) return null;
  const [a, b] = pend.pts, q = hover.p, t = pend.tool;
  if (t === 'line') return { t, a, b: q, w: sw('pen') };
  if (t === 'circle') return { t, c: a, r: Geo.dist(a, q) || 0.01, w: sw('pen') };
  if (t === 'rect') return { t, p: a, q, w: sw('pen') };
  if (t === 'ellipse') return { t, c: [(a[0] + q[0]) / 2, (a[1] + q[1]) / 2], rx: Math.abs(q[0] - a[0]) / 2 || 0.01, ry: Math.abs(q[1] - a[1]) / 2 || 0.01, w: sw('pen') };
  if (t === 'arc3') return b ? { ...(Geo.arcThrough(a, q, b) || { t: 'line', a, b }), w: sw('pen') } : { t: 'line', a, b: q, w: sw('pen'), cons: true };
  if (t === 'arc') { if (!b) return { t: 'line', a, b: q, w: sw('pen'), cons: true }; const a0 = Math.atan2(b[1] - a[1], b[0] - a[0]); return { t, c: a, r: Geo.dist(a, b), a0, a1: Math.atan2(q[1] - a[1], q[0] - a[0]), w: sw('pen') }; }
  if (t === 'dim') return dimDraft(q);
  return null;
}
function hoverMove(sp, p) {
  const t = S.tool;
  cvT.style.cursor = handleAt(sp) ? 'grab' : (t === 'edit' || t === 'lasso' || t === 'box') && pick(p) ? 'move' : t === 'eraser' ? 'cell' : 'crosshair';
  if (GEO_TOOLS.includes(t) || t === 'dim' || t === 'trim' || t === 'split' || t === 'extend') { hover.p = snapPt(p); needT = true; } else if (hover.snap) { hover.snap = null; needT = true; }
}

// ---- dimensions
function dimClick(e, p, q) {
  if (!pend) {
    const o = pick(p);
    if (o && ['line', 'rect', 'circle', 'arc'].includes(o.t)) {
      const edge = o.t === 'rect' ? Geo.rectEdges(o).reduce((bi, e, i, es) => (Geo.distTo(e, p) < Geo.distTo(es[bi], p) ? i : bi), 0) : undefined;
      pend = { tool: 'dim', ref: o, edge, pts: [] }; hover.p = q; needT = true;
      toast(o.t === 'circle' || o.t === 'arc' ? 'Klikni, kam dát kótu · Shift přepne průměr / poloměr' : 'Klikni, kam dát kótu (na kterou stranu a jak daleko)', false, 1800);
      return;
    }
    pend = { tool: 'dim', pts: [q] }; toast('Volná kóta: klikni druhý bod, pak místo kóty · Esc zruší', false, 2200); return;
  }
  const d = dimDraft(q);
  if (pend.ref || pend.pts.length === 2) { pend = null; hover.snap = null; const o = { ...d, id: newId(), layer: 4, z: nextZ(), color: 'ink', w: 0.8 }; commit([o]); select([o.id]); return; }
  pend.pts.push(q);
}
function dimDraft(q) {
  const base = { t: 'dim', w: 0.8, size: r2(11 / view.z) }; // ~11 px text at the zoom it is made at
  if (pend.ref) {
    const r = pend.ref;
    if (r.t === 'line' || r.t === 'rect') {
      const e = r.t === 'rect' ? { edge: pend.edge } : {}, d = Geo.dimGeom({ ...base, ref: r.id, ...e, off: 0 });
      return { ...base, ref: r.id, ...e, kind: 'lin', off: Math.round(((q[0] - d.a[0]) * d.n[0] + (q[1] - d.a[1]) * d.n[1]) * 10) / 10 };
    }
    return { ...base, ref: r.id, kind: (r.t === 'arc') !== shiftNow ? 'rad' : 'dia', ang: Math.atan2(q[1] - r.c[1], q[0] - r.c[0]) };
  }
  const [a, b] = pend.pts;
  if (!b) return { ...base, kind: 'lin', a, b: q, off: 0 };
  const d = Geo.dimGeom({ ...base, a, b, off: 0 });
  return { ...base, kind: 'lin', a, b, off: Math.round(((q[0] - a[0]) * d.n[0] + (q[1] - a[1]) * d.n[1]) * 10) / 10 };
}
function editDim(o) {
  const d = Geo.dimGeom(o), el = $('numEd'), [x, y] = toScreen(...d.label);
  el.style.display = 'block'; el.style.left = `${x - 45}px`; el.style.top = `${y - 12}px`; el.value = r2(d.len); el.focus(); el.select();
  el.onkeydown = ev => {
    if (ev.key === 'Escape') endEdit();
    if (ev.key === 'Enter') { try { const v = parseFloat(el.value); commit(Geo.setDimValue(o, v, objs)); endEdit(); } catch (err) { toast(err.message, true); } }
    ev.stopPropagation();
  };
  el.onblur = endEdit;
}

// ---- trim / split / extend
function editTool(t, p) {
  const o = pick(p, 10 / view.z);
  if (!o || !Geo.GEO.has(o.t)) { toast('Klikni na čáru, kružnici, oblouk nebo obdélník'); return; }
  const others = getOrder().filter(x => visible(x) && x.id !== o.id);
  let parts;
  if (t === 'trim') parts = Geo.trim(o, p, others);
  else if (t === 'split') { parts = Geo.split(o, snapPt(p)); if (parts.length === 1 && parts[0] === o) { toast('Tento objekt nelze rozdělit'); return; } }
  else { const r = Geo.extend(o, p, others); if (!r) { toast('Není kam prodloužit'); return; } commit([r]); return; }
  commit(parts.map(x => ({ ...x, id: newId(), z: o.z })), withDims([o.id]));
}

// ---- temporary alignment chip
let chipT = 0;
function chip(o) {
  const el = $('chip'); clearTimeout(chipT);
  if (!o) { el.style.display = 'none'; return; }
  const [x, y] = toScreen((o.a[0] + o.b[0]) / 2, (o.a[1] + o.b[1]) / 2);
  el.replaceChildren(h('button', { className: 'primary', textContent: 'Srovnat', title: 'Přesně vodorovně / svisle', on: { click: () => { const s = Geo.straighten(objs[o.id] || o); if (s) commit([s]); chip(null); } } }));
  Object.assign(el.style, { display: 'block', left: `${x + 8}px`, top: `${y + 8}px` });
  chipT = setTimeout(() => chip(null), 5000);
}
function offerAlign(o) { if (S.align && o.t === 'line' && !o.cons && Geo.straighten(o)) chip(o); }

// ---- text editing
function endEdit() { const t = $('ed'); if (t.style.display === 'block') t.blur(); const n = $('numEd'); if (n.style.display === 'block') { n.style.display = 'none'; n.onblur = null; } }
function editText(o, p) {
  const t = $('ed'), size = o ? o.size : 14, at = o ? [o.x, o.y] : p, [x, y] = toScreen(...at);
  Object.assign(t.style, { display: 'block', left: `${x}px`, top: `${y}px`, fontSize: `${size * view.z}px`, color: o ? (o.color === 'ink' ? theme.ink : o.color) : theme.ink });
  t.value = o ? o.s : ''; t.focus();
  const done = () => {
    t.removeEventListener('blur', done); t.style.display = 'none';
    const s = t.value.replace(/\s+$/, '');
    if (o) { if (!s) commit([], [o.id]); else if (s !== o.s) commit([{ ...o, s }]); }
    else if (s) commit([{ id: newId(), t: 'text', layer: 3, z: nextZ(), color: S.pen.color, w: 1, x: r2(p[0]), y: r2(p[1]), s, size: 14 }]);
    dirty();
  };
  t.addEventListener('blur', done);
  t.onkeydown = ev => { if (ev.key === 'Escape') { t.value = o ? o.s : ''; t.blur(); } if (ev.key === 'Enter' && (ev.ctrlKey || ev.metaKey)) t.blur(); ev.stopPropagation(); };
}

// ---------------------------------------------------------------- selection actions
let clip = [];
const withDims = ids => [...new Set([...ids, ...Object.values(objs).filter(o => o.t === 'dim' && ids.includes(o.ref)).map(o => o.id)])]; // a dim goes with the object it measures
function del() { const ids = [...sel].filter(id => selectable(objs[id] || { layer: 1 })); if (!ids.length) return; commit([], withDims(ids)); sel.clear(); }
function copy() { clip = selObjs().map(o => JSON.parse(JSON.stringify(o))); if (clip.length) toast(`Zkopírováno: ${clip.length}`, false, 900); }
function paste() {
  if (!clip.length) return;
  const gmap = {}, cp = clip.flatMap(o => [xf(o, { dx: 15, dy: 15 })].flat()).map(o => ({ ...o, id: newId(), z: nextZ(), g: o.g ? (gmap[o.g] ??= newId()) : undefined }));
  const ids = new Map(clip.map((o, i) => [o.id, cp[i]?.id]));
  for (const o of cp) if (o.ref && ids.has(o.ref)) o.ref = ids.get(o.ref);
  commit(cp); select(cp.map(o => o.id));
}
function group(on) { const list = selObjs(); if (list.length < 2 && on) return; const id = newId(); commit(list.map(o => ({ ...o, g: on ? id : undefined }))); }
function nudge(dx, dy) { const list = selObjs().filter(selectable); if (list.length) commit(moveAll(list, dx, dy)); }

// ---------------------------------------------------------------- right panel
const ROWS = {
  line: o => [num('A x', o.a[0], v => ({ a: [v, o.a[1]] })), num('A y', o.a[1], v => ({ a: [o.a[0], v] })), num('B x', o.b[0], v => ({ b: [v, o.b[1]] })), num('B y', o.b[1], v => ({ b: [o.b[0], v] })),
    num('Délka', Geo.dist(o.a, o.b), v => { const L = Geo.dist(o.a, o.b) || 1; return { b: [o.a[0] + (o.b[0] - o.a[0]) / L * v, o.a[1] + (o.b[1] - o.a[1]) / L * v] }; }),
    num('Úhel °', (Math.atan2(o.b[1] - o.a[1], o.b[0] - o.a[0]) * 180) / Math.PI, v => { const L = Geo.dist(o.a, o.b), a = (v * Math.PI) / 180; return { b: [o.a[0] + L * Math.cos(a), o.a[1] + L * Math.sin(a)] }; }), chk('Šipka', o.arrow, v => ({ arrow: v || undefined }))],
  circle: o => [num('Střed x', o.c[0], v => ({ c: [v, o.c[1]] })), num('Střed y', o.c[1], v => ({ c: [o.c[0], v] })), num('Poloměr', o.r, v => ({ r: v })), num('Průměr Ø', o.r * 2, v => ({ r: v / 2 }))],
  arc: o => [num('Střed x', o.c[0], v => ({ c: [v, o.c[1]] })), num('Střed y', o.c[1], v => ({ c: [o.c[0], v] })), num('Poloměr', o.r, v => ({ r: v })), num('Počátek °', (o.a0 * 180) / Math.PI, v => ({ a0: (v * Math.PI) / 180 })), num('Konec °', (o.a1 * 180) / Math.PI, v => ({ a1: (v * Math.PI) / 180 }))],
  rect: o => [num('Roh 1 x', o.p[0], v => ({ p: [v, o.p[1]] })), num('Roh 1 y', o.p[1], v => ({ p: [o.p[0], v] })), num('Šířka', Math.abs(o.q[0] - o.p[0]), v => ({ q: [o.p[0] + v * Math.sign(o.q[0] - o.p[0] || 1), o.q[1]] })), num('Výška', Math.abs(o.q[1] - o.p[1]), v => ({ q: [o.q[0], o.p[1] + v * Math.sign(o.q[1] - o.p[1] || 1)] }))],
  ellipse: o => [num('Střed x', o.c[0], v => ({ c: [v, o.c[1]] })), num('Střed y', o.c[1], v => ({ c: [o.c[0], v] })), num('Poloosa X', o.rx, v => ({ rx: v })), num('Poloosa Y', o.ry, v => ({ ry: v }))],
  dim: o => [num('Hodnota', Geo.dimGeom(o).len, null, v => Geo.setDimValue(o, v, objs)), o.kind === 'lin' || !o.kind ? num('Odsazení', o.off ?? 20, v => ({ off: v })) : null, txt('Text', o.txt || '', v => ({ txt: v || undefined }))],
  text: o => [num('Velikost', o.size, v => ({ size: v })), num('x', o.x, v => ({ x: v })), num('y', o.y, v => ({ y: v }))],
  stroke: () => [],
  mech: o => [txt('Název', o.name || '', v => ({ name: v }))],
};
function num(label, val, patch, whole) { return { label, val: r2(val), patch, whole }; }
function chk(label, val, patch) { return { label, check: !!val, patch }; }
function txt(label, val, patch) { return { label, text: val, patch }; }
function fieldEl(o, f) {
  if (!f) return null;
  const upd = v => { try { commit(f.whole ? f.whole(v) : [{ ...o, ...f.patch(v) }]); } catch (e) { toast(e.message, true); } };
  let inp;
  if (f.check !== undefined) inp = h('input', { type: 'checkbox', checked: f.check, on: { change: e => upd(e.target.checked) } });
  else if (f.text !== undefined) inp = h('input', { type: 'text', value: f.text, on: { change: e => upd(e.target.value) } });
  else inp = h('input', { type: 'number', step: 'any', value: f.val, on: { change: e => { const v = parseFloat(e.target.value); if (Number.isFinite(v)) upd(v); } } });
  return h('div', { className: 'f' }, h('span', { textContent: f.label }), inp);
}
const colorRow = (o, on) => h('div', { className: 'f' }, h('span', { textContent: 'Barva' }), h('div', { style: 'display:flex;gap:4px;flex-wrap:wrap' }, COLORS.map(c => h('button', { className: `sw${(o.color || 'ink') === c ? ' on' : ''}`, style: `background:${c === 'ink' ? theme.ink : c}`, title: c, on: { click: () => on(c) } }))));
const layerSel = (cur, on) => h('div', { className: 'f' }, h('span', { textContent: 'Hladina' }), h('select', { on: { change: e => on(+e.target.value) } }, layers.map(l => h('option', { value: l.n, selected: l.n === cur, textContent: `${String(l.n).padStart(2, '0')} ${l.name}` }))));
function layersPanel() {
  const cnt = {}; for (const o of Object.values(objs)) cnt[o.layer] = (cnt[o.layer] || 0) + 1;
  return [h('h4', { textContent: 'Hladiny' }), h('div', { className: 'muted', textContent: 'Oko skrývá hladinu jen na tomto zařízení.' }), ...layers.map(l => h('div', { className: `lay${l.vis ? '' : ' off'}` },
    h('input', { type: 'radio', name: 'actl', checked: S.layer === l.n, title: 'Aktivní hladina pro kreslení', on: { change: () => { S.layer = l.n; savePrefs(); } } }),
    h('button', { textContent: l.vis ? '👁' : '🚫', title: l.vis ? 'Skrýt hladinu' : 'Zobrazit hladinu', on: { click: () => setLayer(l.n, { vis: !l.vis }) } }),
    h('button', { textContent: l.lock ? '🔒' : '○', title: 'Uzamknout', on: { click: () => setLayer(l.n, { lock: !l.lock }) } }),
    h('span', { className: 'n', textContent: `${String(l.n).padStart(2, '0')} ${l.name}`, title: l.name }), h('span', { className: 'muted', textContent: cnt[l.n] || '' }),
    h('input', { type: 'range', min: 0.1, max: 1, step: 0.05, value: l.op, title: 'Průhlednost', on: { change: e => setLayer(l.n, { op: +e.target.value }) } })))];
}
function idlePanel() {
  const el = [...layersPanel()];
  el.push(h('h4', { textContent: 'Pojmenované oblasti' }), h('div', { className: 'lst' }, regions.map(r => h('button', { className: 'ghost', title: 'Přejít', on: { click: () => goRect(r.rect) } }, r.name, h('span', { className: 'muted', textContent: '×', title: 'Smazat', on: { click: ev => { ev.stopPropagation(); regions = regions.filter(x => x.id !== r.id); sideDirty = true; send({ regions: { [r.id]: null } }); } } })))),
    h('button', { className: 'ghost', textContent: '+ Uložit aktuální pohled', on: { click: () => { const name = prompt('Název oblasti'); if (!name) return; const id = newId(), rect = viewRect().map(r2); regions = [...regions, { id, name, rect }]; sideDirty = true; send({ regions: { [id]: { name, rect } } }); } } }));
  el.push(h('h4', { textContent: 'Verze projektu' }), h('div', { className: 'lst' }, [...snaps].reverse().slice(0, 8).map(s => h('button', { className: 'ghost', title: 'Obnovit jako novou revizi', on: { click: () => restoreSnap(s) } }, `${s.auto ? '⟲ ' : '★ '}${s.name}`, h('span', { className: 'muted', textContent: new Date(s.created * 1000).toLocaleTimeString() })))),
    h('button', { className: 'ghost', textContent: '+ Pojmenovaná verze', on: { click: async () => { const name = prompt('Název verze'); if (name) { await call('/api/canvas/snapshot', { name }).catch(e => toast(e.message, true)); } } } }));
  return el;
}
async function restoreSnap(s) {
  if (!confirm(`Obnovit „${s.name}“? Aktuální stav se předtím uloží jako verze.`)) return;
  try { await call('/api/canvas/restore', { id: s.id }); sel.clear(); toast('Obnoveno'); } catch (e) { toast(e.message, true); }
}
const setSide = (...k) => $('side').replaceChildren(...k.flat().filter(Boolean));
function renderSide() {
  const list = selObjs();
  if (!list.length) return setSide(...idlePanel());
  if (list.length === 1) {
    const o = list[0], tl = { line: 'Úsečka', circle: 'Kružnice', arc: 'Oblouk', rect: 'Obdélník', ellipse: 'Elipsa', dim: 'Kóta', text: 'Text', stroke: 'Ručně kreslený tah', mech: 'Mechanismus' }[o.t];
    const patch = p => commit([{ ...o, ...p }]);
    return setSide(h('h4', { textContent: tl }),
      ...(ROWS[o.t]?.(o) || []).map(f => fieldEl(o, f)),
      o.t === 'text' ? h('textarea', { className: 'in', value: o.s, on: { change: e => patch({ s: e.target.value }) } }) : null,
      o.t !== 'dim' && o.t !== 'text' ? h('div', { className: 'f' }, h('span', { textContent: 'Tloušťka' }), h('input', { type: 'number', step: 0.1, min: 0.1, value: o.w, on: { change: e => patch({ w: Math.max(0.1, +e.target.value || o.w) }) } })) : null,
      colorRow(o, c => patch({ color: c })), layerSel(o.layer, n => patch({ layer: n })),
      Geo.GEO.has(o.t) || o.t === 'ellipse' ? h('div', { className: 'f' }, h('span', { textContent: 'Konstrukční' }), h('input', { type: 'checkbox', checked: !!o.cons, on: { change: e => patch({ cons: e.target.checked || undefined, layer: e.target.checked ? 5 : o.layer }) } })) : null,
      o.g ? h('div', { className: 'muted', textContent: 'Součást skupiny' }) : null,
      o.t === 'mech' ? h('button', { className: 'ghost', textContent: 'Ovládací panel', on: { click: () => { const st = mst(o); st.min = false; st.hidden = false; syncMechs(true); } } }) : null, actionsRow());
  }
  const types = {}; for (const o of list) types[o.t] = (types[o.t] || 0) + 1;
  const b = selB(), ctr = [b[0] + b[2] / 2, b[1] + b[3] / 2], t = { dx: 0, dy: 0, rot: 0, s: 100 };
  const tf = (label, k) => h('div', { className: 'f' }, h('span', { textContent: label }), h('input', { type: 'number', step: 'any', value: t[k], on: { input: e => { t[k] = +e.target.value || 0; } } }));
  setSide(h('h4', { textContent: `Výběr: ${list.length} objektů` }), h('div', { className: 'muted', textContent: Object.entries(types).map(([k, v]) => `${v}× ${k}`).join(', ') }),
    h('h4', { textContent: 'Transformace' }), tf('Posun x', 'dx'), tf('Posun y', 'dy'), tf('Otočení °', 'rot'), tf('Měřítko %', 's'),
    h('button', { className: 'ghost', textContent: 'Použít', on: { click: () => { const sel2 = selObjs().filter(selectable); commit(sel2.flatMap(o => [xf(o, { dx: t.dx, dy: t.dy, rot: (t.rot * Math.PI) / 180, s: (t.s || 100) / 100, about: ctr })].flat())); } } }),
    layerSel(list[0].layer, n => commit(list.map(o => ({ ...o, layer: n })))), colorRow(list[0], c => commit(list.map(o => ({ ...o, color: c })))), actionsRow());
}
function actionsRow() {
  const list = selObjs();
  return h('div', { style: 'display:flex;gap:6px;flex-wrap:wrap;margin-top:10px' },
    h('button', { className: 'ghost', textContent: 'Kopírovat', on: { click: () => { copy(); paste(); } } }),
    list.length > 1 ? h('button', { className: 'ghost', textContent: list.some(o => o.g) ? 'Rozdělit skupinu' : 'Seskupit', on: { click: () => group(!list.some(o => o.g)) } }) : null,
    h('button', { className: 'ghost danger', textContent: 'Smazat', on: { click: del } }),
    h('button', { className: 'ghost', textContent: 'Odeslat do AI ✦', on: { click: sendSelection } }));
}
function goRect(r) { const z = clamp(Math.min(W / (r[2] || 1), H / (r[3] || 1)) * 0.9, 0.03, 60); view = { z, x: r[0] + r[2] / 2 - W / 2 / z, y: r[1] + r[3] / 2 - H / 2 / z }; viewChanged(); }
function updateBar() {
  $('bSnap').classList.toggle('on', S.snap); $('bCons').classList.toggle('on', S.cons); $('bSide').classList.toggle('on', S.side); $('side').classList.toggle('hide', !S.side);
  $('bUndo').disabled = !undos.length; $('bRedo').disabled = !redos.length; $('bAI').disabled = false;
}

// ---------------------------------------------------------------- AI: send, requests, briefing bubbles, proposals
function renderRegion(rect, maxPx = 1400) {
  const scale = clamp(maxPx / Math.max(rect[2], rect[3]), 0.2, 6), cv = document.createElement('canvas');
  cv.width = Math.ceil(rect[2] * scale); cv.height = Math.ceil(rect[3] * scale);
  const c = cv.getContext('2d');
  c.fillStyle = '#ffffff'; c.fillRect(0, 0, cv.width, cv.height); c.setTransform(scale, 0, 0, scale, -rect[0] * scale, -rect[1] * scale);
  Geo.ctx.byId = objs;
  for (const o of getOrder()) if (visible(o) && (o.t === 'dim' || Ink.overlap(bnd(o), rect))) { c.globalAlpha = lay(o).op; drawObj(c, o, '#111111', 1 / scale); c.globalAlpha = 1; }
  return { url: cv.toDataURL('image/png'), scale };
}
// Send to AI like a snipping tool: click the button, drag a box, then scribble on the shot and comment below it.
let sendCtx = null, snipping = false, sInk = null;
function openSend() {
  endEdit(); chip(null); pend = null; snipping = true; $('bAI').classList.add('on');
  $('hint').textContent = 'Táhni obdélník přes oblast, kterou má AI zpracovat · Esc zruší'; toast('Označ oblast tažením', false, 1500);
}
function cancelSnip() { snipping = false; $('bAI').classList.remove('on'); $('hint').textContent = HINTS[S.tool] || ''; needT = true; }
function sendSelection() { // the panel button: the selection already says where
  const list = selObjs();
  if (!list.length) return openSend();
  const b = unionB(list.map(bnd)), m = Math.max(8, Math.max(b[2], b[3]) * 0.06);
  sendRegion([b[0] - m, b[1] - m, b[2] + 2 * m, b[3] + 2 * m].map(r2), list.map(o => o.id));
}
function sendRegion(rect, ids) {
  const r = renderRegion(rect), img = new Image();
  sendCtx = { rect, ids, r, marks: [] };
  img.onload = () => { const cv = $('sendCv'); sendCtx.img = img; cv.width = img.width; cv.height = img.height; fitSendCv(); drawSendCv(); };
  img.src = r.url;
  $('sendCtx').value = S.ctx; $('sendAut').value = S.aut;
  $('sendInfo').textContent = `${ids.length} objektů v oblasti`; $('modal').classList.add('open'); $('sendText').focus();
}
function fitSendCv() { const cv = $('sendCv'), k = Math.min(Math.min(880, innerWidth - 60) / cv.width, (innerHeight * 0.5) / cv.height); cv.style.width = `${cv.width * k}px`; cv.style.height = `${cv.height * k}px`; }
function drawSendCv() {
  const cv = $('sendCv'), c = cv.getContext('2d');
  if (!sendCtx?.img) return;
  c.drawImage(sendCtx.img, 0, 0);
  c.strokeStyle = '#e5484d'; c.lineWidth = Math.max(3, cv.width / 260); c.lineCap = 'round'; c.lineJoin = 'round';
  for (const m of sendCtx.marks) { c.beginPath(); m.forEach((p, i) => (i ? c.lineTo(p[0], p[1]) : c.moveTo(p[0], p[1]))); c.stroke(); }
}
{
  const cv = $('sendCv'), at = e => { const b = cv.getBoundingClientRect(); return [((e.clientX - b.left) * cv.width) / b.width, ((e.clientY - b.top) * cv.height) / b.height]; };
  cv.addEventListener('pointerdown', e => { if (!sendCtx?.img) return; try { cv.setPointerCapture(e.pointerId); } catch { /* ignore */ } sInk = [at(e)]; sendCtx.marks.push(sInk); drawSendCv(); });
  cv.addEventListener('pointermove', e => { if (sInk) { sInk.push(at(e)); drawSendCv(); } });
  const end = () => { if (sInk?.length === 1) sInk.push([sInk[0][0] + 0.5, sInk[0][1]]); sInk = null; drawSendCv(); };
  cv.addEventListener('pointerup', end); cv.addEventListener('pointercancel', end);
  $('inkUndo').onclick = () => { sendCtx?.marks.pop(); drawSendCv(); };
  $('inkClear').onclick = () => { if (sendCtx) sendCtx.marks.length = 0; drawSendCv(); };
  addEventListener('resize', () => { if ($('modal').classList.contains('open')) fitSendCv(); });
}
async function doSend() {
  const text = $('sendText').value.trim(), { rect, r } = sendCtx; S.ctx = $('sendCtx').value; S.aut = $('sendAut').value; savePrefs();
  const marks = sendCtx.marks.map(m => m.map(p => [r2(rect[0] + p[0] / r.scale), r2(rect[1] + p[1] / r.scale)])); // the scribbles in canvas units
  try {
    await call('/api/canvas/send', { rect, ids: sendCtx.ids, text, image: $('sendCv').toDataURL('image/png'), scale: r.scale, context: S.ctx, autonomy: S.aut, marks });
    $('modal').classList.remove('open'); $('sendText').value = ''; toast('Přidáno do zprávy v chatu, odešli ji tam.');
  } catch (e) { toast(e.message, true); }
}
function renderAI() {
  const bar = $('aiBar'), now = Date.now() / 1000, items = [];
  layoutBubbles();
  for (const q of Object.values(reqs).sort((a, b) => a.created - b.created)) {
    if (!FINAL.includes(q.status)) seenOpen.add(q.id);
    if (q.status === 'applied' && !appliedAt[q.id] && seenOpen.has(q.id)) { appliedAt[q.id] = now; setTimeout(renderAI, 8100); }
    if (!(openReq(q) || (q.status === 'applied' && now - (appliedAt[q.id] || 0) < 8))) continue;
    const bs = Object.values(briefs).filter(b => b.req === q.id), done = bs.filter(b => b.state !== 'open').length;
    const btn = (t, f, cls = 'ghost') => h('button', { className: cls, textContent: t, on: { click: f } });
    items.push(h('div', { className: `it${q.status === 'applied' ? ' done' : ''}` },
      h('span', { className: 'pill', textContent: LABEL[q.status] || q.status, title: q.status === 'pending' ? 'Zpráva musí být odeslána v chatu' : '' }),
      h('span', { className: 't', textContent: q.note || q.summary || q.instruction || '(bez textu)', title: q.summary || q.instruction }),
      q.status === 'asking' ? [h('span', { className: 'muted', textContent: `${done}/${bs.length} odpovědí` }), btn('Odeslat odpovědi', () => call('/api/canvas/answers/send', { req: q.id }).then(() => toast('Odpovědi přidány do zprávy v chatu.')).catch(e => toast(e.message, true)), 'primary')] : null,
      q.status === 'proposed' ? [h('span', { className: 'muted', textContent: `+${q.proposal.put.filter(o => !objs[o.id]).length} ~${q.proposal.put.filter(o => objs[o.id]).length} −${q.proposal.del.length}` }), btn(hiddenProp.has(q.id) ? 'Zobrazit' : 'Skrýt', () => { hiddenProp.has(q.id) ? hiddenProp.delete(q.id) : hiddenProp.add(q.id); needT = true; renderAI(); }), btn('Odmítnout', () => decide(q, false)), btn('Přijmout', () => decide(q, true), 'primary')] : null,
      q.status === 'applied' && q.snap ? btn('Vrátit', () => restoreSnap({ id: q.snap, name: 'před úpravou AI' })) : null,
      btn('×', () => closeReq(q), 'ghost')));
  }
  const head = items.length ? [h('div', { className: 'hd' },
    h('span', { className: 'grip', textContent: '⋮⋮', title: 'Přetáhni lištu jinam', on: { pointerdown: dragBar } }),
    h('button', { className: 'ghost', textContent: aiMin ? '▢' : '–', title: aiMin ? 'Rozbalit' : 'Sbalit, ať je vidět plátno', on: { click: () => { aiMin = !aiMin; renderAI(); } } }))] : [];
  bar.classList.toggle('min', aiMin); bar.replaceChildren(...head, ...items); needT = true;
}
let aiMin = false;
function dragBar(e) { // move the proposal bar out of the way (offset kept until reload)
  const bar = $('aiBar'), x0 = e.clientX - (parseFloat(bar.style.getPropertyValue('--dx')) || 0), y0 = e.clientY - (parseFloat(bar.style.getPropertyValue('--dy')) || 0);
  const mv = ev => { bar.style.setProperty('--dx', `${ev.clientX - x0}px`); bar.style.setProperty('--dy', `${ev.clientY - y0}px`); };
  const up = () => { removeEventListener('pointermove', mv); removeEventListener('pointerup', up); };
  addEventListener('pointermove', mv); addEventListener('pointerup', up); e.preventDefault();
}
function closeReq(q) { // × closes it for every device (applied ones only leave the bar)
  dismissed.add(q.id); renderAI();
  if (!FINAL.includes(q.status)) call('/api/canvas/status', { req: q.id, status: 'closed' }).catch(e => toast(e.message, true));
}
async function decide(q, accept, force = false) {
  try { await call('/api/canvas/decide', { req: q.id, accept, force }); if (!accept) toast('Návrh zamítnut', false, 1200); }
  catch (e) {
    if (e.status === 409 && confirm(`Tyto objekty se mezitím změnily: ${e.body.ids.join(', ')}\nPřesto použít návrh AI (původní stav se uloží jako verze)?`)) return decide(q, accept, true);
    if (e.status !== 409) toast(e.message, true);
  }
}
const bubEls = new Map();
let openBub = null;
function anchorOf(b) {
  if (b.anchor.obj) { const o = objs[b.anchor.obj]; if (!o) return null; const bb = bnd(o); return [bb[0] + bb[2] / 2, bb[1] + bb[3] / 2]; }
  return b.anchor.pt;
}
function bubblePos(b) {
  if (!openReq(reqs[b.req])) return null;
  if (!layers[7].vis) return null;
  const w = anchorOf(b); if (!w) return null;
  const [ax, ay] = toScreen(...w), a = -0.8 - (b.n - 1) * 0.55, d = 58 + ((b.n - 1) % 3) * 16;
  const o = b.off || [0, 0]; // user drag offset of the bubble (not saved)
  return { ax, ay, x: clamp(ax + Math.cos(a) * d + o[0], 14, W - 14), y: clamp(ay + Math.sin(a) * d + o[1], 14, H - 14) };
}
function layoutBubbles() { for (const [id, el] of bubEls) { const b = briefs[id], p = b && bubblePos(b); el.style.display = p ? 'flex' : 'none'; if (p) { el.style.left = `${p.x}px`; el.style.top = `${p.y}px`; } } needT = true; }
function renderBubbles() {
  const box = $('bubbles');
  for (const b of Object.values(briefs)) {
    let el = bubEls.get(b.id);
    if (!el) {
      el = h('div', { className: 'bub' });
      el.addEventListener('click', ev => { if (ev.target.closest('.card') || el._drag) return; openBub = openBub === b.id ? null : b.id; renderBubbles(); });
      el.addEventListener('pointerdown', ev => { // drag the bubble itself (the card follows); a short move is still a click
        if (ev.target.closest('.card')) return;
        const p0 = [ev.clientX, ev.clientY], o0 = b.off || [0, 0]; el._drag = false;
        const mv = e2 => { const dx = e2.clientX - p0[0], dy = e2.clientY - p0[1]; if (!el._drag && Math.hypot(dx, dy) < 5) return; el._drag = true; b.off = [o0[0] + dx, o0[1] + dy]; layoutBubbles(); };
        const up = () => { removeEventListener('pointermove', mv); removeEventListener('pointerup', up); setTimeout(() => { el._drag = false; }, 0); };
        addEventListener('pointermove', mv); addEventListener('pointerup', up);
      });
      bubEls.set(b.id, el); box.append(el);
    }
    const open = openBub === b.id, key = `${b.rev}|${open}`;
    if (el._key === key) continue;
    el._key = key; el.className = `bub ${b.kind === 'warning' ? 'warning' : ''} ${b.state !== 'open' ? b.state : ''} ${open ? 'open' : ''}`;
    const ans = (text, state = 'answered') => { b.answer = text; b.state = state; b.rev++; openBub = null; call('/api/canvas/answer', { item: b.id, answer: text, state }).catch(e => toast(e.message, true)); renderBubbles(); renderAI(); };
    const inp = h('input', { type: 'text', placeholder: 'Vlastní odpověď', value: b.state === 'answered' ? b.answer : '', on: { keydown: e => { e.stopPropagation(); if (e.key === 'Enter' && e.target.value.trim()) ans(e.target.value.trim()); } } });
    el.replaceChildren(b.state === 'answered' || b.state === 'assumed' ? '✓' : b.kind === 'warning' ? '!' : String(b.n),
      h('div', { className: 'card' }, h('button', { className: 'x', textContent: '×', title: 'Zavřít', on: { click: () => { openBub = null; renderBubbles(); } } }), h('b', { textContent: b.q }),
        b.options.length ? h('div', { className: 'chips' }, b.options.map(o => h('button', { className: b.answer === o && b.state !== 'open' ? 'on' : '', textContent: o, on: { click: () => ans(o) } }))) : null,
        b.assumption && b.state === 'open' ? h('div', { className: 'chips' }, h('button', { textContent: `Přijmout předpoklad: ${b.assumption}`, on: { click: () => ans(b.assumption, 'assumed') } })) : null,
        h('div', { className: 'ans' }, inp, h('button', { className: 'primary', textContent: 'OK', on: { click: () => inp.value.trim() && ans(inp.value.trim()) } })),
        b.state !== 'open' ? h('div', { className: 'muted', textContent: b.state === 'assumed' ? `Předpoklad přijat: ${b.answer}` : `Odpověď: ${b.answer}` }) : null));
  }
  layoutBubbles();
}

// ---------------------------------------------------------------- mechanisms: live kinematics + floating panels
// The model is an ordinary object (t: 'mech'); its motion state lives only here (angle, play, speed, trial lengths,
// trajectory) and each mechanism has its own panel, so several can run independently.
const mechSt = {};
const deg = r => (r * 180) / Math.PI;
function mst(o) {
  let st = mechSt[o.id];
  if (!st) st = mechSt[o.id] = { playing: false, dir: 1, speed: 60, lens: null, trace: { j: '', pts: [] }, min: false, pos: null, src: null };
  if (st.src !== o) { // new or edited geometry: start again from its drawn pose
    st.src = o; st.lens = null; st.ang = st.keep ?? Geo.mechAngle0(o); st.keep = null; st.prev = null; st.trace.pts = [];
    st.range = Geo.mechRange(o, null, 720, st.ang); st.err = st.range ? '' : 'Neproveditelná konfigurace: v nakreslené poloze se mechanismus nedá sestavit';
    st.panel?.remove(); st.panel = null;
  }
  return st;
}
function solveNow(o, st) {
  const sol = Geo.solveMech(o, st.ang, st.prev, st.lens);
  if (sol) { st.prev = sol; o.cur = sol; st.err = ''; } else st.err = 'Neproveditelná konfigurace: členy na sebe nedosáhnou';
  return sol;
}
let lastTick = performance.now();
function tickMechs() {
  const now = performance.now(), dt = Math.min(0.05, (now - lastTick) / 1000);
  lastTick = now;
  for (const id in mechSt) {
    const st = mechSt[id], o = objs[id];
    if (!o) { st.panel?.remove(); delete mechSt[id]; continue; }
    if (!st.playing || !st.range) continue;
    let a = st.ang + (st.dir * st.speed * Math.PI / 180) * dt;
    if (!st.range.full) { if (a > st.range.hi) { a = st.range.hi; st.dir = -1; } else if (a < st.range.lo) { a = st.range.lo; st.dir = 1; } } // a rocker swings back
    st.ang = a;
    if (solveNow(o, st) && st.trace.j) { st.trace.pts.push(o.cur[st.trace.j].slice()); if (st.trace.pts.length > 5000) st.trace.pts.shift(); }
    needB = true; needT = true;
    if (st.panel) { const ph = st.panel.querySelector('.ph'); if (ph && document.activeElement !== ph) ph.value = deg(st.ang); st.panel.querySelector('.st').textContent = st.err; }
  }
}
function drawTraces(c) { // layer 07 Trajektorie: hiding it does not stop the motion
  const ly = layers[6];
  if (!ly.vis) return;
  c.strokeStyle = theme.blue; c.lineWidth = 1.2 / view.z * 1.5; c.globalAlpha = ly.op; c.lineJoin = 'round';
  for (const id in mechSt) { const p = mechSt[id].trace.pts; if (p.length < 2) continue; c.beginPath(); p.forEach((q, i) => (i ? c.lineTo(q[0], q[1]) : c.moveTo(q[0], q[1]))); c.stroke(); }
  c.globalAlpha = 1;
}
function drawMech(c, o, px) {
  const P = Geo.mechPts(o), r = 2.6, w = o.w || 2;
  const ground = p => { // fixed pivot: triangle, base, hatching
    c.lineWidth = w * 0.8; c.beginPath(); c.moveTo(p[0], p[1] + r); c.lineTo(p[0] - 8, p[1] + 14); c.moveTo(p[0], p[1] + r); c.lineTo(p[0] + 8, p[1] + 14);
    c.moveTo(p[0] - 13, p[1] + 14); c.lineTo(p[0] + 13, p[1] + 14); c.stroke();
    c.lineWidth = w * 0.45; c.beginPath(); for (let x = -10; x <= 12; x += 5.5) { c.moveTo(p[0] + x, p[1] + 14); c.lineTo(p[0] + x - 4, p[1] + 19); } c.stroke();
  };
  for (const sl of o.sliders || []) { // guide on the side away from the link, block on the joint
    const p = P[sl.j], L = Geo.dist(sl.a, sl.b) || 1, u = [(sl.b[0] - sl.a[0]) / L, (sl.b[1] - sl.a[1]) / L];
    let n = [-u[1], u[0]];
    const nb = o.links.find(l => l.includes(sl.j)), q = nb && P[nb[0] === sl.j ? nb[1] : nb[0]];
    if (q && (q[0] - p[0]) * n[0] + (q[1] - p[1]) * n[1] > 0) n = [-n[0], -n[1]];
    const off = (k, m) => [p[0] + u[0] * k + n[0] * m, p[1] + u[1] * k + n[1] * m];
    c.lineWidth = w; c.beginPath(); [off(-8, -4.5), off(8, -4.5), off(8, 4.5), off(-8, 4.5)].forEach((q2, i) => (i ? c.lineTo(q2[0], q2[1]) : c.moveTo(q2[0], q2[1]))); c.closePath(); c.stroke();
    const g0 = [sl.a[0] + n[0] * 6, sl.a[1] + n[1] * 6], g1 = [sl.b[0] + n[0] * 6, sl.b[1] + n[1] * 6];
    c.beginPath(); c.moveTo(g0[0], g0[1]); c.lineTo(g1[0], g1[1]); c.stroke();
    c.lineWidth = w * 0.45; c.beginPath();
    for (let k = 4; k < L; k += 8) { const s0 = [g0[0] + u[0] * k, g0[1] + u[1] * k]; c.moveTo(s0[0], s0[1]); c.lineTo(s0[0] + n[0] * 5 - u[0] * 5, s0[1] + n[1] * 5 - u[1] * 5); }
    c.stroke();
  }
  c.lineWidth = w * 1.1;
  for (const [a, b] of o.links) {
    const p = P[a], q = P[b], d = Geo.dist(p, q) || 1, ux = (q[0] - p[0]) / d, uy = (q[1] - p[1]) / d;
    c.beginPath(); c.moveTo(p[0] + ux * r, p[1] + uy * r); c.lineTo(q[0] - ux * r, q[1] - uy * r); c.stroke();
  }
  for (const j of o.joints) if (j.fixed) ground(P[j.id]);
  const dc = P[o.driver.c]; // the driving crank: a turning arrow around its pivot
  c.lineWidth = w * 0.6; c.beginPath(); c.arc(dc[0], dc[1], 8, -2.6, -0.6); c.stroke(); head(c, [dc[0] + 8 * Math.cos(-0.6), dc[1] + 8 * Math.sin(-0.6)], [dc[0] + 8 * Math.cos(-0.9), dc[1] + 8 * Math.sin(-0.9)], 3);
  c.lineWidth = w * 0.8; c.font = `7px ${FONT}`; c.textBaseline = 'bottom';
  for (const j of o.joints) {
    const p = P[j.id];
    c.save(); c.fillStyle = theme.paper; c.beginPath(); c.arc(p[0], p[1], r, 0, Math.PI * 2); c.fill(); c.restore();
    c.beginPath(); c.arc(p[0], p[1], r, 0, Math.PI * 2); c.stroke();
    c.fillText(j.id, p[0] - 9, p[1] - 3);
  }
}
function moveJoint(o, id, p) {
  const old = o.joints.find(j => j.id === id).p, d = [p[0] - old[0], p[1] - old[1]];
  const n = { ...o, joints: o.joints.map(j => (j.id === id ? { ...j, p } : j)), sliders: (o.sliders || []).map(q => (q.j === id ? { ...q, a: [q.a[0] + d[0], q.a[1] + d[1]], b: [q.b[0] + d[0], q.b[1] + d[1]] } : q)) };
  delete n.cur; delete n.len; // lengths come from the new drawing
  return n;
}
const rangeText = rg => (!rg ? '' : rg.full ? 'Klika se otáčí dokola' : `Kývání ${deg(rg.lo).toFixed(0)}° … ${deg(rg.hi).toFixed(0)}° (dál členy nedosáhnou)`);
function mechPanel(o, st) {
  const L = Geo.mechLens(o, st.lens), rg = st.range;
  const playB = h('button', { className: 'ghost', textContent: st.playing ? '⏸ Pauza' : '▶ Přehrát', on: { click: () => { if (!st.range) return; st.playing = !st.playing; if (!st.playing) st.prev = null; rebuild(); } } });
  const rebuild = () => { st.panel?.remove(); st.panel = null; syncMechs(true); };
  const row = (label, input, out) => h('label', {}, h('span', { textContent: label }), input, out || h('span'));
  const speedOut = h('span', { textContent: `${st.speed}°/s` });
  const traceSel = h('select', { on: { change: e => { st.trace = { j: e.target.value, pts: [] }; needB = true; } } }, h('option', { value: '', textContent: 'vypnuto' }), o.joints.filter(j => !j.fixed).map(j => h('option', { value: j.id, selected: st.trace.j === j.id, textContent: `bod ${j.id}` })));
  const el = h('div', { className: `mp${st.min ? ' min' : ''}` },
    h('div', { className: 'hd' }, h('span', { className: 'grow', textContent: `⚙ ${o.name || 'Mechanismus'}` }),
      h('button', { textContent: st.min ? '▢' : '–', title: st.min ? 'Rozbalit' : 'Sbalit', on: { click: () => { st.min = !st.min; rebuild(); } } })),
    h('div', { className: 'bd' },
      h('div', { className: 'r' }, playB,
        h('button', { className: 'ghost', textContent: '⟲', title: 'Výchozí poloha', on: { click: () => { st.playing = false; st.ang = Geo.mechAngle0(o); st.prev = null; st.trace.pts = []; solveNow(o, st); needB = true; rebuild(); } } }),
        h('button', { className: 'ghost', textContent: '⇄', title: 'Směr pohybu', on: { click: () => { st.dir = -st.dir; } } })),
      row('Rychlost', h('input', { type: 'range', min: 5, max: 360, step: 5, value: st.speed, on: { input: e => { st.speed = +e.target.value; speedOut.textContent = `${st.speed}°/s`; } } }), speedOut),
      rg ? row('Fáze', h('input', { className: 'ph', type: 'range', min: rg.full ? deg(rg.a0) - 180 : deg(rg.lo), max: rg.full ? deg(rg.a0) + 180 : deg(rg.hi), step: 0.5, value: deg(st.ang),
        on: { input: e => { st.ang = (+e.target.value * Math.PI) / 180; solveNow(o, st); needB = true; } } })) : null,
      h('div', { className: 'muted', textContent: 'Délky členů' }),
      o.links.map((l, i) => {
        const out = h('span', { textContent: r2(L[i]) });
        return row(`${l[0]}–${l[1]}`, h('input', { type: 'range', min: r2(L[i] * 0.3), max: r2(L[i] * 2), step: 0.1, value: L[i], on: {
          input: e => { // live: the model is solved again at once; Neproveditelná when it falls apart
            st.lens = Geo.mechLens(o, st.lens); st.lens[i] = +e.target.value; out.textContent = r2(st.lens[i]);
            const rg2 = Geo.mechRange(o, st.lens, 720, st.ang); st.trace.pts = [];
            if (rg2) { st.range = rg2; solveNow(o, st); } else st.err = 'Neproveditelná konfigurace: s touto délkou se mechanismus v této poloze nedá sestavit';
            st.panel.querySelector('.st').textContent = st.err; st.panel.querySelector('.info').textContent = rangeText(st.range); needB = true;
          },
          change: () => { if (!st.err) { st.keep = st.ang; commit([{ ...o, len: st.lens.map(r2), cur: undefined }]); } } } }), out);
      }),
      h('div', { className: 'r' }, h('span', { className: 'muted', textContent: 'Trajectory' }), traceSel, h('button', { className: 'ghost', textContent: 'Vymazat', on: { click: () => { st.trace.pts = []; needB = true; } } })),
      h('div', { className: 'info', textContent: rangeText(rg) }),
      h('div', { className: 'st err', textContent: st.err })));
  el.addEventListener('pointerdown', e => e.stopPropagation());
  const hd = el.querySelector('.hd'); // drag the panel by its title
  hd.addEventListener('pointerdown', e => {
    if (e.target.closest('button')) return;
    const r0 = el.getBoundingClientRect(), w0 = $('wrap').getBoundingClientRect(), dx = e.clientX - r0.left, dy = e.clientY - r0.top;
    const mv = ev => { st.pos = [ev.clientX - w0.left - dx, ev.clientY - w0.top - dy]; placePanel(o, st); };
    const upd = () => { removeEventListener('pointermove', mv); removeEventListener('pointerup', upd); };
    addEventListener('pointermove', mv); addEventListener('pointerup', upd);
  });
  return el;
}
function placePanel(o, st) {
  const el = st.panel, b = bnd(o), [x, y] = st.pos || toScreen(b[0] + b[2], b[1]);
  el.style.left = `${clamp(st.pos ? x : x + 14, 4, Math.max(4, W - el.offsetWidth - 4))}px`;
  el.style.top = `${clamp(y, 4, Math.max(4, H - el.offsetHeight - 4))}px`;
}
function syncMechs(force) {
  for (const o of Object.values(objs)) {
    if (o.t !== 'mech') continue;
    const st = mst(o);
    if (!visible(o)) { if (st.panel) st.panel.style.display = 'none'; continue; }
    if (!st.panel || force) { st.panel?.remove(); if (!st.playing && !o.cur) solveNow(o, st); st.panel = mechPanel(o, st); $('mechs').append(st.panel); }
    st.panel.style.display = '';
    placePanel(o, st);
  }
}

// ---------------------------------------------------------------- minimap, export, toolbar, keys
function drawMini() {
  const m = $('mini'); m.classList.toggle('show', S.mini); if (!S.mini) return;
  const c = m.getContext('2d'), all = unionB([...Object.values(objs).map(bnd), viewRect()]), k = Math.min(m.width / all[2], m.height / all[3]) * 0.9;
  const ox = (m.width - all[2] * k) / 2 - all[0] * k, oy = (m.height - all[3] * k) / 2 - all[1] * k;
  m._map = { k, ox, oy };
  c.clearRect(0, 0, m.width, m.height); c.fillStyle = theme.faint; c.globalAlpha = 0.7;
  for (const o of Object.values(objs)) { if (!visible(o)) continue; const b = bnd(o); c.fillRect(b[0] * k + ox, b[1] * k + oy, Math.max(2, b[2] * k), Math.max(2, b[3] * k)); }
  c.globalAlpha = 1; c.strokeStyle = theme.accent; c.lineWidth = 2; const v = viewRect(); c.strokeRect(v[0] * k + ox, v[1] * k + oy, v[2] * k, v[3] * k);
}
$('mini').addEventListener('click', e => { const m = $('mini'); if (!m._map) return; const r = m.getBoundingClientRect(), { k, ox, oy } = m._map, x = ((e.clientX - r.left) * m.width) / r.width, y = ((e.clientY - r.top) * m.height) / r.height; const w = [(x - ox) / k, (y - oy) / k]; view = { ...view, x: w[0] - W / 2 / view.z, y: w[1] - H / 2 / view.z }; viewChanged(); });
function exportPng() {
  const b = unionB(Object.values(objs).filter(visible).map(bnd)); if (!b) return toast('Plátno je prázdné');
  const r = renderRegion([b[0] - 20, b[1] - 20, b[2] + 40, b[3] + 40], 3000);
  h('a', { href: r.url, download: `platno-${new Date().toISOString().slice(0, 10)}.png` }).click();
}
// Vector export of the visible layers (dims, mechanisms and the live trajectory are not exported). y grows downwards in SVG, so no flip.
function vecObjs() { return getOrder().filter(o => visible(o) && ['line', 'circle', 'arc', 'rect', 'ellipse', 'text', 'stroke'].includes(o.t)); }
function saveText(text, name, type) { const u = URL.createObjectURL(new Blob([text], { type })); h('a', { href: u, download: name }).click(); setTimeout(() => URL.revokeObjectURL(u), 4000); }
const stamp = ext => `platno-${new Date().toISOString().slice(0, 10)}.${ext}`;
function exportSvg() {
  const list = vecObjs(); if (!list.length) return toast('Plátno je prázdné');
  const b = unionB(list.map(bnd)), m = 10, n = v => +v.toFixed(3), esc = s => String(s).replace(/[&<>]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;' })[c]);
  const col = o => (!o.color || o.color === 'ink' ? '#111' : o.color), st = o => `fill="none" stroke="${o.cons ? '#4a7fc1' : col(o)}" stroke-width="${o.w || 1.5}" stroke-linecap="round" stroke-linejoin="round"${o.cons ? ' stroke-dasharray="7 4"' : ''}`;
  const el = o => {
    switch (o.t) {
      case 'line': return `<line x1="${n(o.a[0])}" y1="${n(o.a[1])}" x2="${n(o.b[0])}" y2="${n(o.b[1])}" ${st(o)}/>`;
      case 'circle': return `<circle cx="${n(o.c[0])}" cy="${n(o.c[1])}" r="${n(o.r)}" ${st(o)}/>`;
      case 'arc': { const sp = Geo.arcSpan(o), p0 = Geo.arcPt(o, 0), p1 = Geo.arcPt(o, 1); return `<path d="M${n(p0[0])} ${n(p0[1])}A${n(o.r)} ${n(o.r)} 0 ${sp > Math.PI ? 1 : 0} 1 ${n(p1[0])} ${n(p1[1])}" ${st(o)}/>`; }
      case 'rect': return `<rect x="${n(Math.min(o.p[0], o.q[0]))}" y="${n(Math.min(o.p[1], o.q[1]))}" width="${n(Math.abs(o.q[0] - o.p[0]))}" height="${n(Math.abs(o.q[1] - o.p[1]))}" ${st(o)}/>`;
      case 'ellipse': return `<ellipse cx="${n(o.c[0])}" cy="${n(o.c[1])}" rx="${n(o.rx)}" ry="${n(o.ry)}" ${st(o)}/>`;
      case 'stroke': return `<polyline points="${o.pts.map(p => `${n(p[0])},${n(p[1])}`).join(' ')}" ${st(o)}${o.tool === 'hl' ? ` opacity="${o.alpha ?? 0.4}"` : ''}/>`;
      default: return String(o.s).split('\n').map((l, i) => `<text x="${n(o.x)}" y="${n(o.y + o.size * (0.9 + i * 1.25))}" font-size="${n(o.size)}" font-family="sans-serif" fill="${col(o)}">${esc(l)}</text>`).join('');
    }
  };
  saveText(`<svg xmlns="http://www.w3.org/2000/svg" viewBox="${n(b[0] - m)} ${n(b[1] - m)} ${n(b[2] + 2 * m)} ${n(b[3] + 2 * m)}" width="${n(b[2] + 2 * m)}mm" height="${n(b[3] + 2 * m)}mm">\n${list.map(el).join('\n')}\n</svg>\n`, stamp('svg'), 'image/svg+xml');
}
// DXF (R12 ASCII, 1 unit = 1 mm): y is flipped to the CAD convention, layers are named L1..L9, strokes become polylines.
function exportDxf() {
  const list = vecObjs(); if (!list.length) return toast('Plátno je prázdné');
  const out = ['0', 'SECTION', '2', 'ENTITIES'], g = (c, v) => out.push(String(c), String(typeof v === 'number' ? +v.toFixed(4) : v));
  const ent = (type, o, rows) => { g(0, type); g(8, `L${o.layer || 2}`); rows(); };
  const poly = (o, pts, closed) => { ent('POLYLINE', o, () => { g(66, 1); g(70, closed ? 1 : 0); }); for (const p of pts) { g(0, 'VERTEX'); g(8, `L${o.layer || 2}`); g(10, p[0]); g(20, -p[1]); } g(0, 'SEQEND'); };
  const deg = r => ((((r * 180) / Math.PI) % 360) + 360) % 360;
  for (const o of list) {
    if (o.t === 'line') ent('LINE', o, () => { g(10, o.a[0]); g(20, -o.a[1]); g(11, o.b[0]); g(21, -o.b[1]); });
    else if (o.t === 'circle') ent('CIRCLE', o, () => { g(10, o.c[0]); g(20, -o.c[1]); g(40, o.r); });
    else if (o.t === 'arc') ent('ARC', o, () => { g(10, o.c[0]); g(20, -o.c[1]); g(40, o.r); g(50, deg(-(o.a0 + Geo.arcSpan(o)))); g(51, deg(-o.a0)); }); // clockwise on screen = counter-clockwise after the flip
    else if (o.t === 'rect') { const [x0, x1] = [Math.min(o.p[0], o.q[0]), Math.max(o.p[0], o.q[0])], [y0, y1] = [Math.min(o.p[1], o.q[1]), Math.max(o.p[1], o.q[1])]; poly(o, [[x0, y0], [x1, y0], [x1, y1], [x0, y1]], true); }
    else if (o.t === 'ellipse') poly(o, Array.from({ length: 72 }, (_, i) => [o.c[0] + o.rx * Math.cos((i * Math.PI) / 36), o.c[1] + o.ry * Math.sin((i * Math.PI) / 36)]), true);
    else if (o.t === 'stroke') poly(o, o.pts, false);
    else String(o.s).split('\n').forEach((l, i) => ent('TEXT', o, () => { g(10, o.x); g(20, -(o.y + o.size * (1 + i * 1.25))); g(40, o.size); g(1, l); }));
  }
  out.push('0', 'ENDSEC', '0', 'EOF');
  saveText(out.join('\n') + '\n', stamp('dxf'), 'application/dxf');
}
let toastT = 0;
function toast(msg, err = false, ms = 2800) { const t = $('toast'); t.textContent = msg; t.className = err ? 'err' : ''; t.style.display = 'block'; clearTimeout(toastT); toastT = setTimeout(() => { t.style.display = 'none'; }, ms); }

for (const b of document.querySelectorAll('[data-tool]')) b.addEventListener('click', () => setTool(b.dataset.tool));
async function fileOp(url, body, done) {
  closeMenus(); toast('Otevírám dialog…', false, 1500);
  try { const r = await call(url, body); if (!r.cancelled && (r.path || r.objs !== undefined)) done(r); } catch (e) { toast(e.message, true); }
}
$('fSave').onclick = () => fileOp('/api/canvas/file/save', {}, r => r.path && toast(`Uloženo: ${r.path}`, false, 4000));
$('fOpen').onclick = () => { if (confirm('Otevřít soubor a nahradit jím celé plátno? Aktuální stav se předtím uloží jako verze.')) fileOp('/api/canvas/file/open', { mode: 'replace' }, r => { sel.clear(); toast(`Otevřeno: ${r.objs} objektů`, false, 3000); setTimeout(fit, 600); }); };
$('fAdd').onclick = () => fileOp('/api/canvas/file/open', { mode: 'add' }, r => toast(`Vloženo: ${r.objs} objektů`, false, 3000));
$('fPng').onclick = () => { closeMenus(); exportPng(); };
$('fSvg').onclick = () => { closeMenus(); exportSvg(); };
$('fDxf').onclick = () => { closeMenus(); exportDxf(); };
$('bUndo').onclick = undo; $('bRedo').onclick = redo; $('bFit').onclick = fit; $('bAI').onclick = openSend;
$('bSnap').onclick = () => { S.snap = !S.snap; hover.snap = null; updateBar(); savePrefs(); };
$('bCons').onclick = () => { S.cons = !S.cons; updateBar(); savePrefs(); };
$('bSide').onclick = () => { S.side = !S.side; updateBar(); savePrefs(); };
$('bMini').onclick = () => { S.mini = !S.mini; drawMini(); savePrefs(); };
$('zoom').onclick = () => zoomAt(W / 2, H / 2, 1 / view.z);
$('sendCancel').onclick = () => $('modal').classList.remove('open'); $('sendGo').onclick = doSend;
$('sendText').addEventListener('keydown', e => { e.stopPropagation(); if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) doSend(); if (e.key === 'Escape') $('modal').classList.remove('open'); });
const closeMenus = () => { for (const x of document.querySelectorAll('.menu')) x.classList.remove('open'); };
for (const [btn, menu] of [['bPen', 'menuPen'], ['bView', 'menuView'], ['bFile', 'menuFile']]) $(btn).addEventListener('click', () => {
  const m = $(menu), o = m.classList.contains('open'); closeMenus(); if (o) return;
  m.classList.add('open');
  const b = $(btn).getBoundingClientRect();
  m.style.top = `${b.bottom + 6}px`; m.style.left = `${clamp(b.left - 8, 8, innerWidth - m.offsetWidth - 8)}px`;
});
addEventListener('resize', closeMenus); $('bar').addEventListener('scroll', closeMenus);
document.addEventListener('pointerdown', e => { if (!e.target.closest('.dd')) closeMenus(); });
// menu controls <-> prefs
const bind = (id, path, ev = 'input', conv = v => v) => { const el = $(id), get = () => path.reduce((o, k) => o[k], S), set = v => { const t = path.slice(0, -1).reduce((o, k) => o[k], S); t[path[path.length - 1]] = v; }; if (el.type === 'checkbox') el.checked = !!get(); else el.value = get(); el.addEventListener(ev, () => { set(conv(el.type === 'checkbox' ? el.checked : el.value)); savePrefs(); dirty(); }); };
bind('penW', ['pen', 'w'], 'input', Number); bind('penA', ['pen', 'alpha'], 'input', Number); bind('penS', ['pen', 'smooth'], 'input', Number);
bind('fingerOn', ['finger'], 'change'); bind('qsOn', ['quick'], 'change'); bind('qsHold', ['hold'], 'input', Number); bind('qsTol', ['tol'], 'input', Number); bind('scrOn', ['scribble'], 'change'); bind('alignOn', ['align'], 'change');
bind('gridI', ['gridI'], 'input', Number); bind('axesOn', ['axes'], 'change'); bind('snapGrid', ['snapGrid'], 'change');
const markSw = () => { for (const b of $('penSw').children) b.classList.toggle('on', b.title === S.pen.color); };
$('penSw').replaceChildren(...COLORS.map(c => h('button', { className: 'sw', style: `background:${c === 'ink' ? 'var(--text)' : c}`, title: c, on: { click: () => { S.pen.color = c; markSw(); savePrefs(); } } })));
markSw();
const seg = (id, attr, key, after) => { const el = $(id); const sync = () => { for (const b of el.children) b.classList.toggle('on', b.dataset[attr] === S[key]); }; el.addEventListener('click', e => { const b = e.target.closest('button'); if (b) { S[key] = b.dataset[attr]; sync(); after(); savePrefs(); } }); sync(); };
seg('bgSeg', 'bg', 'bg', readTheme); seg('themeSeg', 'th', 'theme', readTheme);

const typing = () => ['INPUT', 'TEXTAREA', 'SELECT'].includes(document.activeElement?.tagName);
document.addEventListener('keydown', e => {
  if ($('modal').classList.contains('open')) { if (e.key === 'Escape') $('modal').classList.remove('open'); return; }
  if (snipping && e.key === 'Escape') { cancelSnip(); return; }
  if (typing()) return;
  const k = e.key.toLowerCase(), ctrl = e.ctrlKey || e.metaKey;
  if (k === ' ') { spaceDown = true; e.preventDefault(); return; }
  if (ctrl && k === 'z') { e.preventDefault(); (e.shiftKey ? redo : undo)(); return; }
  if (ctrl && k === 'y') { e.preventDefault(); redo(); return; }
  if (ctrl && k === 'c') { copy(); return; } if (ctrl && k === 'v') { e.preventDefault(); paste(); return; }
  if (ctrl && k === 'g') { e.preventDefault(); group(!e.shiftKey); return; }
  if (ctrl && k === 'a') { e.preventDefault(); select(getOrder().filter(selectable).map(o => o.id)); return; }
  if (ctrl && k === 'enter') { e.preventDefault(); openSend(); return; }
  if (ctrl) return;
  if (k === 'delete' || k === 'backspace') { e.preventDefault(); del(); }
  else if (k === 'escape') { if (pend) { pend = null; needT = true; } else { select([]); chip(null); } }
  else if (k.startsWith('arrow')) { e.preventDefault(); const s = e.shiftKey ? 10 : 1; nudge(k === 'arrowleft' ? -s : k === 'arrowright' ? s : 0, k === 'arrowup' ? -s : k === 'arrowdown' ? s : 0); }
  else if (k === 'q') setTool(S.prev); else if (k === 'a') $('bSnap').click(); else if (k === 'c') $('bCons').click(); else if (k === 'f') fit();
  else if (KEYS[k]) setTool(KEYS[k]);
});
document.addEventListener('keyup', e => { if (e.key === ' ') spaceDown = false; });

if (innerWidth < 800) S.side = false; // on a phone / narrow pane the panel would cover the canvas: open it on demand
readTheme(); setTool(S.tool); updateBar(); $('zoom').textContent = `${Math.round(view.z * 100)} %`; resize(); drawMini();
requestAnimationFrame(frame);
poll();
