// CAD4Ai: model checks that run only in the browser (wall thickness, draft, overhang,
// collisions, mass properties). Nothing here is sent to Claude.
import * as THREE from 'three';
import { eigenSym3 } from './geom.js';

const _ray = new THREE.Ray(), _a = new THREE.Vector3(), _b = new THREE.Vector3(), _c = new THREE.Vector3(), _n = new THREE.Vector3();

/** Wall thickness per vertex: a ray from every triangle inwards (against its normal) to the opposite wall. */
export function thickness(geo, eps, far) {
  const P = geo.attributes.position, N = geo.attributes.normal, I = geo.index.array, bvh = geo.boundsTree;
  const out = new Float32Array(P.count).fill(Infinity);
  for (let t = 0; t < I.length; t += 3) {
    const i0 = I[t], i1 = I[t + 1], i2 = I[t + 2];
    _a.fromBufferAttribute(P, i0); _b.fromBufferAttribute(P, i1); _c.fromBufferAttribute(P, i2);
    _n.set(N.getX(i0) + N.getX(i1) + N.getX(i2), N.getY(i0) + N.getY(i1) + N.getY(i2), N.getZ(i0) + N.getZ(i1) + N.getZ(i2));
    if (_n.lengthSq() < 1e-12) continue;
    _n.normalize().negate();
    _ray.origin.copy(_a).add(_b).add(_c).multiplyScalar(1 / 3).addScaledVector(_n, eps);
    _ray.direction.copy(_n);
    const hit = bvh.raycastFirst(_ray, THREE.DoubleSide, eps, far);
    if (!hit) continue;
    const d = hit.distance + eps;
    if (d < out[i0]) out[i0] = d;
    if (d < out[i1]) out[i1] = d;
    if (d < out[i2]) out[i2] = d;
  }
  return out;
}

/** Signed angle (degrees) of every vertex normal against a direction given in the part's local frame. */
export function normalAngles(geo, dirLocal) {
  const N = geo.attributes.normal, out = new Float32Array(N.count);
  for (let i = 0; i < N.count; i++) {
    const d = N.getX(i) * dirLocal.x + N.getY(i) * dirLocal.y + N.getZ(i) * dirLocal.z;
    out[i] = Math.asin(Math.max(-1, Math.min(1, d))) * 180 / Math.PI;
  }
  return out;
}

/** Height of every vertex along a local direction, relative to the lowest one (for the print bed). */
export function heights(geo, dirLocal) {
  const P = geo.attributes.position, out = new Float32Array(P.count);
  let lo = Infinity;
  for (let i = 0; i < P.count; i++) { out[i] = P.getX(i) * dirLocal.x + P.getY(i) * dirLocal.y + P.getZ(i) * dirLocal.z; lo = Math.min(lo, out[i]); }
  for (let i = 0; i < P.count; i++) out[i] -= lo;
  return out;
}

// colour helpers: 0..1 RGB, NEUTRAL is the untouched surface while a check is shown
export const NEUTRAL = [0.78, 0.76, 0.72];
export const RED = [0.92, 0.3, 0.24], ORANGE = [0.96, 0.6, 0.22], YELLOW = [0.95, 0.85, 0.3], GREEN = [0.38, 0.78, 0.45], BLUE = [0.38, 0.6, 0.95];
const mix = (a, b, k) => [a[0] + (b[0] - a[0]) * k, a[1] + (b[1] - a[1]) * k, a[2] + (b[2] - a[2]) * k];
export const scales = {
  thick: (v, min) => !(v < 2 * min) ? NEUTRAL : v < min ? RED : v < 1.5 * min ? mix(RED, YELLOW, (v - min) / (0.5 * min)) : mix(YELLOW, GREEN, (v - 1.5 * min) / (0.5 * min)),
  draft: (v, min) => Math.abs(v) < min ? RED : v > 0 ? GREEN : BLUE,
  overhang: (v, crit) => v > crit ? RED : v > crit - 10 ? mix(YELLOW, ORANGE, (v - crit + 10) / 10) : NEUTRAL,
};
export function paint(geo, fn) {
  const col = geo.attributes.color, arr = col.array;
  for (let i = 0; i < col.count; i++) { const c = fn(i); arr[i * 3] = c[0]; arr[i * 3 + 1] = c[1]; arr[i * 3 + 2] = c[2]; }
  col.needsUpdate = true;
}

