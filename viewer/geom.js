// Analysis of a triangle mesh into B-rep features: faces, edges, vertices.
// Input is either a mesh from STEP (occt-import-js, faces given as triangle ranges)
// or an STL (faces are estimated by merging neighbouring triangles).

const EPS_ANG_PLANE = Math.cos((0.6 * Math.PI) / 180);

// ---------------------------------------------------------------- vectors
export const v3 = {
  sub: (a, b) => [a[0] - b[0], a[1] - b[1], a[2] - b[2]],
  add: (a, b) => [a[0] + b[0], a[1] + b[1], a[2] + b[2]],
  mul: (a, s) => [a[0] * s, a[1] * s, a[2] * s],
  dot: (a, b) => a[0] * b[0] + a[1] * b[1] + a[2] * b[2],
  cross: (a, b) => [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]],
  len: a => Math.hypot(a[0], a[1], a[2]),
  norm: a => { const l = Math.hypot(a[0], a[1], a[2]) || 1; return [a[0] / l, a[1] / l, a[2] / l]; },
  dist: (a, b) => Math.hypot(a[0] - b[0], a[1] - b[1], a[2] - b[2]),
};

/** Eigenvalues and eigenvectors of a symmetric 3x3 matrix (Jacobi), sorted ascending. */
export function eigenSym3(m) {
  const a = [[m[0][0], m[0][1], m[0][2]], [m[1][0], m[1][1], m[1][2]], [m[2][0], m[2][1], m[2][2]]];
  const v = [[1, 0, 0], [0, 1, 0], [0, 0, 1]];
  for (let it = 0; it < 50; it++) {
    let p = 0, q = 1, big = Math.abs(a[0][1]);
    if (Math.abs(a[0][2]) > big) { p = 0; q = 2; big = Math.abs(a[0][2]); }
    if (Math.abs(a[1][2]) > big) { p = 1; q = 2; big = Math.abs(a[1][2]); }
    if (big < 1e-12) break;
    const th = 0.5 * Math.atan2(2 * a[p][q], a[q][q] - a[p][p]);
    const c = Math.cos(th), s = Math.sin(th);
    for (let k = 0; k < 3; k++) {
      const akp = a[k][p], akq = a[k][q];
      a[k][p] = c * akp - s * akq; a[k][q] = s * akp + c * akq;
    }
    for (let k = 0; k < 3; k++) {
      const apk = a[p][k], aqk = a[q][k];
      a[p][k] = c * apk - s * aqk; a[q][k] = s * apk + c * aqk;
    }
    for (let k = 0; k < 3; k++) {
      const vkp = v[k][p], vkq = v[k][q];
      v[k][p] = c * vkp - s * vkq; v[k][q] = s * vkp + c * vkq;
    }
  }
  const vals = [a[0][0], a[1][1], a[2][2]];
  const order = [0, 1, 2].sort((i, j) => vals[i] - vals[j]);
  return { values: order.map(i => vals[i]), vectors: order.map(i => [v[0][i], v[1][i], v[2][i]]) };
}

/** 2D least-squares circle fit (Kasa). */
function fitCircle2(pts) {
  let sx = 0, sy = 0, sxx = 0, syy = 0, sxy = 0, sxz = 0, syz = 0, sz = 0;
  const n = pts.length;
  for (const [x, y] of pts) {
    const z = x * x + y * y;
    sx += x; sy += y; sxx += x * x; syy += y * y; sxy += x * y; sxz += x * z; syz += y * z; sz += z;
  }
  // [sxx sxy sx; sxy syy sy; sx sy n] [A B C] = [sxz syz sz]
  const M = [[sxx, sxy, sx], [sxy, syy, sy], [sx, sy, n]];
  const r = [sxz, syz, sz];
  const det = m => m[0][0] * (m[1][1] * m[2][2] - m[1][2] * m[2][1]) - m[0][1] * (m[1][0] * m[2][2] - m[1][2] * m[2][0]) + m[0][2] * (m[1][0] * m[2][1] - m[1][1] * m[2][0]);
  const D = det(M);
  if (Math.abs(D) < 1e-18) return null;
  const col = (k) => M.map((row, i) => row.map((x, j) => (j === k ? r[i] : x)));
  const A = det(col(0)) / D, B = det(col(1)) / D, C = det(col(2)) / D;
  const cx = A / 2, cy = B / 2;
  const R = Math.sqrt(Math.max(0, C + cx * cx + cy * cy));
  let res = 0;
  for (const [x, y] of pts) res = Math.max(res, Math.abs(Math.hypot(x - cx, y - cy) - R));
  return { cx, cy, r: R, residual: res };
}

