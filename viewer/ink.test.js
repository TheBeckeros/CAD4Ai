// node viewer/ink.test.js : self-check of ink smoothing, outlines, hit tests, region clipping and proposal accept
const assert = require('assert');
const I = require('./ink.js');
const near = (a, b, tol = 1e-6) => Math.abs(a - b) <= tol;

// smoothing: a jittery straight line comes out calmer, start kept
const raw = Array.from({ length: 60 }, (_, i) => [i * 2, (i % 2 ? 1.5 : -1.5), 0.5]);
let prev = null;
const sm = raw.map(p => (prev = I.step(prev, p, 0.5)));
const jitter = a => a.slice(5).reduce((s, p) => s + Math.abs(p[1]), 0) / (a.length - 5);
assert(sm[0][0] === 0 && jitter(sm) < jitter(raw) / 2, 'step smooths');

// simplify: straight runs collapse, corners and ends stay, pressure swells survive
const L = [...Array.from({ length: 50 }, (_, i) => [i, 0, 0.5]), ...Array.from({ length: 50 }, (_, i) => [49, i + 1, 0.5])];
const s = I.simplify(L, 0.4);
assert(s.length === 3 && s[1][0] === 49 && s[1][1] === 0 && s[2][1] === 50, `simplify corners ${JSON.stringify(s)}`);
const sw = Array.from({ length: 40 }, (_, i) => [i, 0, i === 20 ? 1 : 0.3]);
assert(I.simplify(sw, 0.4).some(p => p[2] === 1), 'pressure peak kept');

// outline: closed polygon around the line, width follows pressure
const o = I.outline([[0, 0, 0.5], [10, 0, 0.5], [20, 0, 1]], 4);
const ys = o.map(p => p[1]);
assert(o.length > 10 && near(Math.max(...ys.filter((_, i) => o[i][0] < 1 && o[i][0] > -0.5)), 2, 0.3), 'outline width at p=0.5 is w');
assert(Math.max(...ys) > 3, 'heavier pressure is wider');
assert(I.outline([[5, 5, 0.5]], 4) === null, 'dot');
const corner = I.outline([[0, 0, 0.5], [10, 0, 0.5], [10, 10, 0.5]], 4, false);
for (const seg of [[[0, 0], [10, 0]], [[10, 0], [0, 0]], [[0, 0], [7, 7]]]) { // round caps reach past both ends
  const ol = I.outline(seg, 4, false), d = [(seg[1][0] - seg[0][0]) / Math.hypot(...seg[1].map((v, k) => v - seg[0][k])), (seg[1][1] - seg[0][1]) / Math.hypot(...seg[1].map((v, k) => v - seg[0][k]))];
  assert(ol.some(p => near(p[0], seg[1][0] + 2 * d[0], 1e-6) && near(p[1], seg[1][1] + 2 * d[1], 1e-6)), `end cap ${seg}`);
  assert(ol.some(p => near(p[0], seg[0][0] - 2 * d[0], 1e-6) && near(p[1], seg[0][1] - 2 * d[1], 1e-6)), `start cap ${seg}`);
}
assert(corner.some(p => near(p[0], 12, 0.01) && near(p[1], -2, 0.01)), 'right-angle corner keeps full width (miter)');
assert(near(I.radius(4, 0.5, false), 2) && near(I.radius(4, 0.9, false), 2), 'mouse width constant');

// hit + lasso
const st = { id: 'a', t: 'stroke', w: 2, pts: [[0, 0, 0.5], [100, 0, 0.5]] };
assert(I.hit(st, [50, 3], 2) && !I.hit(st, [50, 6], 2), 'hit');
assert(I.lasso([st, { id: 't', t: 'text', x: 200, y: 0, s: 'hi', size: 10 }], [[-10, -10], [110, -10], [110, 10], [-10, 10]]).map(i => i.id).join() === 'a', 'lasso');