/**
 * Two parts in their current world placement: which vertices touch or sit inside the other part
 * and how deep the deepest one goes. a/b: {geo (with boundsTree), mw: world matrix}.
 */
export function collide(a, b, tol) {
  const toA = new THREE.Matrix4().copy(a.mw).invert().multiply(b.mw);
  const IA = a.geo.index.array, IB = b.geo.index.array;
  const touchA = new Set(), touchB = new Set();
  a.geo.boundsTree.bvhcast(b.geo.boundsTree, toA, {
    intersectsTriangles(t1, t2, i1, i2) {
      if (t1.intersectsTriangle(t2)) for (let k = 0; k < 3; k++) { touchA.add(IA[i1 * 3 + k]); touchB.add(IB[i2 * 3 + k]); }
      return false;
    },
  });
  if (!touchA.size) return null;
  const inA = inside(a, b, toA.clone().invert(), tol), inB = inside(b, a, toA, tol);
  return { touchA, touchB, insideA: inA.set, insideB: inB.set, depth: Math.max(inA.depth, inB.depth) };
}
// vertices of `p` that lie inside `q` (ray parity), with their depth below q's surface
function inside(p, q, pToQ, tol) {
  const P = p.geo.attributes.position, set = new Set();
  const box = q.geo.boundingBox, v = new THREE.Vector3(), target = {};
  const ray = new THREE.Ray(new THREE.Vector3(), new THREE.Vector3(0.5773, 0.5774, 0.5775).normalize());
  let depth = 0;
  for (let i = 0; i < P.count; i++) {
    v.fromBufferAttribute(P, i).applyMatrix4(pToQ);
    if (!box.containsPoint(v)) continue;
    q.geo.boundsTree.closestPointToPoint(v, target);
    if (target.distance <= tol) continue;
    ray.origin.copy(v);
    if (q.geo.boundsTree.raycast(ray, THREE.DoubleSide).length % 2 === 1) { set.add(i); depth = Math.max(depth, target.distance); }
  }
  return { set, depth };
}

/** Volume, centre of mass and inertia tensor about it for a closed mesh, density 1 (Eberly's polyhedral integrals). */
export function massProps(geo) {
  const P = geo.attributes.position.array, I = geo.index.array;
  const s = new Float64Array(10);
  const sub = (w0, w1, w2) => {
    const t0 = w0 + w1, f1 = t0 + w2, t1 = w0 * w0, t2 = t1 + w1 * t0, f2 = t2 + w2 * f1, f3 = w0 * t1 + w1 * t2 + w2 * f2;
    return [f1, f2, f3, f2 + w0 * (f1 + w0), f2 + w1 * (f1 + w1), f2 + w2 * (f1 + w2)];
  };
  for (let t = 0; t < I.length; t += 3) {
    const a = I[t] * 3, b = I[t + 1] * 3, c = I[t + 2] * 3;
    const x0 = P[a], y0 = P[a + 1], z0 = P[a + 2], x1 = P[b], y1 = P[b + 1], z1 = P[b + 2], x2 = P[c], y2 = P[c + 1], z2 = P[c + 2];
    const a1 = x1 - x0, b1 = y1 - y0, c1 = z1 - z0, a2 = x2 - x0, b2 = y2 - y0, c2 = z2 - z0;
    const d0 = b1 * c2 - b2 * c1, d1 = a2 * c1 - a1 * c2, d2 = a1 * b2 - a2 * b1;
    const X = sub(x0, x1, x2), Y = sub(y0, y1, y2), Z = sub(z0, z1, z2);
    s[0] += d0 * X[0]; s[1] += d0 * X[1]; s[2] += d1 * Y[1]; s[3] += d2 * Z[1];
    s[4] += d0 * X[2]; s[5] += d1 * Y[2]; s[6] += d2 * Z[2];
    s[7] += d0 * (y0 * X[3] + y1 * X[4] + y2 * X[5]);
    s[8] += d1 * (z0 * Y[3] + z1 * Y[4] + z2 * Y[5]);
    s[9] += d2 * (x0 * Z[3] + x1 * Z[4] + x2 * Z[5]);
  }
  const k = [1 / 6, 1 / 24, 1 / 24, 1 / 24, 1 / 60, 1 / 60, 1 / 60, 1 / 120, 1 / 120, 1 / 120];
  for (let i = 0; i < 10; i++) s[i] *= k[i];
  if (s[0] < 0) for (let i = 0; i < 10; i++) s[i] = -s[i];   // inside-out mesh
  const m = s[0] || 1e-30, cx = s[1] / m, cy = s[2] / m, cz = s[3] / m;
  const xx = s[5] + s[6] - m * (cy * cy + cz * cz), yy = s[4] + s[6] - m * (cz * cz + cx * cx), zz = s[4] + s[5] - m * (cx * cx + cy * cy);
  const xy = -(s[7] - m * cx * cy), yz = -(s[8] - m * cy * cz), xz = -(s[9] - m * cz * cx);
  return { volume: s[0], com: new THREE.Vector3(cx, cy, cz), inertia: [[xx, xy, xz], [xy, yy, yz], [xz, yz, zz]] };
}

