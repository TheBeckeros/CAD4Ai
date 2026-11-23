// node viewer/markers.test.mjs : self-check of the marker letters and the batch payload rows (geom.js).
import assert from 'assert';
import { markerLabel, markerRows } from './geom.js';

assert.deepStrictEqual([0, 1, 25, 26, 27, 51, 52, 701, 702].map(markerLabel), ['A', 'B', 'Z', 'AA', 'AB', 'AZ', 'BA', 'ZZ', 'AAA']);

const rows = markerRows([
  { type: 'point', pts: [{ part: 'base', local: [1.004, 2.006, 3], normal: [0, 0, 1] }], note: 'chamfer here' },
  { type: 'line', pts: [{ part: 'base', local: [0, 0, 0], normal: [0, 0, 1] }, { part: 'lid', local: [10, 0, 0], normal: [1, 0, 0] }] },
  { type: 'area', pts: [{ part: 'base', local: [0, 0, 5] }, { part: 'base', local: [5, 0, 5] }, { part: 'base', local: [5, 5, 5] }], note: 'pocket' },
]);
assert.deepStrictEqual(rows[0], { label: 'A', type: 'point', points: [[1, 2.01, 3]], faceNormal: [0, 0, 1], part: 'base', note: 'chamfer here' });
assert.strictEqual(rows[1].label, 'B'); assert.strictEqual(rows[1].part, 'base', 'part of the first point');
assert.deepStrictEqual(rows[1].faceNormal, [0.71, 0, 0.71], 'mean of unit normals');
assert.strictEqual(rows[1].note, '', 'missing note -> empty');
assert.deepStrictEqual(rows[2].faceNormal, [0, 0, 0], 'no normals -> zero vector');
assert.strictEqual(rows[2].points.length, 3);
console.log('markers.test: ok');
