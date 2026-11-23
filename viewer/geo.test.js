// node viewer/geo.test.js : self-check of the canvas geometry (recognition, intersections, trim, split, extend, snap, dims).
const assert = require('assert');
const G = require('./geo.js');
const near = (a, b, e = 1e-6) => assert(Math.abs(a - b) < e, `${a} !~ ${b}`);
const line = (id, a, b) => ({ id, t: 'line', a, b, w: 1 });

// QuickShape+: a wobbly line, circle, arc, rectangle, ellipse
const wob = k => Math.sin(k * 12.9898) * 0.6;
const L = Array.from({ length: 30 }, (_, k) => [k * 10 + wob(k), 50 + wob(k + 7)]);
assert.strictEqual(G.recognize(L).t, 'line');
const C = Array.from({ length: 60 }, (_, k) => [100 + 50 * Math.cos(k / 9.5) + wob(k), 100 + 50 * Math.sin(k / 9.5) + wob(k + 3)]);
const rc = G.recognize(C); assert.strictEqual(rc.t, 'circle'); near(rc.r, 50, 2);
const A = Array.from({ length: 40 }, (_, k) => [100 + 50 * Math.cos(k / 20), 100 + 50 * Math.sin(k / 20)]); // ~2 rad
const ra = G.recognize(A); assert.strictEqual(ra.t, 'arc'); near(ra.a0, 0, 0.05);
const side = (a, b, n = 12) => Array.from({ length: n }, (_, k) => G.lerp(a, b, k / n));
const R = [...side([0, 0], [100, 2]), ...side([100, 2], [98, 60]), ...side([98, 60], [1, 62]), ...side([1, 62], [0, 0]), [0, 0]];
const rr = G.recognize(R); assert.strictEqual(rr.t, 'rect'); near(rr.q[0], 100, 3);
const E = Array.from({ length: 60 }, (_, k) => [200 + 80 * Math.cos(k / 9.5), 100 + 30 * Math.sin(k / 9.5)]);
assert.strictEqual(G.recognize(E).t, 'ellipse');
const Z = Array.from({ length: 4 }, (_, k) => [k * 3, k * 5 + (k % 2) * 30]);
assert.strictEqual(G.recognize(Z), null, 'a few random points stay a free stroke');

// scribble: a zig-zag over a small area vs. a long hatching-like pass
const zig = Array.from({ length: 20 }, (_, k) => [(k % 2) * 40, k * 2]);
assert(G.isScribble(zig, 600)); assert(!G.isScribble(zig, 5000)); assert(!G.isScribble(L, 600));

// intersections + trim (a cross of two lines trimmed to the right of the crossing)
const h = line('h', [0, 0], [100, 0]), v = line('v', [40, -50], [40, 50]);
assert.deepStrictEqual(G.intersect(h, v), [[40, 0]]);
assert.deepStrictEqual(G.intersect(h, line('w', [200, -5], [200, 5])), [], 'segments that do not reach');
const tr = G.trim(h, [70, 0], [h, v]); assert.strictEqual(tr.length, 1); assert.deepStrictEqual([tr[0].a, tr[0].b], [[0, 0], [40, 0]]);
const trm = G.trim(h, [20, 0], [h, v]); assert.deepStrictEqual([trm[0].a, trm[0].b], [[40, 0], [100, 0]]);
assert.strictEqual(G.trim(h, [20, 0], [h]).length, 0, 'no boundary: the whole line goes');
// a circle trimmed between two lines becomes an arc
const circ = { id: 'c', t: 'circle', c: [0, 0], r: 10, w: 1 };
const cut = G.trim(circ, [10, 0], [circ, line('a', [8, -20], [8, 20]), line('b', [-20, 6], [20, 6])]);
assert.strictEqual(cut.length, 1); assert.strictEqual(cut[0].t, 'arc'); assert(G.distTo(cut[0], [-10, 0]) < 1e-6 && G.distTo(cut[0], [10, 0]) > 1);
// rect trims into lines
const rect = { id: 'r', t: 'rect', p: [0, 0], q: [100, 50], w: 1 };
const rt = G.trim(rect, [50, 0], [rect, line('x', [30, -10], [30, 60]), line('y', [70, -10], [70, 60])]);
assert(rt.every(o => o.t === 'line') && rt.length === 5, `rect -> ${rt.length} lines`);

// split / extend
const sp = G.split(h, [25, 0]); assert.deepStrictEqual([sp[0].b, sp[1].a], [[25, 0], [25, 0]]);
const ex = G.extend(line('s', [0, 0], [20, 0]), [19, 0], [line('wall', [60, -9], [60, 9])]); assert.deepStrictEqual(ex.b, [60, 0]);
assert.strictEqual(G.extend(line('s', [0, 0], [20, 0]), [19, 0], [line('wall', [60, 5], [60, 9])]), null);

// snapping: end point beats grid; intersection found; nothing far away
assert.strictEqual(G.snap([41, 1], [h, v], 5).kind, 'cross');
assert.strictEqual(G.snap([99, 1], [h, v], 5).kind, 'end');
assert.strictEqual(G.snap([13, 1], [], 5, { grid: 10 }).kind, 'grid');
assert.strictEqual(G.snap([504.9, 504.9], [h, v], 5, { grid: 10 }), null);

