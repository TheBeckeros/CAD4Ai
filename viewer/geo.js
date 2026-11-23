// Geometry of the construction canvas (canvas.js): exact objects (line, circle, arc, rect, ellipse, dim, text, stroke),
// QuickShape+ recognition, scribble-erase detection, intersections, trim / split / extend, snapping, alignment.
// Pure functions, loaded by canvas.js (global Geo, needs Ink for stroke bounds) and by node for geo.test.js.
// Objects: line {a, b} · circle {c, r} · arc {c, r, a0, a1} (radians, y down, drawn clockwise a0 -> a1) · rect {p, q}
// (opposite corners) · ellipse {c, rx, ry} · dim {a, b, off, ref?} · text {x, y, s, size} · stroke {pts, w}.
(function (root) {
  const Ink = typeof require === 'function' && typeof module !== 'undefined' ? require('./ink.js') : root.Ink;
  const TAU = Math.PI * 2, hyp = Math.hypot;
  const norm = a => ((a % TAU) + TAU) % TAU;
  const sub = (p, q) => [p[0] - q[0], p[1] - q[1]];
  const lerp = (p, q, t) => [p[0] + (q[0] - p[0]) * t, p[1] + (q[1] - p[1]) * t];
  const dist = (p, q) => hyp(p[0] - q[0], p[1] - q[1]);
  const ctx = { byId: {} }; // objects by id: dims with a ref read the line / circle they follow from here (set by canvas.js)
  const GEO = new Set(['line', 'circle', 'arc', 'rect']); // the kinds trim / extend / snap work on

  /** rect -> its four edges as lines (ids id.0 .. id.3), used by trim and intersections. */
  function rectEdges(o) {
    const [x0, y0] = o.p, [x1, y1] = o.q, c = [[x0, y0], [x1, y0], [x1, y1], [x0, y1]];
    return c.map((a, i) => ({ ...o, t: 'line', id: `${o.id}.${i}`, a, b: c[(i + 1) % 4] }));
  }
  const parts = o => (o.t === 'rect' ? rectEdges(o) : GEO.has(o.t) ? [o] : []);

  // ---------------------------------------------------------------- bounds, distance, sampling
  function bounds(o) {
    switch (o.t) {
      case 'line': return box([o.a, o.b], o.w);
      case 'rect': return box([o.p, o.q], o.w);
      case 'circle': return [o.c[0] - o.r - o.w, o.c[1] - o.r - o.w, 2 * (o.r + o.w), 2 * (o.r + o.w)];
      case 'ellipse': return [o.c[0] - o.rx - o.w, o.c[1] - o.ry - o.w, 2 * (o.rx + o.w), 2 * (o.ry + o.w)];
      case 'arc': return box(samples(o, 24), o.w);
      case 'dim': { const d = dimGeom(o); return box([d.a, d.b, d.a2, d.b2, d.label], 4); }
      case 'mech': return box([...Object.values(mechPts(o)), ...(o.sliders || []).flatMap(s => [s.a, s.b])], 10);
      case 'text': { const ls = String(o.s).split('\n'); return [o.x, o.y, Math.max(1, ...ls.map(l => l.length)) * o.size * 0.6, ls.length * o.size * 1.25]; }
      default: return Ink.bounds(o);
    }
  }
  function box(pts, m = 0) {
    const xs = pts.map(p => p[0]), ys = pts.map(p => p[1]), x0 = Math.min(...xs), y0 = Math.min(...ys);
    return [x0 - m, y0 - m, Math.max(...xs) - x0 + 2 * m, Math.max(...ys) - y0 + 2 * m];
  }
  /** Points along the outline (n per curve / edge): lasso tests, snapping, ghosts. */
  function samples(o, n = 16) {
    if (o.t === 'mech') return Object.values(mechPts(o));
    if (o.t === 'line') return [o.a, o.b];
    if (o.t === 'rect') return rectEdges(o).flatMap(e => [e.a, lerp(e.a, e.b, 0.5)]);
    if (o.t === 'circle' || o.t === 'ellipse') return Array.from({ length: n }, (_, k) => [o.c[0] + (o.rx ?? o.r) * Math.cos((k * TAU) / n), o.c[1] + (o.ry ?? o.r) * Math.sin((k * TAU) / n)]);
    if (o.t === 'arc') { const s = arcSpan(o); return Array.from({ length: n + 1 }, (_, k) => [o.c[0] + o.r * Math.cos(o.a0 + (s * k) / n), o.c[1] + o.r * Math.sin(o.a0 + (s * k) / n)]); }
    if (o.t === 'stroke') return o.pts;
    const b = bounds(o);
    return [[b[0] + b[2] / 2, b[1] + b[3] / 2]];
  }
  const arcSpan = o => { const s = norm(o.a1 - o.a0); return s === 0 ? TAU : s; };
  const onArc = (o, ang) => norm(ang - o.a0) <= arcSpan(o) + 1e-9;
  const segDist = (p, a, b) => { const d = Math.min(1, Math.max(0, ((p[0] - a[0]) * (b[0] - a[0]) + (p[1] - a[1]) * (b[1] - a[1])) / (dist(a, b) ** 2 || 1))); return dist(p, lerp(a, b, d)); };

  /** Distance from p to the drawn outline of o (0 inside a text box, stroke width ignored). */
  function distTo(o, p) {
    switch (o.t) {
      case 'line': return segDist(p, o.a, o.b);
      case 'rect': return Math.min(...rectEdges(o).map(e => segDist(p, e.a, e.b)));
      case 'circle': return Math.abs(dist(p, o.c) - o.r);
      case 'ellipse': { const q = [(p[0] - o.c[0]) / o.rx, (p[1] - o.c[1]) / o.ry]; return Math.abs(hyp(q[0], q[1]) - 1) * Math.min(o.rx, o.ry); }
      case 'arc': {
        const ang = Math.atan2(p[1] - o.c[1], p[0] - o.c[0]);
        return onArc(o, ang) ? Math.abs(dist(p, o.c) - o.r) : Math.min(dist(p, arcPt(o, 0)), dist(p, arcPt(o, 1)));
      }
      case 'dim': { const d = dimGeom(o); return Math.min(segDist(p, d.a2, d.b2), dist(p, d.label) - 8); }
      case 'mech': { const P = mechPts(o); return Math.min(...o.links.map(l => segDist(p, P[l[0]], P[l[1]])), ...Object.values(P).map(q => dist(p, q) - 3)); }
      case 'stroke': { let m = Infinity; for (let i = 0; i < o.pts.length; i++) m = Math.min(m, o.pts.length === 1 ? dist(p, o.pts[0]) : i ? segDist(p, o.pts[i - 1], o.pts[i]) : Infinity); return Math.max(0, m - o.w / 2); }
      default: { const b = bounds(o); return Ink.inRect(p, b) ? 0 : Infinity; }
    }
  }
  const arcPt = (o, t) => [o.c[0] + o.r * Math.cos(o.a0 + arcSpan(o) * t), o.c[1] + o.r * Math.sin(o.a0 + arcSpan(o) * t)];

  // ---------------------------------------------------------------- dimensions
  /** Resolve a dim: with ref (a line, a rect edge, a circle or arc) it follows that object, so changing the object moves the dim. */
  function dimGeom(d, byId = ctx.byId) {
    let a = d.a, b = d.b;
    const kind = d.kind || 'lin';
    const r = d.ref && byId[d.ref];
    if (r && r.t === 'line') { a = r.a; b = r.b; } else if (r && r.t === 'rect') { const e = rectEdges(r)[d.edge ?? 0]; a = e.a; b = e.b; } else if (r && (r.t === 'circle' || r.t === 'arc')) {
      const k = d.ang ?? -0.8; a = [r.c[0] - r.r * Math.cos(k), r.c[1] - r.r * Math.sin(k)]; b = [r.c[0] + r.r * Math.cos(k), r.c[1] + r.r * Math.sin(k)];
      if (kind === 'rad') a = r.c;
    }
    if (!a || !b) return { a: [0, 0], b: [0, 0], a2: [0, 0], b2: [0, 0], n: [0, 1], len: 0, txt: '', kind, label: [0, 0] }; // its object is gone
    const L = dist(a, b) || 1e-9, n = [-(b[1] - a[1]) / L, (b[0] - a[0]) / L], off = kind === 'lin' ? d.off ?? 20 : 0;
    const a2 = [a[0] + n[0] * off, a[1] + n[1] * off], b2 = [b[0] + n[0] * off, b[1] + n[1] * off];
    const txt = d.txt || `${kind === 'dia' ? 'Ø' : kind === 'rad' ? 'R' : ''}${Math.round(L * 100) / 100}`;
    return { a, b, a2, b2, n, len: L, txt, kind, size: d.size ?? 10, label: kind === 'lin' ? lerp(a2, b2, 0.5) : [b[0] + ((b[0] - a[0]) / L) * (d.size ?? 10) * 0.9, b[1] + ((b[1] - a[1]) / L) * (d.size ?? 10) * 0.9] };
  }
  /** A new numeric value for a dim: returns the object change {put:[...]} (resizes the referenced line / circle, or moves b). */
  function setDimValue(d, v, byId = ctx.byId) {
    const g = dimGeom(d, byId), r = d.ref && byId[d.ref];
    if (!(v > 0)) throw new Error('size must be positive');
    if (r && r.t === 'line') { const u = sub(r.b, r.a), L = hyp(...u); return [{ ...r, b: [r.a[0] + (u[0] / L) * v, r.a[1] + (u[1] / L) * v] }]; }
    if (r && (r.t === 'circle' || r.t === 'arc')) return [{ ...r, r: d.kind === 'dia' ? v / 2 : v }];
    if (r && r.t === 'rect') { const k = d.edge ?? 0, x = k % 2 === 0, s0 = x ? Math.sign(r.q[0] - r.p[0]) || 1 : Math.sign(r.q[1] - r.p[1]) || 1; return [x ? { ...r, q: [r.p[0] + s0 * v, r.q[1]] } : { ...r, q: [r.q[0], r.p[1] + s0 * v] }]; }
    return [{ ...d, b: [d.a[0] + ((g.b[0] - g.a[0]) / g.len) * v, d.a[1] + ((g.b[1] - g.a[1]) / g.len) * v], txt: undefined }];
  }

  // ---------------------------------------------------------------- intersections
  /** Intersection points of two geometric parts (line / circle / arc), each only where it really exists. */
  function intersect(A, B) {
    if (A.t === 'line' && B.t === 'line') {
      const r = sub(A.b, A.a), s = sub(B.b, B.a), den = r[0] * s[1] - r[1] * s[0];
      if (Math.abs(den) < 1e-12) return [];
      const q = sub(B.a, A.a), t = (q[0] * s[1] - q[1] * s[0]) / den, u = (q[0] * r[1] - q[1] * r[0]) / den;
      return t >= -1e-9 && t <= 1 + 1e-9 && u >= -1e-9 && u <= 1 + 1e-9 ? [lerp(A.a, A.b, t)] : [];
    }
    if (A.t !== 'line' && B.t === 'line') return intersect(B, A);
    if (A.t === 'line') { // line with circle / arc
      const d = sub(A.b, A.a), f = sub(A.a, B.c), a = d[0] ** 2 + d[1] ** 2, b = 2 * (f[0] * d[0] + f[1] * d[1]), c = f[0] ** 2 + f[1] ** 2 - B.r ** 2, D = b * b - 4 * a * c;
      if (D < 0 || a < 1e-12) return [];
      return [(-b - Math.sqrt(D)) / (2 * a), (-b + Math.sqrt(D)) / (2 * a)].filter((t, i, ts) => t >= -1e-9 && t <= 1 + 1e-9 && (i === 0 || Math.abs(t - ts[0]) > 1e-9))
        .map(t => lerp(A.a, A.b, t)).filter(p => B.t === 'circle' || onArc(B, Math.atan2(p[1] - B.c[1], p[0] - B.c[0])));
    }
    const d = dist(A.c, B.c); // circle / arc with circle / arc
    if (d < 1e-9 || d > A.r + B.r || d < Math.abs(A.r - B.r)) return [];
    const x = (d * d + A.r * A.r - B.r * B.r) / (2 * d), h = Math.sqrt(Math.max(0, A.r * A.r - x * x)), u = [(B.c[0] - A.c[0]) / d, (B.c[1] - A.c[1]) / d];
    const m = [A.c[0] + u[0] * x, A.c[1] + u[1] * x];
    const ok = (o, p) => o.t === 'circle' || onArc(o, Math.atan2(p[1] - o.c[1], p[0] - o.c[0]));
    return [[m[0] - u[1] * h, m[1] + u[0] * h], [m[0] + u[1] * h, m[1] - u[0] * h]].filter((p, i, ps) => (i === 0 || dist(p, ps[0]) > 1e-9) && ok(A, p) && ok(B, p));
  }
  /** Parameter of p along a part: line 0..1, circle / arc angle from a0 (0 for a circle: from angle 0). */
  const param = (o, p) => (o.t === 'line' ? ((p[0] - o.a[0]) * (o.b[0] - o.a[0]) + (p[1] - o.a[1]) * (o.b[1] - o.a[1])) / (dist(o.a, o.b) ** 2 || 1)
    : norm(Math.atan2(p[1] - o.c[1], p[0] - o.c[0]) - (o.t === 'arc' ? o.a0 : 0)));
  const cuts = (o, others) => others.flatMap(x => parts(x).filter(q => q.id !== o.id).flatMap(q => intersect(o, q))).map(p => param(o, p));

  // ---------------------------------------------------------------- trim, split, extend
  /** Trim: remove the piece of `o` around p between its neighbouring cuts (or its ends). Returns replacement parts ([] = gone).
   *  A rect is trimmed as its four edges (the result are lines). */
  function trim(o, p, others) {
    const out = [];
    for (const e of o.t === 'rect' ? rectEdges(o) : [o]) {
      if (e.id !== o.id && distTo(e, p) > distTo(o, p) + 1e-6) { out.push(e); continue; } // other edges of a rect stay
      const ts = [...new Set(cuts(e, others.filter(x => x.id !== o.id).concat(o.t === 'rect' ? rectEdges(o).filter(x => x.id !== e.id) : [])).map(t => Math.round(t * 1e9) / 1e9))].sort((x, y) => x - y);
      const t = param(e, p);
      if (e.t === 'line') {
        const lo = ts.filter(x => x > 1e-9 && x < t).pop() ?? 0, hi = ts.find(x => x < 1 - 1e-9 && x > t) ?? 1;
        if (lo > 1e-9) out.push({ ...e, id: `${e.id}a`, b: lerp(e.a, e.b, lo) });
        if (hi < 1 - 1e-9) out.push({ ...e, id: `${e.id}b`, a: lerp(e.a, e.b, hi) });
      } else {
        const full = e.t === 'circle', span = full ? TAU : arcSpan(e), base = full ? 0 : e.a0;
        const cs = ts.filter(x => x > 1e-9 && x < span - 1e-9);
        if (full && cs.length < 2) { out.push(e); continue; } // a lone circle needs two cuts to lose a piece
        const lo = cs.filter(x => x < t).pop(), hi = cs.find(x => x > t);
        if (full) { // keep the rest of the circle as one arc (from hi around to lo, wrapping)
          const l = lo ?? cs[cs.length - 1], h = hi ?? cs[0];
          out.push({ ...e, t: 'arc', id: `${e.id}a`, a0: h, a1: l });
        } else {
          if (lo !== undefined) out.push({ ...e, id: `${e.id}a`, a0: base, a1: base + lo });
          if (hi !== undefined) out.push({ ...e, id: `${e.id}b`, a0: base + hi, a1: base + span });
        }
      }
    }
    return out;
  }
  /** Split a line / arc / circle-less object at p: two parts. */
  function split(o, p) {
    if (o.t === 'line') { const t = Math.min(0.999, Math.max(0.001, param(o, p))), m = lerp(o.a, o.b, t); return [{ ...o, id: `${o.id}a`, b: m }, { ...o, id: `${o.id}b`, a: m }]; }
    if (o.t === 'arc') { const t = param(o, p), s = arcSpan(o); return t > 0.001 && t < s - 0.001 ? [{ ...o, id: `${o.id}a`, a1: o.a0 + t }, { ...o, id: `${o.id}b`, a0: o.a0 + t }] : [o]; }
    return [o];
  }
  /** Extend the end of a line nearest to p along its direction to the first object it meets; null if nothing is hit. */
  function extend(o, p, others) {
    if (o.t !== 'line') return null;
    const atB = dist(p, o.b) < dist(p, o.a), from = atB ? o.a : o.b, to = atB ? o.b : o.a, L = dist(from, to) || 1;
    const far = [to[0] + ((to[0] - from[0]) / L) * 1e6, to[1] + ((to[1] - from[1]) / L) * 1e6];
    const ray = { t: 'line', id: o.id, a: to, b: far };
    const hits = others.flatMap(x => parts(x).filter(q => q.id !== o.id && !x.id?.startsWith?.(o.id)).flatMap(q => intersect(ray, q))).filter(q => dist(q, to) > 1e-6).sort((a, b) => dist(a, to) - dist(b, to));
    return hits.length ? { ...o, [atB ? 'b' : 'a']: hits[0] } : null;
  }

  /** Arc from a to b passing through m (three points on the arc); null when they are on one line. */
  function arcThrough(a, m, b) {
    const d = 2 * (a[0] * (m[1] - b[1]) + m[0] * (b[1] - a[1]) + b[0] * (a[1] - m[1]));
    if (Math.abs(d) < 1e-9 * (dist(a, b) ** 2 + 1)) return null;
    const a2 = a[0] ** 2 + a[1] ** 2, m2 = m[0] ** 2 + m[1] ** 2, b2 = b[0] ** 2 + b[1] ** 2;
    const c = [(a2 * (m[1] - b[1]) + m2 * (b[1] - a[1]) + b2 * (a[1] - m[1])) / d, (a2 * (b[0] - m[0]) + m2 * (a[0] - b[0]) + b2 * (m[0] - a[0])) / d];
    const ang = p => Math.atan2(p[1] - c[1], p[0] - c[0]), A = ang(a), B = ang(b);
    return norm(ang(m) - A) < norm(B - A) ? { t: 'arc', c, r: dist(a, c), a0: A, a1: B } : { t: 'arc', c, r: dist(a, c), a0: B, a1: A };
  }

  // ---------------------------------------------------------------- mechanisms
  // mech {joints: [{id, p, fixed?}], links: [[id, id]], sliders: [{j, a, b}] (joint j moves on the line a-b),
  // driver: {j, c} (joint j turns about the fixed joint c), len?: [link lengths]}. o.cur = solved joint positions
  // (set by canvas.js while it animates, never stored).
  const mechInit = m => Object.fromEntries(m.joints.map(j => [j.id, j.p]));
  const mechPts = m => m.cur || mechInit(m);
  const mechLens = (m, lens) => { const P = mechInit(m); return m.links.map((l, i) => lens?.[i] ?? m.len?.[i] ?? dist(P[l[0]], P[l[1]])); };
  const mechAngle0 = m => { const P = mechInit(m); return Math.atan2(P[m.driver.j][1] - P[m.driver.c][1], P[m.driver.j][0] - P[m.driver.c][0]); };
  function lineCircle(a, b, c, r) { // infinite line a-b with a circle
    const d = sub(b, a), f = sub(a, c), A = d[0] ** 2 + d[1] ** 2, B = 2 * (f[0] * d[0] + f[1] * d[1]), D = B * B - 4 * A * (f[0] ** 2 + f[1] ** 2 - r * r);
    if (A < 1e-12 || D < 0) return [];
    return [(-B - Math.sqrt(D)) / (2 * A), (-B + Math.sqrt(D)) / (2 * A)].map(t => lerp(a, b, t));
  }
  /** Joint positions for driver angle `ang`, or null when the mechanism cannot reach it. `prev` keeps the branch. */
  function solveMech(m, ang, prev, lens) {
    const L = mechLens(m, lens), J = {}, ref = prev || mechInit(m), d = m.driver;
    for (const j of m.joints) if (j.fixed) J[j.id] = j.p;
    const di = m.links.findIndex(l => (l[0] === d.j && l[1] === d.c) || (l[1] === d.j && l[0] === d.c));
    if (!J[d.c] || di < 0) return null;
    J[d.j] = [J[d.c][0] + L[di] * Math.cos(ang), J[d.c][1] + L[di] * Math.sin(ang)];
    const pickNear = (id, ps) => (ps.length ? ps.reduce((a, b) => (dist(b, ref[id]) < dist(a, ref[id]) ? b : a)) : null);
    for (let progress = true; progress;) {
      progress = false;
      for (const j of m.joints) {
        if (J[j.id]) continue;
        const known = m.links.map((l, i) => ({ o: l[0] === j.id ? l[1] : l[1] === j.id ? l[0] : null, r: L[i] })).filter(k => k.o && J[k.o]);
        const sl = (m.sliders || []).find(s => s.j === j.id);
        let cand;
        if (known.length >= 2) {
          const [k1, k2] = known, dd = dist(J[k1.o], J[k2.o]);
          if (dd < 1e-9 || dd > k1.r + k2.r || dd < Math.abs(k1.r - k2.r)) return null;
          cand = intersect({ t: 'circle', c: J[k1.o], r: k1.r }, { t: 'circle', c: J[k2.o], r: k2.r });
        } else if (known.length === 1 && sl) cand = lineCircle(sl.a, sl.b, J[known[0].o], known[0].r);
        else continue;
        const p = pickNear(j.id, cand);
        if (!p) return null;
        J[j.id] = p; progress = true;
      }
    }
    return m.joints.every(j => J[j.id]) ? J : null;
  }
  /** Reachable driver angles around the start: {full: true} or {lo, hi} (radians, lo < start < hi), null if stuck. */
  function mechRange(m, lens, steps = 720, start) {
    const a0 = start ?? mechAngle0(m), st = (2 * Math.PI) / steps;
    if (!solveMech(m, a0, null, lens)) return null;
    const walk = dir => { let prev = null, k = 0; for (; k < steps; k++) { const s = solveMech(m, a0 + dir * k * st, prev, lens); if (!s) break; prev = s; } return k; };
    const up = walk(1);
    if (up >= steps) return { full: true, a0 };
    return { full: false, a0, lo: a0 - (walk(-1) - 1) * st, hi: a0 + (up - 1) * st };
  }

  // ---------------------------------------------------------------- snapping + alignment
  /** Snap p (world units) to the nearest object point within tol: end points, centres, mid points, intersections, then the grid. */
  function snap(p, objs, tol, opts = {}) {
    let best = null, bd = tol;
    const tryP = (q, kind) => { const d = dist(p, q) - (kind === 'mid' ? 0 : 1e-3); /* ties go to the stronger point */ if (d < bd) { bd = d; best = { p: q, kind }; } };
    if (opts.objects !== false) {
      const near = objs.filter(o => GEO.has(o.t) && Ink.overlap(bounds(o), [p[0] - tol, p[1] - tol, 2 * tol, 2 * tol]));
      for (const o of near) {
        if (o.t === 'line') { tryP(o.a, 'end'); tryP(o.b, 'end'); tryP(lerp(o.a, o.b, 0.5), 'mid'); }
        else if (o.t === 'rect') for (const e of rectEdges(o)) { tryP(e.a, 'end'); tryP(lerp(e.a, e.b, 0.5), 'mid'); }
        else { tryP(o.c, 'center'); if (o.t === 'arc') { tryP(arcPt(o, 0), 'end'); tryP(arcPt(o, 1), 'end'); } }
      }
      const ps = near.flatMap(parts);
      for (let i = 0; i < ps.length; i++) for (let j = i + 1; j < ps.length; j++) for (const q of intersect(ps[i], ps[j])) tryP(q, 'cross');
    }
    if (!best && opts.grid) { const g = opts.grid, q = [Math.round(p[0] / g) * g, Math.round(p[1] / g) * g]; if (dist(p, q) < tol) best = { p: q, kind: 'grid' }; }
    return best;
  }
  /** Is the line a little off horizontal / vertical (within maxDeg, but not exact)? Returns the straightened line or null. */
  function straighten(o, maxDeg = 6) {
    const dx = o.b[0] - o.a[0], dy = o.b[1] - o.a[1], L = hyp(dx, dy);
    if (o.t !== 'line' || L < 1e-6) return null;
    const a = (Math.atan2(dy, dx) * 180) / Math.PI, off = h => Math.abs(((a - h + 540) % 360) - 180);
    const hz = Math.min(off(0), off(180)), vt = Math.min(off(90), off(-90));
    if (Math.min(hz, vt) > maxDeg || Math.min(hz, vt) < 1e-3) return null;
    return hz < vt ? { ...o, b: [o.b[0], o.a[1]] } : { ...o, b: [o.a[0], o.b[1]] };
  }

  // ---------------------------------------------------------------- QuickShape+
  /** Kåsa circle fit: {c, r, err} with err = rms residual / r. */
  function fitCircle(pts) {
    const n = pts.length;
    let sx = 0, sy = 0; for (const p of pts) { sx += p[0]; sy += p[1]; }
    const mx = sx / n, my = sy / n;
    let suu = 0, svv = 0, suv = 0, suuu = 0, svvv = 0, suvv = 0, svuu = 0;
    for (const p of pts) { const u = p[0] - mx, v = p[1] - my; suu += u * u; svv += v * v; suv += u * v; suuu += u ** 3; svvv += v ** 3; suvv += u * v * v; svuu += v * u * u; }
    const det = suu * svv - suv * suv;
    if (Math.abs(det) < 1e-9) return null;
    const uc = (0.5 * (suuu + suvv) * svv - 0.5 * (svvv + svuu) * suv) / det, vc = (0.5 * (svvv + svuu) * suu - 0.5 * (suuu + suvv) * suv) / det;
    const c = [mx + uc, my + vc], r = pts.reduce((s, p) => s + dist(p, c), 0) / n;
    return r > 0 ? { c, r, err: Math.sqrt(pts.reduce((s, p) => s + (dist(p, c) - r) ** 2, 0) / n) / r } : null;
  }
  /** Recognise a finished stroke (pts [[x, y], ...], world units). `tol` 0.03 strict .. 0.12 loose.
   *  Returns {t: 'line'|'circle'|'arc'|'rect'|'ellipse', ...geometry} or null (keep the free stroke). */
  function recognize(pts, tol = 0.06) {
    if (pts.length < 4) return null;
    const first = pts[0], last = pts[pts.length - 1];
    let len = 0; for (let i = 1; i < pts.length; i++) len += dist(pts[i - 1], pts[i]);
    const chord = dist(first, last), bb = box(pts), diag = hyp(bb[2], bb[3]);
    if (len < 1e-6 || diag < 1e-6) return null;
    const dev = Math.max(...pts.map(p => segDist(p, first, last)));
    if (chord > 0.5 * len && dev <= tol * chord) return { t: 'line', a: first.slice(0, 2), b: last.slice(0, 2) };
    const closed = chord < 0.25 * len;
    const fit = fitCircle(pts);
    if (closed) {
      // RDP needs two distinct ends: split the loop at the point farthest from the start
      const far = pts.reduce((bi, p, i) => (dist(p, first) > dist(pts[bi], first) ? i : bi), 0);
      const poly = [...Ink.simplify(pts.slice(0, far + 1), diag * 0.04), ...Ink.simplify(pts.slice(far), diag * 0.04).slice(1)];
      if (poly.length === 5 || (poly.length === 4 && dist(poly[0], poly[3]) < diag * 0.2)) {
        const xs = pts.map(p => p[0]), ys = pts.map(p => p[1]);
        const axis = poly.slice(1).every((p, i) => { const dx = Math.abs(p[0] - poly[i][0]), dy = Math.abs(p[1] - poly[i][1]); return Math.min(dx, dy) < 0.28 * Math.max(dx, dy); });
        if (axis) return { t: 'rect', p: [Math.min(...xs), Math.min(...ys)], q: [Math.max(...xs), Math.max(...ys)] };
      }
      if (fit && fit.err < tol * 0.9) return { t: 'circle', c: fit.c, r: fit.r };
      const c = [bb[0] + bb[2] / 2, bb[1] + bb[3] / 2], rx = bb[2] / 2, ry = bb[3] / 2;
      const e = Math.sqrt(pts.reduce((s, p) => s + (hyp((p[0] - c[0]) / rx, (p[1] - c[1]) / ry) - 1) ** 2, 0) / pts.length);
      if (rx > 4 && ry > 4 && e < tol * 1.4) return { t: 'ellipse', c, rx, ry };
      return null;
    }
    if (fit && fit.err < tol * 0.7 && fit.r < len * 2) {
      const a0 = Math.atan2(first[1] - fit.c[1], first[0] - fit.c[0]);
      let acc = 0, prev = a0; // swept angle, signed (clockwise on screen = positive)
      for (const p of pts) { let d = Math.atan2(p[1] - fit.c[1], p[0] - fit.c[0]) - prev; d = ((d + 3 * Math.PI) % TAU) - Math.PI; acc += d; prev += d; }
      if (Math.abs(acc) > 0.7 && Math.abs(acc) < TAU - 0.5) return acc > 0 ? { t: 'arc', c: fit.c, r: fit.r, a0, a1: norm(a0 + acc) } : { t: 'arc', c: fit.c, r: fit.r, a0: norm(a0 + acc), a1: a0 };
    }
    return null;
  }
  /** Scribble-erase gesture: one fast stroke zig-zagging back and forth over a small area (hatching is separate strokes). */
  function isScribble(pts, ms) {
    if (pts.length < 8 || ms > 1800) return false;
    let len = 0, rev = 0, pd = null;
    for (let i = 1; i < pts.length; i++) {
      const d = sub(pts[i], pts[i - 1]), l = hyp(...d); len += l;
      if (l < 1e-6) continue;
      if (pd && d[0] * pd[0] + d[1] * pd[1] < -0.3 * l * hyp(...pd)) rev++;
      pd = d;
    }
    const bb = box(pts);
    return rev >= 4 && len > 3.5 * hyp(bb[2], bb[3]);
  }

  const api = { ctx, solveMech, mechRange, mechAngle0, mechLens, mechPts, arcThrough, rectEdges, parts, bounds, samples, distTo, dimGeom, setDimValue, intersect, trim, split, extend, snap, straighten, fitCircle, recognize, isScribble, arcPt, arcSpan, dist, lerp, GEO };
  if (typeof module !== 'undefined' && module.exports) module.exports = api; else root.Geo = api;
})(this);