/** Combines parts {mass, com (world), inertia about own com (world axes)} into one body. */
export function combineMass(items) {
  const M = items.reduce((s, i) => s + i.mass, 0);
  const com = new THREE.Vector3();
  for (const i of items) com.addScaledVector(i.com, i.mass / (M || 1));
  const I = [[0, 0, 0], [0, 0, 0], [0, 0, 0]];
  for (const it of items) {
    const r = it.com.clone().sub(com).toArray(), r2 = r[0] * r[0] + r[1] * r[1] + r[2] * r[2];
    for (let a = 0; a < 3; a++) for (let b = 0; b < 3; b++) I[a][b] += it.inertia[a][b] + it.mass * ((a === b ? r2 : 0) - r[a] * r[b]);
  }
  return { mass: M, com, inertia: I, principal: eigenSym3(I) };
}

/** Inertia tensor rotated into world axes: R I Rᵀ. */
export function rotateInertia(I, m4) {
  const e = new THREE.Matrix3().setFromMatrix4(m4).elements;   // column-major
  const R = [[e[0], e[3], e[6]], [e[1], e[4], e[7]], [e[2], e[5], e[8]]];
  const out = [[0, 0, 0], [0, 0, 0], [0, 0, 0]];
  for (let a = 0; a < 3; a++) for (let b = 0; b < 3; b++) {
    let v = 0;
    for (let i = 0; i < 3; i++) for (let j = 0; j < 3; j++) v += R[a][i] * I[i][j] * R[b][j];
    out[a][b] = v;
  }
  return out;
}

export const MATERIALS = [
  ['Steel', 7.85], ['Stainless steel', 8.0], ['Aluminium', 2.7], ['Brass', 8.5], ['Copper', 8.96], ['Titanium', 4.43],
  ['Cast iron', 7.2], ['PLA', 1.24], ['PETG', 1.27], ['ABS', 1.04], ['Nylon (PA12)', 1.01], ['Resin', 1.15], ['Wood (oak)', 0.75],
];

// self-check of the mass integrals on a 2 x 4 x 6 box (runs when the URL has ?selftest)
export function selfTest() {
  const g = new THREE.BoxGeometry(2, 4, 6).toNonIndexed();
  const idx = [...Array(g.attributes.position.count).keys()];
  g.setIndex(idx);
  const r = massProps(g);
  const ok = Math.abs(r.volume - 48) < 1e-6 && r.com.length() < 1e-9 && Math.abs(r.inertia[0][0] - 48 * (16 + 36) / 12) < 1e-6 && Math.abs(r.inertia[0][1]) < 1e-9;
  console.assert(ok, 'massProps self-test failed', r);
  return ok;
}