// clipping at the region border
const R = [10, -10, 20, 20]; // x 10..30
const c = I.clipStroke([[0, 0, 0.2], [40, 0, 0.6]], R);
assert(c.inside.length === 1 && c.outside.length === 2, 'clip pieces');
assert(near(c.inside[0][0][0], 10) && near(c.inside[0][1][0], 30) && near(c.inside[0][0][2], 0.3), 'inside piece with pressure');
assert(c.outside[0][0][0] === 0 && near(c.outside[0][1][0], 10) && c.outside[1][1][0] === 40, 'outside pieces end on the border');
const zig = I.clipStroke([[0, 0], [20, 0], [20, 30], [20, 0], [50, 0]], R);
assert(zig.inside.length === 2 && zig.outside.length === 3, 'zigzag leaves and re-enters');
assert(I.clipStroke([[0, 50], [40, 50]], R).inside.length === 0, 'miss');

// region ids: crossing strokes yes, text only if fully inside, far things no
const items = {
  cross: { id: 'cross', t: 'stroke', w: 1, z: 1, pts: [[0, 0, 0.5], [40, 0, 0.5]] },
  inner: { id: 'inner', t: 'stroke', w: 1, z: 2, pts: [[15, -5, 0.5], [25, 5, 0.5]] },
  far: { id: 'far', t: 'stroke', w: 1, z: 3, pts: [[100, 100, 0.5], [120, 100, 0.5]] },
  tin: { id: 'tin', t: 'text', x: 12, y: -8, s: 'ab', size: 4, z: 4 },
  tout: { id: 'tout', t: 'text', x: 25, y: -8, s: 'long text', size: 4, z: 5 },
};
const ids = I.regionIds(Object.values(items), R);
assert.deepStrictEqual(ids.sort(), ['cross', 'inner', 'tin'], 'region ids');

// proposal clipped to the region
const prop = [
  { id: 'p1', t: 'stroke', w: 1, pts: [[5, 0, 0.5], [25, 0, 0.5]] }, // pokes out to the left
  { id: 'p2', t: 'text', x: 12, y: 0, s: 'very long label', size: 6 }, // shrunk to fit
  { id: 'p3', t: 'text', x: 50, y: 0, s: 'x', size: 6 }, // outside: dropped
];
const cp = I.clipProposal(prop, R);
assert(cp.length === 2 && near(cp[0].pts[0][0], 10) && cp[1].size < 6, 'clipProposal');

// accept: only snap.ids change, outside geometry kept point for point, proposal strictly inside, undo restores
let n = 0;
const snap = { rect: R, ids, proposal: prop };
const acc = I.accept(items, snap, () => `n${n++}`);
assert.deepStrictEqual(acc.del.sort(), ['cross', 'inner', 'tin'], 'accept deletes the region items');
assert(!acc.put.some(i => ['far', 'tout'].includes(i.id)) && !acc.del.includes('far') && !acc.del.includes('tout'), 'outside untouched');
const kept = acc.put.filter(i => i.z === 1); // pieces of `cross`
assert(kept.length === 2 && kept[0].pts[0][0] === 0 && kept[1].pts[kept[1].pts.length - 1][0] === 40, 'outside parts of a crossing stroke stay');
const outsidePts = items.cross.pts.filter(p => !I.inRect(p, R));
assert(outsidePts.every(p => kept.some(k => k.pts.some(q => q[0] === p[0] && q[1] === p[1]))), 'every outside point survives');
const added = acc.put.filter(i => i.z > 5);
assert(added.length === 2 && added.every(i => (i.t === 'stroke' ? i.pts.every(p => I.inRect(p, R)) : I.inRect([i.x, i.y], R))), 'proposal inside');
assert.deepStrictEqual(acc.undo.del.sort(), acc.put.map(i => i.id).sort(), 'undo removes what accept added');
assert(acc.undo.put.length === 3 && acc.undo.put.find(i => i.id === 'cross') === items.cross, 'undo puts originals back');
// a region item moved out of the rect after the snap is left alone
const moved = { ...items, tin: { ...items.tin, x: 300 } };
assert(!I.accept(moved, snap, () => `m${n++}`).del.includes('tin'), 'moved item stays');

// shapes
assert(I.shapePts('rect', [0, 0], [10, 5]).length === 5 && I.shapePts('ellipse', [0, 0], [10, 10]).every(p => near(Math.hypot(p[0] - 5, p[1] - 5), 5)), 'shapes');
console.log('ink.test.js: all ok');
