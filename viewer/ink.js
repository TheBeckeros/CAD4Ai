// Geometry for the sketch pad (infinite canvas): ink smoothing and outlines, hit tests, lasso, region clipping
// for the snap tool, and the one-step accept of a proposal. Pure functions; loaded by sketch.js (global Ink)
// and by node for ink.test.js. Items: stroke {pts: [[x, y, pressure]], w, tool}, text {x, y, s, size}, image {x, y, w, h}.
(function (root) {
  const hyp = (dx, dy) => Math.sqrt(dx * dx + dy * dy);
  const lerp = (a, b, t) => a + (b - a) * t;
  const lerpP = (a, b, t) => [lerp(a[0], b[0], t), lerp(a[1], b[1], t), lerp(a[2] ?? 0.5, b[2] ?? 0.5, t)];

  /** Input filter: move the pen tip only part of the way to the raw sample (k = 0 raw, 0.6 smooth). */
  const step = (prev, raw, k) => (prev ? lerpP(prev, raw, 1 - k) : raw.slice());

  /** Ramer–Douglas–Peucker on x, y (pressure rides along); keeps the end points. */
  function simplify(pts, eps = 0.4) {
    if (pts.length < 3) return pts.slice();
    const keep = new Uint8Array(pts.length);
    keep[0] = keep[pts.length - 1] = 1;
    const stack = [[0, pts.length - 1]];
    while (stack.length) {
      const [a, b] = stack.pop();
      const [ax, ay] = pts[a], [bx, by] = pts[b], L = hyp(bx - ax, by - ay) || 1e-9;
      let best = -1, bi = -1;
      for (let i = a + 1; i < b; i++) {
        const d = Math.abs((bx - ax) * (ay - pts[i][1]) - (ax - pts[i][0]) * (by - ay)) / L;
        // pressure changes count as detail too, so pressure swells survive
        const dp = Math.abs((pts[i][2] ?? 0.5) - lerp(pts[a][2] ?? 0.5, pts[b][2] ?? 0.5, (i - a) / (b - a))) * 8 * eps;
        if (d + dp > best) { best = d + dp; bi = i; }
      }
      if (best > eps) { keep[bi] = 1; stack.push([a, bi], [bi, b]); }
    }
    return pts.filter((_, i) => keep[i]);
  }

  /** Radius at a point: pressure 0.5 (mouse) gives the nominal width. */
  const radius = (w, p, pressure) => (w / 2) * (pressure ? 0.2 + 1.6 * (p ?? 0.5) : 1);

  /** Filled outline polygon of a stroke (round caps); null for a dot (draw a circle of radius(...)). */
  function outline(pts, w, pressure = true) {
    const P = pts.filter((p, i) => i === 0 || hyp(p[0] - pts[i - 1][0], p[1] - pts[i - 1][1]) > 1e-6);
    if (P.length < 2) return null;
    const n = P.length, rs = P.map(p => radius(w, p[2], pressure));
    const r = rs.map((v, i) => (rs[Math.max(0, i - 1)] + 2 * v + rs[Math.min(n - 1, i + 1)]) / 4); // calm pressure noise
    const N = [], L = [], R = [];
    for (let i = 0; i < n - 1; i++) { const dx = P[i + 1][0] - P[i][0], dy = P[i + 1][1] - P[i][1], d = hyp(dx, dy); N.push([-dy / d, dx / d]); }
    for (let i = 0; i < n; i++) {
      // mitered join: corners (rectangles, sharp pen turns) keep their full width, capped at 2x
      const a = N[Math.max(0, i - 1)], b = N[Math.min(n - 2, i)];
      let mx = a[0] + b[0], my = a[1] + b[1];
      const ml = hyp(mx, my);
      if (ml < 1e-6) { mx = b[0]; my = b[1]; } else { mx /= ml; my /= ml; }
      const k = r[i] / Math.max(0.5, mx * a[0] + my * a[1]);
      L.push([P[i][0] + mx * k, P[i][1] + my * k]);
      R.push([P[i][0] - mx * k, P[i][1] - my * k]);
    }
    // round cap: half circle from side point s around the tip in direction (dx, dy)
    const cap = (c, rad, s, dx, dy, out) => {
      const sl = hyp(s[0] - c[0], s[1] - c[1]) || 1, ux = (s[0] - c[0]) / sl, uy = (s[1] - c[1]) / sl;
      for (let k = 1; k < 8; k++) { const t = (Math.PI * k) / 8, co = Math.cos(t), si = Math.sin(t); out.push([c[0] + (ux * co + dx * si) * rad, c[1] + (uy * co + dy * si) * rad]); }
    };
    const poly = L.slice(), e = N[n - 2], b0 = N[0];
    cap(P[n - 1], r[n - 1], L[n - 1], e[1], -e[0], poly); // forward = normal turned back by 90°
    for (let i = n - 1; i >= 0; i--) poly.push(R[i]);
    cap(P[0], r[0], R[0], -b0[1], b0[0], poly);
    return poly;
  }

  /** Points of a line / rect / ellipse drawn from corner a to corner b (constant pressure). */
  function shapePts(kind, a, b) {
    const [x0, y0] = a, [x1, y1] = b, p = 0.5;
    if (kind === 'line') return [[x0, y0, p], [x1, y1, p]];
    if (kind === 'rect') return [[x0, y0, p], [x1, y0, p], [x1, y1, p], [x0, y1, p], [x0, y0, p]];
    const cx = (x0 + x1) / 2, cy = (y0 + y1) / 2, rx = Math.abs(x1 - x0) / 2, ry = Math.abs(y1 - y0) / 2;
    return Array.from({ length: 65 }, (_, k) => [cx + rx * Math.cos((k * Math.PI) / 32), cy + ry * Math.sin((k * Math.PI) / 32), p]);
  }

  // text size estimate (the canvas measures exactly; this is for bounds without a canvas)
  const textBox = it => { const ls = String(it.s).split('\n'); return [it.x, it.y, Math.max(1, ...ls.map(l => l.length)) * it.size * 0.6, ls.length * it.size * 1.25]; };

  /** Axis-aligned bounds [x, y, w, h] of an item, stroke width included. */
  function bounds(it) {
    if (it.t === 'text') return textBox(it);
    if (it.t === 'image') return [it.x, it.y, it.w, it.h];
    let x0 = Infinity, y0 = Infinity, x1 = -Infinity, y1 = -Infinity;
    for (const p of it.pts) { if (p[0] < x0) x0 = p[0]; if (p[0] > x1) x1 = p[0]; if (p[1] < y0) y0 = p[1]; if (p[1] > y1) y1 = p[1]; }
    const m = it.w; // pressure can reach 0.9 w radius
    return [x0 - m, y0 - m, x1 - x0 + 2 * m, y1 - y0 + 2 * m];
  }
  const union = bs => {
    if (!bs.length) return null;
    const x0 = Math.min(...bs.map(b => b[0])), y0 = Math.min(...bs.map(b => b[1]));
    return [x0, y0, Math.max(...bs.map(b => b[0] + b[2])) - x0, Math.max(...bs.map(b => b[1] + b[3])) - y0];
  };
  const inRect = (p, r) => p[0] >= r[0] && p[0] <= r[0] + r[2] && p[1] >= r[1] && p[1] <= r[1] + r[3];
  const rectIn = (a, r) => a[0] >= r[0] && a[1] >= r[1] && a[0] + a[2] <= r[0] + r[2] && a[1] + a[3] <= r[1] + r[3];
  const overlap = (a, b) => a[0] <= b[0] + b[2] && b[0] <= a[0] + a[2] && a[1] <= b[1] + b[3] && b[1] <= a[1] + a[3];

  function segDist(p, a, b) {
    const dx = b[0] - a[0], dy = b[1] - a[1], L = dx * dx + dy * dy;
    const t = L ? Math.max(0, Math.min(1, ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / L)) : 0;
    return hyp(p[0] - a[0] - t * dx, p[1] - a[1] - t * dy);
  }
  /** Does point p (radius r, world units) touch the item? */
  function hit(it, p, r) {
    if (it.t !== 'stroke') return inRect(p, bounds(it));
    const pts = it.pts, rr = r + it.w / 2;
    if (pts.length === 1) return hyp(p[0] - pts[0][0], p[1] - pts[0][1]) <= rr;
    for (let i = 1; i < pts.length; i++) if (segDist(p, pts[i - 1], pts[i]) <= rr) return true;
    return false;
  }

  function inPoly(p, poly) {
    let c = false;
    for (let i = 0, j = poly.length - 1; i < poly.length; j = i++) {
      const a = poly[i], b = poly[j];
      if ((a[1] > p[1]) !== (b[1] > p[1]) && p[0] < ((b[0] - a[0]) * (p[1] - a[1])) / (b[1] - a[1]) + a[0]) c = !c;
    }
    return c;
  }
  /** Lasso: strokes with most of their points inside, texts / images with their centre inside. */
  function lasso(items, poly) {
    return items.filter(it => {
      if (it.t === 'stroke') return it.pts.filter(p => inPoly(p, poly)).length >= Math.max(1, it.pts.length * 0.6);
      const b = bounds(it);
      return inPoly([b[0] + b[2] / 2, b[1] + b[3] / 2], poly);
    });
  }

  // Liang–Barsky: the part [t0, t1] of segment a-b inside rect r, or null
  function clipSeg(a, b, r) {
    let t0 = 0, t1 = 1;
    const dx = b[0] - a[0], dy = b[1] - a[1];
    const P = [-dx, dx, -dy, dy], Q = [a[0] - r[0], r[0] + r[2] - a[0], a[1] - r[1], r[1] + r[3] - a[1]];
    for (let k = 0; k < 4; k++) {
      if (P[k] === 0) { if (Q[k] < 0) return null; continue; }
      const t = Q[k] / P[k];
      if (P[k] < 0) { if (t > t1) return null; if (t > t0) t0 = t; } else { if (t < t0) return null; if (t < t1) t1 = t; }
    }
    return [t0, t1];
  }

  /** Split a polyline at the rect border: {inside: [runs], outside: [runs]}. Outside runs keep every original outside
   *  point unchanged and end on the border, so cutting the inside away never moves anything outside. */
  function clipStroke(pts, r) {
    const inside = [], outside = [];
    if (pts.length === 1) { (inRect(pts[0], r) ? inside : outside).push([pts[0].slice()]); return { inside, outside }; }
    let run = null, runIn = null;
    const piece = (a, b, isIn) => {
      if (runIn === isIn && run) { run.push(b); return; }
      if (run) (runIn ? inside : outside).push(run);
      run = [a, b]; runIn = isIn;
    };
    for (let i = 1; i < pts.length; i++) {
      const a = pts[i - 1], b = pts[i], c = clipSeg(a, b, r);
      if (!c || c[1] - c[0] < 1e-9) { piece(a.slice(), b.slice(), false); continue; }
      const A = c[0] > 0 ? lerpP(a, b, c[0]) : a.slice(), B = c[1] < 1 ? lerpP(a, b, c[1]) : b.slice();
      if (c[0] > 0) piece(a.slice(), A, false);
      piece(A, B, true);
      if (c[1] < 1) piece(B, b.slice(), false);
    }
    if (run) (runIn ? inside : outside).push(run);
    return { inside, outside };
  }

  /** Items a snap rect covers: strokes that reach into it (they get cut at the border), texts / images fully inside. */
  function regionIds(items, r) {
    return items.filter(it => (it.t === 'stroke' ? overlap(bounds(it), r) && clipStroke(it.pts, r).inside.length > 0 : rectIn(bounds(it), r))).map(it => it.id);
  }

  /** A proposal made to fit the region: strokes cut to it, texts shrunk to fit or dropped, images dropped unless inside. */
  function clipProposal(items, r) {
    const out = [];
    for (const it of items || []) {
      if (it.t === 'stroke') {
        clipStroke(it.pts, r).inside.forEach((pts, k) => out.push({ ...it, id: k ? `${it.id}.${k}` : it.id, pts }));
      } else if (it.t === 'text') {
        if (!inRect([it.x, it.y], r)) continue;
        const b = textBox(it), f = Math.min(1, (r[0] + r[2] - it.x) / b[2], (r[1] + r[3] - it.y) / b[3]);
        if (f * it.size >= 2) out.push({ ...it, size: it.size * f });
      } else if (rectIn(bounds(it), r)) out.push({ ...it });
    }
    return out;
  }

  /** Accept a snap proposal in one step. `items` = id -> current item, `newId()` makes fresh ids.
   *  Returns {put, del, undo: {put, del}}: region items go (strokes crossing the border keep their outside parts as
   *  new items), the clipped proposal comes in; anything not listed in snap.ids is never in put or del. */
  function accept(items, snap, newId) {
    const r = snap.rect, put = [], del = [], back = [];
    for (const id of snap.ids) {
      const it = items[id];
      if (!it || it.deleted) continue;
      if (it.t === 'stroke') {
        const { inside, outside } = clipStroke(it.pts, r);
        if (!inside.length) continue; // moved out of the region since the snap: leave it
        outside.forEach(pts => put.push({ ...it, id: newId(), pts }));
      } else if (!rectIn(bounds(it), r)) continue;
      del.push(id); back.push(it);
    }
    const z = Math.max(0, ...Object.values(items).map(i => i.z || 0));
    clipProposal(snap.proposal, r).forEach((it, k) => put.push({ ...it, id: newId(), z: z + 1 + k * 1e-3 }));
    return { put, del, undo: { put: back, del: put.map(i => i.id) } };
  }

  const api = { step, simplify, radius, outline, shapePts, bounds, union, inRect, rectIn, overlap, hit, inPoly, lasso, clipSeg, clipStroke, regionIds, clipProposal, accept };
  if (typeof module !== 'undefined' && module.exports) module.exports = api; else root.Ink = api;
})(this);