/** In-plane basis for a normal. */
function basis(n) {
  const ref = Math.abs(n[0]) < 0.9 ? [1, 0, 0] : [0, 1, 0];
  const u = v3.norm(v3.cross(n, ref));
  const w = v3.cross(n, u);
  return [u, w];
}

/** Circle in 3D: plane of the points + 2D fit. */
export function fitCircle3(points) {
  if (points.length < 3) return null;
  const c = [0, 0, 0];
  for (const p of points) { c[0] += p[0]; c[1] += p[1]; c[2] += p[2]; }
  c[0] /= points.length; c[1] /= points.length; c[2] /= points.length;
  const cov = [[0, 0, 0], [0, 0, 0], [0, 0, 0]];
  for (const p of points) {
    const d = v3.sub(p, c);
    for (let i = 0; i < 3; i++) for (let j = 0; j < 3; j++) cov[i][j] += d[i] * d[j];
  }
  const e = eigenSym3(cov);
  const n = v3.norm(e.vectors[0]);
  const [u, w] = basis(n);
  const fit = fitCircle2(points.map(p => { const d = v3.sub(p, c); return [v3.dot(d, u), v3.dot(d, w)]; }));
  if (!fit) return null;
  const center = v3.add(c, v3.add(v3.mul(u, fit.cx), v3.mul(w, fit.cy)));
  return { center, normal: n, radius: fit.r, residual: fit.residual, planarity: Math.sqrt(Math.max(0, e.values[0]) / points.length) };
}

// ------------------------------------------------------------- analysis
/**
 * @param {Float32Array|number[]} positions  xyz
 * @param {Uint32Array|number[]|null} index  triangles (null = consecutive triples)
 * @param {{first:number,last:number}[]|null} faceRanges  triangle ranges of the B-rep faces
 */