// alignment suggestion
const sl = G.straighten(line('s', [0, 0], [100, 3])); assert.deepStrictEqual(sl.b, [100, 0]);
assert.strictEqual(G.straighten(line('s', [0, 0], [100, 0])), null); assert.strictEqual(G.straighten(line('s', [0, 0], [100, 40])), null);

// dimensions follow their line and set it
const dl = { id: 'd', t: 'dim', ref: 'h', off: 10 }; assert.strictEqual(G.dimGeom(dl, { h }).txt, '100');
const ch = G.setDimValue(dl, 80, { h }); assert.deepStrictEqual(ch[0].b, [80, 0]);
const dd = { id: 'e', t: 'dim', ref: 'c', kind: 'dia' }; assert.strictEqual(G.dimGeom(dd, { c: circ }).txt, 'Ø20'); assert.strictEqual(G.setDimValue(dd, 30, { c: circ })[0].r, 15);
// arc through three points: passes the middle point, not the other side; collinear -> null
for (const [a, m, b] of [[[10, 0], [0, 10], [-10, 0]], [[10, 0], [0, -10], [-10, 0]], [[0, 0], [5, 3], [12, 0]]]) {
  const arc = G.arcThrough(a, m, b);
  assert(G.distTo(arc, m) < 1e-6 && G.distTo(arc, a) < 1e-6 && G.distTo(arc, b) < 1e-6, 'arc through its points');
  const far = [2 * arc.c[0] - m[0], 2 * arc.c[1] - m[1]]; // opposite of m on the circle
  assert(G.distTo(arc, far) > 1e-3, 'not the other half');
}
assert.strictEqual(G.arcThrough([0, 0], [5, 0], [10, 0]), null);
// mechanisms: a slider-crank that only rocks, a crank-slider that turns fully, a four-bar
const slider = { t: 'mech', joints: [{ id: 'A', p: [70, -97.7], fixed: true }, { id: 'B', p: [70, -203.2] }, { id: 'C', p: [152.3, -275.4] }],
  links: [['A', 'B'], ['B', 'C']], sliders: [{ j: 'C', a: [152.3, -345], b: [152.3, -197] }], driver: { j: 'B', c: 'A' } };
const s0 = G.solveMech(slider, G.mechAngle0(slider));
near(s0.C[0], 152.3, 1e-6); near(s0.C[1], -275.4, 1e-6);
const rg = G.mechRange(slider);
assert(!rg.full && rg.lo < rg.a0 && rg.hi > rg.a0, 'rocks between limits');
assert(G.solveMech(slider, Math.PI) === null, 'crank pointing left: the rod cannot reach the guide');
for (const a of [rg.lo, (rg.lo + rg.a0) / 2, rg.hi]) { const s = G.solveMech(slider, a); near(G.dist(s.B, s.C), G.dist([70, -203.2], [152.3, -275.4]), 1e-6); near(s.C[0], 152.3, 1e-6); }
const crank = { t: 'mech', joints: [{ id: 'A', p: [0, 0], fixed: true }, { id: 'B', p: [20, 0] }, { id: 'C', p: [100, 0] }],
  links: [['A', 'B'], ['B', 'C']], sliders: [{ j: 'C', a: [-200, 0], b: [200, 0] }], driver: { j: 'B', c: 'A' } };
assert(G.mechRange(crank).full, 'short crank turns all the way');
near(G.solveMech(crank, Math.PI).C[0], 60, 1e-6);
assert(G.solveMech(crank, Math.PI / 2, null, [20, 10]) === null, 'rod shorter than the crank height: infeasible');
const fourbar = { t: 'mech', joints: [{ id: 'A', p: [0, 0], fixed: true }, { id: 'D', p: [100, 0], fixed: true }, { id: 'B', p: [0, -30] }, { id: 'C', p: [100, -60] }],
  links: [['A', 'B'], ['B', 'C'], ['C', 'D']], driver: { j: 'B', c: 'A' } };
const f = G.solveMech(fourbar, -Math.PI / 2 + 0.3);
near(G.dist(f.C, [100, 0]), 60, 1e-6); near(G.dist(f.B, f.C), G.dist([0, -30], [100, -60]), 1e-6);
assert(G.distTo(fourbar, [50, -45]) < 1, 'hit test on a link');
// dims on a rect edge and on an arc follow them and resize them
const rq = { id: 'rq', t: 'rect', p: [0, 0], q: [80, 40], w: 1 }, ac = { id: 'ac', t: 'arc', c: [0, 0], r: 12, a0: 0, a1: 2, w: 1 };
assert.strictEqual(G.dimGeom({ t: 'dim', ref: 'rq', edge: 1 }, { rq }).txt, '40');
assert.deepStrictEqual(G.setDimValue({ t: 'dim', ref: 'rq', edge: 0 }, 100, { rq })[0].q, [100, 40]);
assert.deepStrictEqual(G.setDimValue({ t: 'dim', ref: 'rq', edge: 3 }, 25, { rq })[0].q, [80, 25]);
assert.strictEqual(G.dimGeom({ t: 'dim', ref: 'ac', kind: 'rad', ang: 1 }, { ac }).txt, 'R12');
assert.strictEqual(G.setDimValue({ t: 'dim', ref: 'ac', kind: 'rad' }, 20, { ac })[0].r, 20);
console.log('geo.test.js ok');