export function analyzeMesh(positions, index, faceRanges) {
  const P = positions;
  const nVert = P.length / 3;
  const idx = index ? Uint32Array.from(index) : Uint32Array.from({ length: nVert }, (_, i) => i);
  const nTri = idx.length / 3;

  // bbox, vertex welding
  const lo = [Infinity, Infinity, Infinity], hi = [-Infinity, -Infinity, -Infinity];
  for (let i = 0; i < nVert; i++) for (let a = 0; a < 3; a++) {
    const x = P[i * 3 + a]; if (x < lo[a]) lo[a] = x; if (x > hi[a]) hi[a] = x;
  }
  const diag = Math.hypot(hi[0] - lo[0], hi[1] - lo[1], hi[2] - lo[2]) || 1;
  const q = diag * 1e-6;
  const weldMap = new Map();
  const weld = new Int32Array(nVert);
  const wpos = [];
  for (let i = 0; i < nVert; i++) {
    const k = `${Math.round(P[i * 3] / q)},${Math.round(P[i * 3 + 1] / q)},${Math.round(P[i * 3 + 2] / q)}`;
    let w = weldMap.get(k);
    if (w === undefined) { w = wpos.length; weldMap.set(k, w); wpos.push([P[i * 3], P[i * 3 + 1], P[i * 3 + 2]]); }
    weld[i] = w;
  }
  const nW = wpos.length;

  // triangle normals and areas
  const tn = new Float64Array(nTri * 3), ta = new Float64Array(nTri), tc = new Float64Array(nTri * 3);
  for (let t = 0; t < nTri; t++) {
    const a = wpos[weld[idx[t * 3]]], b = wpos[weld[idx[t * 3 + 1]]], c = wpos[weld[idx[t * 3 + 2]]];
    const cr = v3.cross(v3.sub(b, a), v3.sub(c, a));
    const l = v3.len(cr);
    ta[t] = l / 2;
    tn[t * 3] = cr[0] / (l || 1); tn[t * 3 + 1] = cr[1] / (l || 1); tn[t * 3 + 2] = cr[2] / (l || 1);
    for (let k = 0; k < 3; k++) tc[t * 3 + k] = (a[k] + b[k] + c[k]) / 3;
  }

  // mesh edges
  const edgeMap = new Map();
  const ek = (a, b) => (a < b ? a * nW + b : b * nW + a);
  for (let t = 0; t < nTri; t++) {
    for (let e = 0; e < 3; e++) {
      const a = weld[idx[t * 3 + e]], b = weld[idx[t * 3 + ((e + 1) % 3)]];
      if (a === b) continue;
      const k = ek(a, b);
      const rec = edgeMap.get(k);
      if (rec) rec.tris.push(t); else edgeMap.set(k, { a, b, tris: [t] });
    }
  }

  // faces
  const triFace = new Int32Array(nTri).fill(-1);
  let nFace = 0;
  if (faceRanges && faceRanges.length) {
    faceRanges.forEach((r, f) => { for (let t = r.first; t <= r.last && t < nTri; t++) triFace[t] = f; });
    nFace = faceRanges.length;
    for (let t = 0; t < nTri; t++) if (triFace[t] < 0) triFace[t] = nFace++;
  } else {
    // STL: merge neighbouring triangles with similar normals
    const nbr = Array.from({ length: nTri }, () => []);
    for (const rec of edgeMap.values()) if (rec.tris.length === 2) {
      nbr[rec.tris[0]].push(rec.tris[1]); nbr[rec.tris[1]].push(rec.tris[0]);
    }
    const dotT = (a, b) => tn[a * 3] * tn[b * 3] + tn[a * 3 + 1] * tn[b * 3 + 1] + tn[a * 3 + 2] * tn[b * 3 + 2];
    const tol = diag * 1e-5;
    // 1) planes: coplanar connected regions
    const tmp = new Int32Array(nTri).fill(-1);
    const size = [];
    for (let s = 0; s < nTri; s++) {
      if (tmp[s] >= 0) continue;
      const f = size.length; size.push(0);
      tmp[s] = f;
      const off = tn[s * 3] * tc[s * 3] + tn[s * 3 + 1] * tc[s * 3 + 1] + tn[s * 3 + 2] * tc[s * 3 + 2];
      const stack = [s];
      while (stack.length) {
        const t = stack.pop(); size[f]++;
        for (const u of nbr[t]) {
          if (tmp[u] >= 0 || dotT(s, u) < EPS_ANG_PLANE) continue;
          const o = tn[s * 3] * tc[u * 3] + tn[s * 3 + 1] * tc[u * 3 + 1] + tn[s * 3 + 2] * tc[u * 3 + 2];
          if (Math.abs(o - off) > tol * 10) continue;
          tmp[u] = f; stack.push(u);
        }
      }
    }
    // 2) curved: join remaining triangles along a smoothly varying normal
    const cosSmooth = Math.cos((20 * Math.PI) / 180);
    const remap = new Map();
    for (let s = 0; s < nTri; s++) {
      if (triFace[s] >= 0) continue;
      if (size[tmp[s]] > 1) {
        if (!remap.has(tmp[s])) remap.set(tmp[s], nFace++);
        triFace[s] = remap.get(tmp[s]);
        continue;
      }
      const f = nFace++;
      triFace[s] = f;
      const stack = [s];
      while (stack.length) {
        const t = stack.pop();
        for (const u of nbr[t]) {
          if (triFace[u] >= 0 || size[tmp[u]] > 1 || dotT(t, u) < cosSmooth) continue;
          triFace[u] = f; stack.push(u);
        }
      }
    }
  }

  const faces = Array.from({ length: nFace }, (_, id) => ({
    id, tris: [], area: 0, centroid: [0, 0, 0], normal: [0, 0, 0], type: 'plane',
  }));
  for (let t = 0; t < nTri; t++) {
    const f = faces[triFace[t]];
    f.tris.push(t);
    f.area += ta[t];
    for (let k = 0; k < 3; k++) { f.centroid[k] += tc[t * 3 + k] * ta[t]; f.normal[k] += tn[t * 3 + k] * ta[t]; }
  }
  for (const f of faces) {
    if (f.area > 0) f.centroid = v3.mul(f.centroid, 1 / f.area);
    const nl = v3.len(f.normal);
    const avg = v3.norm(f.normal);
    let minDot = 1;
    for (const t of f.tris) minDot = Math.min(minDot, avg[0] * tn[t * 3] + avg[1] * tn[t * 3 + 1] + avg[2] * tn[t * 3 + 2]);
    if (minDot > EPS_ANG_PLANE && nl > 0) {
      f.type = 'plane'; f.normal = avg; f.offset = v3.dot(avg, f.centroid);
      continue;
    }
    f.normal = avg;
    // cylinder / cone: normals perpendicular to the axis
    const cov = [[0, 0, 0], [0, 0, 0], [0, 0, 0]];
    for (const t of f.tris) {
      const n = [tn[t * 3], tn[t * 3 + 1], tn[t * 3 + 2]];
      for (let i = 0; i < 3; i++) for (let j = 0; j < 3; j++) cov[i][j] += ta[t] * n[i] * n[j];
    }
    const e = eigenSym3(cov);
    const sum = e.values[0] + e.values[1] + e.values[2] || 1;
    f.type = 'curved';
    if (e.values[0] / sum < 0.003) {
      const axis = v3.norm(e.vectors[0]);
      const [u, w] = basis(axis);
      const vs = new Set();
      for (const t of f.tris) for (let k = 0; k < 3; k++) vs.add(weld[idx[t * 3 + k]]);
      const pts = [...vs].map(i => wpos[i]);
      const fit = fitCircle2(pts.map(p => [v3.dot(p, u), v3.dot(p, w)]));
      if (fit && fit.residual < Math.max(0.01 * fit.r, diag * 1e-4)) {
        let amin = Infinity, amax = -Infinity;
        for (const p of pts) { const s = v3.dot(p, axis); amin = Math.min(amin, s); amax = Math.max(amax, s); }
        const mid = (amin + amax) / 2;
        f.type = 'cylinder';
        f.axis = axis;
        f.radius = fit.r;
        f.center = v3.add(v3.add(v3.mul(u, fit.cx), v3.mul(w, fit.cy)), v3.mul(axis, mid));
        f.length = amax - amin;
        // inner (hole) or outer (pin): do the triangle normals point at the axis?
        let dots = 0;
        for (const t of f.tris) {
          const c = [tc[t * 3], tc[t * 3 + 1], tc[t * 3 + 2]];
          const d = v3.sub(c, f.center);
          const radial = v3.sub(d, v3.mul(axis, v3.dot(d, axis)));
          dots += ta[t] * (tn[t * 3] * radial[0] + tn[t * 3 + 1] * radial[1] + tn[t * 3 + 2] * radial[2]);
        }
        f.inner = dots < 0;
      }
    }
  }

  // feature edges: boundaries between different faces
  const groups = new Map();
  for (const rec of edgeMap.values()) {
    const fs = [...new Set(rec.tris.map(t => triFace[t]))].sort((x, y) => x - y);
    if (rec.tris.length === 2 && fs.length === 1) continue;
    const label = fs.length === 1 ? `${fs[0]}|-` : fs.join('|');
    let g = groups.get(label);
    if (!g) { g = { faces: fs, segs: [] }; groups.set(label, g); }
    g.segs.push([rec.a, rec.b]);
  }
  const edges = [];
  const vertSet = new Map();
  const addVert = (w) => { if (!vertSet.has(w)) vertSet.set(w, { id: vertSet.size, w, p: wpos[w], edges: [] }); return vertSet.get(w); };
  for (const g of groups.values()) {
    const adj = new Map();
    g.segs.forEach(([a, b], i) => {
      if (!adj.has(a)) adj.set(a, []); if (!adj.has(b)) adj.set(b, []);
      adj.get(a).push(i); adj.get(b).push(i);
    });
    const used = new Uint8Array(g.segs.length);
    const walk = (start) => {
      const chain = [start];
      let cur = start;
      for (;;) {
        const next = (adj.get(cur) || []).find(i => !used[i]);
        if (next === undefined) break;
        used[next] = 1;
        const [a, b] = g.segs[next];
        cur = a === cur ? b : a;
        chain.push(cur);
        if (cur === start) break;
      }
      return chain;
    };
    const ends = [...adj.entries()].filter(([, l]) => l.length !== 2).map(([w]) => w);
    const chains = [];
    for (const s of ends) while ((adj.get(s) || []).some(i => !used[i])) chains.push(walk(s));
    for (let i = 0; i < g.segs.length; i++) if (!used[i]) chains.push(walk(g.segs[i][0]));
    for (const ch of chains) {
      if (ch.length < 2) continue;
      const pts = ch.map(w => wpos[w]);
      let length = 0; for (let i = 1; i < pts.length; i++) length += v3.dist(pts[i - 1], pts[i]);
      const closed = ch[0] === ch[ch.length - 1];
      const e = { id: edges.length, faces: g.faces, points: pts, length, closed, type: 'curve' };
      const dir = v3.sub(pts[pts.length - 1], pts[0]);
      if (!closed && v3.len(dir) > 1e-9) {
        const d = v3.norm(dir);
        let dev = 0;
        for (const p of pts) { const r = v3.sub(p, pts[0]); dev = Math.max(dev, v3.len(v3.sub(r, v3.mul(d, v3.dot(r, d))))); }
        if (dev < Math.max(diag * 1e-5, 1e-6)) { e.type = 'line'; e.dir = d; }
      }
      if (e.type !== 'line' && pts.length >= 4) {
        const c = fitCircle3(closed ? pts.slice(0, -1) : pts);
        if (c && c.residual < Math.max(0.01 * c.radius, diag * 1e-4) && c.planarity < diag * 1e-4) {
          e.type = closed ? 'circle' : 'arc';
          e.center = c.center; e.radius = c.radius; e.normal = c.normal;
        }
      }
      if (!closed) {
        const va = addVert(ch[0]), vb = addVert(ch[ch.length - 1]);
        va.edges.push(e.id); vb.edges.push(e.id);
        e.verts = [va.id, vb.id];
      }
      edges.push(e);
    }
  }
  const verts = [...vertSet.values()];
  for (const f of faces) f.edges = [];
  for (const e of edges) for (const fid of e.faces) if (faces[fid]) faces[fid].edges.push(e.id);

  // volume
  let volume = 0;
  for (let t = 0; t < nTri; t++) {
    const a = wpos[weld[idx[t * 3]]], b = wpos[weld[idx[t * 3 + 1]]], c = wpos[weld[idx[t * 3 + 2]]];
    volume += v3.dot(a, v3.cross(b, c)) / 6;
  }
  let area = 0; for (let t = 0; t < nTri; t++) area += ta[t];

  return {
    triFace, faces, edges, verts, index: idx, nTri,
    bbox: { min: lo, max: hi }, diag, volume: Math.abs(volume), area,
  };
}

// ---------------------------------------------------- feature descriptions
const r2 = x => (Math.abs(x) < 5e-4 ? 0 : Math.round(x * 100) / 100);
export const fmtv = v => `[${v.map(r2).join(', ')}]`;
export const fmtn = (x, d = 2) => (Math.abs(x) < 5 * 10 ** -(d + 1) ? '0' : x.toFixed(d));

export function describeFace(f) {
  if (f.type === 'plane') return `plane, normal ${fmtv(f.normal)}, area ${fmtn(f.area)} mm²`;
  if (f.type === 'cylinder') return `cylindrical face ${f.inner ? '(hole)' : '(pin)'} Ø${fmtn(2 * f.radius)} mm, axis ${fmtv(f.axis)} through ${fmtv(f.center)}, length ${fmtn(f.length)} mm`;
  return `curved face, area ${fmtn(f.area)} mm²`;
}
export function describeEdge(e) {
  if (e.type === 'line') return `straight edge ${fmtv(e.points[0])} → ${fmtv(e.points[e.points.length - 1])}, length ${fmtn(e.length)} mm`;
  if (e.type === 'circle') return `circular edge Ø${fmtn(2 * e.radius)} mm, center ${fmtv(e.center)}, normal ${fmtv(e.normal)}`;
  if (e.type === 'arc') return `arc R${fmtn(e.radius)} mm, center ${fmtv(e.center)}, length ${fmtn(e.length)} mm`;
  return `curve, length ${fmtn(e.length)} mm`;
}

// ---------------------------------------------------------------- markers
/** Marker letter for index i (0-based): A … Z, AA, AB, … */
export function markerLabel(i) {
  let s = '';
  for (let n = i + 1; n > 0; n = Math.floor((n - 1) / 26)) s = String.fromCharCode(65 + ((n - 1) % 26)) + s;
  return s;
}
/** Viewer markers {type, pts:[{part, local, normal}], note} -> rows of the batch payload (model coordinates, home pose, mm). */
export function markerRows(markers) {
  return markers.map((m, i) => ({
    label: markerLabel(i), type: m.type, points: m.pts.map(p => p.local.map(r2)),
    faceNormal: v3.norm(m.pts.reduce((a, p) => v3.add(a, p.normal || [0, 0, 0]), [0, 0, 0])).map(r2),
    part: m.pts[0]?.part ?? null, note: m.note || '',
    // the feature under each point, in words, when the viewer recorded it
    ...(m.pts.some(p => p.feature) ? { features: m.pts.map(p => p.feature || null) } : {}),
  }));
}
