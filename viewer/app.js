// CAD4Ai: interactive 3D viewer with feature selection, measurement, section,
// version comparison, notes and parameters.
import * as THREE from 'three';
import { TrackballControls } from 'three/addons/controls/TrackballControls.js';
import { STLLoader } from 'three/addons/loaders/STLLoader.js';
import { Line2 } from 'three/addons/lines/Line2.js';
import { LineMaterial } from 'three/addons/lines/LineMaterial.js';
import { LineGeometry } from 'three/addons/lines/LineGeometry.js';
import { LineSegments2 } from 'three/addons/lines/LineSegments2.js';
import { LineSegmentsGeometry } from 'three/addons/lines/LineSegmentsGeometry.js';
import { CSS2DRenderer, CSS2DObject } from 'three/addons/renderers/CSS2DRenderer.js';
import { MeshBVH, acceleratedRaycast } from 'three-mesh-bvh';
import { EffectComposer } from 'three/addons/postprocessing/EffectComposer.js';
import { RenderPass } from 'three/addons/postprocessing/RenderPass.js';
import { GTAOPass } from 'three/addons/postprocessing/GTAOPass.js';
import { OutputPass } from 'three/addons/postprocessing/OutputPass.js';
import { analyzeMesh, v3, fmtv, fmtn, describeFace, describeEdge, markerLabel, markerRows } from './geom.js';
import * as ana from './analysis.js';

THREE.Mesh.prototype.raycast = acceleratedRaycast;
const $ = id => document.getElementById(id);
const OCCT_CDN = 'https://cdn.jsdelivr.net/npm/occt-import-js@0.0.23/dist/';
// Claude dark palette: warm greys with the clay accent
const BASE_COLOR = 0xa9a49a;
const PALETTE = [0xa9a49a, 0x8ea3bd, 0xc79b80, 0x9db79a, 0xb79bb8, 0xc9b47f, 0x8fb5b1, 0xbb9090];
const C_HOVER = 0x7fa7d6, C_SEL = 0xd97757;
const WHITE = new THREE.Color(1, 1, 1), ALERT = new THREE.Color(0xe5655a);

// =================================================================== scene
const view = $('view');
const renderer = new THREE.WebGLRenderer({ antialias: true, preserveDrawingBuffer: true });
renderer.setPixelRatio(devicePixelRatio);
renderer.localClippingEnabled = true;
view.appendChild(renderer.domElement);
const labelRenderer = new CSS2DRenderer();
labelRenderer.domElement.style.cssText = 'position:absolute;inset:0;pointer-events:none';
view.appendChild(labelRenderer.domElement);

const scene = new THREE.Scene();
scene.background = new THREE.Color(0x262624);
const persp = new THREE.PerspectiveCamera(35, 1, 0.01, 1e7);
const ortho = new THREE.OrthographicCamera(-1, 1, 1, -1, -1e6, 1e6);
for (const c of [persp, ortho]) c.up.set(0, 0, 1);
let camera = persp;
// free 360° rotation like SolidWorks (OrbitControls stops at the poles)
const controls = new TrackballControls(camera, renderer.domElement);
controls.rotateSpeed = 3;
controls.zoomSpeed = 1.2;
controls.staticMoving = true;   // no inertia: the model stops where you let go
controls.keys = [];             // A/S/D are viewer shortcuts, not control modifiers
// TrackballControls keys are the actions (LEFT = rotate, MIDDLE = zoom, RIGHT = pan), values the button numbers: middle rotates, right or Ctrl + middle pans, wheel zooms
controls.mouseButtons = { LEFT: 1, MIDDLE: -1, RIGHT: -1 };
scene.add(new THREE.HemisphereLight(0xffffff, 0x3d3c38, 1.05));
const camLight = new THREE.DirectionalLight(0xffffff, 1.5);
camLight.position.set(0.6, 1, 0.8);
persp.add(camLight);
const camLight2 = camLight.clone();
ortho.add(camLight2);
scene.add(persp, ortho);
// world-fixed light from above that casts the optional shadows onto a ground plane
const sunLight = new THREE.DirectionalLight(0xffffff, 0);
sunLight.shadow.mapSize.set(2048, 2048);
sunLight.shadow.bias = -0.0004;
scene.add(sunLight, sunLight.target);
const ground = new THREE.Mesh(new THREE.PlaneGeometry(1, 1), new THREE.ShadowMaterial({ opacity: 0.45 }));
ground.receiveShadow = true; ground.visible = false;
scene.add(ground);

const grid = new THREE.GridHelper(1, 20, 0x55524b, 0x33322f);
grid.rotation.x = Math.PI / 2;
scene.add(grid);
const axes = new THREE.AxesHelper(1);
scene.add(axes);

const lineMats = new Set();
function lineMat(opts) {
  const m = new LineMaterial({ resolution: new THREE.Vector2(view.clientWidth, view.clientHeight), ...opts });
  lineMats.add(m);
  return m;
}
// matcap textures drawn once on a canvas: a soft clay look and a rim glow for X-ray
function matcapTex(stops) {
  const c = document.createElement('canvas'); c.width = c.height = 256;
  const g = c.getContext('2d');
  const gr = g.createRadialGradient(100, 90, 4, 128, 128, 128);
  for (const [o, col] of stops) gr.addColorStop(o, col);
  g.fillStyle = gr; g.fillRect(0, 0, 256, 256);
  const t = new THREE.CanvasTexture(c); t.colorSpace = THREE.SRGBColorSpace;
  return t;
}
const MATCAP = {
  clay: matcapTex([[0, '#fbf8f2'], [0.35, '#d8d3c9'], [0.75, '#8d887f'], [1, '#3b3935']]),
  xray: (() => {
    const c = document.createElement('canvas'); c.width = c.height = 256;
    const g = c.getContext('2d'), gr = g.createRadialGradient(128, 128, 0, 128, 128, 128);
    gr.addColorStop(0, '#000'); gr.addColorStop(0.55, '#0a0a0a'); gr.addColorStop(0.85, '#5b6f8c'); gr.addColorStop(1, '#c9dcf5');
    g.fillStyle = gr; g.fillRect(0, 0, 256, 256);
    const t = new THREE.CanvasTexture(c); t.colorSpace = THREE.SRGBColorSpace; return t;
  })(),
};
let composer = null, gtao = null, renderPass = null;
const clipMats = new Set();
function clipMat(m) { clipMats.add(m); const pl = activePlanes(); m.clippingPlanes = pl.length ? pl : null; return m; }

function resize() {
  const w = view.clientWidth, h = view.clientHeight;
  renderer.setSize(w, h);
  labelRenderer.setSize(w, h);
  persp.aspect = w / h; persp.updateProjectionMatrix();
  updateOrthoFrustum();
  for (const m of lineMats) m.resolution.set(w, h);
  measDirty = true;
  if (composer) composer.setSize(w, h);
  controls.handleResize();
}
new ResizeObserver(resize).observe(view);

// ================================================================= state
const model = { info: null, parts: [], radius: 10, center: new THREE.Vector3(), bbox: null, source: '' };
let tool = 'select';
let penColor = '#ff3b30';
const selection = [];       // {type, part, id, local:[x,y,z]}
const strokes = [];         // {color, screen:[[x,y]] css px, hits:[{part, local, normal}], misses:[[x,y]] 0..1}
const measurements = [];    // see addMeasurement
let measPicks = [];
let measSel = null;          // id of the selected dimension (label click or list click), Delete removes it
let measDirty = false;       // redraw all dimensions on the next frame (camera moved, display changed)
const section = { on: false, mode: 'z', flip: false, t: 0.5, d: 0, n: new THREE.Vector3(0, 0, 1), plane: new THREE.Plane(), az: 0, el: 90, extra: [], box: new THREE.Box3() };
const display = { edges: true, wire: false, grid: false, axes: false, look: 'shaded', shadow: false, ao: false, cube: true, triad: true, alpha: 0.4 }; // alpha: opacity of parts marked transparent
let explode = 0;
const xplan = { def: null, error: '', mode: 'radial', s: 0, playing: false, last: 0, modelPath: '', trails: new THREE.Group() };
scene.add(xplan.trails);
const motion = { def: null, error: '', byName: {}, values: {}, anims: [], anim: 0, playing: false, t: 0, last: 0, axes: new THREE.Group(), modelPath: '' };
let notes = [];
let noteFilter = 'all';
let activePin = null;

// ============================================================= utilities
const fmtTime = t => new Date(t * 1000).toLocaleTimeString('cs-CZ');
const esc = s => String(s ?? '').replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
const r2 = x => Math.round(x * 100) / 100;
const arr = v => [r2(v.x), r2(v.y), r2(v.z)];
let toastT;
function toast(msg, err) {
  const t = $('toast'); t.textContent = msg; t.classList.toggle('err', !!err); t.style.display = 'block';
  clearTimeout(toastT); toastT = setTimeout(() => (t.style.display = 'none'), 2800);
}
async function api(path, body) {
  const res = await fetch(path, body === undefined ? { cache: 'no-store' } : {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body),
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.error || res.statusText);
  return data;
}
function partOffset(p) { return model.parts[p]?.group.position ?? new THREE.Vector3(); }
const toWorld = (p, local) => new THREE.Vector3(...local).add(partOffset(p));

// ============================================================ model loading
let occtPromise = null;
function occt() {
  if (!occtPromise) occtPromise = window.occtimportjs({ locateFile: f => OCCT_CDN + f });
  return occtPromise;
}

async function readStep(path) {
  const colP = fetch('/api/stepcolors?path=' + encodeURIComponent(path)).then(r => r.ok ? r.json() : {}).catch(() => ({}));
  const parts = await parseStep(await (await fetch('/api/file?path=' + encodeURIComponent(path), { cache: 'no-store' })).arrayBuffer());
  // occt-import-js drops colours set on instances or on the solids of a multi-solid part: fill them in from the server's XCAF read
  if (parts.some(p => !p.color && !p.faceRanges?.some(f => f.color))) {
    const cols = (await colP).colors || {};
    for (const p of parts) {
      const c = cols[p.name] ?? cols[p.path?.[p.path.length - 1]];
      if (!p.color && c && !p.faceRanges?.some(f => f.color)) p.color = stepColor(c);
    }
  }
  return parts;
}
// occt-import-js hands colours over already linear (OCCT converts the STEP sRGB values), which is three's working space
const stepColor = c => new THREE.Color(c[0], c[1], c[2]);
async function parseStep(arrayBuf) {
  const buf = new Uint8Array(arrayBuf);
  const o = await occt();
  const res = o.ReadStepFile(buf, { linearUnit: 'millimeter', linearDeflectionType: 'bounding_box_ratio', linearDeflection: 0.0015, angularDeflection: 0.3 });
  if (!res || !res.success || !res.meshes.length) throw new Error('Could not load the STEP file');
  // names and the assembly chain above every mesh (["testasm", "podsestava_vika"] for the lid in a sub-assembly)
  const names = new Map(), chains = new Map();
  (function walk(node, prefix, chain) {
    const nm = node.name || prefix;
    const here = node.name ? [...chain, node.name] : chain;
    for (const mi of node.meshes || []) { names.set(mi, nm); chains.set(mi, here); }
    for (const ch of node.children || []) walk(ch, ch.name || nm, here);
  })(res.root, '', []);
  const partName = (m, i) => m.name || names.get(i) || `Part ${i + 1}`;
  const paths = res.meshes.map((m, i) => {
    const c = [...(chains.get(i) || [])];
    if (c[c.length - 1] === partName(m, i)) c.pop();   // the part's own node is not a group
    return c;
  });
  // the top assembly every part sits in is no group either: drop the prefix all parts share
  while (paths.length > 1 && paths.every(p => p.length && p[0] === paths[0][0])) paths.forEach(p => p.shift());
  if (paths.length === 1) paths[0] = [];
  return res.meshes.map((m, i) => ({
    name: partName(m, i), path: paths[i],
    positions: Float32Array.from(m.attributes.position.array),
    normals: m.attributes.normal ? Float32Array.from(m.attributes.normal.array) : null,
    index: Uint32Array.from(m.index.array),
    // per-face STEP colours (SolidWorks and others often colour faces, not bodies)
    faceRanges: m.brep_faces.map(f => ({ first: f.first, last: f.last, color: f.color ? stepColor(f.color) : null })),
    color: m.color ? stepColor(m.color) : null,
  }));
}

async function readStl(path) {
  const geo = new STLLoader().parse(await (await fetch('/api/file?path=' + encodeURIComponent(path), { cache: 'no-store' })).arrayBuffer());
  return [{ name: path.split(/[\\/]/).pop().replace(/\.stl$/i, ''), positions: Float32Array.from(geo.attributes.position.array), normals: null, index: null, faceRanges: null, color: null }];
}

function buildPart(src, i, count) {
  const an = analyzeMesh(src.positions, src.index, src.faceRanges);
  const geo = new THREE.BufferGeometry();
  geo.setAttribute('position', new THREE.BufferAttribute(src.positions, 3));
  geo.setIndex(new THREE.BufferAttribute(Uint32Array.from(an.index), 1));
  const nV = src.positions.length / 3;
  const faceId = new Float32Array(nV);
  for (let t = 0; t < an.nTri; t++) for (let k = 0; k < 3; k++) faceId[an.index[t * 3 + k]] = an.triFace[t];
  geo.setAttribute('faceId', new THREE.BufferAttribute(faceId, 1));
  geo.setAttribute('color', new THREE.BufferAttribute(new Float32Array(nV * 3).fill(1), 3));
  if (src.normals && !src.index) geo.setAttribute('normal', new THREE.BufferAttribute(src.normals, 3));
  else if (src.normals) geo.setAttribute('normal', new THREE.BufferAttribute(src.normals, 3));
  else geo.computeVertexNormals();
  geo.computeBoundingBox(); geo.computeBoundingSphere();
  const bvhGeo = geo.clone();
  geo.boundsTree = new MeshBVH(geo);

  // faces with their own STEP colour: the vertex colours carry them and the material goes white (see applyPartLook)
  const faceCols = src.faceRanges?.some(f => f.color) ? src.faceRanges.map(f => f.color) : null;
  const color = src.color ?? (faceCols ? faceCols.find(Boolean).clone() : new THREE.Color(count > 1 ? PALETTE[i % PALETTE.length] : BASE_COLOR));
  let baseCol = null;
  if (faceCols) {
    baseCol = new Float32Array(nV * 3);
    for (let t = 0; t < an.nTri; t++) {
      const c = faceCols[an.triFace[t]] ?? color;
      for (let k = 0; k < 3; k++) { const v = an.index[t * 3 + k]; baseCol[v * 3] = c.r; baseCol[v * 3 + 1] = c.g; baseCol[v * 3 + 2] = c.b; }
    }
    geo.attributes.color.array.set(baseCol);
  }
  const po = { polygonOffset: true, polygonOffsetFactor: 1, polygonOffsetUnits: 1 };
  const mats = {
    shaded: clipMat(new THREE.MeshStandardMaterial({ color, metalness: 0.15, roughness: 0.62, vertexColors: true, ...po })),
    matcap: clipMat(new THREE.MeshMatcapMaterial({ color, matcap: MATCAP.clay, vertexColors: true, ...po })),
    xray: clipMat(new THREE.MeshMatcapMaterial({ color, matcap: MATCAP.xray, vertexColors: true, transparent: true, depthWrite: false, blending: THREE.AdditiveBlending, side: THREE.DoubleSide })),
  };
  const mat = mats[display.look];
  const mesh = new THREE.Mesh(geo, mat);
  mesh.castShadow = mesh.receiveShadow = true;
  const cap = new THREE.Mesh(geo, clipMat(new THREE.MeshBasicMaterial({ color: $('secCapColor').value, side: THREE.BackSide })));
  cap.visible = false;
  // model edges
  const seg = [];
  for (const e of an.edges) for (let k = 1; k < e.points.length; k++) seg.push(...e.points[k - 1], ...e.points[k]);
  const eg = new THREE.BufferGeometry();
  eg.setAttribute('position', new THREE.Float32BufferAttribute(seg, 3));
  const edgesObj = new THREE.LineSegments(eg, clipMat(new THREE.LineBasicMaterial({ color: 0x101210 })));
  const group = new THREE.Group();
  group.add(mesh, cap, edgesObj);
  group.userData.part = i;
  mesh.userData.part = i;
  const pose = new THREE.Group();  // motion transform (Motion tab); identity in the home pose
  pose.matrixAutoUpdate = false;
  pose.add(group);
  const bb = geo.boundingBox;
  return {
    index: i, name: src.name, path: src.path || [], an, geo, bvhGeo, mesh, cap, edgesObj, group, pose, mat, mats, alert: false, baseCol, faceTint: !!baseCol, vtint: !!baseCol, paint: new Map(), paintRev: 0, vSig: '',
    // per-part display: '' follows the Display menu; a mesh without B-rep faces (STL, scan) with
    // thousands of estimated edges would be a black tangle, so it starts shaded without edges
    mode: !src.faceRanges && an.edges.length > 1500 ? 'shaded' : '',
    color: color.clone(), defaultColor: color.clone(), visible: true, transp: false,
    center: bb.getCenter(new THREE.Vector3()), bbox: bb.clone(), faceHl: new Map(),
  };
}

function disposeModel() {
  for (const p of model.parts) {
    scene.remove(p.pose);
    p.geo.dispose(); p.bvhGeo.dispose(); p.edgesObj.geometry.dispose();
    for (const m of [...Object.values(p.mats), p.cap.material, p.edgesObj.material]) { clipMats.delete(m); m.dispose(); }
  }
  model.parts = [];
}

async function loadModel(info, keepCamera) {
  if (model.info && tabKey(model.info.path) !== tabKey(info.path)) rememberTabCamera();
  $('loading').classList.add('on');
  await seedProjectState(info);
  let srcs, source;
  try {
    if (info.step && info.stepMtimeMs >= info.mtimeMs - 120000) {
      srcs = await readStep(info.step); source = 'STEP (exact faces and edges)';
    } else throw new Error('bez STEP');
  } catch (e) {
    srcs = await readStl(info.path); source = info.step ? 'STL (STEP failed to load)' : 'STL (estimated faces)';
  }
  // reference mesh (e.g. a scan) shown as an extra part: <model>.ref.stl next to the model
  const refPath = info.path.replace(/\.(stl|step|stp)$/i, '.ref.stl');
  if (refPath !== info.path) {
    const r = await fetch('/api/file?path=' + encodeURIComponent(refPath), { cache: 'no-store' });
    if (r.ok) {
      const geo = new STLLoader().parse(await r.arrayBuffer());
      srcs = srcs.concat([{ name: refPath.split(/[\\/]/).pop().replace(/\.stl$/i, ''), positions: Float32Array.from(geo.attributes.position.array), normals: null, index: null, faceRanges: null, color: new THREE.Color(0x8fb4ff) }]);
    }
  }
  const keepVis = new Map(model.parts.map(p => [p.name, { visible: p.visible, color: p.color, transp: p.transp, mode: p.mode }]));
  disposeModel();
  clearSelection(); clearStrokes(true); clearMeasurements(true);
  model.parts = srcs.map((s, i) => buildPart(s, i, srcs.length));
  for (const p of model.parts) {
    const k = keepVis.get(p.name);
    if (k && keepCamera) { p.visible = k.visible; p.color.copy(k.color); p.transp = k.transp; p.mode = k.mode; applyPartLook(p); }
    scene.add(p.pose);
  }
  const box = new THREE.Box3();
  for (const p of model.parts) box.union(p.bbox);
  model.bbox = box;
  model.center = box.getCenter(new THREE.Vector3());
  model.radius = box.getBoundingSphere(new THREE.Sphere()).radius || 10;
  model.info = info; model.source = source;
  const size = box.getSize(new THREE.Vector3());
  const g = Math.pow(10, Math.ceil(Math.log10(Math.max(size.x, size.y, 1) * 2)));
  grid.scale.setScalar(g); grid.position.set(0, 0, box.min.z);
  axes.scale.setScalar(model.radius * 0.5);
  placeSun();
  anaState.thick.clear(); anaState.colliding = null;
  applyExplode(); applyDisplay();
  if (!tabLoaded(info, keepCamera) && !keepCamera) setView('iso', false);
  updateSection(true);
  $('overlay').style.display = 'none';
  const vol = model.parts.reduce((s, p) => s + p.an.volume, 0);
  $('title').innerHTML = `<b>${esc(info.name)}</b><div class="d">${fmtn(size.x)} × ${fmtn(size.y)} × ${fmtn(size.z)} mm · volume ${fmtn(vol, 1)} mm³${model.parts.length > 1 ? ` · ${model.parts.length} parts` : ''}</div>`;
  $('src').textContent = source;
  $('loading').classList.remove('on');
  renderParts(); renderSelection(); loadParams(); loadVersions(); loadNotes(true); loadMotion(); loadVariants(); loadExplode(); loadMarkers(); loadPartsMeta();
  if (ghost.id) loadGhost(ghost.id);
  renderSavedViews(); restoreMeas(); restorePaint();
  if (paramT) {
    const tot = (performance.now() - paramT.t0 + paramT.script) / 1000;
    renderParamsState(`Done in ${tot.toFixed(1)} s (script ${(paramT.script / 1000).toFixed(2)} s${paramT.warm === false ? ', cold start' : ''}, model reload ${((performance.now() - paramT.t0) / 1000).toFixed(1)} s): ${paramT.changes.join(', ')}`);
    paramT = null;
    afterRebuildChecks();
  }
  if (anaState.kind === 'collide') runCollisions(); else if (anaState.kind) runAnalysis();
}

// ============================================================== model tabs
// Open models as tabs along the bottom. A tab is just the model's path: switching calls /api/open, so
// parameters, notes, versions and paint go to that model's own files. The camera is kept per tab.
// Variants (name@label.step) share one tab that follows the variant picked.
const TABS_KEY = 'cadp.mtabs';
const tabKey = path => path.replace(/@[^\\/]*(\.(step|stp|stl))$/i, '$1').toLowerCase();
let mtabs = (() => { try { return JSON.parse(localStorage.getItem(TABS_KEY) || '[]'); } catch { return []; } })();
const saveTabs = () => { try { localStorage.setItem(TABS_KEY, JSON.stringify(mtabs)); } catch { /* per-viewer convenience */ } };
function tabCamera() {
  return { p: camera.position.toArray(), t: controls.target.toArray(), u: camera.up.toArray(), z: ortho.zoom };
}
function rememberTabCamera() {
  const t = model.info && mtabs.find(x => x.key === tabKey(model.info.path));
  if (t) { t.cam = tabCamera(); saveTabs(); }
}
/** After a model loaded: make sure it has a tab, mark it active; true when that tab had a camera to restore. */
function tabLoaded(info, keepCamera) {
  const key = tabKey(info.path);
  let t = mtabs.find(x => x.key === key);
  if (!t) { t = { key }; mtabs.push(t); if (mtabs.length > 20) mtabs.splice(0, mtabs.length - 20); }
  t.path = info.path; t.name = info.name.replace(/\.(step|stp|stl)$/i, '');
  let restored = false;
  if (!keepCamera && t.cam) {
    ortho.zoom = t.cam.z || 1; ortho.updateProjectionMatrix();
    flyTo(new THREE.Vector3(...t.cam.p), new THREE.Vector3(...t.cam.t), new THREE.Vector3(...t.cam.u), false);
    restored = true;
  }
  saveTabs(); renderTabs();
  return restored;
}
function renderTabs() {
  const el = $('mtabs'), cur = model.info && tabKey(model.info.path);
  el.innerHTML = mtabs.length < 2 && !cur ? '' : mtabs.map((t, i) => `<div class="mt ${t.key === cur ? 'on' : ''}" role="tab" aria-selected="${t.key === cur}" data-i="${i}" title="${esc(t.path)}"><span>${esc(t.name)}</span><button data-a="x" title="Close tab" aria-label="Close ${esc(t.name)}">✕</button></div>`).join('');
  el.querySelectorAll('.mt').forEach(d => {
    const t = mtabs[+d.dataset.i];
    d.onclick = e => { if (e.target.dataset.a === 'x') closeTab(t); else switchTab(t); };
    d.onauxclick = e => { if (e.button === 1) closeTab(t); };
  });
  el.querySelector('.mt.on')?.scrollIntoView({ block: 'nearest', inline: 'nearest' });
}
async function switchTab(t) {
  if (model.info && tabKey(model.info.path) === t.key) return;
  rememberTabCamera();
  try { await api('/api/open', { path: t.path }); await checkLatest(); }
  catch (e) {
    toast('Could not open ' + t.name + ': ' + e.message, true);
    mtabs = mtabs.filter(x => x !== t); saveTabs(); renderTabs();
  }
}
function closeTab(t) {
  const i = mtabs.indexOf(t), active = model.info && tabKey(model.info.path) === t.key;
  mtabs.splice(i, 1); saveTabs();
  if (active && mtabs.length) switchTab(mtabs[Math.min(i, mtabs.length - 1)]);
  else renderTabs();
}
addEventListener('beforeunload', rememberTabCamera);

let checking = null;
/** Look for a new model or changed side files now (also called right after a parameter rebuild). */
function checkLatest() { return checking ??= checkLatestOnce().finally(() => { checking = null; }); }
async function poll() { await checkLatest(); setTimeout(poll, 1200); }
async function checkLatestOnce() {
  try {
    const info = await api('/api/latest');
    const cur = model.info;
    if (info.path && (!cur || info.path !== cur.path || info.mtimeMs !== cur.mtimeMs || info.stepMtimeMs !== cur.stepMtimeMs)) {
      const same = !!cur && (info.path === cur.path || variantBase(info.path) === variantBase(cur.path));  // variants keep the camera
      try {
        await loadModel(info, same);
        if (same && info.path === cur.path) toast('Model updated');
      } catch (err) {
        console.error(err);
        $('loading').classList.remove('on');
        model.info = info;
        toast('Could not load the model: ' + err.message, true);
      }
    } else if (cur && info.path === cur.path && (info.motionMtimeMs !== cur.motionMtimeMs || info.explodeMtimeMs !== cur.explodeMtimeMs || info.partsMtimeMs !== cur.partsMtimeMs)) {
      const m = info.motionMtimeMs !== cur.motionMtimeMs, x = info.explodeMtimeMs !== cur.explodeMtimeMs, pm = info.partsMtimeMs !== cur.partsMtimeMs;
      model.info = info; if (m) loadMotion(); if (x) loadExplode(); if (pm) loadPartsMeta();
    }
  } catch (e) { /* server is restarting */ }
}

// ========================================================== camera, views
function updateOrthoFrustum() {
  const w = view.clientWidth || 1, h = view.clientHeight || 1;
  const dist = camera === ortho ? ortho.position.distanceTo(controls.target) : persp.position.distanceTo(controls.target);
  const halfH = dist * Math.tan(THREE.MathUtils.degToRad(persp.fov / 2));
  ortho.left = -halfH * w / h; ortho.right = halfH * w / h; ortho.top = halfH; ortho.bottom = -halfH;
  ortho.updateProjectionMatrix();
}
function setOrtho(on) {
  const from = camera, to = on ? ortho : persp;
  if (from === to) return;
  to.position.copy(from.position); to.up.copy(from.up);
  if (on) { updateOrthoFrustum(); ortho.zoom = 1; ortho.updateProjectionMatrix(); }
  else {
    const dist = from.position.distanceTo(controls.target) / (ortho.zoom || 1);
    const dir = from.position.clone().sub(controls.target).normalize();
    to.position.copy(controls.target).addScaledVector(dir, dist);
  }
  camera = to; controls.object = to; controls.update();
  $('bOrtho').classList.toggle('on', on);
}
let anim = null;
function flyTo(pos, target, up, animate = true) {
  if (!animate) { camera.position.copy(pos); controls.target.copy(target); camera.up.copy(up); controls.update(); updateOrthoFrustum(); return; }
  anim = { t0: performance.now(), p0: camera.position.clone(), q0: controls.target.clone(), u0: camera.up.clone(), p1: pos, q1: target, u1: up };
}
function visibleSphere() {
  const box = new THREE.Box3();
  for (const p of model.parts) if (p.visible) box.union(p.bbox.clone().translate(p.group.position));
  if (box.isEmpty()) return new THREE.Sphere(model.center.clone(), model.radius);
  return box.getBoundingSphere(new THREE.Sphere());
}
const VIEWS = { iso: [0.9, -1.2, 0.85], front: [0, -1, 0], back: [0, 1, 0], left: [-1, 0, 0], right: [1, 0, 0], top: [0, -1e-4, 1], bottom: [0, 1e-4, -1] };
function setView(name, animate = true, dirOverride) {
  const s = visibleSphere();
  const dir = new THREE.Vector3(...(dirOverride || VIEWS[name] || VIEWS.iso)).normalize();
  const dist = s.radius / Math.sin(THREE.MathUtils.degToRad(persp.fov / 2)) * 1.25;
  if (camera === ortho) { ortho.zoom = 1; ortho.updateProjectionMatrix(); }
  const up = Math.abs(dir.z) > 0.99 ? new THREE.Vector3(0, 1, 0) : new THREE.Vector3(0, 0, 1);
  flyTo(s.center.clone().addScaledVector(dir, dist), s.center.clone(), up, animate);
  persp.near = dist / 1000; persp.far = dist * 100; persp.updateProjectionMatrix();
}
function fitTo(sphere) {
  const dir = camera.position.clone().sub(controls.target).normalize();
  const dist = Math.max(sphere.radius, model.radius * 0.05) / Math.sin(THREE.MathUtils.degToRad(persp.fov / 2)) * 1.3;
  flyTo(sphere.center.clone().addScaledVector(dir, dist), sphere.center.clone(), camera.up.clone());
}

// ============================================================== rendering
let needOutline = false;
(function loop() {
  requestAnimationFrame(loop);
  if (anim) {
    const k = Math.min(1, (performance.now() - anim.t0) / 320), e = 1 - Math.pow(1 - k, 3);
    camera.position.lerpVectors(anim.p0, anim.p1, e);
    controls.target.lerpVectors(anim.q0, anim.q1, e);
    camera.up.lerpVectors(anim.u0, anim.u1, e).normalize();
    if (k >= 1) anim = null;
    updateOrthoFrustum();
  }
  tickMotion();
  controls.update();
  if (needOutline) { needOutline = false; buildOutline(); }
  if (anim) measDirty = true;
  if (measDirty) { measDirty = false; for (const m of measurements) drawMeasurement(m); }
  renderMain();
  renderCube();
  renderTriad();
  labelRenderer.render(scene, camera);
})();
function renderMain() {
  if (!display.ao || display.look === 'xray') { renderer.render(scene, camera); return; }
  if (!composer || gtao.camera !== camera) setupAO();
  const pl = activePlanes();
  gtao.normalMaterial.clippingPlanes = pl.length ? pl : null;   // the cut-away part must not darken the rest
  composer.render();
}
function setupAO() {
  // GTAOPass bakes the camera type in, so it is rebuilt when ortho/perspective switches
  composer?.dispose(); gtao?.dispose();
  const w = view.clientWidth, h = view.clientHeight;
  composer = new EffectComposer(renderer);
  renderPass = new RenderPass(scene, camera);
  gtao = new GTAOPass(scene, camera, w, h);
  gtao.updateGtaoMaterial({ radius: model.radius * 0.06, distanceExponent: 1.5, thickness: model.radius * 0.02, scale: 1.2, samples: 16 });
  gtao.blendIntensity = 0.85;
  composer.addPass(renderPass); composer.addPass(gtao); composer.addPass(new OutputPass());
  composer.setSize(w, h);
}
function placeSun() {
  const r = model.radius, c = model.center, b = model.bbox;
  sunLight.position.set(c.x + r * 1.4, c.y - r * 0.9, b.max.z + r * 2);
  sunLight.target.position.copy(c);
  const sc = sunLight.shadow.camera;
  sc.left = sc.bottom = -r * 1.8; sc.right = sc.top = r * 1.8; sc.near = 0.01; sc.far = r * 8; sc.updateProjectionMatrix();
  sunLight.shadow.normalBias = r * 0.002;
  ground.scale.setScalar(r * 8); ground.position.set(c.x, c.y, b.min.z - r * 0.001);
}

// ============================================================== view cube
// drawn into the top-right corner of the same canvas; click a face, edge or corner to turn the view
const CUBE = { size: 96, margin: 10 };
const cubeScene = new THREE.Scene();
const cubeCam = new THREE.OrthographicCamera(-0.95, 0.95, 0.95, -0.95, 0.1, 10);
const cubeMesh = (() => {
  const face = txt => {
    const c = document.createElement('canvas'); c.width = c.height = 128;
    const g = c.getContext('2d');
    g.fillStyle = '#33322f'; g.fillRect(0, 0, 128, 128);
    g.strokeStyle = '#4d4b46'; g.lineWidth = 6; g.strokeRect(3, 3, 122, 122);
    g.fillStyle = '#faf9f5'; g.font = '600 25px system-ui, sans-serif'; g.textAlign = 'center'; g.textBaseline = 'middle';
    g.fillText(txt, 64, 66);
    const t = new THREE.CanvasTexture(c); t.colorSpace = THREE.SRGBColorSpace; t.anisotropy = 4;
    return new THREE.MeshBasicMaterial({ map: t });
  };
  // BoxGeometry is Y-up: turned so that its +Y is world +Z (the model is Z-up)
  const m = new THREE.Mesh(new THREE.BoxGeometry(1, 1, 1), ['Right', 'Left', 'Top', 'Bottom', 'Front', 'Back'].map(face));
  m.rotation.x = Math.PI / 2;
  const e = new THREE.LineSegments(new THREE.EdgesGeometry(m.geometry), new THREE.LineBasicMaterial({ color: 0x8e8c84 }));
  m.add(e);
  return m;
})();
cubeScene.add(cubeMesh);
const cubeHl = new THREE.Mesh(new THREE.SphereGeometry(0.12, 16, 12), new THREE.MeshBasicMaterial({ color: C_SEL, depthTest: false }));
cubeHl.visible = false; cubeHl.renderOrder = 5;
cubeScene.add(cubeHl);
function cubeRect() { const w = view.clientWidth; return { x: w - CUBE.size - CUBE.margin, y: CUBE.margin, s: CUBE.size }; }
function renderCube() {
  if (!display.cube || !model.parts.length) return;
  const r = cubeRect(), h = view.clientHeight;
  cubeCam.position.copy(camera.position).sub(controls.target).normalize().multiplyScalar(4);
  cubeCam.up.copy(camera.up); cubeCam.lookAt(0, 0, 0);
  renderer.autoClear = false; renderer.clearDepth();
  renderer.setScissorTest(true);
  renderer.setScissor(r.x, h - r.y - r.s, r.s, r.s); renderer.setViewport(r.x, h - r.y - r.s, r.s, r.s);
  renderer.render(cubeScene, cubeCam);
  renderer.setScissorTest(false); renderer.setViewport(0, 0, view.clientWidth, h);
  renderer.autoClear = true;
}
// ========================================================= axis triad
// X/Y/Z arrows in the bottom-left corner, turning with the model (same camera direction as the view cube)
const TRIAD = { size: 84, margin: 6 };
const triadScene = new THREE.Scene();
const triadCam = new THREE.OrthographicCamera(-1.25, 1.25, 1.25, -1.25, 0.1, 10);
(() => {
  const label = (txt, col) => {
    const c = document.createElement('canvas'); c.width = c.height = 64;
    const g = c.getContext('2d');
    g.fillStyle = col; g.font = '700 44px system-ui, sans-serif'; g.textAlign = 'center'; g.textBaseline = 'middle';
    g.fillText(txt, 32, 34);
    const t = new THREE.CanvasTexture(c); t.colorSpace = THREE.SRGBColorSpace;
    const s = new THREE.Sprite(new THREE.SpriteMaterial({ map: t, depthTest: false })); s.scale.setScalar(0.42); s.renderOrder = 2;
    return s;
  };
  for (const [txt, col, dir] of [['X', '#e5655a', [1, 0, 0]], ['Y', '#7cbf8a', [0, 1, 0]], ['Z', '#7fa7d6', [0, 0, 1]]]) {
    const d = new THREE.Vector3(...dir);
    const arrow = new THREE.ArrowHelper(d, new THREE.Vector3(), 0.82, col, 0.22, 0.12);
    arrow.line.material.linewidth = 2;
    triadScene.add(arrow);
    const l = label(txt, col); l.position.copy(d).multiplyScalar(1.02); triadScene.add(l);
  }
  triadScene.add(new THREE.Mesh(new THREE.SphereGeometry(0.06, 12, 8), new THREE.MeshBasicMaterial({ color: 0xc2c0b6 })));
})();
function renderTriad() {
  if (!display.triad || !model.parts.length) return;
  const h = view.clientHeight, s = TRIAD.size, x = TRIAD.margin, y = TRIAD.margin + 22;  // above the hint line
  triadCam.position.copy(camera.position).sub(controls.target).normalize().multiplyScalar(4);
  triadCam.up.copy(camera.up); triadCam.lookAt(0, 0, 0);
  renderer.autoClear = false; renderer.clearDepth();
  renderer.setScissorTest(true);
  renderer.setScissor(x, y, s, s); renderer.setViewport(x, y, s, s);
  renderer.render(triadScene, triadCam);
  renderer.setScissorTest(false); renderer.setViewport(0, 0, view.clientWidth, h);
  renderer.autoClear = true;
}
/** Direction of the cube face/edge/corner under the pointer, or null when it is not over the cube. */
function cubeDir(ev) {
  if (!display.cube || !model.parts.length) return null;
  const px = eventPx(ev), r = cubeRect();
  if (px.x < r.x || px.x > r.x + r.s || px.y < r.y || px.y > r.y + r.s) return null;
  raycaster.setFromCamera(new THREE.Vector2((px.x - r.x) / r.s * 2 - 1, -((px.y - r.y) / r.s * 2 - 1)), cubeCam);
  const hit = raycaster.intersectObject(cubeMesh, false)[0];
  if (!hit) return null;
  return hit.point.toArray().map(c => Math.abs(c) > 0.3 ? Math.sign(c) : 0);
}
controls.addEventListener('change', () => { if (camera === ortho) return; });

// ============================================================== selection
const raycaster = new THREE.Raycaster();
const ndc = new THREE.Vector2();
function eventPx(ev) {
  const r = renderer.domElement.getBoundingClientRect();
  return { x: ev.clientX - r.left, y: ev.clientY - r.top, w: r.width, h: r.height };
}
function isClipped(world) { return activePlanes().some(pl => pl.distanceToPoint(world) < -1e-6); }
function faceHit(ev) {
  const px = eventPx(ev);
  ndc.set((px.x / px.w) * 2 - 1, -(px.y / px.h) * 2 + 1);
  raycaster.setFromCamera(ndc, camera);
  const meshes = model.parts.filter(p => p.visible).map(p => p.mesh);
  for (const h of raycaster.intersectObjects(meshes, false)) {
    if (isClipped(h.point)) continue;
    const part = h.object.userData.part;
    const p = model.parts[part];
    const fid = p.geo.attributes.faceId.getX(h.face.a);
    const local = h.point.clone().sub(p.group.position);
    const n = h.face.normal.clone().transformDirection(h.object.matrixWorld);
    return { part, faceId: fid, local: [local.x, local.y, local.z], world: h.point.clone(), distance: h.distance, normal: [n.x, n.y, n.z], vertex: h.face.a };
  }
  return null;
}
function toScreen(world, px) {
  const v = world.clone().project(camera);
  return { x: (v.x + 1) / 2 * px.w, y: (1 - v.y) / 2 * px.h, z: v.z };
}
function visibleAt(world, hit) {
  if (isClipped(world)) return false;
  if (!hit) return true;
  const d = camera === ortho
    ? world.clone().sub(camera.position).dot(camera.getWorldDirection(new THREE.Vector3()))
    : world.distanceTo(camera.position);
  const hd = camera === ortho
    ? hit.world.clone().sub(camera.position).dot(camera.getWorldDirection(new THREE.Vector3()))
    : hit.distance;
  return d <= hd + model.radius * 0.015;
}
/** Finds the feature under the cursor according to the filter (auto/face/edge/vertex/part). */
function pickAt(ev, filter) {
  const hit = faceHit(ev);
  const px = eventPx(ev);
  const wantV = filter === 'auto' || filter === 'vertex';
  const wantE = filter === 'auto' || filter === 'edge';
  const tolV = filter === 'vertex' ? 14 : 9, tolE = filter === 'edge' ? 11 : 6;
  let best = null;
  if (wantV) {
    for (const p of model.parts) {
      if (!p.visible) continue;
      for (const v of p.an.verts) {
        const w = toWorld(p.index, v.p);
        const s = toScreen(w, px);
        const d = Math.hypot(s.x - px.x, s.y - px.y);
        if (d < tolV && (!best || d < best.d) && visibleAt(w, hit)) best = { d, type: 'vertex', part: p.index, id: v.id, local: [...v.p] };
      }
    }
  }
  if (!best && wantE) {
    for (const p of model.parts) {
      if (!p.visible) continue;
      for (const e of p.an.edges) {
        for (let k = 1; k < e.points.length; k++) {
          const a = toWorld(p.index, e.points[k - 1]), b = toWorld(p.index, e.points[k]);
          const sa = toScreen(a, px), sb = toScreen(b, px);
          const dx = sb.x - sa.x, dy = sb.y - sa.y, l2 = dx * dx + dy * dy || 1;
          const t = Math.max(0, Math.min(1, ((px.x - sa.x) * dx + (px.y - sa.y) * dy) / l2));
          const d = Math.hypot(sa.x + t * dx - px.x, sa.y + t * dy - px.y);
          if (d < tolE && (!best || d < best.d)) {
            const w = a.clone().lerp(b, t);
            if (visibleAt(w, hit)) { const l = w.clone().sub(partOffset(p.index)); best = { d, type: 'edge', part: p.index, id: e.id, local: [l.x, l.y, l.z] }; }
          }
        }
      }
    }
  }
  if (best) return best;
  if (!hit || filter === 'vertex' || filter === 'edge') return null;
  if (filter === 'part') return { type: 'part', part: hit.part, id: hit.part, local: hit.local };
  return { type: 'face', part: hit.part, id: hit.faceId, local: hit.local, normal: hit.normal };
}

// ---- highlighting
function faceGeometry(p, fid) {
  if (p.faceHl.has(fid)) return p.faceHl.get(fid);
  const f = p.an.faces[fid];
  const pos = new Float32Array(f.tris.length * 9);
  const P = p.geo.attributes.position.array, I = p.an.index;
  f.tris.forEach((t, i) => { for (let k = 0; k < 3; k++) { const vi = I[t * 3 + k]; pos.set([P[vi * 3], P[vi * 3 + 1], P[vi * 3 + 2]], i * 9 + k * 3); } });
  const g = new THREE.BufferGeometry();
  g.setAttribute('position', new THREE.BufferAttribute(pos, 3));
  p.faceHl.set(fid, g);
  return g;
}
function highlight(pick, color, strong) {
  const p = model.parts[pick.part];
  if (!p) return null;
  let obj;
  if (pick.type === 'face') {
    obj = new THREE.Mesh(faceGeometry(p, pick.id), clipMat(new THREE.MeshBasicMaterial({ color, transparent: true, opacity: strong ? 0.5 : 0.32, depthWrite: false, polygonOffset: true, polygonOffsetFactor: -2, polygonOffsetUnits: -2 })));
  } else if (pick.type === 'edge') {
    const g = new LineGeometry(); g.setPositions(p.an.edges[pick.id].points.flat());
    obj = new Line2(g, clipMat(lineMat({ color, linewidth: strong ? 4 : 3, depthTest: false })));
    obj.renderOrder = 10;
  } else if (pick.type === 'vertex') {
    const g = new THREE.BufferGeometry(); g.setAttribute('position', new THREE.Float32BufferAttribute(p.an.verts[pick.id].p, 3));
    obj = new THREE.Points(g, clipMat(new THREE.PointsMaterial({ color, size: strong ? 12 : 10, sizeAttenuation: false, depthTest: false })));
    obj.renderOrder = 11;
  } else if (pick.type === 'part') {
    obj = new THREE.Mesh(p.geo, clipMat(new THREE.MeshBasicMaterial({ color, transparent: true, opacity: strong ? 0.28 : 0.18, depthWrite: false, polygonOffset: true, polygonOffsetFactor: -2, polygonOffsetUnits: -2 })));
  }
  if (obj) p.group.add(obj);
  return obj;
}
function dropObj(o) {
  if (!o) return;
  o.parent?.remove(o);
  if (o.material) { clipMats.delete(o.material); lineMats.delete(o.material); o.material.dispose(); }
  if (o.geometry && (o.isLine2 || o.isPoints || o.userData.ownGeo)) o.geometry.dispose();
}
let hoverObj = null, hoverKey = '';

function entityInfo(pick) {
  const p = model.parts[pick.part];
  const prefix = model.parts.length > 1 ? `${p.name}: ` : '';
  if (pick.type === 'face') { const f = p.an.faces[pick.id]; return { title: `${prefix}Face #${pick.id}`, desc: describeFace(f) }; }
  if (pick.type === 'edge') { const e = p.an.edges[pick.id]; return { title: `${prefix}Edge #${pick.id}`, desc: describeEdge(e) }; }
  if (pick.type === 'vertex') { const v = p.an.verts[pick.id]; return { title: `${prefix}Vertex #${pick.id}`, desc: `point ${fmtv(v.p)}` }; }
  const s = p.bbox.getSize(new THREE.Vector3());
  return { title: `Part ${p.name}`, desc: `${fmtn(s.x)} × ${fmtn(s.y)} × ${fmtn(s.z)} mm, volume ${fmtn(p.an.volume, 1)} mm³, ${p.an.faces.length} faces` };
}

function setHover(pick) {
  const key = pick ? `${pick.type}:${pick.part}:${pick.id}` : '';
  if (key === hoverKey) return;
  hoverKey = key; dropObj(hoverObj); hoverObj = null;
  if (pick && !selection.some(s => `${s.type}:${s.part}:${s.id}` === key)) hoverObj = highlight(pick, C_HOVER, false);
}

function selKey(s) { return `${s.type}:${s.part}:${s.id}`; }
function toggleSelect(pick, additive) {
  const k = selKey(pick);
  const i = selection.findIndex(s => selKey(s) === k);
  if (!additive) { const had = i >= 0 && selection.length === 1; clearSelection(); if (had) return; selection.push(pick); }
  else if (i >= 0) { dropObj(selection[i].obj); selection.splice(i, 1); renderSelection(); return; }
  else selection.push(pick);
  pick.obj = highlight(pick, C_SEL, true);
  dropObj(hoverObj); hoverObj = null; hoverKey = '';
  renderSelection();
}
function clearSelection() { for (const s of selection) dropObj(s.obj); selection.length = 0; renderSelection(); }

function renderSelection() {
  $('nSel').textContent = selection.length;
  const el = $('selList');
  if (!selection.length) { el.innerHTML = '<div class="muted">With the Select tool (S) click a face, edge or vertex. Shift adds more.</div>'; }
  else {
    el.innerHTML = selection.map((s, i) => { const inf = entityInfo(s); return `<div class="item"><div class="t">${esc(inf.title)}</div><div class="d">${esc(inf.desc)}</div><div class="acts"><button data-i="${i}" data-a="rm">Remove</button><button data-i="${i}" data-a="zoom">Focus</button></div></div>`; }).join('');
  }
  el.querySelectorAll('button').forEach(b => b.onclick = () => {
    const s = selection[+b.dataset.i];
    if (b.dataset.a === 'rm') { dropObj(s.obj); selection.splice(+b.dataset.i, 1); renderSelection(); }
    else focusPick(s);
  });
  const fSel = selection.find(s => s.type === 'face' && model.parts[s.part].an.faces[s.id].type === 'plane');
  $('selSection').disabled = !fSel;
  $('selFocus').disabled = !selection.length;
  renderStrokeInfo();
}
function pickSphere(s) {
  const p = model.parts[s.part];
  const pts = [];
  if (s.type === 'face') for (const t of p.an.faces[s.id].tris.slice(0, 400)) pts.push(...[0, 1, 2].map(k => { const vi = p.an.index[t * 3 + k]; return new THREE.Vector3().fromBufferAttribute(p.geo.attributes.position, vi); }));
  else if (s.type === 'edge') pts.push(...p.an.edges[s.id].points.map(q => new THREE.Vector3(...q)));
  else if (s.type === 'part') return p.bbox.clone().translate(p.group.position).getBoundingSphere(new THREE.Sphere());
  else pts.push(new THREE.Vector3(...p.an.verts[s.id].p));
  const sp = new THREE.Sphere().setFromPoints(pts);
  sp.center.add(p.group.position);
  if (sp.radius < model.radius * 0.08) sp.radius = model.radius * 0.08;
  return sp;
}
function focusPick(s) { fitTo(pickSphere(s)); }

// ================================================================ drawing
// The pen draws over the screen (a 2D layer above the 3D view), so the view is locked while a
// drawing exists. Each screen point that lands on the model also keeps its exact 3D hit for Claude.
let active = null;
const ink = document.createElement('canvas');
// explicit size: a canvas is shown at its pixel size (w × devicePixelRatio) otherwise, which drifts from the cursor
ink.style.cssText = 'position:absolute;left:0;top:0;width:100%;height:100%;pointer-events:none';
view.appendChild(ink);
function drawInk() {
  const w = view.clientWidth, h = view.clientHeight, d = devicePixelRatio;
  if (ink.width !== Math.round(w * d) || ink.height !== Math.round(h * d)) { ink.width = Math.round(w * d); ink.height = Math.round(h * d); }
  const c = ink.getContext('2d');
  c.setTransform(d, 0, 0, d, 0, 0);
  c.clearRect(0, 0, w, h);
  c.lineWidth = 3; c.lineCap = c.lineJoin = 'round';
  for (const s of strokes) {
    c.strokeStyle = s.color;
    c.beginPath();
    s.screen.forEach(([x, y], i) => i ? c.lineTo(x, y) : c.moveTo(x, y));
    if (s.screen.length === 1) c.lineTo(s.screen[0][0] + 0.1, s.screen[0][1]);
    c.stroke();
  }
}
new ResizeObserver(drawInk).observe(view);
function penPoint(s, ev) {
  const px = eventPx(ev);
  s.screen.push([px.x, px.y]);
  const h = faceHit(ev);
  if (h) s.hits.push({ part: h.part, local: h.local, normal: h.normal });
  else s.misses.push([px.x / px.w, px.y / px.h]);
}
// a drawing is tied to the current view: the view moves freely until the first stroke starts
function lockView() { controls.enabled = !strokes.length; }
function clearStrokes(silent) {
  strokes.length = 0;
  drawInk(); lockView();
  if (!silent) renderStrokeInfo();
}
function undoStroke() { strokes.pop(); drawInk(); lockView(); renderStrokeInfo(); }
function renderStrokeInfo() {
  $('strokeInfo').textContent = strokes.length ? `${strokes.length} pen ${strokes.length === 1 ? 'stroke' : 'strokes'}.` : 'No strokes.';
  hint();
}

// ============================================================ measurement
const measGroup = new THREE.Group(); scene.add(measGroup);
let measSeq = 0;
function entGeom(pk) {
  const p = model.parts[pk.part];
  const e = { pick: pk, part: pk.part, point: pk.local.slice() };
  if (pk.type === 'face') {
    const f = p.an.faces[pk.id];
    e.face = f;
    if (f.type === 'plane') { e.kind = 'plane'; e.n = f.normal; e.c = f.centroid; }
    else if (f.type === 'cylinder') { e.kind = 'cyl'; e.axis = f.axis; e.center = f.center; e.r = f.radius; e.len = f.length; }
    else e.kind = 'point';
  } else if (pk.type === 'edge') {
    const ed = p.an.edges[pk.id];
    e.edge = ed;
    if (ed.type === 'line') { e.kind = 'line'; e.dir = ed.dir; e.p0 = ed.points[0]; }
    else if (ed.type === 'circle' || ed.type === 'arc') { e.kind = 'circle'; e.axis = ed.normal; e.center = ed.center; e.r = ed.radius; }
    else e.kind = 'point';
  } else { e.kind = 'point'; e.point = (pk.type === 'vertex' ? p.an.verts[pk.id].p : pk.local).slice(); }
  return e;
}
const ang = (a, b) => THREE.MathUtils.radToDeg(Math.acos(Math.min(1, Math.abs(v3.dot(v3.norm(a), v3.norm(b))))));
function lineLineClosest(p1, d1, p2, d2) {
  const w = v3.sub(p1, p2), a = v3.dot(d1, d1), b = v3.dot(d1, d2), c = v3.dot(d2, d2), d = v3.dot(d1, w), e = v3.dot(d2, w);
  const den = a * c - b * b;
  if (Math.abs(den) < 1e-12) { const t = e / c; const q = v3.add(p2, v3.mul(d2, t)); return [p1, q]; }
  const s = (b * e - c * d) / den, t = (a * e - b * d) / den;
  return [v3.add(p1, v3.mul(d1, s)), v3.add(p2, v3.mul(d2, t))];
}
function describeEnt(e) { return entityInfo(e.pick).title; }
// vertex and the two leg directions of an angle, for the arc; like the distances, A and B are taken in one frame
function angleGeom(A, B) {
  const V = a => new THREE.Vector3(...a);
  const P1 = V(A.point), P2 = V(B.point);
  const lineOf = e => e.kind === 'line' ? [V(e.p0), V(e.dir).normalize()] : (e.kind === 'cyl' || e.kind === 'circle') ? [V(e.center), V(e.axis).normalize()] : null;
  const toward = (d, o, p) => d.clone().multiplyScalar(p.clone().sub(o).dot(d) < 0 ? -1 : 1);
  const anyPerp = n => new THREE.Vector3().crossVectors(n, Math.abs(n.x) < 0.9 ? new THREE.Vector3(1, 0, 0) : new THREE.Vector3(0, 1, 0)).normalize();
  let vx, u, w;
  if (A.kind === 'plane' && B.kind === 'plane') {
    const n1 = V(A.n).normalize(), n2 = V(B.n).normalize(), L = new THREE.Vector3().crossVectors(n1, n2), l2 = L.lengthSq();
    if (l2 < 1e-12) return {};
    const x0 = new THREE.Vector3().crossVectors(n2, L).multiplyScalar(n1.dot(V(A.c))).add(new THREE.Vector3().crossVectors(L, n1).multiplyScalar(n2.dot(V(B.c)))).divideScalar(l2);
    L.normalize();
    const M = P1.clone().add(P2).multiplyScalar(0.5);
    vx = x0.clone().addScaledVector(L, L.dot(M.sub(x0)));
    const leg = (p, n) => { const d = p.clone().sub(vx); d.addScaledVector(L, -L.dot(d)); return d.lengthSq() > 1e-12 ? d.normalize() : new THREE.Vector3().crossVectors(L, n).normalize(); };
    u = leg(P1, n1); w = leg(P2, n2);
  } else if (A.kind === 'plane' || B.kind === 'plane') {
    const pl = A.kind === 'plane' ? A : B, o = pl === A ? B : A, lo = lineOf(o);
    if (!lo) return {};
    const [p0, d] = lo, n = V(pl.n).normalize(), den = n.dot(d);
    if (Math.abs(den) < 1e-9) return {};
    vx = p0.clone().addScaledVector(d, n.dot(V(pl.c).sub(p0)) / den);
    const uL = toward(d, vx, V(o.point)), uP = uL.clone().addScaledVector(n, -n.dot(uL));
    const uPn = uP.lengthSq() > 1e-12 ? uP.normalize() : anyPerp(n);
    [u, w] = pl === A ? [uPn, uL] : [uL, uPn];
  } else {
    const la = lineOf(A), lb = lineOf(B);
    if (!la || !lb) return {};
    const [q1, q2] = lineLineClosest(la[0].toArray(), la[1].toArray(), lb[0].toArray(), lb[1].toArray());
    vx = V(q1).lerp(V(q2), 0.5);
    u = toward(la[1], vx, P1); w = toward(lb[1], vx, P2);
  }
  return { vertex: { part: A.part, p: vx.toArray() }, u: u.toArray(), w: w.toArray() };
}

function computeMeasure(mode, A, B) {
  const refs = B ? [describeEnt(A), describeEnt(B)] : [describeEnt(A)];
  const isRound = e => e.kind === 'cyl' || e.kind === 'circle';
  // centre line drawn with axis dimensions: through the feature, a bit longer than it
  const axisOf = e => ({ part: e.part, c: e.center, d: v3.norm(e.axis), half: Math.max(e.len ?? 0, 2 * e.r) / 2 + e.r * 0.6 });
  if (!B) {
    if (isRound(A)) return { kind: 'dia', value: 2 * A.r, text: `Ø ${fmtn(2 * A.r)} mm (R ${fmtn(A.r)})`, a: { part: A.part, p: A.center }, b: { part: A.part, p: A.point }, round: { axis: A.axis, center: A.center, point: A.point, r: A.r }, refs };
    return null;
  }
  const P1 = A.point, P2 = B.point;
  const ptpt = () => {
    const d = v3.dist(P1, P2), dd = v3.sub(P2, P1);
    return { kind: 'dist', value: d, text: `${fmtn(d)} mm`, comp: dd, a: { part: A.part, p: P1 }, b: { part: B.part, p: P2 }, refs };
  };
  if (mode === 'pp') return ptpt();
  const dirOf = e => (e.kind === 'plane' ? e.n : e.kind === 'line' ? e.dir : isRound(e) ? e.axis : null);
  if (mode === 'angle') {
    const da = dirOf(A), db = dirOf(B);
    if (!da || !db) return { error: 'Measure angles between planes or straight edges.' };
    let deg;
    if ((A.kind === 'plane') !== (B.kind === 'plane') && (A.kind === 'line' || B.kind === 'line')) deg = 90 - ang(da, db);
    else deg = ang(da, db);
    return { kind: 'angle', value: deg, text: `${fmtn(deg, 2)}°${deg > 0.01 && deg < 179.99 ? ` (${fmtn(180 - deg, 2)}°)` : ''}`, a: { part: A.part, p: P1 }, b: { part: B.part, p: P2 }, refs, ...angleGeom(A, B) };
  }
  // auto
  if (isRound(A) && isRound(B)) {
    if (ang(A.axis, B.axis) < 0.05) {
      // pitch of two parallel axes: closest points on the axes near the clicked spots, with ΔX ΔY ΔZ
      const [q1, q2] = lineLineClosest(A.point, A.axis, B.center, B.axis);
      const d = v3.dist(q1, q2);
      return { kind: 'dist', value: d, text: `axes ${fmtn(d)} mm`, comp: v3.sub(q2, q1), a: { part: A.part, p: q1 }, b: { part: B.part, p: q2 }, refs, axes: [axisOf(A), axisOf(B)] };
    }
    const d = v3.dist(A.center, B.center);
    return { kind: 'dist', value: d, text: `centers ${fmtn(d)} mm`, a: { part: A.part, p: A.center }, b: { part: B.part, p: B.center }, refs };
  }
  if (A.kind === 'plane' && B.kind === 'plane') {
    if (ang(A.n, B.n) < 0.05) {
      const d = Math.abs(v3.dot(A.n, v3.sub(P1, B.c)));
      const q = v3.sub(P1, v3.mul(B.n, v3.dot(B.n, v3.sub(P1, B.c))));
      return { kind: 'dist', value: d, text: `${fmtn(d)} mm (parallel faces)`, a: { part: A.part, p: P1 }, b: { part: B.part, p: q }, refs };
    }
    const deg = ang(A.n, B.n);
    return { kind: 'angle', value: deg, text: `${fmtn(deg, 2)}° mezi plochami`, a: { part: A.part, p: P1 }, b: { part: B.part, p: P2 }, refs, ...angleGeom(A, B) };
  }
  // a point or a straight edge against the axis of a hole / pin
  const round = isRound(A) ? A : isRound(B) ? B : null, rest = round === A ? B : A;
  if (round && (rest.kind === 'point' || (rest.kind === 'line' && ang(rest.dir, round.axis) < 0.05))) {
    const ax = v3.norm(round.axis), from = rest.point;
    const q = v3.add(round.center, v3.mul(ax, v3.dot(v3.sub(from, round.center), ax)));
    const d = v3.dist(from, q);
    const what = rest.kind === 'line' ? 'edge ∥ axis' : 'point ↔ axis';
    return { kind: 'dist', value: d, text: `${what} ${fmtn(d)} mm`, comp: v3.sub(from, q), a: { part: round.part, p: q }, b: { part: rest.part, p: from }, refs, axes: [axisOf(round)] };
  }
  const plane = A.kind === 'plane' ? A : B.kind === 'plane' ? B : null;
  const other = plane === A ? B : A;
  if (plane && (other.kind === 'point')) {
    const d = Math.abs(v3.dot(plane.n, v3.sub(other.point, plane.c)));
    const q = v3.sub(other.point, v3.mul(plane.n, v3.dot(plane.n, v3.sub(other.point, plane.c))));
    return { kind: 'dist', value: d, text: `${fmtn(d)} mm (normal to face)`, a: { part: other.part, p: other.point }, b: { part: plane.part, p: q }, refs };
  }
  if (plane && other.kind === 'line') {
    if (Math.abs(v3.dot(plane.n, other.dir)) < 1e-3) {
      const d = Math.abs(v3.dot(plane.n, v3.sub(other.point, plane.c)));
      const q = v3.sub(other.point, v3.mul(plane.n, v3.dot(plane.n, v3.sub(other.point, plane.c))));
      return { kind: 'dist', value: d, text: `${fmtn(d)} mm (edge ∥ face)`, a: { part: other.part, p: other.point }, b: { part: plane.part, p: q }, refs };
    }
    const deg = 90 - ang(plane.n, other.dir);
    return { kind: 'angle', value: deg, text: `${fmtn(deg, 2)}° edge to face`, a: { part: other.part, p: other.point }, b: { part: plane.part, p: P2 === other.point ? P1 : P2 }, refs, ...angleGeom(A, B) };
  }
  if (plane && isRound(other)) {
    const parallel = Math.abs(v3.dot(plane.n, other.axis)) < 1e-3;
    if (parallel) {
      const d = Math.abs(v3.dot(plane.n, v3.sub(other.center, plane.c)));
      const q = v3.sub(other.center, v3.mul(plane.n, v3.dot(plane.n, v3.sub(other.center, plane.c))));
      return { kind: 'dist', value: d, text: `axis ${fmtn(d)} mm, surface ${fmtn(d - other.r)} mm`, a: { part: other.part, p: other.center }, b: { part: plane.part, p: q }, refs };
    }
    // axis normal to the face: where the axis hits the face and how far that is from the clicked point
    const ax = v3.norm(other.axis);
    const t = v3.dot(plane.n, v3.sub(plane.c, other.center)) / v3.dot(plane.n, ax);
    const hitP = v3.add(other.center, v3.mul(ax, t));
    const d = v3.dist(hitP, plane.point);
    return { kind: 'dist', value: d, text: `axis ↔ point ${fmtn(d)} mm (axis meets face at ${fmtv(hitP)})`, a: { part: other.part, p: hitP }, b: { part: plane.part, p: plane.point }, refs, comp: v3.sub(plane.point, hitP) };
  }
  if (A.kind === 'line' && B.kind === 'line') {
    if (ang(A.dir, B.dir) < 0.05) {
      const [q1, q2] = lineLineClosest(P1, A.dir, B.p0, B.dir);
      const d = v3.dist(q1, q2);
      return { kind: 'dist', value: d, text: `${fmtn(d)} mm (parallel edges)`, a: { part: A.part, p: q1 }, b: { part: B.part, p: q2 }, refs };
    }
    const deg = ang(A.dir, B.dir);
    return { kind: 'angle', value: deg, text: `${fmtn(deg, 2)}° mezi hranami`, a: { part: A.part, p: P1 }, b: { part: B.part, p: P2 }, refs, ...angleGeom(A, B) };
  }
  return ptpt();
}

// ---- dimensions on screen: sizes are in screen pixels (pxWorld) and every dimension is redrawn when the camera moves,
// so arrows, offsets and arcs keep their size at any zoom and the dimension line stays square to the view
controls.addEventListener('change', () => { measDirty = true; });
const MEAS_PX = { off: 34, arrow: 13, ext: 7, arc: 58, lead: 30, dot: 7 };
/** World length of one CSS pixel at `at` (perspective depends on the depth, orthographic does not). */
function pxWorld(at) {
  const h = view.clientHeight || 1;
  if (camera === ortho) return (ortho.top - ortho.bottom) / ortho.zoom / h;
  const dir = camera.getWorldDirection(new THREE.Vector3());
  const depth = Math.max(1e-6, at.clone().sub(camera.position).dot(dir));
  return 2 * depth * Math.tan(THREE.MathUtils.degToRad(persp.fov / 2)) / h;
}
function screenDir(from, dir) {   // unit 2D screen direction (CSS px, y down) of a world direction at a point
  const px = { w: view.clientWidth, h: view.clientHeight };
  const a = toScreen(from, px), b = toScreen(from.clone().addScaledVector(dir, pxWorld(from) * 20), px);
  const v = new THREE.Vector2(b.x - a.x, b.y - a.y);
  return v.lengthSq() > 1e-9 ? v.normalize() : new THREE.Vector2(1, 0);
}
function storeMeas() {
  if (!model.info) return;
  const keep = measurements.map(({ objs, label, _drag, ...m }) => m);
  try { localStorage.setItem('cadp.meas:' + model.info.path, JSON.stringify({ seq: measSeq, list: keep })); } catch { /* per-viewer convenience */ }
}
function restoreMeas() {
  let saved = null;
  try { saved = JSON.parse(localStorage.getItem('cadp.meas:' + (model.info?.path || '')) || 'null'); } catch { /* none */ }
  if (!saved?.list?.length) return;
  measSeq = Math.max(measSeq, saved.seq || 0);
  for (const m of saved.list) if (model.parts[m.a?.part] && model.parts[m.b?.part]) { measurements.push(m); drawMeasurement(m); }
  renderMeasurements();
}
function addMeasurement(m) {
  m.id = ++measSeq;
  measurements.push(m);
  measSel = m.id;
  drawMeasurement(m);
  renderMeasurements(); storeMeas(); hint();
}
// measurement drawing helpers: every object owns its geometry and material, disposeMeas frees them
const MEAS_COLOR = 0x8fb4ff, AXIS_COL = [0xe5655a, 0x7cbf8a, 0x7fa7d6];
function measLine(pts, opts) {
  const g = new LineGeometry(); g.setPositions(pts.flatMap(p => p.toArray()));
  const ln = new Line2(g, lineMat({ color: MEAS_COLOR, linewidth: 1.5, depthTest: false, ...opts }));
  if (opts?.dashed) ln.computeLineDistances();
  ln.renderOrder = 12; return ln;
}
const measDash = (at = model.center) => { const k = pxWorld(at); return { dashed: true, dashSize: k * 7, gapSize: k * 5 }; };
function measPoints(pts, size = MEAS_PX.dot, color = MEAS_COLOR) {
  const g = new THREE.BufferGeometry(); g.setAttribute('position', new THREE.Float32BufferAttribute(pts.flatMap(p => p.toArray()), 3));
  const o = new THREE.Points(g, new THREE.PointsMaterial({ color, size, sizeAttenuation: false, depthTest: false })); o.renderOrder = 12; return o;
}
function measLabel(text, pos, cls = '') {
  const div = document.createElement('div'); div.className = `lbl meas ${cls}`; div.textContent = text;
  const l = new CSS2DObject(div); l.position.copy(pos); return l;
}
function measArrow(tip, dir, h) {  // cone whose tip sits at `tip`, pointing along `dir`
  const c = new THREE.Mesh(new THREE.ConeGeometry(h * 0.33, h, 12), new THREE.MeshBasicMaterial({ color: MEAS_COLOR, depthTest: false }));
  c.quaternion.setFromUnitVectors(new THREE.Vector3(0, 1, 0), dir); c.position.copy(tip).addScaledVector(dir, -h / 2); c.renderOrder = 12; return c;
}
function disposeMeas(objs) {
  for (const o of objs || []) {
    o.parent?.remove(o); if (o.element) o.element.remove();
    o.geometry?.dispose();
    if (o.material) { lineMats.delete(o.material); o.material.dispose(); }
  }
}
let measFirst = [], measPrev = [];   // temporary: marker of the first pick, hover preview
function clearMeasPrev() { disposeMeas(measPrev); measPrev = []; }
function clearMeasTemp() { disposeMeas(measFirst); measFirst = []; clearMeasPrev(); }
/** The label is one persistent HTML element per dimension (it must survive redraws while it is dragged). */
function measLabelObj(m) {
  if (!m.label) {
    m.label = measLabel('', new THREE.Vector3());
    const el = m.label.element;
    el.style.pointerEvents = 'auto'; el.style.cursor = 'move';
    el.addEventListener('pointerdown', ev => {
      if (ev.button !== 0) return;
      ev.stopPropagation(); ev.preventDefault();
      measSel = m.id; renderMeasurements(); measDirty = true;
      const start = { x: ev.clientX, y: ev.clientY, off: m.offPx ?? null, dir: m._drag?.clone() };
      // listen on the window: the pointer may leave the label while dragging
      const move = e => {
        if (!start.dir) return;
        const d = (e.clientX - start.x) * start.dir.x + (e.clientY - start.y) * start.dir.y;
        m.offPx = (start.off ?? defaultOff(m)) + d; measDirty = true;
      };
      const up = () => { removeEventListener('pointermove', move); removeEventListener('pointerup', up); storeMeas(); };
      addEventListener('pointermove', move); addEventListener('pointerup', up);
    });
  }
  return m.label;
}
const defaultOff = m => (m.kind === 'angle' ? MEAS_PX.arc : m.kind === 'dist' ? MEAS_PX.off : MEAS_PX.lead);
function drawMeasurement(m) {
  disposeMeas(m.objs);
  m.objs = [];
  const a = toWorld(m.a.part, m.a.p), b = toWorld(m.b.part, m.b.p);
  const mid = a.clone().lerp(b, 0.5), k = pxWorld(mid), off = m.offPx ?? defaultOff(m);
  const camRight = new THREE.Vector3().setFromMatrixColumn(camera.matrixWorld, 0), camUp = new THREE.Vector3().setFromMatrixColumn(camera.matrixWorld, 1);
  let labelPos, anchor = null, dragDir = camRight.clone().add(camUp).normalize();
  if (m.kind === 'dia' && m.round) {
    // circle around the axis at the clicked point, diameter with arrows, label on a leader outside the circle
    const R = m.round, ax = new THREE.Vector3(...R.axis).normalize(), o = partOffset(m.a.part);
    const c = new THREE.Vector3(...R.center); const pp = new THREE.Vector3(...R.point);
    c.addScaledVector(ax, pp.clone().sub(c).dot(ax));
    // the diameter is drawn square to the view, so it reads at any angle
    let u = new THREE.Vector3().crossVectors(ax, camera.getWorldDirection(new THREE.Vector3()));
    if (u.lengthSq() < 1e-8) u.crossVectors(ax, Math.abs(ax.x) < 0.9 ? new THREE.Vector3(1, 0, 0) : new THREE.Vector3(0, 1, 0));
    u.normalize();
    const w = new THREE.Vector3().crossVectors(ax, u);
    const pts = [];
    for (let i = 0; i <= 64; i++) { const t = i / 64 * Math.PI * 2; pts.push(c.clone().addScaledVector(u, Math.cos(t) * R.r).addScaledVector(w, Math.sin(t) * R.r).add(o)); }
    const d1 = c.clone().addScaledVector(u, R.r).add(o), d2 = c.clone().addScaledVector(u, -R.r).add(o), kc = pxWorld(d1);
    m.objs.push(measLine(pts, { linewidth: 2.2 }), measLine([d1, d2], { linewidth: 1.4 }),
      measArrow(d1, u.clone(), MEAS_PX.arrow * kc), measArrow(d2, u.clone().negate(), MEAS_PX.arrow * kc));
    anchor = d1; labelPos = d1.clone().addScaledVector(u, off * kc); dragDir = u;
    m.objs.push(measLine([d1, labelPos], { linewidth: 1 }));
  } else if (m.kind === 'angle' && m.vertex) {
    // arc between the two legs at the vertex, radius in screen pixels
    const V = toWorld(m.vertex.part, m.vertex.p), u = new THREE.Vector3(...m.u).normalize(), w = new THREE.Vector3(...m.w).normalize();
    const R = Math.abs(off) * pxWorld(V), th = Math.acos(THREE.MathUtils.clamp(u.dot(w), -1, 1));
    const e2 = w.clone().addScaledVector(u, -u.dot(w));
    if (e2.lengthSq() < 1e-12) e2.crossVectors(u, Math.abs(u.x) < 0.9 ? new THREE.Vector3(1, 0, 0) : new THREE.Vector3(0, 1, 0));
    e2.normalize();
    const at = (t, r) => V.clone().addScaledVector(u, Math.cos(t) * r).addScaledVector(e2, Math.sin(t) * r);
    const arc = []; for (let i = 0; i <= 40; i++) arc.push(at(th * i / 40, R));
    const kv = pxWorld(V), h = MEAS_PX.arrow * kv;
    const tan0 = e2.clone(), tan1 = u.clone().multiplyScalar(-Math.sin(th)).addScaledVector(e2, Math.cos(th));
    m.objs.push(measLine(arc, { linewidth: 2 }), measLine([V, V.clone().addScaledVector(u, R * 1.15)], { linewidth: 1 }), measLine([V, V.clone().addScaledVector(w, R * 1.15)], { linewidth: 1 }),
      measArrow(at(0, R), tan0.negate(), h), measArrow(at(th, R), tan1, h), measPoints([a, b]));
    anchor = at(th / 2, R); labelPos = at(th / 2, R + 18 * kv); dragDir = anchor.clone().sub(V).normalize();
  } else if (m.kind === 'dist' && a.distanceTo(b) > 1e-9) {
    // dimension line offset sideways, square to the segment and the current view; extension lines past it, arrowheads
    const dir = b.clone().sub(a).normalize(), vd = camera.getWorldDirection(new THREE.Vector3());
    const side = new THREE.Vector3().crossVectors(dir, vd);
    if (side.lengthSq() < 1e-8) side.copy(camUp).addScaledVector(dir, -camUp.dot(dir));
    side.normalize();
    // keep the side the label was on: flip so the side points up/right on screen
    if (side.dot(camUp) + side.dot(camRight) * 0.3 < 0) side.negate();
    const a2 = a.clone().addScaledVector(side, off * k), b2 = b.clone().addScaledVector(side, off * k), h = MEAS_PX.arrow * k;
    const ext = Math.sign(off || 1) * MEAS_PX.ext * k;
    const inside = a.distanceTo(b) > 2.6 * h;   // arrows outside when the dimension is too short for them
    m.objs.push(measLine([a2, b2], { linewidth: 1.8 }), measLine([a, a2.clone().addScaledVector(side, ext)], { linewidth: 1 }), measLine([b, b2.clone().addScaledVector(side, ext)], { linewidth: 1 }),
      measArrow(a2, inside ? dir.clone().negate() : dir.clone(), h), measArrow(b2, inside ? dir.clone() : dir.clone().negate(), h), measPoints([a, b]));
    if (!inside) m.objs.push(measLine([a2.clone().addScaledVector(dir, -3 * h), b2.clone().addScaledVector(dir, 3 * h)], { linewidth: 1.2 }));
    labelPos = a2.clone().lerp(b2, 0.5).addScaledVector(side, Math.sign(off || 1) * 14 * k); dragDir = side;
    // ΔX ΔY ΔZ drawn as three axis-coloured legs from A to B
    if ($('measComp').checked && m.comp) {
      let p = a.clone();
      [0, 1, 2].forEach(i => {
        if (Math.abs(m.comp[i]) < 1e-6) return;
        const q = p.clone(); q.setComponent(i, q.getComponent(i) + m.comp[i]);
        m.objs.push(measLine([p, q], { color: AXIS_COL[i], linewidth: 1.4, ...measDash(p) }));
        const l = measLabel(`${'XYZ'[i]} ${fmtn(Math.abs(m.comp[i]))}`, p.clone().lerp(q, 0.5), 'comp'); l.element.style.borderColor = '#' + AXIS_COL[i].toString(16).padStart(6, '0');
        m.objs.push(l); p = q;
      });
    }
    // centre lines of the measured axes (dash-dot style of a drawing)
    for (const x of m.axes || []) {
      const o = partOffset(x.part), c = new THREE.Vector3(...x.c).add(o), d = new THREE.Vector3(...x.d);
      m.objs.push(measLine([c.clone().addScaledVector(d, -x.half), c.clone().addScaledVector(d, x.half)], { linewidth: 1, ...measDash(c) }));
    }
  } else if (m.kind === 'info') {
    // one feature: dot and a label on a short leader up-right on screen
    const kp = pxWorld(a);
    m.objs.push(measPoints([a], 9));
    anchor = a; dragDir = camRight.clone().add(camUp).normalize(); labelPos = a.clone().addScaledVector(dragDir, off * kp);
    m.objs.push(measLine([a, labelPos], { linewidth: 1 }));
  } else {
    m.objs.push(measLine([a, b], { linewidth: 2, ...measDash(mid) }), measPoints([a, b]));
    labelPos = mid;
  }
  let text = m.text;
  if ($('measComp').checked && m.comp && m.kind !== 'dist') text += `  ΔX ${fmtn(m.comp[0])} ΔY ${fmtn(m.comp[1])} ΔZ ${fmtn(m.comp[2])}`;
  const lbl = measLabelObj(m);
  lbl.element.textContent = `${m.id}: ${text}`;
  lbl.element.classList.toggle('sel', m.id === measSel);
  lbl.position.copy(labelPos);
  if (lbl.parent !== measGroup) measGroup.add(lbl);
  m._drag = screenDir(labelPos, dragDir);
  // a label on a leader starts at the leader's end instead of covering it
  if (anchor) { const d = m._drag.clone().multiplyScalar(Math.sign(off || 1)); lbl.center.set(d.x > 0.35 ? 0 : d.x < -0.35 ? 1 : 0.5, d.y > 0.35 ? 0 : d.y < -0.35 ? 1 : 0.5); }
  else lbl.center.set(0.5, 0.5);
  for (const o of m.objs) measGroup.add(o);
  measGroup.visible = $('measShow').checked;
}
function removeMeasurement(id) {
  const i = measurements.findIndex(m => m.id === id);
  if (i < 0) return;
  disposeMeas(measurements[i].objs); disposeMeas([measurements[i].label]);
  measurements.splice(i, 1);
  if (measSel === id) measSel = null;
  renderMeasurements(); storeMeas();
}
function clearMeasurements(keepStore) {
  for (const m of [...measurements]) { disposeMeas(m.objs); disposeMeas([m.label]); }
  measurements.length = 0; measSel = null; measPicks = []; clearMeasTemp(); renderMeasurements();
  if (!keepStore) storeMeas();
}
function renderMeasurements() {
  $('nMeas').textContent = measurements.length;
  const el = $('measList');
  el.innerHTML = measurements.map(m => `<div class="item ${m.id === measSel ? 'sel' : ''}" data-id="${m.id}"><div class="t">${m.id}: ${esc(m.text)}</div>
    <div class="d">${esc(m.refs.join(' ↔ '))}${m.comp ? `<br>ΔX ${fmtn(m.comp[0])} · ΔY ${fmtn(m.comp[1])} · ΔZ ${fmtn(m.comp[2])} mm` : ''}</div>
    <div class="acts"><button data-id="${m.id}" data-a="note">Request for this dimension…</button><button data-id="${m.id}" data-a="copy" title="Copy the value">Copy</button><button data-id="${m.id}" data-a="rm" class="danger">Delete</button></div></div>`).join('')
    || '<div class="muted">No measurements yet.</div>';
  el.querySelectorAll('.item[data-id]').forEach(it => it.onclick = e => { if (e.target.closest('button')) return; measSel = +it.dataset.id; renderMeasurements(); measDirty = true; });
  el.querySelectorAll('button').forEach(b => b.onclick = () => {
    const id = +b.dataset.id, m = measurements.find(x => x.id === id);
    if (b.dataset.a === 'rm') removeMeasurement(id);
    else if (b.dataset.a === 'copy') navigator.clipboard?.writeText(m.value !== undefined ? fmtn(m.value) : m.text).then(() => toast('Copied: ' + fmtn(m.value)), () => toast('The browser did not allow copying.', true));
    else openNote({ measurementOnly: id });
  });
}
/** Point-point mode: a click near the middle of a straight edge snaps to the middle, on a circular edge to its centre. */
function snapPick(pick, ev) {
  if (pick?.type !== 'edge' || !ev) return pick;
  const p = model.parts[pick.part], e = p.an.edges[pick.id], px = { w: view.clientWidth, h: view.clientHeight }, mouse = eventPx(ev);
  const near = (local, r) => { const s = toScreen(toWorld(pick.part, local), px); return Math.hypot(s.x - mouse.x, s.y - mouse.y) < r; };
  if ((e.type === 'circle' || e.type === 'arc') && e.center) return { ...pick, local: [...e.center], snap: 'centre' };
  if (e.type === 'line') {
    const m = e.points[0].map((c, i) => (c + e.points[e.points.length - 1][i]) / 2);
    if (near(m, 14)) return { ...pick, local: m, snap: 'middle' };
  }
  return pick;
}
/** One feature on its own: area of a face, length of an edge, coordinates of a point. */
function infoMeasure(pick) {
  const p = model.parts[pick.part], refs = [entityInfo(pick).title];
  const at = { part: pick.part, p: pick.local.slice() };
  if (pick.type === 'face') {
    const f = p.an.faces[pick.id];
    const t = f.type === 'cylinder' ? `Ø ${fmtn(2 * f.radius)} · L ${fmtn(f.length)} · A ${fmtn(f.area)} mm²` : `A ${fmtn(f.area)} mm²${f.type === 'plane' ? ` · n ${fmtv(f.normal)}` : ''}`;
    return { kind: 'info', value: f.area, text: t, a: at, b: at, refs };
  }
  if (pick.type === 'edge') {
    const e = p.an.edges[pick.id];
    const t = e.type === 'line' ? `L ${fmtn(e.length)} mm` : e.radius ? `R ${fmtn(e.radius)} (Ø ${fmtn(2 * e.radius)}) · L ${fmtn(e.length)} mm` : `L ${fmtn(e.length)} mm`;
    return { kind: 'info', value: e.length, text: t, a: at, b: at, refs };
  }
  const v = pick.type === 'vertex' ? p.an.verts[pick.id].p : pick.local;
  const w = toWorld(pick.part, v);
  return { kind: 'info', value: 0, text: `X ${fmtn(v[0])}  Y ${fmtn(v[1])}  Z ${fmtn(v[2])}`, a: { part: pick.part, p: v.slice() }, b: { part: pick.part, p: v.slice() }, refs, world: w.toArray() };
}
/** Shortest distance between two parts (their meshes in the current placement). */
function minDistance(ia, ib) {
  const A = model.parts[ia], B = model.parts[ib];
  const oa = partOffset(ia), ob = partOffset(ib);
  const M = new THREE.Matrix4().makeTranslation(ob.x - oa.x, ob.y - oa.y, ob.z - oa.z);   // B local -> A local
  const t1 = {}, t2 = {};
  A.geo.boundsTree.closestPointToGeometry(B.geo, M, t1, t2);
  // three-mesh-bvh gives target1 in A's frame and target2 already back in B's own frame
  const p1 = t1.point.clone(), p2 = t2.point.clone();
  const d = t1.distance;
  return { kind: 'dist', value: d, text: d < 1e-4 ? 'touching / overlapping (0 mm)' : `min ${fmtn(d)} mm`, comp: v3.sub(p2.clone().add(ob).toArray(), p1.clone().add(oa).toArray()),
    a: { part: ia, p: p1.toArray() }, b: { part: ib, p: p2.toArray() }, refs: [`Part ${A.name}`, `Part ${B.name}`] };
}
function measureClick(pick, shift, ev) {
  clearMeasPrev();
  if (!pick) return;
  const mode = $('measMode').value;
  if (mode === 'one') return addMeasurement(infoMeasure(pick));
  if (mode === 'min') {
    measPicks.push({ part: pick.part, obj: highlight({ type: 'part', part: pick.part, id: pick.part }, 0x8fb4ff, true) });
    if (measPicks.length < 2) { hint(); return; }
    const [A, B] = measPicks;
    for (const mp of measPicks) dropObj(mp.obj);
    measPicks = []; clearMeasTemp(); hint();
    if (A.part === B.part) return toast('Pick two different parts.', true);
    return addMeasurement(minDistance(A.part, B.part));
  }
  if (mode === 'pp') pick = snapPick(pick, ev);
  const e = entGeom(pick);
  if (pick.snap) e.kind = 'point', e.point = pick.local.slice();
  if (mode === 'dia') {
    const m = computeMeasure('auto', e);
    if (!m) return toast('Click a hole, pin or circular edge.', true);
    return addMeasurement(m);
  }
  if (mode === 'auto' && measPicks.length === 0 && (e.kind === 'cyl' || e.kind === 'circle') && !shift) {
    const m = computeMeasure('auto', e); addMeasurement(m);
    toast('Ø measured. Shift+click to measure the distance from the hole.');
    return;
  }
  measPicks.push({ e, obj: highlight(pick, 0x8fb4ff, true) });
  if (measPicks.length === 2) {
    const [A, B] = measPicks;
    const m = computeMeasure(mode, A.e, B.e);
    for (const mp of measPicks) dropObj(mp.obj);
    measPicks = []; clearMeasTemp();
    if (!m || m.error) return toast(m?.error || 'Cannot measure this combination.', true);
    addMeasurement(m);
  } else {
    // show the first point right away
    measFirst = [measPoints([toWorld(e.part, e.point)], 11)];
    if (mode === 'pp') measFirst.push(measLabel(pick.snap ? `${pick.snap} · click the second point` : 'Click the second point', toWorld(e.part, e.point)));
    for (const o of measFirst) measGroup.add(o);
    measGroup.visible = $('measShow').checked;
    hint();
  }
}
// hover preview while one pick is held: dashed line and value to the feature under the cursor
function measPreview(pk, ev) {
  clearMeasPrev();
  const mode = $('measMode').value;
  if (tool !== 'measure' || measPicks.length !== 1 || !pk || mode === 'min' || mode === 'one') return;
  if (mode === 'pp') pk = snapPick(pk, ev);
  const e = entGeom(pk);
  if (pk.snap) e.kind = 'point', e.point = pk.local.slice();
  const m = computeMeasure(mode, measPicks[0].e, e);
  if (!m || m.error || !m.a || !m.b) return;
  const a = toWorld(m.a.part, m.a.p), b = toWorld(m.b.part, m.b.p);
  measPrev = [measLine([a, b], { linewidth: 1.5, ...measDash(a.clone().lerp(b, 0.5)) }), measLabel(m.text, a.clone().lerp(b, 0.5))];
  if (pk.snap) measPrev.push(measPoints([toWorld(pk.part, pk.local)], 11, 0xd97757));
  for (const o of measPrev) measGroup.add(o);
}

// ================================================================ section
const secPlaneMesh = new THREE.Mesh(new THREE.PlaneGeometry(1, 1), new THREE.MeshBasicMaterial({ color: 0x8fb4ff, transparent: true, opacity: 0.1, side: THREE.DoubleSide, depthWrite: false }));
const secPlaneEdge = new THREE.LineLoop(new THREE.BufferGeometry().setFromPoints([new THREE.Vector3(-0.5, -0.5, 0), new THREE.Vector3(0.5, -0.5, 0), new THREE.Vector3(0.5, 0.5, 0), new THREE.Vector3(-0.5, 0.5, 0)]), new THREE.LineBasicMaterial({ color: 0x8fb4ff, transparent: true, opacity: 0.6 }));
secPlaneMesh.add(secPlaneEdge);
secPlaneMesh.visible = false;
scene.add(secPlaneMesh);
const secBoxHelper = new THREE.Box3Helper(section.box, 0x7fa7d6);
secBoxHelper.visible = false;
scene.add(secBoxHelper);
let outlineObj = null;

/** Every plane that cuts right now: the main plane (or the six box faces) plus the kept ones. */
function activePlanes() {
  if (!section.on) return [];
  const out = section.extra.filter(e => e.on).map(e => e.plane);
  if (section.mode === 'box') {
    const a = section.box.min, b = section.box.max;
    out.push(new THREE.Plane(new THREE.Vector3(1, 0, 0), -a.x), new THREE.Plane(new THREE.Vector3(-1, 0, 0), b.x),
      new THREE.Plane(new THREE.Vector3(0, 1, 0), -a.y), new THREE.Plane(new THREE.Vector3(0, -1, 0), b.y),
      new THREE.Plane(new THREE.Vector3(0, 0, 1), -a.z), new THREE.Plane(new THREE.Vector3(0, 0, -1), b.z));
  } else out.push(section.plane);
  return out;
}
function planeLabel(pl) {
  const n = pl.normal, i = [0, 1, 2].find(k => Math.abs(n.getComponent(k)) > 0.9999);
  if (i === undefined) return `plane ⟂ ${fmtv(n.toArray())}`;
  const sg = Math.sign(n.getComponent(i));
  return `${'XYZ'[i]} = ${fmtn(-pl.constant * sg)} mm${sg < 0 ? ' · keeps −' : ' · keeps +'}`;
}
function renderSecExtra() {
  $('secExtra').innerHTML = section.extra.map((e, i) => `<div class="row" style="margin:3px 0"><input type="checkbox" data-i="${i}" data-a="on" ${e.on ? 'checked' : ''}>
    <span class="grow mono">${esc(planeLabel(e.plane))}</span><button class="icon ghost" data-i="${i}" data-a="flip" title="Flip">⇅</button><button class="icon ghost" data-i="${i}" data-a="rm" title="Remove">✕</button></div>`).join('');
  $('secExtra').querySelectorAll('[data-a]').forEach(el => {
    const e = section.extra[+el.dataset.i];
    if (el.dataset.a === 'on') el.onchange = () => { e.on = el.checked; updateSection(); };
    else el.onclick = () => { if (el.dataset.a === 'flip') e.plane.negate(); else section.extra.splice(+el.dataset.i, 1); renderSecExtra(); updateSection(); };
  });
}
function renderSecBox() {
  const B = model.bbox; if (!B) return;
  const pad = model.radius * 0.02;
  $('secBoxRows').innerHTML = ['x', 'y', 'z'].map(a => {
    const lo = B.min[a] - pad, hi = B.max[a] + pad, st = (hi - lo) / 500;
    return `<div class="row" style="margin:2px 0"><b style="width:12px">${a.toUpperCase()}</b>
      <input type="range" data-a="${a}" data-e="min" min="${lo}" max="${hi}" step="${st}" value="${section.box.min[a]}" class="grow" style="width:auto">
      <input type="range" data-a="${a}" data-e="max" min="${lo}" max="${hi}" step="${st}" value="${section.box.max[a]}" class="grow" style="width:auto"></div>
      <div class="muted mono" style="margin:-3px 0 4px 18px;font-size:11px" data-v="${a}"></div>`;
  }).join('');
  const label = () => { for (const a of ['x', 'y', 'z']) $('secBoxRows').querySelector(`[data-v="${a}"]`).textContent = `${fmtn(section.box.min[a])} … ${fmtn(section.box.max[a])} mm`; };
  $('secBoxRows').querySelectorAll('input').forEach(r => r.oninput = () => {
    const a = r.dataset.a, other = $('secBoxRows').querySelector(`input[data-a="${a}"][data-e="${r.dataset.e === 'min' ? 'max' : 'min'}"]`);
    if (r.dataset.e === 'min') section.box.min[a] = Math.min(+r.value, +other.value - 1e-3); else section.box.max[a] = Math.max(+r.value, +other.value + 1e-3);
    label(); updateSection();
  });
  label();
}
function fitSecBox(box) {
  if (!box || box.isEmpty()) return;
  section.box.copy(box).expandByScalar(model.radius * 0.01);
  renderSecBox(); updateSection();
}
function visibleBox() {
  const box = new THREE.Box3();
  for (const p of model.parts) if (p.visible) box.union(p.bbox.clone().translate(p.group.position));
  return box;
}

function sectionNormal() {
  if (section.mode === 'x') return new THREE.Vector3(1, 0, 0);
  if (section.mode === 'y') return new THREE.Vector3(0, 1, 0);
  if (section.mode === 'z') return new THREE.Vector3(0, 0, 1);
  if (section.mode === 'custom') {
    const az = THREE.MathUtils.degToRad(section.az), el = THREE.MathUtils.degToRad(section.el);
    return new THREE.Vector3(Math.cos(el) * Math.cos(az), Math.cos(el) * Math.sin(az), Math.sin(el));
  }
  return section.n.clone();
}
function sectionRange(n) {
  let lo = Infinity, hi = -Infinity;
  for (const p of model.parts) {
    if (!p.visible) continue;
    const b = p.bbox.clone().translate(p.group.position);
    for (const x of [b.min.x, b.max.x]) for (const y of [b.min.y, b.max.y]) for (const z of [b.min.z, b.max.z]) {
      const d = n.x * x + n.y * y + n.z * z; lo = Math.min(lo, d); hi = Math.max(hi, d);
    }
  }
  if (!isFinite(lo)) { lo = -1; hi = 1; }
  return [lo, hi];
}
function updateSection(fromModel) {
  const n = sectionNormal();
  const [lo, hi] = sectionRange(n);
  if (fromModel && section.mode !== 'face') section.d = lo + section.t * (hi - lo);
  section.d = Math.min(hi, Math.max(lo, section.d));
  section.t = hi > lo ? (section.d - lo) / (hi - lo) : 0.5;
  const nn = section.flip ? n.clone().negate() : n;
  section.plane.set(nn, section.flip ? section.d : -section.d);
  const all = activePlanes(), planes = all.length ? all : null;
  for (const m of clipMats) { if ((m.clippingPlanes?.length || 0) !== (planes?.length || 0)) m.needsUpdate = true; m.clippingPlanes = planes; }
  for (const p of model.parts) p.cap.visible = section.on && $('secCap').checked && p.visible;
  secPlaneMesh.visible = section.on && $('secPlane').checked && section.mode !== 'box';
  secBoxHelper.visible = section.on && $('secPlane').checked && section.mode === 'box';
  const s = model.radius * 2.6;
  secPlaneMesh.scale.set(s, s, 1);
  const center = model.center.clone().addScaledVector(n, section.d - n.dot(model.center));
  secPlaneMesh.position.copy(center);
  secPlaneMesh.lookAt(center.clone().add(n));
  $('secOff').value = section.t;
  $('secOffN').value = r2(section.d);
  $('secOffN').min = r2(lo); $('secOffN').max = r2(hi);
  needOutline = true;
}
function buildOutline() {
  if (outlineObj) { scene.remove(outlineObj); outlineObj.geometry.dispose(); lineMats.delete(outlineObj.material); outlineObj = null; }
  $('secInfo').textContent = '';
  if (!section.on || !$('secOutline').checked) return;
  const planes = activePlanes();
  const seg = [];
  const A = new THREE.Vector3(), B = new THREE.Vector3(), C = new THREE.Vector3();
  // each plane's cut, trimmed by the other planes so only the visible outline remains
  const trim = (a, b, others) => {
    for (const q of others) {
      const da = q.distanceToPoint(a), db = q.distanceToPoint(b);
      if (da < 0 && db < 0) return null;
      if (da < 0) a = a.clone().lerp(b, da / (da - db)); else if (db < 0) b = b.clone().lerp(a, db / (db - da));
    }
    return [a, b];
  };
  for (const pl of planes) {
    const others = planes.filter(q => q !== pl);
    for (const p of model.parts) {
      if (!p.visible) continue;
      const P = p.geo.attributes.position, I = p.an.index, off = p.group.position;
      for (let t = 0; t < p.an.nTri; t++) {
        A.fromBufferAttribute(P, I[t * 3]).add(off); B.fromBufferAttribute(P, I[t * 3 + 1]).add(off); C.fromBufferAttribute(P, I[t * 3 + 2]).add(off);
        const da = pl.distanceToPoint(A), db = pl.distanceToPoint(B), dc = pl.distanceToPoint(C);
        const out = [];
        const edge = (p1, p2, d1, d2) => { if ((d1 > 0) !== (d2 > 0)) { const k = d1 / (d1 - d2); out.push(p1.clone().lerp(p2, k)); } };
        edge(A, B, da, db); edge(B, C, db, dc); edge(C, A, dc, da);
        if (out.length !== 2) continue;
        const s2 = others.length ? trim(out[0], out[1], others) : out;
        if (s2) seg.push(...s2[0].toArray(), ...s2[1].toArray());
      }
    }
  }
  if (!seg.length) { $('secInfo').textContent = 'The section does not cut the model.'; return; }
  const g = new LineSegmentsGeometry(); g.setPositions(seg);
  outlineObj = new LineSegments2(g, lineMat({ color: 0xf0c27a, linewidth: 2.5, depthTest: false }));
  outlineObj.renderOrder = 9;
  scene.add(outlineObj);
  if (planes.length > 1) { $('secInfo').textContent = section.mode === 'box' ? `Box ${fmtv(section.box.min.toArray())} … ${fmtv(section.box.max.toArray())} mm` : `${planes.length} planes cut the model`; return; }
  const pl = planes[0];
  // size of the section outline in its plane
  const n = pl.normal, u = new THREE.Vector3().crossVectors(n, Math.abs(n.x) < 0.9 ? new THREE.Vector3(1, 0, 0) : new THREE.Vector3(0, 1, 0)).normalize(), w = new THREE.Vector3().crossVectors(n, u);
  let u0 = Infinity, u1 = -Infinity, w0 = Infinity, w1 = -Infinity;
  for (let i = 0; i < seg.length; i += 3) { const q = new THREE.Vector3(seg[i], seg[i + 1], seg[i + 2]); const a = q.dot(u), b = q.dot(w); u0 = Math.min(u0, a); u1 = Math.max(u1, a); w0 = Math.min(w0, b); w1 = Math.max(w1, b); }
  $('secInfo').textContent = `Section at ${section.mode === 'face' || section.mode === 'custom' ? 'plane' : section.mode.toUpperCase() + ' ='} ${fmtn(section.d)} mm · outline ${fmtn(u1 - u0)} × ${fmtn(w1 - w0)} mm`;
}
function setSectionOn(on) { section.on = on; $('secOn').checked = on; updateSection(); }

// ===================================================== parts, exploded view
/** Vertex colours back to the part's own look: STEP face colours while the part keeps its STEP colour, otherwise white (the material colour shows). */
/**
 * Vertex colours back to the part's own look. While the vertex colours carry the colour (p.vtint), the material is white:
 * STEP face colours while the part keeps its STEP colour, otherwise the part colour, and painted faces (Paint tool) on top.
 */
/** The part still has the colour it was loaded with (compared as 8-bit sRGB: a hex round trip must not count as a change). */
const ownColor = p => p.color.getHex() === p.defaultColor.getHex();
const paintSig = p => `${p.baseCol && ownColor(p) ? 'step' : p.color.getHex()}:${p.paintRev}`;
function resetVertexColors(p) {
  const arr = p.geo.attributes.color.array;
  p.faceTint = !!p.baseCol && ownColor(p);
  p.vtint = p.faceTint || p.paint.size > 0;
  if (!p.vtint) arr.fill(1);
  else {
    if (p.faceTint) arr.set(p.baseCol);
    else for (let i = 0; i < arr.length; i += 3) { arr[i] = p.color.r; arr[i + 1] = p.color.g; arr[i + 2] = p.color.b; }
    if (p.paint.size) {
      const fid = p.geo.attributes.faceId.array, cols = new Map([...p.paint].map(([f, hex]) => [f, new THREE.Color(hex)]));
      for (let v = 0; v < fid.length; v++) { const c = cols.get(fid[v]); if (c) { arr[v * 3] = c.r; arr[v * 3 + 1] = c.g; arr[v * 3 + 2] = c.b; } }
    }
  }
  p.vSig = paintSig(p);
  p.geo.attributes.color.needsUpdate = true;
}
function applyPartLook(p) {
  p.mat = p.mats[display.look]; p.mesh.material = p.mat;
  // part colour or paint changed: rebuild the vertex colours (a part colour replaces the STEP face colours, paint stays on top)
  if (!anaState.kind && !ghost.geo && p.vSig !== paintSig(p)) resetVertexColors(p);
  // a colour map paints vertex colours, so the base colour goes white while it is shown; so do STEP face colours and paint
  p.mat.color.copy(anaState.kind || p.vtint ? WHITE : p.color);
  if (p.alert) p.mat.color.lerp(ALERT, 0.75);
  const xr = display.look === 'xray', op = partAlpha(p);
  p.mat.transparent = xr || op < 1; p.mat.opacity = xr ? 0.65 * op : op; p.mat.depthWrite = !xr && op >= 1;
  const mode = p.mode || (display.wire ? 'wire' : display.edges ? 'edges' : 'shaded');
  p.mat.wireframe = mode === 'wire';
  p.edgesObj.visible = mode === 'edges' || (!p.mode && display.edges);
  p.mesh.castShadow = !xr;
  p.mat.needsUpdate = true;
  p.group.visible = p.visible;
}
function setPartsVisible(fn) { for (const q of model.parts) { q.visible = fn(q); applyPartLook(q); } renderParts(); updateSection(); }
function applyExplode() {
  const c = model.center;
  if (xplan.mode !== 'radial' && xplan.def) applyPlan();
  else for (const p of model.parts) p.group.position.copy(p.center.clone().sub(c).multiplyScalar(explode * 1.2));
  drawTrails();
  for (const m of measurements) drawMeasurement(m);
  renderPins(); drawMarkers();
  if (section.on) updateSection();
}
// ===================================================== parts list (left panel)
// row = visibility, display style, colour, transparency (yes/no); display and colour open popups
const PI = {
  eye: '<svg viewBox="0 0 16 16"><path d="M1.5 8s2.4-4.5 6.5-4.5S14.5 8 14.5 8 12.1 12.5 8 12.5 1.5 8 1.5 8z"/><circle cx="8" cy="8" r="2"/></svg>',
  eyeOff: '<svg viewBox="0 0 16 16"><path d="M1.5 8s2.4-4.5 6.5-4.5S14.5 8 14.5 8 12.1 12.5 8 12.5 1.5 8 1.5 8z"/><path d="M2.5 13.5l11-11"/></svg>',
  disp: m => {
    const fill = m === 'shaded' || m === 'edges' ? 'fill:currentColor;fill-opacity:.35' : 'fill:none';
    const lines = m === 'edges' || m === 'wire' ? '<path d="M2.4 4.8L8 7.8l5.6-3M8 7.8v6.4"/>' : '';
    return `<svg viewBox="0 0 16 16"><path style="${fill}" d="M8 1.8l5.6 3v6.4L8 14.2l-5.6-3V4.8z"/>${lines}</svg>`;
  },
  trans: on => on
    ? '<svg viewBox="0 0 16 16"><circle cx="8" cy="8" r="5.8"/><path style="fill:currentColor;fill-opacity:.35;stroke:none" d="M8 2.2A5.8 5.8 0 0 1 8 13.8Z"/></svg>'
    : '<svg viewBox="0 0 16 16"><circle cx="8" cy="8" r="5.8" style="fill:currentColor;stroke:none"/></svg>',
  focus: '<svg viewBox="0 0 16 16"><circle cx="8" cy="8" r="4.5"/><path d="M8 1v3M8 12v3M1 8h3M12 8h3"/></svg>',
  check: '<svg viewBox="0 0 16 16"><path d="M3 8.5l3 3 7-7"/></svg>',
  modes: ['', 'shaded', 'edges', 'wire'],
  dispLabel: { '': 'As Display menu', shaded: 'Shaded', edges: 'Shaded with edges', wire: 'Wireframe' },
};
const SWATCHES = ['#d9d4cc', '#9a9a9a', '#3d3d3d', '#e0533d', '#f0a23b', '#f2d64b', '#7bc043', '#2fa39a', '#3b82f6', '#7c5cd6', '#d6469f', '#b08968'];
const partAlpha = p => (p.transp ? display.alpha : 1);
let popEl = null;
function closePop() { popEl?.remove(); popEl = null; document.querySelectorAll('.pk-picker').forEach(n => n.remove()); }
function openPop(anchor, html, bind) {
  closePop();
  const el = document.createElement('div');
  el.className = 'pop'; el.innerHTML = html; document.body.append(el); popEl = el;
  const r = anchor.getBoundingClientRect(), w = el.offsetWidth, h = el.offsetHeight;
  el.style.left = `${Math.max(8, Math.min(r.left, innerWidth - w - 8))}px`;
  el.style.top = `${r.bottom + 6 + h > innerHeight ? Math.max(8, r.top - h - 6) : r.bottom + 6}px`;
  bind(el);
}
document.addEventListener('pointerdown', e => { if (popEl && !popEl.contains(e.target)) closePop(); });
document.addEventListener('keydown', e => { if (e.key === 'Escape') closePop(); });
function showDispMenu(p, anchor) {
  const cur = p.mode || '';
  openPop(anchor, PI.modes.map(v => `<div class="it" data-v="${v}"><span class="ck">${v === cur ? PI.check : ''}</span>${PI.dispLabel[v]}</div>`).join(''), el => {
    el.querySelectorAll('.it').forEach(it => it.onclick = () => { p.mode = it.dataset.v; applyPartLook(p); closePop(); renderParts(); });
  });
}
function showColorMenu(p, anchor) {
  const cur = '#' + p.color.getHexString();
  openPop(anchor, `<div class="swatches">${SWATCHES.map(c => `<i data-c="${c}" title="${c}" class="${c === cur ? 'on' : ''}" style="background:${c}"></i>`).join('')}</div><div class="sep"></div><div class="it" data-custom><span class="ck"></span>Custom colour…</div>`, el => {
    const apply = hex => { p.color.set(hex); applyPartLook(p); };
    el.querySelectorAll('[data-c]').forEach(s => s.onclick = () => { apply(s.dataset.c); closePop(); renderParts(); });
    el.querySelector('[data-custom]').onclick = () => {
      const picker = document.createElement('input');
      picker.type = 'color'; picker.value = cur; picker.className = 'pk-picker';
      picker.style.cssText = 'position:fixed;left:0;top:0;opacity:0;width:1px;height:1px;pointer-events:none';
      document.body.append(picker);
      picker.oninput = e => apply(e.target.value);
      picker.onchange = () => { closePop(); renderParts(); };
      picker.click();
    };
  });
}
// Part properties fold away (by part name, so they survive reloads); one part starts open
const partOpen = new Set();
let partOpenModel = null;
/** The tree as wide as its widest row (long names scroll sideways together); measured while the panel is shown. */
function fitPartRows() {
  const el = $('partList'), tree = el.querySelector('.ptree');
  if (!tree) return;
  tree.style.removeProperty('min-width');
  const L = tree.getBoundingClientRect().left;
  const rows = [...tree.querySelectorAll('.prow')].filter(r => r.offsetParent);
  const w = Math.max(0, ...rows.map(r => r.getBoundingClientRect().left - L + r.scrollWidth)) + 12;   // + the row's padding and border
  if (rows.length && w > el.clientWidth) tree.style.minWidth = `${w}px`;
}
new ResizeObserver(() => fitPartRows()).observe($('pside'));
// ---- part attributes: <model>.parts.json written by Claude, otherwise guessed from the name
// {"parts": {"<part name>": {"type": "fastener", "group": "…", "subassembly": "…", "standard": "ISO 4017 M5x16", "material": "…"}}}
const PART_TYPES = { custom: 'Custom parts', fastener: 'Fasteners', bearing: 'Bearings', seal: 'Seals', spring: 'Springs', purchased: 'Purchased parts', electrical: 'Electrical', other: 'Other' };
const TYPE_GUESS = [
  ['fastener', /(screw|bolt|nut\b|washer|rivet|dowel|circlip|šroub|sroub|matice|matka|podlo[žz]k|nýt|nyt|kol[ií]k|pojistn|\b(iso|din|en|čsn|csn)[ _-]?\d{3,5}|\bm\d{1,2}([x×]\d+)?\b)/i],
  ['bearing', /(bearing|lo[žz]isk|\b6[0-4]\d{2}(-?2?rs|-?2?z)?\b)/i],
  ['seal', /(o-?ring|seal|t[ěe]sn|gufer)/i],
  ['spring', /(spring|pru[žz]in)/i],
];
let partsMeta = {};   // name -> attributes from parts.json
async function loadPartsMeta() {
  partsMeta = {};
  if (model.info?.parts) { try { partsMeta = (await api('/api/parts')).parts || {}; } catch (e) { toast('parts.json: ' + e.message, true); } }
  renderParts();
}
function partInfo(p) {
  const m = partsMeta[p.name] || {};
  const guess = TYPE_GUESS.find(([, re]) => re.test(p.name))?.[0];
  const type = PART_TYPES[m.type] ? m.type : (m.type ? 'other' : guess || 'custom');
  const sub = m.subassembly ? String(m.subassembly).split('/').map(x => x.trim()).filter(Boolean) : p.path;
  return { type, guessed: !m.type && !!guess, group: m.group || PART_TYPES[type], sub, meta: m };
}
const partGrpClosed = new Set();
let partGroupMode = (() => { try { return localStorage.getItem('cadp.partsGroup') || 'auto'; } catch { return 'auto'; } })();
function groupMode() {
  if (partGroupMode !== 'auto') return partGroupMode;
  if (model.parts.some(p => partInfo(p).sub.length)) return 'asm';
  return model.parts.some(p => partInfo(p).type !== 'custom') ? 'type' : 'flat';
}
function partRowHtml(p, q) {
  const s = p.bbox.getSize(new THREE.Vector3()), inf = partInfo(p);
  const extra = [inf.meta.standard, inf.meta.material].filter(Boolean).map(esc).join(' · ');
  return `<div class="item ${partOpen.has(p.name) ? 'open' : ''}" data-i="${p.index}" ${q && !partMatches(p, q) ? 'hidden' : ''}><div class="prow">
      <span class="t grow tog" data-a="tog" title="${esc(p.name)}">${esc(p.name)}</span>
      <span class="icons"><button class="car" data-a="tog" title="Details">▸</button>
      <button class="pico ${p.visible ? '' : 'off'}" data-a="vis" title="${p.visible ? 'Hide' : 'Show'}">${p.visible ? PI.eye : PI.eyeOff}</button>
      <button class="pico" data-a="disp" title="Display style: ${PI.dispLabel[p.mode || '']}">${PI.disp(p.mode)}</button>
      <button class="pico" data-a="col" title="Colour"><span class="swc" style="background:#${p.color.getHexString()}"></span></button>
      <button class="pico ${p.transp ? 'act' : ''}" data-a="tr" title="Transparent: ${p.transp ? 'yes' : 'no'}">${PI.trans(p.transp)}</button></span></div>
      <div class="props"><div class="d"><span class="badge">${esc(PART_TYPES[inf.type])}${inf.guessed ? ' ?' : ''}</span>${extra ? ` ${extra}` : ''}<br>${fmtn(s.x)} × ${fmtn(s.y)} × ${fmtn(s.z)} mm · ${fmtn(p.an.volume, 1)} mm³ · ${p.an.faces.length} faces, ${p.an.edges.length} edges</div></div></div>`;
}
function partMatches(p, q) {
  const inf = partInfo(p);
  return [p.name, inf.group, PART_TYPES[inf.type], ...inf.sub, inf.meta.standard, inf.meta.material].some(x => x && String(x).toLowerCase().includes(q));
}
/** Groups for the current mode: a tree of {key, label, kids: Map, parts: []}. */
function partTree(mode) {
  const root = { key: '', label: '', kids: new Map(), parts: [] };
  for (const p of model.parts) {
    const inf = partInfo(p);
    const chain = mode === 'asm' ? inf.sub : mode === 'type' ? [inf.group] : [];
    let node = root;
    for (const name of chain) {
      const key = `${mode}:${node.key}/${name}`;
      if (!node.kids.has(name)) node.kids.set(name, { key, label: name, kids: new Map(), parts: [] });
      node = node.kids.get(name);
    }
    node.parts.push(p);
  }
  if (mode === 'type') root.kids = new Map([...root.kids].sort((a, b) => (a[1].parts[0] && partInfo(a[1].parts[0]).type === 'custom' ? -1 : 0) - (b[1].parts[0] && partInfo(b[1].parts[0]).type === 'custom' ? -1 : 0)));
  return root;
}
const groupParts = g => [...g.parts, ...[...g.kids.values()].flatMap(groupParts)];
function groupHtml(g, q) {
  const all = groupParts(g), shown = q ? all.filter(p => partMatches(p, q)) : all;
  const vis = all.some(p => p.visible), tr = all.length && all.every(p => p.transp);
  const open = q || !partGrpClosed.has(g.key);
  return `<div class="pgrp ${open ? 'open' : ''}" data-g="${esc(g.key)}" ${shown.length ? '' : 'hidden'}>
    <div class="item ghead"><div class="prow">
      <span class="t grow tog" data-a="gtog" title="${esc(g.label)}"><span class="gcar">▸</span> ${esc(g.label)} <span class="muted">${all.length}</span></span>
      <span class="icons"><button class="pico ${vis ? '' : 'off'}" data-a="gvis" title="${vis ? 'Hide the group' : 'Show the group'}">${vis ? PI.eye : PI.eyeOff}</button>
      <button class="pico ${tr ? 'act' : ''}" data-a="gtr" title="Group transparent: ${tr ? 'yes' : 'no'}">${PI.trans(tr)}</button></span></div></div>
    <div class="pgkids">${[...g.kids.values()].map(k => groupHtml(k, q)).join('')}${g.parts.map(p => partRowHtml(p, q)).join('')}</div></div>`;
}
function renderParts() {
  const el = $('partList');
  if (partOpenModel !== model.info?.path) { partOpenModel = model.info?.path; partOpen.clear(); if (model.parts.length === 1) partOpen.add(model.parts[0].name); }
  const q = $('partsFilter').value.trim().toLowerCase();
  const mode = groupMode();
  document.querySelectorAll('#partsGroup button').forEach(b => b.classList.toggle('on', b.dataset.m === mode));
  $('partsGroupRow').style.display = model.parts.length > 1 ? '' : 'none';
  const tree = partTree(mode);
  el.innerHTML = `<div class="ptree">${[...tree.kids.values()].map(g => groupHtml(g, q)).join('')}${tree.parts.map(p => partRowHtml(p, q)).join('')}</div>`;
  el.querySelectorAll('.item[data-i]').forEach(it => {
    const p = model.parts[+it.dataset.i];
    it.querySelector('[data-a=vis]').onclick = () => { p.visible = !p.visible; applyPartLook(p); updateSection(); renderParts(); };
    it.querySelector('[data-a=disp]').onclick = e => showDispMenu(p, e.currentTarget);
    it.querySelector('[data-a=col]').onclick = e => showColorMenu(p, e.currentTarget);
    it.querySelector('[data-a=tr]').onclick = () => { p.transp = !p.transp; applyPartLook(p); renderParts(); };
    it.querySelectorAll('[data-a=tog]').forEach(t => t.onclick = () => { if (it.classList.toggle('open')) partOpen.add(p.name); else partOpen.delete(p.name); });
  });
  const groups = new Map();
  (function index(g) { for (const k of g.kids.values()) { groups.set(k.key, k); index(k); } })(tree);
  el.querySelectorAll('.pgrp').forEach(gEl => {
    const g = groups.get(gEl.dataset.g), parts = groupParts(g), head = gEl.querySelector(':scope > .ghead');
    head.querySelector('[data-a=gtog]').onclick = () => { if (partGrpClosed.has(g.key)) partGrpClosed.delete(g.key); else partGrpClosed.add(g.key); gEl.classList.toggle('open'); fitPartRows(); };
    head.querySelector('[data-a=gvis]').onclick = () => { const v = !parts.some(p => p.visible); for (const p of parts) { p.visible = v; applyPartLook(p); } updateSection(); renderParts(); };
    head.querySelector('[data-a=gtr]').onclick = () => { const t = !parts.every(p => p.transp); for (const p of parts) { p.transp = t; applyPartLook(p); } renderParts(); };
  });
  fitPartRows();
  const size = model.bbox ? model.bbox.getSize(new THREE.Vector3()) : null;
  const faces = model.parts.reduce((s, p) => s + p.an.faces.length, 0), edges = model.parts.reduce((s, p) => s + p.an.edges.length, 0);
  $('modelInfo').innerHTML = size ? `Source: ${esc(model.source)}<br>Size: ${fmtn(size.x)} × ${fmtn(size.y)} × ${fmtn(size.z)} mm<br>Faces: ${faces}, edges: ${edges}<br><span class="mono">${esc(model.info?.path)}</span>` : '';
  renderMass();
}
// =============================================================== variants
// <base>@<label>.step files in one folder are design variants of one part (server: variants_of)
const variantBase = p => p.replace(/[^\\/]*$/, '') + p.replace(/^.*[\\/]/, '').replace(/\.(step|stp|stl)$/i, '').split('@')[0];
let variants = { items: [] };
async function loadVariants() {
  try { variants = await api('/api/variants'); } catch { variants = { items: [] }; }
  const items = variants.items || [];
  const cur = model.info?.path;
  $('variants').classList.toggle('on', items.length > 1);
  $('varSeg').innerHTML = items.map((v, i) => `<button data-i="${i}" class="${v.path === cur ? 'on' : ''}" title="${esc(v.name)}">${v.path === variants.chosen ? '★ ' : ''}${esc(v.label)}</button>`).join('');
  $('varSeg').querySelectorAll('button').forEach(b => b.onclick = () => openVariant(+b.dataset.i));
  const chosen = !!cur && cur === variants.chosen;
  $('varChoose').textContent = chosen ? '★ Chosen' : 'Choose';
  $('varChoose').disabled = chosen;
}
async function openVariant(i) {
  const v = variants.items?.[i];
  if (!v || v.path === model.info?.path) return;
  try { await api('/api/open', { path: v.path }); } catch (e) { toast('Could not open the variant: ' + e.message, true); }
}
function stepVariant(d) {
  const items = variants.items || [];
  if (items.length < 2) return;
  const i = items.findIndex(v => v.path === model.info?.path);
  openVariant((i + d + items.length) % items.length);
}
$('varChoose').onclick = async () => {
  try { await api('/api/variants/choose', { path: model.info.path }); toast('Choice added to your chat draft ✔'); loadVariants(); }
  catch (e) { toast('Could not save the choice: ' + e.message, true); }
};

// ================================================================= export
let exportQuality = 'normal';
async function loadExportFormats() {
  let fmts = [];
  try { fmts = await api('/api/export/formats'); } catch { /* server restarting */ }
  const isStl = !!model.info && !model.info.step;
  $('expList').classList.remove('muted');
  $('expList').innerHTML = fmts.map(f => {
    const ok = f.available && (!isStl || f.id === 'stl');
    const why = ok ? '' : isStl ? 'An STL model can only be saved as STL' : 'Needs CadQuery in the Python that runs the viewer';
    return `<button class="fmt" data-f="${f.id}" ${ok ? '' : 'disabled'} title="${why}"><b>${f.id.toUpperCase()}</b> ${esc(f.label)}<span class="muted">${f.ext}</span></button>`;
  }).join('') || '<div class="muted">The server did not answer.</div>';
  $('expList').querySelectorAll('button').forEach(b => b.onclick = () => runExport(b.dataset.f));
}
async function runExport(fmt) {
  if (!model.info) return toast('No model is loaded.', true);
  closeMenus();
  toast(`Choose where to save the ${fmt.toUpperCase()} file…`);
  try {
    const r = await api('/api/export', { format: fmt, quality: exportQuality });
    if (r.cancelled) toast('Export cancelled');
    else toast(`Saved ${r.path} (${Math.max(1, Math.round(r.size / 1024))} kB)`);
  } catch (e) { toast('Export failed: ' + e.message, true); }
}
document.querySelectorAll('#expQuality button').forEach(b => b.onclick = () => {
  exportQuality = b.dataset.q;
  document.querySelectorAll('#expQuality button').forEach(x => x.classList.toggle('on', x === b));
});

// =============================================================== versions
const ghost = { id: null, mesh: null, geo: null, volume: 0 };
let versions = [];
async function loadVersions() {
  try { versions = await api('/api/history'); } catch { versions = []; }
  renderVersions();
}
function renderVersions() {
  const el = $('versList');
  const cur = model.info?.version;
  el.classList.remove('muted');
  el.innerHTML = [...versions].reverse().map(v => `<div class="item ${v.id === ghost.id ? 'sel' : ''}"><div class="row" style="margin:0"><span class="t">${fmtTime(v.time)}</span>
    ${v.id === cur ? '<span class="badge done">current</span>' : ''}<span class="grow"></span>
    <button data-id="${v.id}" data-a="ghost">${v.id === ghost.id ? 'Ghost ✓' : 'Compare'}</button>
    ${v.id !== cur ? `<button data-id="${v.id}" data-a="restore">Restore</button>` : ''}</div>
    <div class="d">${esc(v.label)}</div>
    ${v.params?.length ? `<div class="d mono">${v.params.map(p => `${p.name}=${p.value}`).join('  ')}</div>` : ''}</div>`).join('') || '<div class="muted">Only one version of the model so far.</div>';
  el.querySelectorAll('button').forEach(b => b.onclick = async () => {
    const id = b.dataset.id;
    if (b.dataset.a === 'ghost') { if (ghost.id === id) clearGhost(); else loadGhost(id); }
    else if (b.dataset.a === 'restore') {
      if (b.dataset.confirm !== '1') { b.dataset.confirm = '1'; b.textContent = 'Sure?'; b.classList.add('danger'); setTimeout(() => { b.dataset.confirm = ''; b.textContent = 'Restore'; b.classList.remove('danger'); }, 3000); return; }
      try { await api('/api/history/restore', { id }); toast('Version restored'); } catch (e) { toast('Restore failed: ' + e.message, true); }
    }
  });
}
function clearGhost() {
  if (ghost.mesh) { scene.remove(ghost.mesh); ghost.geo.dispose(); ghost.mesh.material.dispose(); }
  if (ghost.removed) { scene.remove(ghost.removed); ghost.removed.geometry.dispose(); ghost.removed.material.dispose(); ghost.removed = null; }
  ghost.id = null; ghost.mesh = null; ghost.geo = null;
  for (const p of model.parts) resetVertexColors(p);
  $('ghostName').textContent = 'none'; $('diffStats').textContent = '';
  renderVersions();
}
async function loadGhost(id) {
  try {
    // STEP-only models keep no STL in their versions: mesh the STEP into one triangle soup
    const v0 = versions.find(x => x.id === id);
    const kind = v0?.hasStl === false ? 'step' : 'stl';
    const buf = await (await fetch(`/api/history/file?id=${encodeURIComponent(id)}&kind=${kind}`, { cache: 'no-store' })).arrayBuffer();
    let geo;
    if (kind === 'stl') geo = new STLLoader().parse(buf);
    else {
      const soup = [];
      for (const m of await parseStep(buf)) for (const k of m.index) soup.push(m.positions[k * 3], m.positions[k * 3 + 1], m.positions[k * 3 + 2]);
      geo = new THREE.BufferGeometry();
      geo.setAttribute('position', new THREE.Float32BufferAttribute(soup, 3));
      geo.computeVertexNormals();
    }
    if (ghost.mesh) { scene.remove(ghost.mesh); ghost.geo.dispose(); ghost.mesh.material.dispose(); }
    geo.setAttribute('color', new THREE.BufferAttribute(new Float32Array(geo.attributes.position.count * 3).fill(1), 3));
    ghost.geo = geo; ghost.id = id;
    ghost.mesh = new THREE.Mesh(geo, new THREE.MeshStandardMaterial({ color: 0x8fb4ff, vertexColors: true, transparent: true, opacity: +$('ghostOp').value, depthWrite: false, side: THREE.DoubleSide }));
    ghost.mesh.renderOrder = 3;
    scene.add(ghost.mesh);
    const v = versions.find(x => x.id === id);
    $('ghostName').textContent = v ? `${fmtTime(v.time)} · ${v.label}` : id;
    computeDiff();
    renderVersions();
  } catch (e) { toast('Could not load the version', true); }
}
function computeDiff() {
  if (!ghost.geo) return;
  const tol = Math.max(1e-4, +$('diffTol').value || 0.05);
  const on = $('diffOn').checked;
  const gB = new MeshBVH(ghost.geo.clone());
  const target = {};
  const tri = [new THREE.Vector3(), new THREE.Vector3(), new THREE.Vector3()];
  const cen = new THREE.Vector3();
  let changedArea = 0, totalArea = 0;
  for (const p of model.parts) {
    resetVertexColors(p); const col = p.geo.attributes.color.array;
    if (!p.bvh) p.bvh = new MeshBVH(p.bvhGeo);
    if (on) {
      const P = p.geo.attributes.position, I = p.an.index;
      for (let t = 0; t < p.an.nTri; t++) {
        for (let k = 0; k < 3; k++) tri[k].fromBufferAttribute(P, I[t * 3 + k]);
        cen.copy(tri[0]).add(tri[1]).add(tri[2]).multiplyScalar(1 / 3);
        const area = new THREE.Triangle(tri[0], tri[1], tri[2]).getArea();
        totalArea += area;
        gB.closestPointToPoint(cen, target);
        if (target.distance > tol) {
          changedArea += area;
          for (let k = 0; k < 3; k++) { const vi = I[t * 3 + k]; col[vi * 3] = 0.45; col[vi * 3 + 1] = 1.9; col[vi * 3 + 2] = 0.6; }
        }
      }
    }
    p.geo.attributes.color.needsUpdate = true;
  }
  const gp = ghost.geo.attributes.position;
  let gVol = 0;
  const removed = [];
  for (let t = 0; t < gp.count / 3; t++) {
    for (let k = 0; k < 3; k++) tri[k].fromBufferAttribute(gp, t * 3 + k);
    gVol += tri[0].dot(new THREE.Vector3().crossVectors(tri[1], tri[2])) / 6;
    if (!on) continue;
    cen.copy(tri[0]).add(tri[1]).add(tri[2]).multiplyScalar(1 / 3);
    let dmin = Infinity;
    for (const p of model.parts) { p.bvh.closestPointToPoint(cen, target); dmin = Math.min(dmin, target.distance); }
    if (dmin > tol) for (let k = 0; k < 3; k++) removed.push(tri[k].x, tri[k].y, tri[k].z);
  }
  // with change highlighting on: show only what was removed instead of the whole ghost
  if (ghost.removed) { scene.remove(ghost.removed); ghost.removed.geometry.dispose(); ghost.removed.material.dispose(); ghost.removed = null; }
  if (on) {
    const rg = new THREE.BufferGeometry(); rg.setAttribute('position', new THREE.Float32BufferAttribute(removed, 3)); rg.computeVertexNormals();
    ghost.removed = new THREE.Mesh(rg, new THREE.MeshBasicMaterial({ color: 0xef6b6b, transparent: true, opacity: 0.55, depthWrite: false, side: THREE.DoubleSide }));
    ghost.removed.renderOrder = 4;
    scene.add(ghost.removed);
  }
  ghost.mesh.visible = !on;
  ghost.geo.computeBoundingBox();
  const gs = ghost.geo.boundingBox.getSize(new THREE.Vector3()), cs = model.bbox.getSize(new THREE.Vector3());
  const cVol = model.parts.reduce((s, p) => s + p.an.volume, 0);
  gVol = Math.abs(gVol);
  const d = (a, b) => `${b - a >= 0 ? '+' : ''}${fmtn(b - a)}`;
  $('diffStats').innerHTML = `Size: ${fmtn(gs.x)}×${fmtn(gs.y)}×${fmtn(gs.z)} → ${fmtn(cs.x)}×${fmtn(cs.y)}×${fmtn(cs.z)} mm (Δ ${d(gs.x, cs.x)}, ${d(gs.y, cs.y)}, ${d(gs.z, cs.z)})<br>
    Volume: ${fmtn(gVol, 1)} → ${fmtn(cVol, 1)} mm³ (Δ ${d(gVol, cVol)} mm³, ${gVol ? `${((cVol - gVol) / gVol * 100).toFixed(2)} %` : ''})<br>
    ${on ? `Changed ${fmtn(changedArea, 1)} mm² of surface (${totalArea ? (changedArea / totalArea * 100).toFixed(1) : 0} %)` : ''}`;
}

// ========================================================== notes, pins
const pinGroup = new THREE.Group(); scene.add(pinGroup);
async function loadNotes(force) {
  try {
    const list = await api('/api/annotations');
    const sig = JSON.stringify(list.map(n => [n.id, n.status]));
    if (!force && sig === loadNotes.sig) return;
    loadNotes.sig = sig;
    notes = list;
  } catch { return; }
  renderNotes(); renderPins();
}
function noteAnchor(n) {
  if (n.anchor) return n.anchor;
  if (n.features?.length) return n.features[0].point || n.features[0].centroid;
  if (n.strokes?.length) return n.strokes[0].center;
  return model.center.toArray();
}
function renderPins() {
  for (const o of [...pinGroup.children]) { pinGroup.remove(o); o.element?.remove(); }
  if (!$('pinsOn').checked) return;
  for (const n of notes) {
    if (n.status === 'hidden') continue;
    if (noteFilter !== 'all' && n.status !== noteFilter) continue;
    const div = document.createElement('div');
    div.className = `pin ${n.status}${activePin === n.id ? ' active' : ''}`;
    div.innerHTML = `<span>${n.number}</span>`;
    div.title = n.comment;
    div.addEventListener('pointerdown', e => { e.stopPropagation(); showPinPop(n, div); });
    const o = new CSS2DObject(div);
    const partIdx = model.parts.findIndex(p => p.name === n.anchorPart);
    o.position.copy(new THREE.Vector3(...noteAnchor(n)).add(partIdx >= 0 ? partOffset(partIdx) : new THREE.Vector3()));
    o.center.set(0, 1);
    pinGroup.add(o);
  }
}
let noteOverlay = [];
function clearNoteOverlay() { for (const o of noteOverlay) dropObj(o); noteOverlay = []; }
function showNoteOverlay(n) {
  clearNoteOverlay();
  for (const s of n.strokes || []) {
    if (!s.points || s.points.length < 2) continue;
    const g = new LineGeometry(); g.setPositions(s.points.flat());
    const l = new Line2(g, lineMat({ color: new THREE.Color(s.color || '#ff3b30'), linewidth: 3, depthTest: false, dashed: true, dashSize: model.radius * 0.02, gapSize: model.radius * 0.015 }));
    l.computeLineDistances(); l.renderOrder = 13; scene.add(l); noteOverlay.push(l);
  }
  for (const f of n.features || []) {
    if (f.points?.length > 1) {
      const g = new LineGeometry(); g.setPositions(f.points.flat());
      const l = new Line2(g, lineMat({ color: 0xc9d66b, linewidth: 4, depthTest: false })); l.renderOrder = 13; scene.add(l); noteOverlay.push(l);
    } else if (f.point || f.centroid) {
      const g = new THREE.BufferGeometry(); g.setAttribute('position', new THREE.Float32BufferAttribute(f.point || f.centroid, 3));
      const pt = new THREE.Points(g, new THREE.PointsMaterial({ color: 0xc9d66b, size: 12, sizeAttenuation: false, depthTest: false })); pt.renderOrder = 13; scene.add(pt); noteOverlay.push(pt);
    }
  }
}
function showNote(n) {
  activePin = n.id; renderPins();
  if (n.camera?.position && n.camera?.target) {
    const up = n.camera.up ? new THREE.Vector3(...n.camera.up) : new THREE.Vector3(0, 0, 1);
    setOrtho(!!n.camera.ortho);
    flyTo(new THREE.Vector3(...n.camera.position), new THREE.Vector3(...n.camera.target), up);
  }
  showNoteOverlay(n);
}
async function setNoteStatus(n, status) {
  try { await api('/api/annotations/status', { id: n.id, status }); n.status = status; await loadNotes(true); } catch (e) { toast('Could not save the status', true); }
}
function showPinPop(n, anchorEl) {
  const pop = $('pinpop');
  pop.innerHTML = `<div class="row" style="margin:0"><b>#${n.number}</b><span class="badge ${n.status}">${n.status === 'done' ? 'done' : n.status === 'hidden' ? 'hidden' : 'open'}</span><span class="grow"></span><button class="icon" data-a="x">✕</button></div>
    <div class="c">${esc(n.comment)}</div>${n.statusNote ? `<div class="d muted">Claude: ${esc(n.statusNote)}</div>` : ''}
    <div class="d muted">${n.created ? fmtTime(n.created) : ''}</div>
    <div class="row"><button data-a="show">Show</button>${n.status !== 'done' ? '<button data-a="done">✓ Done</button>' : '<button data-a="open">Reopen</button>'}<button data-a="hide">Hide</button></div>`;
  const vr = view.getBoundingClientRect(), ar = anchorEl.getBoundingClientRect();
  pop.style.display = 'block';
  pop.style.left = Math.min(vr.width - 260, Math.max(6, ar.left - vr.left + 16)) + 'px';
  pop.style.top = Math.min(vr.height - pop.offsetHeight - 6, Math.max(6, ar.top - vr.top - 10)) + 'px';
  pop.querySelectorAll('button').forEach(b => b.onclick = () => {
    const a = b.dataset.a;
    if (a === 'x') { pop.style.display = 'none'; activePin = null; clearNoteOverlay(); renderPins(); }
    else if (a === 'show') showNote(n);
    else { setNoteStatus(n, a === 'done' ? 'done' : a === 'open' ? 'open' : 'hidden'); pop.style.display = 'none'; }
  });
}
function renderNotes() {
  const open = notes.filter(n => n.status === 'open').length;
  $('nNotes').textContent = open;
  const el = $('noteList');
  const list = notes.filter(n => noteFilter === 'all' || n.status === noteFilter);
  el.classList.toggle('muted', !list.length);
  el.innerHTML = list.map(n => `<div class="item ${activePin === n.id ? 'sel' : ''}"><div class="row" style="margin:0"><b>#${n.number}</b>
    <span class="badge ${n.status}">${n.status === 'done' ? 'done' : n.status === 'hidden' ? 'hidden' : 'open'}</span><span class="grow"></span><span class="muted">${n.created ? fmtTime(n.created) : ''}</span></div>
    <div>${esc(n.comment)}</div>
    <div class="d">${[n.markers?.length ? `${n.markers.length}× marker` : '', n.strokes?.length ? `${n.strokes.length}× drawing` : '', n.features?.length ? `${n.features.length}× feature` : '', n.measurements?.length ? `${n.measurements.length}× dimension` : '', n.section ? 'section' : ''].filter(Boolean).join(' · ')}</div>
    ${n.statusNote ? `<div class="d">Claude: ${esc(n.statusNote)}</div>` : ''}
    <div class="acts"><button data-id="${n.id}" data-a="show">Show</button>${n.status !== 'done' ? `<button data-id="${n.id}" data-a="done">✓ Done</button>` : `<button data-id="${n.id}" data-a="open">Reopen</button>`}
    ${n.status !== 'hidden' ? `<button data-id="${n.id}" data-a="hide">Hide</button>` : ''}</div></div>`).join('') || 'No notes match this filter.';
  el.querySelectorAll('button').forEach(b => b.onclick = () => {
    const n = notes.find(x => x.id === b.dataset.id);
    const a = b.dataset.a;
    if (a === 'show') showNote(n); else setNoteStatus(n, a === 'done' ? 'done' : a === 'open' ? 'open' : 'hidden');
  });
}

// "Delete all": notes go to inbox/_trash (kept, not erased); markers are dropped from the page (no trash).
// Confirmed by a second click on the button: the browser pane suppresses confirm(), which then returns false silently.
let clearArmed = null;
$('noteClear').onclick = async () => {
  const btn = $('noteClear');
  if (!notes.length && !markers.length) return toast('Nothing to delete.');
  if (!clearArmed) {
    btn.textContent = 'Click again to delete';
    clearArmed = setTimeout(() => { clearArmed = null; btn.textContent = 'Delete all'; }, 4000);
    return toast(`Click "Delete all" again to delete ${notes.length} note(s) and ${markers.length} marker(s). Notes go to inbox/_trash; markers cannot be restored.`);
  }
  clearTimeout(clearArmed); clearArmed = null; btn.textContent = 'Delete all';
  try {
    const r = notes.length ? await api('/api/annotations/clear', { model: model.info.path }) : { moved: 0 };
    markers = []; markDraft = null; markSel = -1; markEdit = false; storeMarkers(); drawMarkers(); hint();
    toast(`Moved ${r.moved} note(s) to inbox/_trash, markers removed.`);
    await loadNotes(true);
  } catch (e) { toast('Delete failed: ' + e.message, true); }
};

// ================================================================ markers
// Point / line / area markers with a note each, sent together as one batch. Points are home-pose model coordinates
// (part-local, like picks) and labels are CSS2DObjects, so the label renderer re-projects them every frame.
// Area = a few clicks on the model (closed by clicking the first point or Enter), not the pen: it stays 3D and draggable.
const markGroup = new THREE.Group(); scene.add(markGroup);
let markers = [];        // {type: point|line|area, pts: [{part: name, local, normal}], note}
let markDraft = null;    // the line / area being clicked
let markSel = -1, markEdit = false, markText = '';
const MARK_NEED = { point: 1, line: 2 };
const markKey = () => 'cadp.markers:' + (model.info?.path || '');
function storeMarkers() { try { localStorage.setItem(markKey(), JSON.stringify(markers)); } catch { /* storage blocked: markers last until reload */ } }
function loadMarkers() {
  try { markers = JSON.parse(localStorage.getItem(markKey()) || '[]'); } catch { markers = []; }
  markDraft = null; markSel = -1; markEdit = false; drawMarkers();
}
function markWorld(pt) {
  const i = model.parts.findIndex(p => p.name === pt.part);
  return new THREE.Vector3(...pt.local).add(i >= 0 ? partOffset(i) : new THREE.Vector3());
}
function markPick(ev) {
  const pk = pickAt(ev, 'auto');
  if (!pk) return null;
  // what lies under the click, in words ("Face #5: cylindrical face (hole) Ø5.5 mm…"): Claude reads it next to the screenshot
  const inf = entityInfo(pk);
  return { part: model.parts[pk.part].name, local: pk.local.map(r2), normal: (pk.normal || faceHit(ev)?.normal || [0, 0, 0]).map(r2), feature: `${inf.title}: ${inf.desc}` };
}
function markClick(ev) {
  const type = $('markType').value;
  if (markDraft?.type !== type) markDraft = { type, pts: [], note: '' };
  const first = markDraft.pts[0];
  if (type === 'area' && markDraft.pts.length >= 3) {
    const s = toScreen(markWorld(first), eventPx(ev)), px = eventPx(ev);
    if (Math.hypot(s.x - px.x, s.y - px.y) < 10) return finishMarkDraft();
  }
  const pt = markPick(ev);
  if (!pt) return toast('Click on the model.', true);
  markDraft.pts.push(pt);
  if (markDraft.pts.length === MARK_NEED[type]) return finishMarkDraft();
  drawMarkers(); hint();
}
function finishMarkDraft() {
  if (!markDraft) return;
  if (markDraft.type === 'area' && markDraft.pts.length < 3) return toast('An area needs at least 3 points.', true);
  markers.push(markDraft); markDraft = null; storeMarkers();
  openMarker(markers.length - 1);
}
function openMarker(i) { markSel = i; markEdit = true; markText = markers[i].note; drawMarkers(); hint(); }
function closeMarker(save) {
  if (save && markers[markSel]) { markers[markSel].note = markText.trim(); storeMarkers(); }
  markEdit = false; drawMarkers();
}
function deleteMarker(i) {
  markers.splice(i, 1); markSel = -1; markEdit = false; storeMarkers(); drawMarkers(); hint();
}
function markDrag(ev, i, k, el) {
  ev.stopPropagation(); ev.preventDefault();
  if (motion.def && !motionAtHome()) motionHome();   // anchors are home-pose coordinates
  const o = el.__obj, x0 = ev.clientX, y0 = ev.clientY;
  let moved = false;
  const move = e => {
    if (!moved && Math.hypot(e.clientX - x0, e.clientY - y0) < 4) return;
    moved = true;
    const pt = markPick(e);
    if (pt) o.position.copy(markWorld(pt));   // preview only; the anchor changes on drop
  };
  const up = e => {
    removeEventListener('pointermove', move); removeEventListener('pointerup', up);
    if (!moved) return k === 0 && !(markEdit && markSel === i) ? openMarker(i) : undefined;
    const pt = markPick(e);
    if (pt && markers[i]) { markers[i].pts[k] = pt; storeMarkers(); } else toast('Not over the model: the marker stays where it was.', true);
    drawMarkers();
  };
  addEventListener('pointermove', move); addEventListener('pointerup', up);
}
function drawMarkers() {
  for (const o of [...markGroup.children]) { o.element?.remove(); dropObj(o); }
  const btn = $('bMarkSend');
  btn.style.display = markers.length ? '' : 'none'; btn.textContent = `Send markers (${markers.length})`;
  if (!model.parts.length) return;
  [...markers, ...(markDraft ? [markDraft] : [])].forEach((m, i) => {
    const draft = m === markDraft, sel = i === markSel;
    const w = m.pts.map(markWorld);
    if (!w.length) return;
    const color = sel ? C_SEL : 0xe0b050;
    if (w.length > 1) {
      const loop = m.type === 'area' && !draft ? [...w, w[0]] : w;
      const g = new LineGeometry(); g.setPositions(loop.flatMap(v => v.toArray()));
      const l = new Line2(g, lineMat({ color, linewidth: 2.5, depthTest: false })); l.renderOrder = 13; markGroup.add(l);
    }
    const pg = new THREE.BufferGeometry(); pg.setAttribute('position', new THREE.Float32BufferAttribute(w.flatMap(v => v.toArray()), 3));
    const pts = new THREE.Points(pg, new THREE.PointsMaterial({ color, size: 8, sizeAttenuation: false, depthTest: false }));
    pts.renderOrder = 13; markGroup.add(pts);
    if (draft) return;
    w.forEach((v, k) => {
      const div = document.createElement('div');
      if (k === 0) {
        div.className = `lbl mark${sel ? ' sel' : ''}`;
        div.innerHTML = sel && markEdit
          ? `<b>${markerLabel(i)}</b> <input type="text" placeholder="Note for this marker" value="${esc(markText)}"><button class="mx" title="Delete the marker">×</button>`
          : `<b>${markerLabel(i)}</b>${m.note ? ' ' + esc(m.note) : ''}`;
        div.title = `${m.type} marker ${markerLabel(i)} · click = edit, drag = move${sel ? ', Delete = remove' : ''}`;
      } else { div.className = 'mh'; div.title = `${markerLabel(i)}, point ${k + 1}: drag to move`; }
      const o = new CSS2DObject(div); o.position.copy(v); if (k === 0) o.center.set(0, 1);
      div.__obj = o;
      div.addEventListener('pointerdown', e => { if (e.target.closest('input, .mx')) { e.stopPropagation(); return; } markDrag(e, i, k, div); });
      markGroup.add(o);
      const inp = div.querySelector('input');
      if (!inp) return;
      inp.oninput = () => { markText = inp.value; };
      inp.onkeydown = e => { e.stopPropagation(); if (e.key === 'Enter') closeMarker(true); else if (e.key === 'Escape') closeMarker(false); };
      div.querySelector('.mx').onclick = () => deleteMarker(i);
      setTimeout(() => { inp.focus(); inp.setSelectionRange(inp.value.length, inp.value.length); }, 0);
    });
  });
}

// ================================================================= paint
// Paint tool (B): click or drag over faces (or whole parts) to colour them; Alt+click picks a colour from the model.
// Painted faces sit on top of the part and STEP colours (resetVertexColors), are kept per model in this browser
// and go to Claude with a note, so colours can mark places ("the red faces get a 1 mm chamfer").
let paintColor = '#e0533d', painting = false, paintStroke = [], paintUndo = [];
const paintKey = () => 'cadp.paint:' + (model.info?.path || '');
function storePaint() {
  const out = {};
  for (const p of model.parts) {
    const e = {};
    if (!ownColor(p)) e.color = '#' + p.color.getHexString();
    if (p.paint.size) e.faces = Object.fromEntries(p.paint);
    if (Object.keys(e).length) out[p.name] = e;
  }
  try { localStorage.setItem(paintKey(), JSON.stringify(out)); } catch { /* per-viewer convenience */ }
}
function restorePaint() {
  let saved = {};
  try { saved = JSON.parse(localStorage.getItem(paintKey()) || '{}'); } catch { /* none */ }
  for (const p of model.parts) {
    const e = saved[p.name];
    if (!e) continue;
    if (e.color) p.color.set(e.color);
    if (e.faces) p.paint = new Map(Object.entries(e.faces).filter(([f]) => +f < p.an.faces.length).map(([f, c]) => [+f, c]));
    p.paintRev++; applyPartLook(p);
  }
  paintUndo = [];
}
function setPaintColor(hex) {
  paintColor = hex.toLowerCase();
  $('paintColor').value = paintColor;
  document.querySelectorAll('#paintSw .psw').forEach(b => b.classList.toggle('on', b.dataset.c === paintColor));
}
function paintAt(ev) {
  const h = faceHit(ev);
  if (!h) return;
  const p = model.parts[h.part];
  if ($('paintMode').value === 'part') {
    if ('#' + p.color.getHexString() === paintColor) return;
    paintStroke.push({ part: p.index, face: null, prev: p.color.clone() });
    p.color.set(paintColor); applyPartLook(p);
  } else {
    if (p.paint.get(h.faceId) === paintColor) return;
    paintStroke.push({ part: p.index, face: h.faceId, prev: p.paint.get(h.faceId) ?? null });
    p.paint.set(h.faceId, paintColor); p.paintRev++; applyPartLook(p);
  }
}
function endPaint() {
  if (!painting) return;
  painting = false;
  if (paintStroke.length) { paintUndo.push(paintStroke); storePaint(); if (paintStroke.some(x => x.face === null)) renderParts(); }
  paintStroke = [];
}
function undoPaint() {
  const st = paintUndo.pop();
  if (!st) return toast('Nothing to undo.');
  for (const x of [...st].reverse()) {
    const p = model.parts[x.part];
    if (x.face === null) p.color.copy(x.prev);
    else { if (x.prev) p.paint.set(x.face, x.prev); else p.paint.delete(x.face); p.paintRev++; }
    applyPartLook(p);
  }
  storePaint(); renderParts();
}
function pickPaintColor(ev) {
  const h = faceHit(ev);
  if (!h) return;
  const p = model.parts[h.part];
  const hex = p.paint.get(h.faceId) ?? (p.vtint
    ? '#' + new THREE.Color().fromArray(p.geo.attributes.color.array, h.vertex * 3).getHexString()
    : '#' + p.color.getHexString());
  setPaintColor(hex); toast(`Colour ${hex} picked`);
}
function clearPaint() {
  for (const p of model.parts) { p.paint.clear(); p.paintRev++; p.color.copy(p.defaultColor); applyPartLook(p); }
  paintUndo = []; storePaint(); renderParts();
}
// colour names for the note, so "the purple face" in the request finds #7c5cd6 (the nearest named colour for custom ones)
const COLOR_NAMES = { '#d9d4cc': 'light grey', '#9a9a9a': 'grey', '#3d3d3d': 'dark grey', '#e0533d': 'red', '#f0a23b': 'orange', '#f2d64b': 'yellow', '#7bc043': 'green', '#2fa39a': 'teal', '#3b82f6': 'blue', '#7c5cd6': 'purple', '#d6469f': 'pink', '#b08968': 'brown', '#ffffff': 'white', '#000000': 'black', '#4682b4': 'steel blue' };
function colorName(hex) {
  const c = new THREE.Color(hex);
  let best = '', bd = Infinity;
  for (const [h, n] of Object.entries(COLOR_NAMES)) { const k = new THREE.Color(h), d = (k.r - c.r) ** 2 + (k.g - c.g) ** 2 + (k.b - c.b) ** 2; if (d < bd) { bd = d; best = n; } }
  return best;
}
/** Painted faces and repainted parts, for the note to Claude. */
function paintData() {
  const out = [];
  for (const p of model.parts) {
    if (!ownColor(p)) out.push({ part: p.name, face: null, color: '#' + p.color.getHexString(), name: colorName('#' + p.color.getHexString()), description: 'whole part' });
    for (const [f, c] of p.paint) {
      const fa = p.an.faces[f];
      if (fa) out.push({ part: p.name, face: f, color: c, name: colorName(c), description: describeFace(fa), centroid: fa.centroid.map(r2) });
    }
  }
  return out;
}
$('paintSw').innerHTML = SWATCHES.map(c => `<button class="psw" data-c="${c}" style="background:${c}" title="${c}"></button>`).join('');
document.querySelectorAll('#paintSw .psw').forEach(b => b.onclick = () => { setPaintColor(b.dataset.c); setTool('paint'); });
$('paintColor').oninput = e => setPaintColor(e.target.value);
$('paintMode').onchange = () => setTool('paint');
$('paintClear').onclick = () => { if (confirm('Remove all paint and part colours of this model?')) clearPaint(); };
$('tPaint').onclick = () => setTool('paint');
setPaintColor(paintColor);

// ============================================================= parameters
let params = [], paramEdits = {}, paramBusy = false, liveT = null, paramScript = '', paramT = null;
let paramFilter = 'all';
const REL_G = '@@related';
let relState = null;   // {label, list: [{name, score, why}]} from the context menu
const relWhy = p => { const r = relState?.list.find(x => x.name === p.name); return r ? `<span class="why">◎ ${esc(r.why)}</span>` : ''; };
const paramGrpClosed = new Set();
// per script, in this browser: the values first seen (to reset to) and the pinned parameters
const pKey = k => `cadp.param${k}:${paramScript}`;
const pLoad = (k, d) => { try { return JSON.parse(localStorage.getItem(pKey(k)) || 'null') ?? d; } catch { return d; } };
const pSave = (k, v) => { try { localStorage.setItem(pKey(k), JSON.stringify(v)); } catch { /* per-viewer convenience */ } };
let paramOrig = {}, paramPins = new Set();
async function loadParams() {
  let res;
  try { res = await api('/api/params'); } catch { res = { params: [] }; }
  if (res.script !== paramScript) relState = null;
  params = res.params || []; paramEdits = {};
  paramScript = res.script || '';
  paramOrig = pLoad('Orig', {}); paramPins = new Set(pLoad('Pins', []));
  let added = false;
  for (const p of params) if (!(p.name in paramOrig)) { paramOrig[p.name] = p.value; added = true; }
  if (added) pSave('Orig', paramOrig);
  $('paramHead').innerHTML = res.script
    ? `Script: <span class="mono">${esc(res.script.split(/[\\/]/).pop())}</span> · ${params.length} parameter${params.length === 1 ? '' : 's'}${res.error ? `<div style="color:var(--bad)">${esc(res.error)}</div>` : ''}`
    : 'No parametric script found for this model (a .py file in the same folder that mentions the model file name).';
  $('paramTools').style.display = params.length > 3 ? '' : 'none';
  renderParams(); renderSweep();
}
function paramStep(p) {
  if (p.type === 'int') return 1;
  const v = Math.abs(p.value);
  return v >= 100 ? 1 : v >= 10 ? 0.1 : v >= 1 ? 0.05 : 0.01;
}
const paramCur = p => (p.name in paramEdits ? paramEdits[p.name] : p.value);
const paramChanged = p => paramCur(p) !== (paramOrig[p.name] ?? p.value) || (p.name in paramEdits && paramEdits[p.name] !== p.value);
function paramHtml(p) {
  const v = paramCur(p), pending = p.name in paramEdits && paramEdits[p.name] !== p.value;
  const orig = paramOrig[p.name], off = orig !== undefined && v !== orig;
  const tools = `<span class="ptools"><button class="pico ${paramPins.has(p.name) ? 'act' : ''}" data-pin="${p.name}" title="${paramPins.has(p.name) ? 'Unpin' : 'Pin to the top'}">${paramPins.has(p.name) ? '★' : '☆'}</button>${off ? `<button class="pico" data-reset="${p.name}" title="Back to the original value ${esc(String(orig))}">↺</button>` : ''}</span>`;
  const cls = `param ${pending ? 'changed' : ''} ${off ? 'off' : ''}`;
  if (p.type === 'bool') return `<div class="${cls}" data-p="${p.name}"><span class="nm">${esc(p.name)}${tools}</span><input type="checkbox" data-n="${p.name}" ${v ? 'checked' : ''}><span class="cm">${esc(p.comment)}</span>${relWhy(p)}</div>`;
  const step = paramStep(p);
  let min, max;
  if (p.min !== undefined) { min = p.min; max = p.max; }
  else {
    const span = Math.max(Math.abs(p.value) * 2, step * 20);
    min = p.value >= 0 ? 0 : p.value - span / 2; max = p.value >= 0 ? Math.max(span, p.value * 2) : p.value + span / 2;
  }
  const out = p.min !== undefined && (v < p.min || v > p.max);
  return `<div class="${cls}" data-p="${p.name}"><span class="nm">${esc(p.name)}${tools}</span>
      <span><input type="number" data-n="${p.name}" value="${v}" step="${step}" ${p.min !== undefined ? `min="${p.min}" max="${p.max}"` : ''} ${out ? 'class="bad"' : ''}> <span class="muted">${esc(p.unit)}</span></span>
      <input type="range" data-r="${p.name}" min="${min}" max="${max}" step="${step}" value="${v}">
      <span class="cm">${esc(p.comment)}</span>${relWhy(p)}</div>`;
}
function renderParams() {
  const el = $('paramList');
  const q = $('paramSearch').value.trim().toLowerCase();
  document.querySelectorAll('#paramFilter button').forEach(b => b.classList.toggle('on', b.dataset.f === paramFilter));
  const shown = params.filter(p => (!q || [p.name, p.comment, p.group, p.unit].some(x => x && x.toLowerCase().includes(q)))
    && (paramFilter === 'all' || (paramFilter === 'changed' ? paramChanged(p) : paramPins.has(p.name))));
  // pinned first, then the groups in script order (from "# --- Name ---" comment lines)
  const groups = new Map();
  const pinned = paramFilter !== 'pinned' ? shown.filter(p => paramPins.has(p.name)) : [];
  if (pinned.length) groups.set('★ Pinned', pinned);
  // related to the right-clicked place (context menu): their own group at the top, best first
  const rel = relState ? relState.list.map(r => shown.find(p => p.name === r.name)).filter(p => p && !pinned.includes(p)) : [];
  if (rel.length) groups.set(REL_G, rel);
  for (const p of shown) { if (pinned.includes(p) || rel.includes(p)) continue; const g = p.group || ''; if (!groups.has(g)) groups.set(g, []); groups.get(g).push(p); }
  const many = groups.size > 1 || [...groups.keys()].some(Boolean);
  el.innerHTML = [...groups].map(([g, ps]) => {
    const open = q || !paramGrpClosed.has(g);
    const head = g === REL_G
      ? `<div class="pgh rel ${open ? 'open' : ''}" data-g="${esc(g)}" title="Found in the script: where the part is built and what feeds it; values equal to the clicked size"><span class="gcar">▸</span> ◎ Related: ${esc(relState.label)} <span class="muted">${ps.length}</span><button class="relx" data-a="relx" title="Back to the normal order" aria-label="Clear related">✕</button></div>`
      : many ? `<div class="pgh ${open ? 'open' : ''}" data-g="${esc(g)}"><span class="gcar">▸</span> ${esc(g || 'Other')} <span class="muted">${ps.length}</span></div>` : '';
    return head + (open || !many ? ps.map(paramHtml).join('') : '');
  }).join('') || `<div class="muted" style="padding:8px 0">${params.length ? 'No parameter matches.' : ''}</div>`;
  el.querySelector('[data-a=relx]')?.addEventListener('click', e => { e.stopPropagation(); relState = null; renderParams(); });
  el.querySelectorAll('.pgh').forEach(h => h.onclick = () => { const g = h.dataset.g; if (paramGrpClosed.has(g)) paramGrpClosed.delete(g); else paramGrpClosed.add(g); renderParams(); });
  el.querySelectorAll('[data-pin]').forEach(b => b.onclick = () => { const n = b.dataset.pin; if (paramPins.has(n)) paramPins.delete(n); else paramPins.add(n); pSave('Pins', [...paramPins]); renderParams(); });
  el.querySelectorAll('[data-reset]').forEach(b => b.onclick = () => {
    const p = params.find(x => x.name === b.dataset.reset), v = paramOrig[p.name];
    if (v === p.value) delete paramEdits[p.name]; else paramEdits[p.name] = v;
    renderParams(); updateParamButtons();
    if ($('paramLive').checked) { clearTimeout(liveT); liveT = setTimeout(applyParams, 800); }
  });
  el.querySelectorAll('input[data-n]').forEach(inp => {
    const name = inp.dataset.n, p = params.find(x => x.name === name);
    inp.onchange = inp.oninput = () => {
      const val = p.type === 'bool' ? inp.checked : (p.type === 'int' ? Math.round(+inp.value) : +inp.value);
      if (p.type !== 'bool' && !isFinite(val)) return;
      setEdit(p, val, inp);
    };
  });
  el.querySelectorAll('input[data-r]').forEach(r => {
    const p = params.find(x => x.name === r.dataset.r);
    r.oninput = () => { const val = p.type === 'int' ? Math.round(+r.value) : +r.value; const num = el.querySelector(`input[data-n="${p.name}"]`); num.value = val; setEdit(p, val, r); };
  });
  updateParamButtons();
}
function updateParamButtons() {
  const dirty = Object.keys(paramEdits).some(k => paramEdits[k] !== params.find(p => p.name === k)?.value);
  $('paramApply').disabled = !dirty || paramBusy;
  $('paramRevert').disabled = !dirty || paramBusy;
}
function setEdit(p, val, srcEl) {
  paramEdits[p.name] = val;
  srcEl.closest('.param').classList.toggle('changed', val !== p.value);
  const num = srcEl.closest('.param').querySelector('input[type=number]');
  if (num && p.min !== undefined) num.classList.toggle('bad', val < p.min || val > p.max);
  updateParamButtons();
  if ($('paramLive').checked) { clearTimeout(liveT); liveT = setTimeout(applyParams, 800); }
}
async function applyParams() {
  if (paramBusy) { clearTimeout(liveT); liveT = setTimeout(applyParams, 600); return; }
  const values = {};
  for (const [k, v] of Object.entries(paramEdits)) if (v !== params.find(p => p.name === k)?.value) values[k] = v;
  if (!Object.keys(values).length) return;
  paramBusy = true; renderParamsState('Rebuilding the model…');
  $('paramApply').disabled = true;
  try {
    const r = await api('/api/params', { values });
    const log = $('paramLog');
    log.style.display = (r.stderr || !r.ok) ? 'block' : 'none';
    log.classList.toggle('err', !r.ok);
    log.textContent = (r.stdout || '') + (r.stderr ? '\n' + r.stderr : '');
    if (r.ok && r.changes?.length) { paramT = { t0: performance.now(), script: r.ms, warm: r.warm, changes: r.changes }; checkLatest(); }
    renderParamsState(r.ok ? `Script ${(r.ms / 1000).toFixed(2)} s${r.warm === false ? ' (cold start)' : ''}, loading the model…: ${r.changes.join(', ')}` : `The script failed (exit code ${r.code}). The new values stay in the file; use Restore in the Versions tab to undo them.`, !r.ok);
  } catch (e) {
    renderParamsState('Error: ' + e.message, true);
  } finally {
    paramBusy = false;
    const keepEdits = { ...paramEdits };
    await loadParams();
    for (const [k, v] of Object.entries(keepEdits)) if (params.find(p => p.name === k)?.value !== v) paramEdits[k] = v;
    renderParams();
  }
}
function renderParamsState(t, err) { const s = $('paramState'); s.textContent = t; s.style.color = err ? 'var(--bad)' : ''; }

// =================================================================== note
let modalOpts = {};
function sampled(points, max) { const step = Math.max(1, Math.ceil(points.length / max)); return points.filter((_, i) => i % step === 0 || i === points.length - 1).map(p => p.map(r2)); }
function strokeData() {
  const camDir = controls.target.clone().sub(camera.position).normalize();
  const plane = new THREE.Plane().setFromNormalAndCoplanarPoint(camDir, controls.target);
  return strokes.map((s, i) => {
    // off-model points: where the screen ray meets the plane through the view centre
    const pts = s.hits.length ? s.hits.map(h => h.local) : s.misses.map(([x, y]) => {
      raycaster.setFromCamera(ndc.set(x * 2 - 1, -y * 2 + 1), camera);
      const p = raycaster.ray.intersectPlane(plane, new THREE.Vector3());
      return p ? [p.x, p.y, p.z] : null;
    }).filter(Boolean);
    if (!pts.length) pts.push(arr(controls.target));
    const b = new THREE.Box3().setFromPoints(pts.map(p => new THREE.Vector3(...p)));
    const n = s.hits.reduce((a, h) => [a[0] + h.normal[0], a[1] + h.normal[1], a[2] + h.normal[2]], [0, 0, 0]);
    const counts = {};
    for (const h of s.hits) counts[h.part] = (counts[h.part] || 0) + 1;
    const part = Object.keys(counts).sort((a, b) => counts[b] - counts[a])[0];
    return {
      index: i + 1, color: s.color, part: part !== undefined ? model.parts[part].name : null, pointCount: pts.length,
      onModel: r2(s.hits.length / s.screen.length),
      center: arr(b.getCenter(new THREE.Vector3())), bboxMin: arr(b.min), bboxMax: arr(b.max),
      avgNormal: (s.hits.length ? v3.norm(n) : arr(camDir.clone().negate())).map(r2), points: sampled(pts, 40),
    };
  });
}
function featureData() {
  return selection.map((s, i) => {
    const p = model.parts[s.part];
    const inf = entityInfo(s);
    const f = { index: i + 1, type: s.type, part: p.name, title: inf.title, description: inf.desc };
    if (s.type === 'face') {
      const fa = p.an.faces[s.id];
      Object.assign(f, { surface: fa.type, centroid: fa.centroid.map(r2), normal: fa.type === 'plane' ? fa.normal.map(r2) : undefined, area: r2(fa.area), point: s.local.map(r2) });
      if (fa.type === 'cylinder') Object.assign(f, { axis: fa.axis.map(r2), center: fa.center.map(r2), diameter: r2(2 * fa.radius), inner: fa.inner });
      const pts = [], stride = Math.max(1, Math.floor(fa.tris.length / 6));
      for (let i = 0; i < fa.tris.length && pts.length < 6; i += stride) {
        const t = fa.tris[i];
        const c = [0, 1, 2].map(a => r2([0, 1, 2].reduce((s, k) => s + p.geo.attributes.position.array[p.an.index[t * 3 + k] * 3 + a], 0) / 3));
        pts.push(c);
      }
      f.samples = pts;
    } else if (s.type === 'edge') {
      const e = p.an.edges[s.id];
      Object.assign(f, { curve: e.type, length: r2(e.length), points: sampled(e.points, 24) });
      if (e.center) Object.assign(f, { center: e.center.map(r2), diameter: r2(2 * e.radius), normal: e.normal.map(r2) });
    } else if (s.type === 'vertex') f.point = p.an.verts[s.id].p.map(r2);
    else if (s.type === 'part') { const b = p.bbox; f.bboxMin = arr(b.min); f.bboxMax = arr(b.max); f.volume = r2(p.an.volume); }
    return f;
  });
}
function measureData(onlyId) {
  return measurements.filter(m => onlyId === undefined || m.id === onlyId).map(m => ({ index: m.id, kind: m.kind, value: r2(m.value), text: m.text, refs: m.refs, from: m.a.p.map(r2), to: m.b.p.map(r2), comp: m.comp?.map(r2) }));
}
function openNote(opts = {}) {
  if (!model.info) return toast('No model is loaded.', true);
  modalOpts = opts;
  if (markEdit) closeMarker(true);
  // the record for Claude: the view with the drawing, markers, dimensions and numbered selection on it
  $('mShot').src = composeShot().toDataURL('image/png');
  const rows = [];
  const only = opts.measurementOnly;
  rows.push(['strokes', strokes.length, `Pen drawing (${strokes.length})`, strokes.length > 0 && only === undefined]);
  rows.push(['features', selection.length, `Selected features (${selection.length})`, selection.length > 0 && only === undefined, selection.map(s => entityInfo(s).title).join(', ')]);
  rows.push(['meas', only !== undefined ? 1 : measurements.length, only !== undefined ? `Dimension ${only}` : `Measurements (${measurements.length})`, only !== undefined || measurements.length > 0, only !== undefined ? measurements.find(m => m.id === only)?.text : measurements.map(m => `${m.id}: ${m.text}`).join(', ')]);
  const pd = paintData();
  rows.push(['paint', pd.length, `Painted faces / parts (${pd.length})`, pd.length > 0 && only === undefined, [...new Set(pd.map(x => x.color))].join(' ')]);
  rows.push(['markers', markers.length, `Markers (${markers.length})`, markers.length > 0 && only === undefined, markers.map((m, i) => `${markerLabel(i)}: ${m.note || '(no note)'}`).join(' · ')]);
  rows.push(['section', section.on ? 1 : 0, 'Current section', section.on, section.on ? $('secInfo').textContent : '']);
  $('mInc').innerHTML = rows.filter(r => r[1] > 0).map(r => `<label><input type="checkbox" data-k="${r[0]}" ${r[3] ? 'checked' : ''}><span>${esc(r[2])}${r[4] ? `<div class="d">${esc(r[4])}</div>` : ''}</span></label>`).join('')
    || '<div class="muted">No drawing or selection: the note will apply to the whole model.</div>';
  if (only !== undefined) { const m = measurements.find(x => x.id === only); $('mText').value = m ? `Dimension ${m.id} (${m.text}) should be ` : ''; }
  $('modal').classList.add('open');
  setTimeout(() => { const t = $('mText'); t.focus(); t.setSelectionRange(t.value.length, t.value.length); }, 0);
}
function closeNote() { $('modal').classList.remove('open'); }
async function sendNote() {
  const comment = $('mText').value.trim();
  const inc = k => !!$('mInc').querySelector(`input[data-k="${k}"]`)?.checked;
  const markD = inc('markers') ? markerRows(markers) : [];
  if (!comment && !markD.some(m => m.note) && !(inc('paint') && paintData().length)) { $('mText').focus(); return toast('Write a request or comment.', true); }
  const strokesD = inc('strokes') ? strokeData() : [];
  const featuresD = inc('features') ? featureData() : [];
  const measD = inc('meas') ? measureData(modalOpts.measurementOnly) : [];
  let anchor = null, anchorPart = null;
  if (featuresD.length) { anchor = featuresD[0].point || featuresD[0].centroid || featuresD[0].points?.[0]; anchorPart = featuresD[0].part; }
  else if (strokesD.length) { anchor = strokesD[0].center; anchorPart = strokesD[0].part; }
  else if (measD.length) { anchor = measD[0].from; }
  else if (markD.length) { anchor = markD[0].points[0]; anchorPart = markD[0].part; }
  const camDir = controls.target.clone().sub(camera.position).normalize();
  const payload = {
    model: model.info.path, name: model.info.name, step: model.info.step || null, comment,
    strokes: strokesD, features: featuresD, measurements: measD, markers: markD, paint: inc('paint') ? paintData() : [],
    section: !(inc('section') && section.on) ? null
      : section.mode === 'box' ? { mode: 'box', min: arr(section.box.min), max: arr(section.box.max), info: $('secInfo').textContent }
      : { mode: section.mode, normal: arr(section.plane.normal.clone().multiplyScalar(section.flip ? -1 : 1)), offset: r2(section.d), flip: section.flip, info: $('secInfo').textContent,
        ...(section.extra.some(e => e.on) ? { extraPlanes: section.extra.filter(e => e.on).map(e => ({ normal: arr(e.plane.normal), constant: r2(e.plane.constant) })) } : {}) },
    camera: { position: arr(camera.position), target: arr(controls.target), up: arr(camera.up), viewDir: arr(camDir), ortho: camera === ortho },
    explode: r2(explode), anchor, anchorPart, parts: model.parts.map(p => p.name), source: model.source,
    nearParts: nearPartNames([...featuresD.map(f => f.point || f.centroid), ...strokesD.flatMap(s => s.points || [s.center]), ...markD.flatMap(m => m.points || []), ...measD.flatMap(m => [m.from, m.to]), anchor]),
    image: appSettings['note.screenshot'] === false ? '' : $('mShot').src,
  };
  $('mSend').disabled = true;
  try {
    await api('/api/annotate', payload);
    closeNote(); $('mText').value = '';
    if (strokesD.length) clearStrokes();
    if (featuresD.length) clearSelection();
    if (markD.length) { markers = []; markSel = -1; markEdit = false; storeMarkers(); drawMarkers(); hint(); }
    toast('Sent to Claude ✔');
    loadNotes(true);
  } catch (e) { toast('Saving the note failed: ' + e.message, true); }
  finally { $('mSend').disabled = false; }
}

// ================================================================= input
function setTool(t) {
  // picks, strokes and measurements are stored in home-pose model coordinates
  if (t !== 'select' && motion.def && !motionAtHome()) { motionHome(); toast('Motion returned to the home pose'); }
  tool = t;
  for (const [id, name] of [['tSelect', 'select'], ['tPen', 'pen'], ['tMeasure', 'measure'], ['tMark', 'mark'], ['tPaint', 'paint']]) $(id).classList.toggle('on', t === name);
  for (const [id, name] of [['ctxSelect', 'select'], ['ctxPen', 'pen'], ['ctxMeasure', 'measure'], ['ctxMark', 'mark'], ['ctxPaint', 'paint']]) $(id).classList.toggle('on', t === name);
  lockView();
  renderer.domElement.style.cursor = t === 'pen' || t === 'mark' || t === 'paint' ? 'crosshair' : 'default';
  if (markDraft) { markDraft = null; drawMarkers(); }
  for (const mp of measPicks) dropObj(mp.obj);
  measPicks = []; clearMeasTemp();
  setHover(null);
  hint();
}
function hint() {
  const h = {
    select: 'Click = select · Shift+click = add · Esc = clear · middle drag = rotate (pivot under cursor) · right drag or Ctrl + middle drag = pan · wheel = zoom · ? = all shortcuts',
    pen: strokes.length ? 'Draw over the view · view locked by the drawing · Enter = write the note · Ctrl+Z = undo'
      : 'Left = draw over the view · middle = rotate · right = pan · wheel = zoom (locked once you draw)',
    mark: markDraft ? (markDraft.type === 'area' ? `Click more points · click the first point or Enter = close the area (${markDraft.pts.length} so far) · Esc = cancel` : 'Click point B · Esc = cancel')
      : 'Click the model = new marker (type in Options) · click a label = edit · drag = move · Delete = remove',
    paint: 'Click or drag over faces to paint (Face / Part in Options) · Alt+click = pick a colour · Ctrl+Z = undo · middle = rotate',
    measure: measPicks.length ? ($('measMode').value === 'min' ? 'Click the second part · Esc = cancel' : $('measMode').value === 'pp' ? 'Click the second point (snaps to edge middles and circle centres) · Esc = cancel' : 'Pick the second feature · Esc = cancel') : ({ auto: 'Click a hole (Ø) or the first of two features', pp: 'Click the first point (snaps to vertices/edges)', angle: 'Click the first plane or edge', dia: 'Click a hole, pin or circular edge', one: 'Click a face (area), edge (length) or vertex (coordinates)', min: 'Click the first part' })[$('measMode').value],
  }[tool];
  $('hint').textContent = h + (strokes.length && tool !== 'pen' ? ' · view locked by the drawing: send the note or clear it 🗑' : '');
}
$('tSelect').onclick = () => setTool('select');
$('tPen').onclick = () => setTool('pen');
$('tMeasure').onclick = () => setTool('measure');
$('tMark').onclick = () => setTool('mark');
$('markType').onchange = () => setTool('mark');
$('bMarkSend').onclick = () => openNote();
$('measMode').onchange = () => { setTool('measure'); };
$('selFilter').onchange = () => setTool('select');
document.querySelectorAll('.sw').forEach(b => b.onclick = () => { document.querySelectorAll('.sw').forEach(x => x.classList.remove('on')); b.classList.add('on'); penColor = b.dataset.c; setTool('pen'); });

let downAt = null, rightDownAt = null, midDownAt = null, lastPointer = null, cubeDown = null;
const cvs = renderer.domElement;
// middle drag rotates, right drag and Ctrl + middle drag pan. Set before TrackballControls reads the press.
cvs.addEventListener('pointerdown', ev => { controls.mouseButtons = ev.button === 1 && ev.ctrlKey ? { LEFT: -1, MIDDLE: -1, RIGHT: 1 } : ev.button === 2 ? { LEFT: -1, MIDDLE: -1, RIGHT: 2 } : { LEFT: 1, MIDDLE: -1, RIGHT: -1 }; }, true);
// middle-drag pivot: TrackballControls rotates about controls.target; after each rotation step shift camera and target
// by (I - q)(pivot - target), which turns that into the same rotation about the point under the cursor (no jump).
// No model under the cursor: pivot stays null and the rotation is about the target, the screen-centre point at the current distance.
let pivot = null;
const pivotQ = new THREE.Quaternion();
controls.addEventListener('change', () => {
  if (!pivot) return;
  const q = camera.quaternion.clone().multiply(pivotQ.invert());
  pivotQ.copy(camera.quaternion);
  const d = pivot.clone().sub(controls.target), off = d.clone().sub(d.clone().applyQuaternion(q));
  camera.position.add(off); controls.target.add(off);
});
cvs.addEventListener('pointerdown', ev => {
  $('pinpop').style.display = 'none';
  closeMenus();
  if (ev.button === 2) rightDownAt = { x: ev.clientX, y: ev.clientY };
  if (ev.button === 1) midDownAt = { x: ev.clientX, y: ev.clientY };
  // pivot under the cursor but at the target depth: a pivot on the grabbed surface freezes that point on screen, which feels heavy
  if (ev.button === 1 && !ev.ctrlKey && controls.enabled) { const h = faceHit(ev)?.world, v = camera.getWorldDirection(new THREE.Vector3()); pivot = h ? h.addScaledVector(v, -v.dot(h.clone().sub(controls.target))) : null; pivotQ.copy(camera.quaternion); }
  if (ev.button !== 0) return;
  downAt = { x: ev.clientX, y: ev.clientY };
  cubeDown = cubeDir(ev);
  if (cubeDown) return;
  if (tool === 'paint') {
    if (ev.altKey) { pickPaintColor(ev); return; }
    painting = true; paintStroke = []; paintAt(ev);
    try { cvs.setPointerCapture(ev.pointerId); } catch { /* synthetic pointer */ }
    return;
  }
  if (tool === 'pen') {
    active = { color: penColor, screen: [], hits: [], misses: [] };
    penPoint(active, ev);
    strokes.push(active); drawInk(); lockView(); renderStrokeInfo();
    cvs.setPointerCapture(ev.pointerId);
  }
});
let moveRaf = 0, lastMove = null;
cvs.addEventListener('pointermove', ev => {
  lastPointer = ev;
  if (painting) { if (ev.buttons & 1) paintAt(ev); else endPaint(); return; }
  if (active) {
    const px = eventPx(ev), last = active.screen[active.screen.length - 1];
    if (Math.hypot(px.x - last[0], px.y - last[1]) < 3) return;
    penPoint(active, ev); drawInk();
    return;
  }
  lastMove = ev;
  if (moveRaf) return;
  moveRaf = requestAnimationFrame(() => {
    moveRaf = 0;
    const e = lastMove;
    if (!model.parts.length || e.buttons) { return; }
    const cd = cubeDir(e);
    cubeHl.visible = !!cd;
    if (cd) { cubeHl.position.set(...cd).multiplyScalar(0.5); cvs.style.cursor = 'pointer'; setHover(null); $('hover').textContent = 'View cube: click a face, edge or corner'; return; }
    cvs.style.cursor = tool === 'pen' || tool === 'mark' || tool === 'paint' ? 'crosshair' : 'default';
    const filter = tool === 'select' ? $('selFilter').value : 'auto';
    const pk = (tool === 'select' || tool === 'measure' || tool === 'mark') ? pickAt(e, filter) : null;
    setHover(pk);
    if (measPicks.length || measPrev.length) measPreview(pk, e);
    const h = pk || faceHit(e);
    if (pk) { const inf = entityInfo(pk); $('hover').textContent = `${inf.title}: ${inf.desc} · point ${fmtv(pk.local)}`; }
    else if (h) $('hover').textContent = `point ${fmtv(h.local)} · ${model.parts.length > 1 ? model.parts[h.part].name + ' · ' : ''}face #${h.faceId}${anaReadout(h)}`;
    else $('hover').textContent = '';
  });
});
const endStroke = () => { active = null; };
cvs.addEventListener('pointerup', ev => {
  if (painting) { endPaint(); return; }
  // keep the pivot for the controls' last update (next frame), then drop it so view animations are not corrected
  if (ev.button === 1) {
    const p = pivot; requestAnimationFrame(() => { if (pivot === p) pivot = null; });
    // a middle click (not a rotate drag) in Measure deletes all dimensions
    const click = midDownAt && Math.hypot(ev.clientX - midDownAt.x, ev.clientY - midDownAt.y) <= 5;
    midDownAt = null;
    if (click && tool === 'measure' && (measurements.length || measPicks.length)) {
      const n = measurements.length; clearMeasurements(); toast(`Deleted ${n} dimension(s).`);
    }
  }
  if (active) { endStroke(); return; }
  if (ev.button !== 0 || !downAt || Math.hypot(ev.clientX - downAt.x, ev.clientY - downAt.y) > 5) return;
  if (cubeDown) { const d = cubeDir(ev); cubeDown = null; if (d) setView('', true, d); return; }
  if (tool === 'select') {
    const pk = pickAt(ev, $('selFilter').value);
    if (!pk) { if (!ev.shiftKey) clearSelection(); return; }
    toggleSelect(pk, ev.shiftKey);
  } else if (tool === 'measure') {
    measureClick(pickAt(ev, $('measMode').value === 'min' ? 'part' : 'auto'), ev.shiftKey, ev);
  } else if (tool === 'mark') markClick(ev);
});
cvs.addEventListener('pointercancel', () => { endStroke(); endPaint(); pivot = null; });
cvs.addEventListener('pointerleave', () => { lastPointer = null; cubeHl.visible = false; setHover(null); clearMeasPrev(); $('hover').textContent = ''; });
// right click (no drag, since right-drag pans) on a part: hide, isolate, transparency, look at the face
cvs.addEventListener('contextmenu', ev => {
  ev.preventDefault();
  if (!rightDownAt || Math.hypot(ev.clientX - rightDownAt.x, ev.clientY - rightDownAt.y) > 5) return;
  const h = faceHit(ev);
  if (!h) return;
  const p = model.parts[h.part], pop = $('pinpop');
  pop.innerHTML = `<div class="row" style="margin:0 0 4px"><b>${esc(p.name)}</b><span class="grow"></span><button class="icon" data-a="x">✕</button></div>
    <div class="row"><label><input type="checkbox" data-a="tr" ${p.transp ? 'checked' : ''}> Transparent</label></div>
    <button class="mi" data-a="hide">Hide <kbd>H</kbd></button>
    <button class="mi" data-a="solo">${isolated ? 'Show the others again' : 'Isolate'} <kbd>I</kbd></button>
    <button class="mi" data-a="look">Look at this face <kbd>N</kbd></button>
    <button class="mi" data-a="focus">Zoom to this part</button>
    ${paramScript ? `<button class="mi" data-a="rel" title="Group the parameters that drive this part or this place at the top of the Params tab">Show related parameters</button>
    <button class="mi" data-a="quick" title="A short request for Claude about this place: few tokens, no screenshot by default">Quick change…</button>` : ''}
    ${model.parts.some(q => !q.visible) ? '<button class="mi" data-a="all">Show all parts <kbd>Shift+H</kbd></button>' : ''}`;
  const vr = view.getBoundingClientRect();
  pop.style.display = 'block';
  pop.style.left = Math.min(vr.width - 260, Math.max(6, ev.clientX - vr.left + 8)) + 'px';
  pop.style.top = Math.min(vr.height - pop.offsetHeight - 6, Math.max(6, ev.clientY - vr.top - 10)) + 'px';
  const close = () => { pop.style.display = 'none'; };
  pop.querySelector('[data-a=tr]').onchange = e => { p.transp = e.target.checked; applyPartLook(p); renderParts(); };
  const acts = {
    x: () => {}, hide: () => hideParts([p]), solo: () => isolate([p]), all: () => setPartsVisible(() => true),
    rel: () => showRelated(h), quick: () => openQuick(h),
    look: () => setView('', true, h.normal), focus: () => fitTo(p.bbox.clone().translate(p.group.position).getBoundingSphere(new THREE.Sphere())),
  };
  pop.querySelectorAll('button[data-a]').forEach(b => b.onclick = () => { acts[b.dataset.a](); close(); });
});
// parts under the cursor or the selected ones, for the H / T / I keys
function targetParts() {
  const sel = [...new Set(selection.map(s => s.part))].map(i => model.parts[i]);
  if (sel.length) return sel;
  const h = lastPointer && faceHit(lastPointer);
  return h ? [model.parts[h.part]] : [];
}
// Shift pressed and released on its own (no click, no other key in between) = reveal; Shift+click keeps adding to the selection
let shiftAlone = false;
addEventListener('pointerdown', () => { shiftAlone = false; }, true);
addEventListener('keyup', e => {
  if (e.key !== 'Shift' || !shiftAlone) return;
  shiftAlone = false;
  if (!/^(INPUT|TEXTAREA|SELECT)$/.test(document.activeElement?.tagName)) revealPartUnderCursor();
});
function revealPartUnderCursor() {
  const h = lastPointer && model.parts.length > 1 && faceHit(lastPointer);
  if (!h) return;
  $('pside').classList.remove('hidden');
  if ($('partsFilter').value) { $('partsFilter').value = ''; renderParts(); }
  const it = document.querySelector(`#partList .item[data-i="${h.part}"]`);
  if (!it) return;
  for (let g = it.closest('.pgrp'); g; g = g.parentElement.closest('.pgrp')) { if (!g.classList.contains('open')) { g.classList.add('open'); partGrpClosed.delete(g.dataset.g); } }
  fitPartRows();
  it.scrollIntoView({ block: 'center', inline: 'start', behavior: 'smooth' });
  it.classList.remove('flash'); void it.offsetWidth; it.classList.add('flash');
}
let isolated = null;   // visibility before I was pressed
function isolate(parts) {
  if (isolated) { const prev = isolated; isolated = null; setPartsVisible(q => prev.get(q.name) ?? true); return; }
  if (!parts.length) return;
  isolated = new Map(model.parts.map(q => [q.name, q.visible]));
  setPartsVisible(q => parts.includes(q));
}
function hideParts(parts) {
  if (!parts.length) return;
  for (const q of parts) { q.visible = false; applyPartLook(q); }
  renderParts(); updateSection();
  toast(`Hidden: ${parts.map(q => q.name).join(', ')} · Shift+H shows all`);
}
cvs.addEventListener('dblclick', ev => { if (strokes.length) return; const h = faceHit(ev); if (h) { const s = new THREE.Sphere(h.world, Math.max(model.radius * 0.2, 1)); fitTo(s); } });

// --- toolbar
function closeMenus() { document.querySelectorAll('.menu.open').forEach(m => m.classList.remove('open')); }
for (const [b, m] of [['bViewMenu', 'menuView'], ['bDispMenu', 'menuDisp'], ['bExportMenu', 'menuExport']]) $(b).onclick = () => {
  const open = $(m).classList.contains('open');
  closeMenus();
  if (!open) { $(m).classList.add('open'); if (m === 'menuView') renderSavedViews(); if (m === 'menuExport') loadExportFormats(); }
};
addEventListener('pointerdown', e => { if (!e.target.closest('.dd')) closeMenus(); });
function viewNormalToSelection() {
  const f = selection.find(s => s.type === 'face' && model.parts[s.part].an.faces[s.id].type === 'plane');
  if (!f) return toast('Select a planar face first, or hover a face and press N.', true);
  setView('', true, model.parts[f.part].an.faces[f.id].normal);
}
document.querySelectorAll('#menuView [data-v]').forEach(b => b.onclick = () => {
  closeMenus();
  if (b.dataset.v === 'normal') viewNormalToSelection(); else setView(b.dataset.v);
});

// --- saved views: camera + which parts are shown, kept in this browser per model
const svKey = () => 'cadp.views:' + (model.info?.path || '');
function savedViews() { try { return JSON.parse(localStorage.getItem(svKey()) || '[]'); } catch { return []; } }
function storeViews(v) { try { localStorage.setItem(svKey(), JSON.stringify(v)); } catch { toast('This browser does not allow saving views.', true); } }
function renderSavedViews() {
  const vs = savedViews();
  $('savedViews').innerHTML = vs.length ? vs.map((v, i) => `<div class="row" style="margin:2px 0"><button class="grow" data-i="${i}" data-a="go" style="justify-content:flex-start">${esc(v.name)}</button><button class="icon" data-i="${i}" data-a="rm" title="Delete">✕</button></div>`).join('')
    : '<div class="d muted">None yet. Set up the view and the visible parts, then save.</div>';
  $('savedViews').querySelectorAll('button').forEach(b => b.onclick = () => {
    const all = savedViews(), v = all[+b.dataset.i];
    if (b.dataset.a === 'rm') { all.splice(+b.dataset.i, 1); storeViews(all); renderSavedViews(); return; }
    closeMenus(); restoreView(v);
  });
}
function restoreView(v) {
  setOrtho(!!v.ortho);
  if (v.ortho) { ortho.zoom = v.zoom || 1; ortho.updateProjectionMatrix(); }
  flyTo(new THREE.Vector3(...v.pos), new THREE.Vector3(...v.target), new THREE.Vector3(...v.up));
  if (v.parts) setPartsVisible(q => v.parts[q.name]?.[0] ?? q.visible);
  for (const q of model.parts) if (v.parts?.[q.name]) { q.transp = v.parts[q.name][1] < 1; applyPartLook(q); }
  if (v.explode !== undefined) { explode = v.explode; $('explode').value = explode; $('explodeV').textContent = Math.round(explode / 1.5 * 100) + ' %'; applyExplode(); }
  renderParts();
}
$('svSave').onclick = () => {
  const all = savedViews();
  all.push({ name: $('svName').value.trim() || `View ${all.length + 1}`, pos: camera.position.toArray(), target: controls.target.toArray(), up: camera.up.toArray(),
    ortho: camera === ortho, zoom: ortho.zoom, explode, parts: Object.fromEntries(model.parts.map(q => [q.name, [q.visible, partAlpha(q)]])) });
  storeViews(all); $('svName').value = ''; renderSavedViews();
};
$('svName').onkeydown = e => { if (e.key === 'Enter') $('svSave').click(); };
$('bOrtho').onclick = () => setOrtho(camera !== ortho);
/**
 * The view as Claude should see it: the 3D render, the pen drawing, the HTML labels (dimensions, markers, pins)
 * and a numbered badge on every selected feature. The numbers and letters match the lists in the note text.
 */
function composeShot() {
  renderer.render(scene, camera);
  const c = document.createElement('canvas');
  c.width = renderer.domElement.width; c.height = renderer.domElement.height;
  const g = c.getContext('2d');
  g.drawImage(renderer.domElement, 0, 0);
  drawInk(); g.drawImage(ink, 0, 0, c.width, c.height);
  const k = c.width / view.clientWidth;
  const vr = view.getBoundingClientRect();
  g.font = `${12 * k}px Consolas, monospace`; g.textBaseline = 'middle';
  for (const el of labelRenderer.domElement.querySelectorAll('.lbl, .pin')) {
    if (el.style.display === 'none' || !el.offsetParent) continue;
    const r = el.getBoundingClientRect();
    const x = (r.left - vr.left) * k, y = (r.top - vr.top) * k, w = r.width * k, h = r.height * k;
    if (el.classList.contains('pin')) {
      g.fillStyle = getComputedStyle(el).backgroundColor; g.beginPath(); g.arc(x + w / 2, y + h / 2, w / 2, 0, 7); g.fill();
      g.fillStyle = '#111'; g.textAlign = 'center'; g.fillText(el.textContent, x + w / 2, y + h / 2);
    } else {
      const mark = el.classList.contains('mark');
      g.fillStyle = 'rgba(20,22,26,.88)'; g.fillRect(x, y, w, h); g.strokeStyle = mark ? '#e0b050' : '#8fb4ff'; g.lineWidth = 1.5 * k; g.strokeRect(x, y, w, h);
      g.fillStyle = '#fff'; g.textAlign = 'left'; g.fillText(el.textContent, x + 5 * k, y + h / 2);
    }
  }
  // selected features: badge "1", "2"… at the clicked point, as in "Selected features" of the note
  const px = { w: c.width, h: c.height };
  selection.forEach((s, i) => {
    const s2 = toScreen(toWorld(s.part, s.local), px);
    if (s2.z > 1) return;
    const R = 10 * k;
    g.fillStyle = '#d97757'; g.beginPath(); g.arc(s2.x, s2.y, R, 0, 7); g.fill();
    g.lineWidth = 2 * k; g.strokeStyle = '#fff'; g.stroke();
    g.fillStyle = '#fff'; g.textAlign = 'center'; g.font = `700 ${12 * k}px system-ui, sans-serif`; g.fillText(String(i + 1), s2.x, s2.y + 0.5 * k);
  });
  return c;
}
// ---- save project: model, script, exports, history, notes and a viewer copy into one folder (project.py)
// What only this browser keeps (dimensions, saved views, paint, markers) goes along in viewer-state.json and is
// loaded back the first time the saved project is opened.
const STATE_KEYS = ['meas', 'views', 'paint', 'markers'];
async function saveProject() {
  if (!model.info) return toast('No model is loaded.', true);
  const storage = {};
  for (const k of STATE_KEYS) { try { const v = localStorage.getItem(`cadp.${k}:${model.info.path}`); if (v) storage[k] = JSON.parse(v); } catch { /* skip */ } }
  const state = { storage, camera: { position: arr(camera.position), target: arr(controls.target), up: arr(camera.up), ortho: camera === ortho } };
  $('bProject').disabled = true;
  toast('Choose a folder for the project (the dialog may open behind this window)…');
  try {
    const r = await api('/api/project/save', { state });
    if (r.cancelled) toast('Saving the project was cancelled.');
    else toast(`Project saved: ${r.path} · ${(r.log || []).join(' · ')}`);
  } catch (e) { toast('Saving the project failed: ' + e.message, true); }
  finally { $('bProject').disabled = false; }
}
async function openFile() {
  $('bOpen').disabled = true;
  toast('Choose a model file (the dialog may open behind this window)…');
  try {
    const r = await api('/api/open/dialog', {});
    toast(r.cancelled ? 'Opening was cancelled.' : 'Opening ' + r.path.split(/[\\/]/).pop());
  } catch (e) { toast('Could not open the file: ' + e.message, true); }
  finally { $('bOpen').disabled = false; }
}
async function seedProjectState(info) {
  const flag = 'cadp.seeded:' + info.path;
  try { if (localStorage.getItem(flag)) return; } catch { return; }
  let st = {};
  try { st = await api('/api/project-state'); } catch { return; }
  for (const k of STATE_KEYS) {
    const key = `cadp.${k}:${info.path}`, v = st.storage?.[k];
    try { if (v && !localStorage.getItem(key)) localStorage.setItem(key, JSON.stringify(v)); } catch { /* per-viewer convenience */ }
  }
  try { localStorage.setItem(flag, '1'); } catch { /* ignore */ }
}
async function saveShot() {
  const c = composeShot();
  const r = await api('/api/screenshot', { image: c.toDataURL('image/png') });
  toast('Screenshot saved: ' + r.path.split(/[\\/]/).pop());
  return r.path;
}
$('bOpen').onclick = openFile;
$('bProject').onclick = saveProject;
$('bShot').onclick = () => saveShot().catch(e => toast('Could not save the screenshot: ' + e.message, true));
$('bFit').onclick = () => setView('', true, camera.position.clone().sub(controls.target).normalize().toArray());
const DISP = [['dEdges', 'edges'], ['dWire', 'wire'], ['dGrid', 'grid'], ['dAxes', 'axes'], ['dShadow', 'shadow'], ['dAO', 'ao'], ['dCube', 'cube'], ['dTriad', 'triad']];
function applyDisplay() {
  renderer.shadowMap.enabled = display.shadow; sunLight.castShadow = display.shadow; sunLight.intensity = display.shadow ? 1.7 : 0;
  camLight.intensity = camLight2.intensity = display.shadow ? 0.6 : 1.5;   // the sun takes over so its shadows read
  ground.visible = display.shadow; ground.material.needsUpdate = true;
  for (const p of model.parts) applyPartLook(p);
  grid.visible = display.grid; axes.visible = display.axes;
  for (const [id, k] of DISP) $(id).checked = display[k];
  document.querySelectorAll('#lookSeg button').forEach(b => b.classList.toggle('on', b.dataset.l === display.look));
  try { localStorage.setItem('cadp.display', JSON.stringify({ ...display, axes: undefined, v: 2 }));  /* axes always start hidden */ } catch { /* per-viewer convenience only */ }
}
for (const [id, k] of DISP) $(id).onchange = e => { display[k] = e.target.checked; applyDisplay(); };
document.querySelectorAll('#lookSeg button').forEach(b => b.onclick = () => { display.look = b.dataset.l; applyDisplay(); });
$('bUndo').onclick = undoStroke;
$('bClear').onclick = () => { clearStrokes(); clearSelection(); };
$('bNote').onclick = () => openNote();
$('bSide').onclick = () => { $('side').classList.toggle('hidden'); };
$('bParts').onclick = () => { $('pside').classList.toggle('hidden'); };
if (innerWidth < 640) $('side').classList.add('hidden');
// Right panel: a thin rail of icons; clicking an icon opens its details, clicking the open one closes them.
$('side').classList.add('rail');
document.querySelectorAll('#tabs button').forEach(b => {
  if (!b.title) b.title = b.textContent.replace(/\s+\d+\s*$/, '').trim();
  b.onclick = () => {
    const was = b.classList.contains('on') && !$('side').classList.contains('rail');
    document.querySelectorAll('#tabs button').forEach(x => x.classList.toggle('on', x === b));
    document.querySelectorAll('.tab').forEach(t => t.classList.toggle('on', t.id === 'tab-' + b.dataset.tab));
    $('side').classList.toggle('rail', was);
  };
});
function openTab(name, expand = true) {
  const b = document.querySelector(`#tabs button[data-tab="${name}"]`);
  if (!b) return;
  document.querySelectorAll('#tabs button').forEach(x => x.classList.toggle('on', x === b));
  document.querySelectorAll('.tab').forEach(t => t.classList.toggle('on', t.id === 'tab-' + name));
  if (expand) $('side').classList.remove('hidden', 'rail');
}
// zero counters do not show a badge on the rail
new MutationObserver(() => document.querySelectorAll('#tabs .n').forEach(n => n.toggleAttribute('data-zero', n.textContent.trim() === '0'))).observe($('tabs'), { subtree: true, childList: true, characterData: true });
document.querySelectorAll('#tabs .n').forEach(n => n.toggleAttribute('data-zero', n.textContent.trim() === '0'));

// --- selection
$('selClear').onclick = clearSelection;
$('selFocus').onclick = () => { if (!selection.length) return; const sp = selection.map(pickSphere).reduce((a, b) => a.union(b)); fitTo(sp); };
$('selSection').onclick = () => {
  const s = selection.find(x => x.type === 'face' && model.parts[x.part].an.faces[x.id].type === 'plane');
  if (!s) return;
  const f = model.parts[s.part].an.faces[s.id];
  section.mode = 'face'; section.n.set(...f.normal);
  section.d = section.n.dot(new THREE.Vector3(...f.centroid).add(partOffset(s.part)));
  syncSecMode();
  setSectionOn(true); openTab('sect');
};

// --- parts
$('explode').oninput = e => { explode = +e.target.value; $('explodeV').textContent = Math.round(explode / 1.5 * 100) + ' %'; applyExplode(); };
$('partsFilter').oninput = renderParts;
document.querySelectorAll('#partsGroup button').forEach(b => b.onclick = () => {
  partGroupMode = b.dataset.m; try { localStorage.setItem('cadp.partsGroup', partGroupMode); } catch { /* per-viewer convenience */ }
  renderParts();
});
$('partsExpand').onclick = () => { for (const p of model.parts) partOpen.add(p.name); renderParts(); };
$('partsCollapse').onclick = () => { partOpen.clear(); renderParts(); };
$('partsShowAll').onclick = () => { isolated = null; setPartsVisible(() => true); };
$('partsReset').onclick = () => { for (const p of model.parts) { p.color.copy(p.defaultColor); p.paint.clear(); p.paintRev++; p.transp = false; applyPartLook(p); } paintUndo = []; storePaint(); renderParts(); };
$('partsAlpha').oninput = e => { display.alpha = 1 - e.target.value / 100; $('partsAlphaV').textContent = `${e.target.value} %`; for (const p of model.parts) applyPartLook(p); };

// --- measurement
$('measShow').onchange = e => { measGroup.visible = e.target.checked; };
$('measComp').onchange = () => { measDirty = true; };
$('measClear').onclick = clearMeasurements;

// --- section
$('secOn').onchange = e => setSectionOn(e.target.checked);
document.querySelectorAll('#secAxis button').forEach(b => b.onclick = () => {
  if (b.dataset.a === 'face') {
    const s = selection.find(x => x.type === 'face' && model.parts[x.part].an.faces[x.id].type === 'plane');
    if (!s) { toast('Select a planar face first (Select tool).', true); return; }
    const f = model.parts[s.part].an.faces[s.id];
    section.n.set(...f.normal); section.d = section.n.dot(new THREE.Vector3(...f.centroid).add(partOffset(s.part)));
  }
  section.mode = b.dataset.a;
  syncSecMode();
  if (section.mode === 'box') { if (section.box.isEmpty() || !section.box.intersectsBox(model.bbox ?? section.box)) section.box.copy(visibleBox()).expandByScalar(model.radius * 0.01); renderSecBox(); }
  else if (section.mode !== 'face') { const [lo, hi] = sectionRange(sectionNormal()); section.d = (lo + hi) / 2; }
  if (!section.on) setSectionOn(true); else updateSection();
});
function syncSecMode() {
  document.querySelectorAll('#secAxis button').forEach(x => x.classList.toggle('on', x.dataset.a === section.mode));
  $('secCustom').style.display = section.mode === 'custom' ? 'block' : 'none';
  $('secPlaneCtl').style.display = section.mode === 'box' ? 'none' : '';
  $('secBoxCtl').style.display = section.mode === 'box' ? '' : 'none';
}
$('secKeep').onclick = () => {
  if (!section.on) return toast('Turn the section on first.', true);
  section.extra.push({ plane: section.plane.clone(), on: true });
  renderSecExtra(); updateSection();
  toast('Plane kept · move the cut to add another');
};
$('secBoxFit').onclick = () => fitSecBox(visibleBox());
$('secBoxSel').onclick = () => {
  if (!selection.length) return toast('Select something first (S).', true);
  const box = new THREE.Box3();
  for (const s of selection) { const sp = pickSphere(s); box.union(new THREE.Box3().setFromCenterAndSize(sp.center, new THREE.Vector3().setScalar(sp.radius * 2))); }
  fitSecBox(box);
};
$('secFlip').onclick = () => { section.flip = !section.flip; $('secFlip').classList.toggle('on', section.flip); updateSection(); };
$('secAz').oninput = e => { section.az = +e.target.value; $('secAzV').textContent = section.az + '°'; updateSection(); };
$('secEl').oninput = e => { section.el = +e.target.value; $('secElV').textContent = section.el + '°'; updateSection(); };
$('secOff').oninput = e => { const [lo, hi] = sectionRange(sectionNormal()); section.d = lo + (+e.target.value) * (hi - lo); if (!section.on) setSectionOn(true); else updateSection(); };
$('secOffN').onchange = e => { section.d = +e.target.value; if (!section.on) setSectionOn(true); else updateSection(); };
$('secMinus').onclick = () => { section.d -= +$('secStep').value; updateSection(); };
$('secPlus').onclick = () => { section.d += +$('secStep').value; updateSection(); };
for (const id of ['secPlane', 'secOutline', 'secCap']) $(id).onchange = () => updateSection();
$('secCapColor').oninput = e => { for (const p of model.parts) p.cap.material.color.set(e.target.value); };

// --- versions
$('ghostOff').onclick = clearGhost;
$('ghostOp').oninput = e => { if (ghost.mesh) ghost.mesh.material.opacity = +e.target.value; };
$('diffOn').onchange = computeDiff;
$('diffTol').onchange = computeDiff;

// --- notes
document.querySelectorAll('#noteFilter button').forEach(b => b.onclick = () => {
  noteFilter = b.dataset.f;
  document.querySelectorAll('#noteFilter button').forEach(x => x.classList.toggle('on', x === b));
  renderNotes(); renderPins();
});
$('pinsOn').onchange = renderPins;

// --- parameters
$('paramSearch').oninput = () => renderParams();
document.querySelectorAll('#paramFilter button').forEach(b => b.onclick = () => { paramFilter = b.dataset.f; renderParams(); });
$('paramApply').onclick = applyParams;
$('paramRevert').onclick = () => { paramEdits = {}; renderParams(); };

// --- modal
$('mCancel').onclick = closeNote;
$('mSend').onclick = sendNote;
$('modal').addEventListener('pointerdown', e => { if (e.target === $('modal')) closeNote(); });

// --- keyboard
addEventListener('keydown', e => {
  if ($('modal').classList.contains('open')) {
    if (e.key === 'Escape') closeNote();
    if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) sendNote();
    return;
  }
  if ($('help').classList.contains('open')) { if (e.key === 'Escape' || e.key === '?') $('help').classList.remove('open'); return; }
  if (/^(INPUT|TEXTAREA|SELECT)$/.test(document.activeElement?.tagName)) return;
  const k = e.key.toLowerCase();
  // Shift alone over a part: find it in the parts tree (Shift+click still adds to the selection)
  if (e.key === 'Shift') { if (!e.repeat) shiftAlone = !e.ctrlKey && !e.altKey && !e.metaKey; return; }
  shiftAlone = false;
  if (e.ctrlKey || e.metaKey || e.altKey) { if (k === 'z' && !e.altKey) { if (tool === 'paint') undoPaint(); else undoStroke(); e.preventDefault(); } return; }
  if (k === 'escape') { closeMenus(); if (measPicks.length) setTool('measure'); else if (markDraft || markSel >= 0) { markDraft = null; markSel = -1; markEdit = false; drawMarkers(); hint(); } else { clearSelection(); $('pinpop').style.display = 'none'; clearNoteOverlay(); activePin = null; renderPins(); } }
  else if (k === 'h' && e.shiftKey) { isolated = null; setPartsVisible(() => true); }
  else if (k === 'h') hideParts(targetParts());
  else if (k === 't') { const ps = targetParts(); const next = !ps[0]?.transp; for (const q of ps) { q.transp = next; applyPartLook(q); } renderParts(); }
  else if (k === 'i') isolate(targetParts());
  else if (k === 'n') { const h = lastPointer && faceHit(lastPointer); if (h) setView('', true, h.normal); else viewNormalToSelection(); }
  else if (e.key === '?') $('help').classList.add('open');
  else if (e.key === '[' || e.key === ']') stepVariant(e.key === ']' ? 1 : -1);
  else if (k === 's') setTool('select');
  else if (k === 'd') setTool('pen');
  else if (k === 'm') setTool('measure');
  else if (k === 'k') setTool('mark');
  else if (k === 'b') setTool('paint');
  else if ((k === 'delete' || k === 'backspace') && markSel >= 0) deleteMarker(markSel);
  else if ((k === 'delete' || k === 'backspace') && measSel !== null) removeMeasurement(measSel);
  else if (k === 'f') $('bFit').click();
  else if (k === 'p') setOrtho(camera !== ortho);
  else if (k === 'x') setSectionOn(!section.on);
  else if (k === 'enter' && markDraft?.type === 'area') finishMarkDraft();
  else if (k === 'enter') openNote();
  else if (k === '1') setView('iso'); else if (k === '2') setView('front'); else if (k === '3') setView('top'); else if (k === '4') setView('right');
  else return;
  e.preventDefault();
});

// ============================================================ disassembly
// <model>.explode.json (skill cad-explode): {base, steps:[{name, parts, direction, distance, note?, tool?, locked?}],
// locked:[parts], notes:[...]}. Steps run in disassembly order; a part listed in several steps adds them up.
const ease = k => k * k * (3 - 2 * k);
function applyPlan() {
  const off = new Map(model.parts.map(p => [p, new THREE.Vector3()]));
  xplan.def.steps.forEach((st, i) => {
    const k = ease(Math.min(1, Math.max(0, xplan.s - i)));
    if (!k || !st.direction) return;
    const d = new THREE.Vector3(...st.direction).normalize().multiplyScalar((st.distance ?? model.radius) * k);
    for (const ref of st.parts ?? []) { const p = findPart(ref); if (p) off.get(p).add(d); }
  });
  for (const [p, o] of off) p.group.position.copy(o);
}
function drawTrails() {
  for (const c of [...xplan.trails.children]) { c.geometry.dispose(); c.material.dispose(); xplan.trails.remove(c); }
  if (!$('xTrails').checked) return;
  for (const p of model.parts) {
    if (p.group.position.lengthSq() < 1e-6 || !p.visible) continue;
    const a = p.center.clone(), b = p.center.clone().add(p.group.position);
    const g = new THREE.BufferGeometry().setFromPoints([a, b]);
    const l = new THREE.Line(g, new THREE.LineDashedMaterial({ color: 0x8e8c84, dashSize: model.radius / 30, gapSize: model.radius / 40, depthTest: false, transparent: true, opacity: 0.8 }));
    l.computeLineDistances(); l.renderOrder = 9;
    xplan.trails.add(l);
  }
}
async function loadExplode() {
  const info = model.info;
  const fresh = xplan.modelPath !== (info?.path || '');
  xplan.modelPath = info?.path || '';
  let def = null, error = '';
  if (info?.explode) { try { def = await api('/api/explode'); } catch (e) { error = e.message; } }
  const had = !!xplan.def;
  xplan.def = def && Array.isArray(def.steps) ? def : null;
  xplan.error = error || (def && !xplan.def ? 'explode.json has no steps' : '');
  xplan.playing = false;
  if (xplan.def && (!had || fresh)) {  // a new plan: show it fully exploded
    xplan.s = xplan.def.steps.length; setXMode('dis');
    if (!had && !fresh) toast(`Disassembly plan: ${xplan.def.steps.length} steps, see the Parts panel`);
  } else if (!xplan.def && xplan.mode !== 'radial' && fresh) setXMode('radial');
  xplan.s = Math.min(xplan.s, xplan.def?.steps.length ?? 0);
  renderPlan(); applyExplode();
}
function setXMode(m) {
  xplan.mode = m;
  document.querySelectorAll('#xMode button').forEach(b => b.classList.toggle('on', b.dataset.m === m));
  $('xRadial').style.display = m === 'radial' ? '' : 'none';
  $('xPlan').style.display = m === 'radial' ? 'none' : '';
  xplan.playing = false;
  renderPlan(); applyExplode();
}
// xplan.s is always the disassembly state (0 assembled … n exploded); Assembly runs it backwards
const xAsm = () => xplan.mode === 'asm';
const xN = () => xplan.def?.steps.length ?? 0;
const xProg = () => xAsm() ? xN() - xplan.s : xplan.s;
const xSetProg = p => { xplan.s = xAsm() ? xN() - p : p; };
function renderPlan() {
  const d = xplan.def, n = xN(), asm = xAsm();
  $('xEmpty').style.display = d ? 'none' : '';
  $('xBody').style.display = d || xplan.error ? '' : 'none';
  const warn = [xplan.error, ...(d?.locked ?? []).map(p => asm ? `Cannot be assembled: ${p}` : `Locked: ${p} cannot be taken out`),
    ...(d?.steps ?? []).flatMap(st => (st.parts ?? []).filter(r => !findPart(r)).map(r => `${st.name}: part “${r}” not found`))];
  $('xWarn').innerHTML = warn.filter(Boolean).map(esc).join('<br>');
  const p = xProg();
  $('xT').max = n; $('xT').step = 0.001; $('xT').value = p;
  $('xTV').textContent = `${Math.ceil(p - 1e-6)}/${n}`;
  $('xPlay').textContent = xplan.playing ? '❚❚ Pause' : '▶ Play';
  const cur = Math.ceil(p - 1e-6) - 1;
  const order = (d?.steps ?? []).map((st, i) => ({ st, i }));
  if (asm) order.reverse();
  $('xSteps').innerHTML = order.map(({ st }, j) => {
    const name = asm ? st.assemblyName || `Install ${(st.parts ?? []).join(', ')}` : st.name;
    const dir = st.direction && (asm ? st.direction.map(x => -x) : st.direction);
    return `<div class="item xs ${j < cur ? 'done' : ''} ${j === cur ? 'sel' : ''} ${st.locked ? 'locked' : ''}" data-j="${j}">
    <div class="t">${j + 1}. ${esc(name)}${st.locked ? ` <span class="badge bad">${asm ? 'cannot be assembled' : 'locked'}</span>` : ''}</div>
    <div class="d">${esc((st.parts ?? []).join(', '))}${dir ? ` · ${esc(dirLabel(dir))}` : ''}${st.tool ? ` · 🔧 ${esc(st.tool)}` : ''}</div>
    ${(asm && st.assemblyNote) || st.note ? `<div class="d muted">${esc(asm && st.assemblyNote ? st.assemblyNote : st.note)}</div>` : ''}</div>`;
  }).join('')
    + ((d?.notes ?? []).length ? `<h4>Notes</h4>${d.notes.map(t => `<div class="d" style="margin:3px 0">• ${esc(t)}</div>`).join('')}` : '');
  $('xSteps').querySelectorAll('.xs').forEach(it => it.onclick = () => { xplan.playing = false; xSetProg(+it.dataset.j + 1); renderPlan(); applyExplode(); });
}
function dirLabel(v) {
  const ax = ['X', 'Y', 'Z'], i = v.map(Math.abs).indexOf(Math.max(...v.map(Math.abs)));
  return Math.abs(Math.abs(v[i]) - 1) < 1e-3 ? (v[i] > 0 ? '+' : '−') + ax[i] : `[${v.map(x => r2(x)).join(', ')}]`;
}
(function xTick() {
  requestAnimationFrame(xTick);
  const now = performance.now(), dt = now - xplan.last; xplan.last = now;
  if (!xplan.playing || !xplan.def) return;
  const n = xN(), p = Math.min(n, xProg() + dt / 1000 / 1.2);  // 1.2 s per step
  xSetProg(p);
  if (p >= n) xplan.playing = false;
  applyExplode(); renderPlan();
})();
document.querySelectorAll('#xMode button').forEach(b => b.onclick = () => setXMode(b.dataset.m));
$('xT').oninput = e => { xplan.playing = false; xSetProg(+e.target.value); applyExplode(); renderPlan(); };
$('xPlay').onclick = () => {
  if (!xplan.def) return;
  if (!xplan.playing && xProg() >= xN() - 1e-6) xSetProg(0);
  xplan.playing = !xplan.playing; renderPlan();
};
$('xTrails').onchange = drawTrails;
async function requestPlan() {
  if (!model.info) return;
  try {
    await api('/api/annotate', { kind: 'explode', model: model.info.path, name: model.info.name, step: model.info.step || null,
      comment: $('xFocus').value.trim() || 'explode', parts: model.parts.map(p => p.name) });
    toast('Added to your chat draft ✔');
    loadNotes(true);
  } catch (e) { toast('Sending failed: ' + e.message, true); }
}
$('xCreate').onclick = requestPlan;
$('xRedo').onclick = requestPlan;

// ================================================================= motion
// <model>.motion.json: {joints:[{name, type:'revolute'|'prismatic', parts:[...], origin, axis, min, max, home,
//   parent?, drive?:{joint, ratio, offset}}], animations?:[{name, duration, keyframes:[{t, values:{joint: v}}]}]}
// Revolute values are degrees, prismatic mm. The STEP geometry is the pose where every joint = home.
motion.axes.renderOrder = 10;
scene.add(motion.axes);

async function loadMotion() {
  const info = model.info;
  const samePath = motion.modelPath === (info?.path || '');
  motion.modelPath = info?.path || '';
  if (!info?.motion) { setMotionDef(null, ''); return; }
  try { setMotionDef(await api('/api/motion'), '', samePath); }
  catch (e) { setMotionDef(null, e.message); }
}
const jMin = j => j.min ?? (j.type === 'prismatic' ? 0 : -180);
const jMax = j => j.max ?? (j.type === 'prismatic' ? 10 : 180);
const jHome = j => j.home ?? 0;
const isFree = j => !j.drive;
function setMotionDef(def, error, keep) {
  const had = !!motion.def;
  motion.playing = false;
  motion.def = def && Array.isArray(def.joints) && def.joints.length ? def : null;
  motion.error = error || (def && !motion.def ? 'motion.json has no joints' : '');
  const old = keep ? motion.values : {};
  motion.byName = {}; motion.values = {};
  for (const j of motion.def?.joints ?? []) {
    motion.byName[j.name] = j;
    const v = old[j.name];
    motion.values[j.name] = v !== undefined && v >= jMin(j) && v <= jMax(j) ? v : jHome(j);
  }
  motion.anims = motion.def ? [...(motion.def.animations ?? []).filter(a => a.keyframes?.length), defaultAnimation()] : [];
  motion.anim = Math.min(motion.anim, Math.max(0, motion.anims.length - 1));
  motion.t = 0;
  const show = motion.def || motion.error || model.parts.length > 1;
  $('motionTabBtn').style.display = show ? '' : 'none';
  $('motionEmpty').style.display = motion.def ? 'none' : '';
  $('motionBody').style.display = motion.def || motion.error ? '' : 'none';
  $('nJoints').textContent = motion.def?.joints.length ?? 0;
  if (!show && $('tab-motion').classList.contains('on')) openTab('sel', false);
  if (motion.def && !had) toast(`Motion: ${motion.def.joints.length} joint${motion.def.joints.length > 1 ? 's' : ''}, see the Motion tab`);
  renderMotion(); applyMotion();
}
function defaultAnimation() {
  // home -> max -> min -> home on every free joint at once
  const free = motion.def.joints.filter(isFree);
  const at = f => Object.fromEntries(free.map(j => [j.name, f(j)]));
  return { name: 'Full range (all joints)', duration: 4, keyframes: [
    { t: 0, values: at(jHome) }, { t: 1 / 3, values: at(jMax) }, { t: 2 / 3, values: at(jMin) }, { t: 1, values: at(jHome) }] };
}
function sampleAnimation(a, t) {
  const kf = [...a.keyframes].sort((x, y) => x.t - y.t);
  const out = {};
  for (const name of new Set(kf.flatMap(k => Object.keys(k.values || {})))) {
    const pts = kf.filter(k => name in (k.values || {}));
    const i = pts.findIndex(k => k.t >= t);
    if (i < 0) out[name] = pts[pts.length - 1].values[name];
    else if (i === 0) out[name] = pts[0].values[name];
    else {
      const A = pts[i - 1], B = pts[i], u = B.t > A.t ? (t - A.t) / (B.t - A.t) : 1;
      out[name] = A.values[name] + (B.values[name] - A.values[name]) * u;
    }
  }
  return out;
}
function jointValue(j, depth = 0) {
  const src = j.drive && depth < 16 && motion.byName[j.drive.joint];
  if (src) return jointValue(src, depth + 1) * (j.drive.ratio ?? 1) + (j.drive.offset ?? 0);
  return motion.values[j.name] ?? jHome(j);
}
function jointMatrix(j, cache, depth = 0) {
  if (cache.has(j.name)) return cache.get(j.name);
  const d = jointValue(j) - jHome(j);
  const o = new THREE.Vector3(...(j.origin ?? [0, 0, 0])), a = new THREE.Vector3(...(j.axis ?? [0, 0, 1])).normalize();
  const m = j.type === 'prismatic'
    ? new THREE.Matrix4().makeTranslation(a.x * d, a.y * d, a.z * d)
    : new THREE.Matrix4().makeTranslation(o.x, o.y, o.z)
      .multiply(new THREE.Matrix4().makeRotationAxis(a, THREE.MathUtils.degToRad(d)))
      .multiply(new THREE.Matrix4().makeTranslation(-o.x, -o.y, -o.z));
  const parent = j.parent && depth < 16 && motion.byName[j.parent];
  if (parent) m.premultiply(jointMatrix(parent, cache, depth + 1));
  cache.set(j.name, m);
  return m;
}
function findPart(ref) {
  if (typeof ref === 'number') return model.parts[ref];
  const s = String(ref).toLowerCase();
  return model.parts.find(p => p.name === ref) ?? model.parts.find(p => p.name.toLowerCase() === s);
}
function applyMotion() {
  const cache = new Map();
  for (const p of model.parts) p.pose.matrix.identity();
  for (const j of motion.def?.joints ?? []) {
    const m = jointMatrix(j, cache);
    for (const ref of j.parts ?? []) { const p = findPart(ref); if (p) p.pose.matrix.copy(m); }
  }
  for (const p of model.parts) p.pose.matrixWorldNeedsUpdate = true;
  // joint axes, carried by their parent joint
  for (const c of [...motion.axes.children]) { c.geometry.dispose(); c.material.dispose(); motion.axes.remove(c); }
  if (motion.def && $('motionAxes').checked) {
    const L = model.radius * 0.5;
    for (const j of motion.def.joints) {
      const o = new THREE.Vector3(...(j.origin ?? [0, 0, 0])), a = new THREE.Vector3(...(j.axis ?? [0, 0, 1])).normalize();
      const pm = j.parent && motion.byName[j.parent] ? jointMatrix(motion.byName[j.parent], cache) : new THREE.Matrix4();
      const ends = j.type === 'prismatic' ? [jMin(j) - jHome(j), jMax(j) - jHome(j)] : [-L, L];
      const g = new THREE.BufferGeometry().setFromPoints(ends.map(e => o.clone().addScaledVector(a, e).applyMatrix4(pm)));
      motion.axes.add(new THREE.Line(g, new THREE.LineBasicMaterial({ color: j.type === 'prismatic' ? 0x4fc3f7 : 0xffa726, depthTest: false, transparent: true })));
    }
  }
  renderJointValues();
  onPoseChange();
}
function motionAtHome() { return (motion.def?.joints ?? []).every(j => Math.abs((motion.values[j.name] ?? 0) - jHome(j)) < 1e-9); }
function motionHome() {
  motion.playing = false; motion.t = 0;
  for (const j of motion.def?.joints ?? []) motion.values[j.name] = jHome(j);
  applyMotion(); renderMotionTransport();
}
function setMotionT(t) {
  motion.t = t;
  const a = motion.anims[motion.anim];
  if (a) Object.assign(motion.values, sampleAnimation(a, t));
  applyMotion(); renderMotionTransport();
}
function tickMotion() {
  const now = performance.now(), dt = now - motion.last;
  motion.last = now;
  if (!motion.playing) return;
  const a = motion.anims[motion.anim];
  let t = motion.t + dt / 1000 * +$('motionSpeed').value / (a.duration || 4);
  if (t >= 1) { if ($('motionLoop').checked) t %= 1; else { t = 1; motion.playing = false; } }
  setMotionT(t);
}
function renderMotion() {
  const joints = motion.def?.joints ?? [];
  const warn = [motion.error,
    ...joints.flatMap(j => (j.parts ?? []).filter(r => !findPart(r)).map(r => `${j.name}: part “${r}” not found`)),
    ...joints.filter(j => j.parent && !motion.byName[j.parent]).map(j => `${j.name}: unknown parent “${j.parent}”`),
    ...joints.filter(j => j.drive && !motion.byName[j.drive.joint]).map(j => `${j.name}: unknown drive joint “${j.drive.joint}”`)];
  $('motionWarn').innerHTML = warn.filter(Boolean).map(esc).join('<br>');
  $('motionAnim').innerHTML = motion.anims.map((a, i) => `<option value="${i}" ${i === motion.anim ? 'selected' : ''}>${esc(a.name || 'Animation ' + (i + 1))}</option>`).join('');
  $('jointList').innerHTML = joints.map(j => {
    const unit = j.type === 'prismatic' ? 'mm' : '°';
    const head = `<span class="nm">${esc(j.name)}</span><span class="mono" data-jv="${esc(j.name)}"></span>`;
    const what = `${j.type === 'prismatic' ? 'slides' : 'rotates'} ${esc((j.parts ?? []).join(', '))}${j.parent ? ` · on ${esc(j.parent)}` : ''}${j.note ? ' · ' + esc(j.note) : ''}`;
    if (!isFree(j)) return `<div class="param">${head}<span class="cm">${what} · follows ${esc(j.drive.joint)} × ${j.drive.ratio ?? 1}${j.drive.offset ? ` + ${j.drive.offset}` : ''}</span></div>`;
    return `<div class="param">${head}<input type="range" data-j="${esc(j.name)}" min="${jMin(j)}" max="${jMax(j)}" step="${j.type === 'prismatic' ? 0.1 : 0.5}">
      <span class="cm">${what} · ${jMin(j)} … ${jMax(j)} ${unit}</span></div>`;
  }).join('');
  $('jointList').querySelectorAll('input[data-j]').forEach(r => r.oninput = () => {
    motion.playing = false; motion.values[r.dataset.j] = +r.value; applyMotion(); renderMotionTransport();
  });
  renderJointValues(); renderMotionTransport();
}
function renderJointValues() {
  for (const j of motion.def?.joints ?? []) {
    const el = $('jointList').querySelector(`[data-jv="${CSS.escape(j.name)}"]`);
    if (el) el.textContent = `${fmtn(jointValue(j), j.type === 'prismatic' ? 2 : 1)} ${j.type === 'prismatic' ? 'mm' : '°'}`;
    const r = $('jointList').querySelector(`input[data-j="${CSS.escape(j.name)}"]`);
    if (r && document.activeElement !== r) r.value = motion.values[j.name];
  }
}
function renderMotionTransport() {
  $('motionPlay').textContent = motion.playing ? '❚❚ Pause' : '▶ Play';
  if (document.activeElement !== $('motionT')) $('motionT').value = motion.t;
  $('motionTV').textContent = Math.round(motion.t * 100) + ' %';
}
$('motionPlay').onclick = () => {
  if (!motion.def) return;
  if (tool !== 'select') setTool('select');
  if (!motion.playing && motion.t >= 1) motion.t = 0;
  motion.playing = !motion.playing; motion.last = performance.now(); renderMotionTransport();
};
$('motionT').oninput = e => { motion.playing = false; setMotionT(+e.target.value); };
$('motionAnim').onchange = e => { motion.anim = +e.target.value; motion.playing = false; setMotionT(0); };
$('motionHome').onclick = motionHome;
$('motionCreate').onclick = async () => {
  if (!model.info) return;
  try {
    await api('/api/annotate', { kind: 'motion', model: model.info.path, name: model.info.name, step: model.info.step || null,
      comment: 'Create motion for this assembly', parts: model.parts.map(p => p.name) });
    toast('Added to your chat draft ✔');
    loadNotes(true);
  } catch (e) { toast('Sending failed: ' + e.message, true); }
};
$('motionAxes').onchange = applyMotion;

// ================================================================ analysis
// Colour maps (wall thickness, draft, overhang), collisions and mass properties. Everything is
// computed and shown here in the browser; nothing of it goes into notes for Claude.
const anaState = { kind: '', values: new Map(), thick: new Map(), colliding: null, homeContacts: null, liveT: 0, poseRaf: 0 };
const parseDir = s => new THREE.Vector3(...s.split(',').map(Number));
/** A world direction expressed in the part's own frame (the motion pose may rotate parts). */
function dirInPart(p, d) { return d.clone().applyMatrix3(new THREE.Matrix3().setFromMatrix4(p.pose.matrix).invert()).normalize(); }
function anaParams() { return { minWall: Math.max(0.001, +$('anaMinWall').value || 1), minDraft: Math.max(0, +$('anaMinDraft').value || 0), crit: Math.min(89, Math.max(0, +$('anaCrit').value || 45)) }; }

function runAnalysis() {
  const kind = anaState.kind;
  if (!kind || kind === 'collide' || !model.parts.length) return;
  const P = anaParams();
  if (kind === 'thick' && model.parts.some(p => !anaState.thick.has(p.index))) {
    $('loading').textContent = 'Measuring wall thickness…'; $('loading').classList.add('on');
    // let the overlay paint before the (synchronous) ray casting
    return setTimeout(() => {
      try { for (const p of model.parts) if (!anaState.thick.has(p.index)) anaState.thick.set(p.index, ana.thickness(p.geo, model.radius * 1e-5, model.radius * 4)); }
      finally { $('loading').classList.remove('on'); $('loading').textContent = 'Loading model…'; }
      runAnalysis();
    }, 30);
  }
  let worst = null, bad = 0;
  for (const p of model.parts) {
    let vals, color;
    if (kind === 'thick') {
      vals = anaState.thick.get(p.index);
      color = i => ana.scales.thick(vals[i], P.minWall);
      for (let i = 0; i < vals.length; i++) if (isFinite(vals[i]) && (!worst || vals[i] < worst.v)) worst = { v: vals[i], p };
    } else if (kind === 'draft') {
      const pull = dirInPart(p, parseDir($('anaPull').value));
      vals = ana.normalAngles(p.geo, pull);
      color = i => ana.scales.draft(vals[i], P.minDraft);
      for (const f of p.an.faces) if (f.type === 'plane' && f.normal && Math.abs(Math.asin(Math.max(-1, Math.min(1, pull.dot(new THREE.Vector3(...f.normal))))) * 180 / Math.PI) < P.minDraft) bad++;
    } else {
      const up = dirInPart(p, parseDir($('anaBuild').value));
      const ang = ana.normalAngles(p.geo, up), hgt = ana.heights(p.geo, up), bed = model.radius * 1e-3;
      vals = ang.map(a => -a);   // degrees the surface faces downwards: 90 = flat ceiling
      color = i => hgt[i] < bed && vals[i] > 89 ? ana.NEUTRAL : ana.scales.overhang(vals[i], P.crit);
    }
    anaState.values.set(p.index, vals);
    ana.paint(p.geo, color);
    applyPartLook(p);
  }
  const L = (c, t) => `<div class="k"><i style="background:rgb(${c.map(x => Math.round(x * 255)).join(',')})"></i>${t}</div>`;
  if (kind === 'thick') {
    $('legend').innerHTML = `<div class="t">Wall thickness</div>${L(ana.RED, `under ${fmtn(P.minWall)} mm`)}${L(ana.YELLOW, `${fmtn(P.minWall)} – ${fmtn(P.minWall * 1.5)} mm`)}${L(ana.GREEN, `up to ${fmtn(P.minWall * 2)} mm`)}${L(ana.NEUTRAL, 'thicker')}`;
    $('anaStats').innerHTML = worst ? `Thinnest wall <b style="color:${worst.v < P.minWall ? 'var(--bad)' : 'var(--ok)'}">${fmtn(worst.v)} mm</b>${model.parts.length > 1 ? ` in ${esc(worst.p.name)}` : ''}. Hover the model to read the thickness.` : 'No walls found.';
  } else if (kind === 'draft') {
    $('legend').innerHTML = `<div class="t">Draft to ${$('anaPull').selectedOptions[0].text}</div>${L(ana.GREEN, `≥ ${fmtn(P.minDraft, 1)}° towards the pull`)}${L(ana.BLUE, `≥ ${fmtn(P.minDraft, 1)}° the other way`)}${L(ana.RED, `under ${fmtn(P.minDraft, 1)}° (needs draft)`)}`;
    $('anaStats').innerHTML = bad ? `<b style="color:var(--bad)">${bad}</b> planar face${bad > 1 ? 's' : ''} with too little draft. Hover to read the angle.` : 'Every planar face has enough draft (or is square to the pull).';
  } else {
    $('legend').innerHTML = `<div class="t">Overhang, build ${$('anaBuild').selectedOptions[0].text}</div>${L(ana.RED, `needs support (over ${fmtn(P.crit, 0)}°)`)}${L(ana.ORANGE, `close to the limit`)}${L(ana.NEUTRAL, 'prints without support')}`;
    $('anaStats').textContent = 'Faces resting on the bed are not marked. Hover to read the angle from vertical.';
  }
  $('legend').classList.add('on');
}
function clearColours() {
  for (const p of model.parts) resetVertexColors(p);
  if (ghost.geo) computeDiff();
}
function setAnalysis(kind) {
  anaState.kind = kind;
  document.querySelectorAll('#anaSeg button').forEach(b => b.classList.toggle('on', b.dataset.k === (kind === 'collide' ? '' : kind)));
  for (const [id, k] of [['anaThickCtl', 'thick'], ['anaDraftCtl', 'draft'], ['anaOverCtl', 'overhang']]) $(id).style.display = kind === k ? '' : 'none';
  anaState.values.clear();
  if (!kind) { clearColours(); for (const p of model.parts) applyPartLook(p); $('legend').classList.remove('on'); $('anaStats').textContent = ''; return; }
  if (kind !== 'collide') runAnalysis();
}
function anaReadout(h) {
  const v = anaState.values.get(h.part)?.[h.vertex];
  if (v === undefined) return '';
  if (anaState.kind === 'thick') return isFinite(v) ? ` · wall ${fmtn(v)} mm` : '';
  if (anaState.kind === 'draft') return ` · draft ${fmtn(v, 1)}°`;
  if (anaState.kind === 'overhang') return v > 0 ? ` · overhang ${fmtn(v, 1)}° from vertical` : '';
  return '';
}

// --- collisions
function partMatrix(p, home) {
  p.mesh.updateWorldMatrix(true, false);
  return home ? new THREE.Matrix4().makeTranslation(p.group.position.x, p.group.position.y, p.group.position.z) : p.mesh.matrixWorld.clone();
}
function pairs(home) {
  const vis = model.parts.filter(p => p.visible), out = [];
  for (let i = 0; i < vis.length; i++) for (let j = i + 1; j < vis.length; j++) {
    const a = vis[i], b = vis[j], ma = partMatrix(a, home), mb = partMatrix(b, home);
    if (a.bbox.clone().applyMatrix4(ma).intersectsBox(b.bbox.clone().applyMatrix4(mb))) out.push({ a, b, ma, mb });
  }
  return out;
}
function runCollisions() {
  if (model.parts.length < 2) { $('colList').textContent = 'Collisions need an assembly of two or more parts.'; return; }
  const tol = Math.max(0, +$('colTol').value || 0);
  const res = [];
  for (const { a, b, ma, mb } of pairs(false)) {
    const r = ana.collide({ geo: a.geo, mw: ma }, { geo: b.geo, mw: mb }, tol);
    if (r) res.push({ a, b, r, ma });
  }
  anaState.kind = 'collide';
  setAnalysis('collide');
  // paint: grey everywhere, orange where surfaces meet, red where one part is inside the other
  // STEP is meshed with a chord error of 0.15 % of the model size: round parts in bores dip in by up to that much
  const meshTol = model.source.startsWith('STEP') ? model.bbox.min.distanceTo(model.bbox.max) * 0.0015 : 0;
  const mark = new Map(model.parts.map(p => [p.index, { touch: new Set(), inside: new Set() }]));
  for (const { a, b, r } of res) {
    for (const v of r.touchA) mark.get(a.index).touch.add(v); for (const v of r.touchB) mark.get(b.index).touch.add(v);
    if (r.depth <= Math.max(tol, meshTol)) continue;
    for (const v of r.insideA) mark.get(a.index).inside.add(v);
    for (const v of r.insideB) mark.get(b.index).inside.add(v);
  }
  for (const p of model.parts) {
    const m = mark.get(p.index);
    ana.paint(p.geo, i => m.inside.has(i) ? ana.RED : m.touch.has(i) ? ana.ORANGE : ana.NEUTRAL);
    applyPartLook(p);
  }
  anaState.colliding = res;
  const L = (c, t) => `<div class="k"><i style="background:rgb(${c.map(x => Math.round(x * 255)).join(',')})"></i>${t}</div>`;
  $('legend').innerHTML = `<div class="t">Collisions</div>${L(ana.RED, 'inside another part')}${L(ana.ORANGE, 'surfaces touch or cross')}`;
  $('legend').classList.add('on');
  const nVis = model.parts.filter(p => p.visible).length;
  $('colList').classList.toggle('muted', !res.length);
  $('colList').innerHTML = res.length ? res.map((x, i) => {
    const deep = x.r.depth > Math.max(tol, meshTol);
    return `<div class="item"><div class="row" style="margin:0"><span class="t grow">${esc(x.a.name)} ↔ ${esc(x.b.name)}</span><span class="badge ${deep ? 'bad' : 'open'}">${deep ? 'interference' : 'contact'}</span></div>
      <div class="d">${deep ? `goes ${fmtn(x.r.depth)} mm deep` : (x.r.depth > 0 ? `touch (${fmtn(x.r.depth)} mm overlap is within mesh accuracy)` : 'surfaces touch, nothing goes inside')} · <button class="ghost" data-i="${i}" style="padding:0 6px">Focus</button></div></div>`;
  }).join('') : `No collisions between the ${nVis} visible parts.`;
  $('colList').querySelectorAll('button[data-i]').forEach(btn => btn.onclick = () => {
    const x = res[+btn.dataset.i], P = x.a.geo.attributes.position, pts = [];
    for (const v of [...x.r.touchA].slice(0, 2000)) pts.push(new THREE.Vector3().fromBufferAttribute(P, v).applyMatrix4(x.ma));
    if (pts.length) fitTo(new THREE.Sphere().setFromPoints(pts));
  });
}
// while the mechanism moves: flag pairs that touch now but did not touch in the home pose
function liveCollisions() {
  if (!$('colLive').checked || !motion.def) return;
  const now = performance.now();
  if (now - anaState.liveT < 120) return;
  anaState.liveT = now;
  if (!anaState.homeContacts) {
    // shortcut: pairs already touching at home (pins in bores…) are not checked live; a real clash between them would be missed
    anaState.homeContacts = new Set(pairs(true).filter(({ a, b, ma, mb }) => a.geo.boundsTree.intersectsGeometry(b.geo, ma.clone().invert().multiply(mb))).map(({ a, b }) => a.name + '|' + b.name));
  }
  const hit = new Set(), names = [];
  for (const { a, b, ma, mb } of pairs(false)) {
    if (anaState.homeContacts.has(a.name + '|' + b.name)) continue;
    if (a.geo.boundsTree.intersectsGeometry(b.geo, ma.clone().invert().multiply(mb))) { hit.add(a); hit.add(b); names.push(`${a.name} ↔ ${b.name}`); }
  }
  for (const p of model.parts) if (p.alert !== hit.has(p)) { p.alert = hit.has(p); applyPartLook(p); }
  $('colList').classList.toggle('muted', !names.length);
  $('colList').innerHTML = names.length ? `<b style="color:var(--bad)">Colliding now:</b> ${names.map(esc).join(', ')}` : `Live: no new collisions${anaState.homeContacts.size ? ` · ${anaState.homeContacts.size} pair(s) touching at home are not checked` : ''}.`;
}
function onPoseChange() {
  liveCollisions();
  if ((anaState.kind === 'draft' || anaState.kind === 'overhang' || $('massCom').checked) && !anaState.poseRaf) {
    anaState.poseRaf = requestAnimationFrame(() => { anaState.poseRaf = 0; if (anaState.kind === 'draft' || anaState.kind === 'overhang') runAnalysis(); if ($('massCom').checked) renderMass(); });
  }
}

// --- mass properties
const comMarker = (() => {
  const g = new THREE.Group();
  g.add(new THREE.Mesh(new THREE.SphereGeometry(1, 20, 14), new THREE.MeshBasicMaterial({ color: C_SEL, depthTest: false, transparent: true, opacity: 0.9 })));
  for (const ax of [[1, 0, 0], [0, 1, 0], [0, 0, 1]]) {
    const geo = new THREE.BufferGeometry().setFromPoints([new THREE.Vector3(...ax).multiplyScalar(-2.5), new THREE.Vector3(...ax).multiplyScalar(2.5)]);
    g.add(new THREE.Line(geo, new THREE.LineBasicMaterial({ color: 0xfaf9f5, depthTest: false })));
  }
  g.traverse(o => { o.renderOrder = 12; });
  g.visible = false; scene.add(g);
  return g;
})();
function renderMass() {
  if (!model.parts.length) { $('massOut').innerHTML = ''; comMarker.visible = false; return; }
  const rho = Math.max(1e-6, +$('massRho').value || 1) / 1000;   // g/mm³
  const items = model.parts.filter(p => p.visible).map(p => {
    p.massProps ??= ana.massProps(p.geo);
    const mp = p.massProps, m = mp.volume * rho;
    return { p, mass: m, com: mp.com.clone().applyMatrix4(p.pose.matrix), inertia: ana.rotateInertia(mp.inertia.map(r => r.map(x => x * rho)), p.pose.matrix) };
  });
  if (!items.length) { $('massOut').innerHTML = '<div class="d muted">No visible parts.</div>'; comMarker.visible = false; return; }
  const tot = ana.combineMass(items);
  const fm = g => g >= 1000 ? `${fmtn(g / 1000, 3)} kg` : `${fmtn(g, 1)} g`;
  const pr = tot.principal.values.map(v => fmtn(v / 1000, 1));   // g·mm² → kg·mm²
  $('massOut').innerHTML = `<div class="kv" style="margin-top:4px">
      <span>Mass</span><b>${fm(tot.mass)}</b>
      <span>Volume</span><span>${fmtn(tot.mass / rho / 1000, 2)} cm³</span>
      <span>Centre of mass</span><span class="mono">${fmtv(tot.com.toArray())} mm</span>
      <span>Principal inertia</span><span class="mono">${pr.join(' · ')} kg·mm²</span></div>
    ${items.length > 1 ? `<h4>Per part</h4>${items.map(i => `<div class="row" style="margin:2px 0"><span class="grow">${esc(i.p.name)}</span><span class="mono">${fm(i.mass)}</span></div>`).join('')}` : ''}
    <div class="d muted" style="margin-top:6px">Visible parts only, current pose, without the exploded offset.</div>`;
  comMarker.visible = $('massCom').checked;
  comMarker.position.copy(tot.com);
  comMarker.scale.setScalar(model.radius * 0.025);
}

function initAnalysis() {
  document.querySelectorAll('#anaSeg button').forEach(b => b.onclick = () => setAnalysis(b.dataset.k));
  for (const id of ['anaMinWall', 'anaMinDraft', 'anaCrit', 'anaPull', 'anaBuild']) $(id).oninput = () => runAnalysis();
  $('colRun').onclick = runCollisions;
  $('colLive').onchange = e => {
    anaState.homeContacts = null;
    if (!e.target.checked) { for (const p of model.parts) if (p.alert) { p.alert = false; applyPartLook(p); } $('colList').textContent = ''; return; }
    if (!motion.def) toast('Live checking needs motion (Motion tab).', true);
    anaState.liveT = 0; liveCollisions();
  };
  $('massMat').innerHTML = ana.MATERIALS.map(([n, r]) => `<option value="${r}">${n}</option>`).join('') + '<option value="">Custom…</option>';
  let saved = null; try { saved = localStorage.getItem('cadp.density'); } catch { /* default */ }
  $('massRho').value = saved || '7.85';
  $('massMat').value = [...$('massMat').options].some(o => o.value === $('massRho').value) ? $('massRho').value : '';
  $('massMat').onchange = e => { if (e.target.value) $('massRho').value = e.target.value; else $('massRho').focus(); saveRho(); renderMass(); };
  $('massRho').oninput = () => { $('massMat').value = [...$('massMat').options].some(o => o.value === $('massRho').value) ? $('massRho').value : ''; saveRho(); renderMass(); };
  $('massCom').onchange = renderMass;
  function saveRho() { try { localStorage.setItem('cadp.density', $('massRho').value); } catch { /* per-viewer convenience */ } }
}

// --- help
$('bHelp').onclick = () => $('help').classList.add('open');
$('helpClose').onclick = () => $('help').classList.remove('open');
$('help').addEventListener('pointerdown', e => { if (e.target === $('help')) $('help').classList.remove('open'); });

// ================================================================= start
// v2: the grid starts off; settings saved before that keep everything except the grid
try { const { axes: _, v, ...saved } = JSON.parse(localStorage.getItem('cadp.display') || '{}'); if (v !== 2) delete saved.grid; Object.assign(display, saved); } catch { /* defaults */ }
applyDisplay();
initAnalysis();
if (location.search.includes('selftest')) { const ok = ana.selfTest(); toast(ok ? 'Self-test passed' : 'Self-test FAILED', !ok); }
setTool('select');
resize();
poll();
setInterval(() => { if (model.info) loadNotes(false); }, 3000);
setInterval(() => { if (model.info) loadVariants(); }, 4000);  // variants Claude exports later appear in the switcher
setInterval(() => { if (model.info && document.querySelector('#tabs button[data-tab="vers"]').classList.contains('on')) loadVersions(); }, 4000);
window.__cad = { model, motion, setMotionT, motionHome, selection, measurements, section, strokes, notes: () => notes, pickAt, faceHit, setView, setTool, computeMeasure, entGeom, toggleSelect, addMeasurement, openNote, saveShot, setSectionOn, updateSection, loadGhost, clearGhost, versions: () => versions, setOrtho, camera: () => camera, controls };

// ============================================================= settings (whole app) and token savers
// Stored by the server in ~/.CAD4Ai-settings.json, so they apply to every model, project and browser.
let appSettings = {}, appDefaults = {};
const SETTINGS_UI = [
  { sec: 'Notes for Claude (what one note costs)' },
  { k: 'note.parts', label: 'Part names in a note', opts: [['nearby', 'Only near the marked place'], ['all', 'All parts'], ['none', 'None']],
    t: { nearby: 'ok:Recommended. Saves 5–8k tokens in big assemblies, quality practically the same.', all: 'warn:Quality +0–2 %, cost up to +8k tokens per note. Only if Claude keeps missing distant parts.', none: 'bad:Saves a bit more, but quality −15 %: Claude must guess which parts exist.' },
    x: 'A note lists the assembly’s part names so Claude knows what exists. In a big assembly that is the most expensive line: the panel with ~700 parts costs <em>5–8 thousand tokens</em> per note. “Only near the marked place” keeps the parts around your drawing, selection or markers (max 40) and says how many others exist. Small models (≤ 25 parts) always get all names.' },
  { k: 'note.params', label: 'Parameters in a note', opts: [['related', 'Only related ones'], ['all', 'All'], ['none', 'None']],
    t: { related: 'ok:Recommended. Small, and Claude still sees what matters.', all: 'warn:Quality +0–3 %, cost +0.5–3k tokens per note on big scripts.', none: 'bad:Saves ~0.5k tokens, quality −10 %: Claude reads values from the script itself (often costs more).' },
    x: 'The values of the script parameters. “Only related ones” sends the parameters that drive the marked part or place (found in the script, the same as <em>Show related parameters</em>), at most as many as set below, and says how many more there are.' },
  { k: 'note.scriptMap', label: 'Script map', bool: true,
    t: { true: 'ok:Recommended. Saves 8–10k tokens per change, no quality loss.', false: 'bad:Costs 8–10k tokens more per change, quality the same or worse. No reason to turn off.' },
    x: 'Adds the script lines (file:from-to) where the marked parts are built, also in imported modules. Claude reads those few dozen lines instead of the whole script: on the panel (812 lines) that saves roughly <em>8–10 thousand tokens</em> per change.' },
  { k: 'note.screenshot', label: 'Screenshot in a note', bool: true,
    t: { true: 'ok:Recommended. Claude sees what you mean.', false: 'warn:Saves ~1.5k tokens, quality −5 to −20 % for notes without a selection or markers.' },
    x: 'The picture shows Claude what you mean (about <em>1.5 thousand tokens</em>). Turn it off if your notes always have a selection, measurements or markers that say precisely where.' },
  { k: 'note.modelHint', label: 'Model suggestion', bool: true,
    t: { true: 'ok:Recommended. One line (~30 tokens), helps you pick a cheaper model.', false: 'warn:Saves ~30 tokens, you lose the hint. Quality unaffected.' },
    x: 'One line in the note with the cheapest Claude model and effort that should do the request on the first try (from the request text, the script size and the part count). A guide only: you switch the model yourself.' },
  { k: 'note.contextFile', label: 'Project context file', bool: true,
    t: { true: 'ok:Recommended. First note +1–2k tokens, every next one −3–6k tokens. No quality loss.', false: 'warn:Each note on a big script costs 3–6k tokens more (Claude explores again).' },
    x: 'For scripts over 300 lines Claude writes a short <span class="mono">&lt;model&gt;.context.md</span> once (what each function builds, line ranges) and reads it in later notes instead of exploring the script. The first note costs a bit more, the following ones less.' },
  { sec: 'Related parameters' },
  { k: 'related.byValue', label: 'Match by dimension', bool: true,
    t: { true: 'ok:Recommended. Finds more right parameters, costs nothing.', false: 'warn:Some related parameters missed, quality −3 %. No tokens saved.' },
    x: 'Besides tracing the script, a parameter whose value equals the clicked size (a Ø11 hole → <span class="mono">FL_HOLE_D = 11</span>, also 2× and ½×) counts as related.' },
  { k: 'related.max', label: 'How many in a note', num: [3, 40],
    t: n => n === 12 ? 'ok:Recommended (12). Enough for nearly every change.' : n < 12 ? `warn:Saves ~${(12 - n) * 25} tokens, quality −${Math.min(15, (12 - n) * 2)} %: the right parameter may be cut off.` : `warn:Costs ~${(n - 12) * 25} tokens more, quality +0–1 %.`,
    x: 'Upper limit of related parameters sent with a note.' },
  { sec: 'After a rebuild (Params tab)' },
  { k: 'checks.afterRebuild', label: 'Checks', opts: [['basic', 'Validity and volume'], ['full', '+ collisions'], ['off', 'Off']],
    t: { basic: 'ok:Recommended. Catches broken solids in ~5 s, no tokens.', full: 'warn:No tokens, just slower (+5–30 s). Worth it when parts move.', off: 'bad:Faster, but broken geometry goes unnoticed. Saves no tokens.' },
    x: 'Runs on this computer, <em>no tokens</em>. “Validity and volume” checks every solid (BRepCheck) and the volume change against the last rebuild (about 5 s for the panel). “+ collisions” also runs the collision analysis of the Analyze tab and colours the touching places.' },
  { sec: 'Storage' },
  { k: 'history.keep', label: 'Versions kept per model', num: [5, 500],
    t: n => n === 30 ? 'ok:Recommended (30). Does not affect tokens.' : n < 30 ? 'warn:Less disk space, fewer versions to go back to. Tokens unaffected.' : 'warn:More versions to go back to, more disk space. Tokens unaffected.',
    x: 'Every rebuild or export stores a version (STEP + script) in <span class="mono">~/.CAD4Ai/history</span>: one place for all models and sessions, never inside a project or the app folder. Older versions beyond this number are deleted. One version of a large assembly can take several MB.' },
  { sec: 'Quick change (right-click menu)' },
  { k: 'quick.screenshot', label: 'Screenshot with a quick change', bool: true,
    t: { false: 'ok:Recommended. The clicked face says where; ~1.5k tokens saved.', true: 'warn:Cost +1.5k tokens, quality +0–5 % (only helps for vague sentences).' },
    x: 'A quick change sends the clicked face, the related parameters and your sentence. Without the picture it is the cheapest way to ask Claude for a small edit.' },
];
async function loadSettings() {
  try { const r = await api('/api/settings'); appSettings = r.values || {}; appDefaults = r.defaults || {}; } catch { /* older server */ }
}
async function saveSetting(k, v) {
  appSettings[k] = v;
  try { appSettings = (await api('/api/settings', { values: { [k]: v } })).values; } catch (e) { toast('Saving the setting failed: ' + e.message, true); }
}
/** Coloured line under a setting: recommended, or what you trade (quality vs. tokens). */
function tradeNote(o, v) {
  if (!o.t) return '';
  const raw = typeof o.t === 'function' ? o.t(+v) : o.t[String(v)];
  if (!raw) return '';
  const [cls, ...rest] = raw.split(':');
  return `<div class="t ${cls}">${cls === 'ok' ? '✓ ' : '⚠ '}${esc(rest.join(':'))}</div>`;
}
function renderSettings() {
  $('setList').innerHTML = SETTINGS_UI.map(o => {
    if (o.sec) return `<div class="set-sec">${esc(o.sec)}</div>`;
    const v = appSettings[o.k], id = 'set_' + o.k.replace('.', '_');
    const ctl = o.bool ? `<input type="checkbox" id="${id}" data-k="${o.k}" ${v ? 'checked' : ''}>`
      : o.num ? `<input type="number" id="${id}" data-k="${o.k}" min="${o.num[0]}" max="${o.num[1]}" value="${v}" style="width:70px">`
      : `<select id="${id}" data-k="${o.k}">${o.opts.map(([val, t]) => `<option value="${val}" ${v === val ? 'selected' : ''}>${esc(t)}${appDefaults[o.k] === val ? ' (recommended)' : ''}</option>`).join('')}</select>`;
    return `<div class="set"><div class="h"><label for="${id}"><b>${esc(o.label)}</b></label>${ctl}</div>${tradeNote(o, v)}<div class="x">${o.x}</div></div>`;
  }).join('');
  $('setList').querySelectorAll('[data-k]').forEach(c => c.onchange = () => {
    const o = SETTINGS_UI.find(x => x.k === c.dataset.k);
    saveSetting(o.k, o.bool ? c.checked : o.num ? Math.max(o.num[0], Math.min(o.num[1], Math.round(+c.value || 0))) : c.value).then(renderSettings);
  });
}
$('bSettings').onclick = async () => { await loadSettings(); renderSettings(); $('settings').classList.add('open'); };

// ---- Settings tabs: everything the plugin contains (libraries, candidates, rules, tools, skills, data)
let plugCat = null, libSel = null;
const libOpen = new Set();   // open categories of the library tree
const stBadge = st => `<span class="badge ${({ verified: 'ok', formula: 'info', vendor: 'warn', unverified: 'warn' })[st] || ''}">${esc(st || '?')}</span>`;
const lvBadge = lv => `<span class="badge ${({ mandatory: 'bad', check: 'info', default: 'ok', convention: 'warn' })[lv] || ''}">${esc(lv)}</span>`;
async function loadCatalog(force) {
  if (plugCat && !force) return plugCat;
  plugCat = await api('/api/plugin/catalog');
  $('plVersion').textContent = plugCat.version ? 'CAD4Ai ' + plugCat.version : '';
  const n = (plugCat.candidates || []).filter(c => c.status === 'suggested' || c.status === 'new').length;
  $('nCands').textContent = n ? n : '';
  return plugCat;
}
async function plugAct(body) {
  const r = await api('/api/plugin/action', body);
  if (!r.ok) throw new Error(r.error || 'failed');
  return r;
}
const SET_RENDER = { libs: () => renderLibs(), cands: () => renderCands(), rules: () => renderRules(), tools: () => renderTools(), skills: () => renderSkills(), data: () => renderData() };
document.querySelectorAll('#setTabs button').forEach(b => b.onclick = async () => {
  document.querySelectorAll('#setTabs button').forEach(x => x.classList.toggle('on', x === b));
  document.querySelectorAll('.spane').forEach(x => x.classList.toggle('on', x.id === 'sp-' + b.dataset.st));
  $('setReset').style.display = b.dataset.st === 'presets' ? '' : 'none';
  if (b.dataset.st === 'presets') return;
  try { await loadCatalog(); SET_RENDER[b.dataset.st](); }
  catch (e) { $('sp-' + b.dataset.st).innerHTML = `<div class="muted">Could not load: ${esc(e.message)}</div>`; }
});
function famCode(f, row, i) {
  if (f.codes) return f.codes[i ?? f.rows.indexOf(row)] || null;   // registry families: the server checked each code
  const k = String(row[0]);
  if (/^M\d/.test(k) && /M\d/.test(f.example)) return f.example.replace(/M\d+(\.\d+)?/, k);
  if (f.id === 'bearing') return k;
  if (f.id === 'NEMA') return `${k} x40`;
  if (f.id === 'profile') return `${k}x200`;
  if (f.id === 'DIN 471' || f.id === 'DIN 472') return `${f.id} ${k}`;
  if (f.id === 'key' || f.id === 'thread') return null;
  return f.example || null;
}
function renderLibs() {
  const q = ($('libQ').value || '').toLowerCase();
  const norm = s => String(s).toLowerCase().normalize('NFD').replace(/[̀-ͯ]/g, '');
  const words = norm(q).split(/\s+/).filter(Boolean);
  const fams = plugCat.libraries.filter(f => {
    const hay = norm([f.title, f.id, f.path || '', f.aliases, f.example, f.rows.map(r => r[0]).join(' ')].join(' '));
    return words.every(w => hay.includes(w));
  });
  // tree: category (first path segment) > sub-folder > families, as in CAD part libraries
  const groups = new Map();
  for (const f of fams) {
    const [top, ...rest] = String(f.path || 'Ostatní').split('/');
    const sub = rest.join(' / ');
    if (!groups.has(top)) groups.set(top, new Map());
    const g = groups.get(top);
    if (!g.has(sub)) g.set(sub, []);
    g.get(sub).push(f);
  }
  const item = f => `<div class="libitem ${libSel === f.id ? 'on' : ''}" data-id="${esc(f.id)}" style="padding-left:18px"><span class="t">${esc(f.title)}</span>${f.origin === 'user' ? '<span class="badge info">own</span>' : ''}${stBadge(f.status)}</div>`;
  $('libList').innerHTML = [...groups].map(([top, subs]) => {
    const n = [...subs.values()].reduce((a, l) => a + l.length, 0);
    const open = words.length || libOpen.has(top) || [...subs.values()].some(l => l.some(f => f.id === libSel));
    return `<details class="libcat" data-top="${esc(top)}" ${open ? 'open' : ''}><summary style="cursor:pointer;font-weight:600;padding:4px 2px">${esc(top)} <span class="muted">(${n})</span></summary>`
      + [...subs].map(([sub, list]) => (sub ? `<div class="muted" style="padding:4px 2px 2px 8px;font-size:11px">${esc(sub)}</div>` : '') + list.map(item).join('')).join('')
      + `</details>`;
  }).join('') + `<div style="margin-top:10px"><button class="ghost" id="libNew">+ Own family…</button></div>`;
  $('libList').querySelectorAll('details.libcat').forEach(el => el.ontoggle = () => { if (el.open) libOpen.add(el.dataset.top); else libOpen.delete(el.dataset.top); });
  $('libList').querySelectorAll('.libitem').forEach(el => el.onclick = () => { libSel = el.dataset.id; renderLibs(); });
  $('libNew').onclick = async () => {
    const id = prompt('Id of the new family (e.g. alu30, hinge_small):'); if (!id) return;
    try { const r = await plugAct({ action: 'new-family', id, title: id }); toast('Created ' + r.file + ' - ask Claude to fill it in.'); await loadCatalog(true); renderLibs(); } catch (e) { toast(e.message, true); }
  };
  const f = plugCat.libraries.find(x => x.id === libSel);
  if (!f) { $('libMain').innerHTML = `<div class="muted">${plugCat.libraries.length} families. Pick one on the left, or search. Claude calls them by code, e.g. <span class="mono">place("ISO 4762 M5x16", at=…)</span>.</div>`; return; }
  const code3d = f.codes ? f.example : (f.rows.length ? famCode(f, f.rows[0], 0) : f.example);
  $('libMain').innerHTML = `<div class="row" style="margin:0;gap:8px;align-items:center"><b>${esc(f.title)}</b>${stBadge(f.status)}${f.origin === 'user' ? '<span class="badge info">own family</span>' : ''}</div>
    ${f.path ? `<div class="muted" style="margin-top:2px">${esc(f.path.replace(/\//g, ' › '))}</div>` : ''}
    <div class="mono" style="margin-top:6px;font-size:11.5px">part("${esc(f.example)}")${f.tools?.length ? ` · tools: ${f.tools.map(esc).join(', ')}` : ''}</div>
    <div class="muted" style="margin-top:4px">Source: ${esc(f.source || '—')}</div>
    ${f.note ? `<div class="muted" style="margin-top:4px">${esc(f.note)}</div>` : ''}
    ${f.file ? `<div class="muted mono" style="margin-top:4px">${esc(f.file)}</div>` : ''}
    <div class="row" style="margin:8px 0 0;gap:6px"><input id="libCode" value="${esc(code3d || '')}" style="flex:1" placeholder="code, e.g. ${esc(f.example)}"><button class="ghost" id="libInfo">Info</button><button class="primary" id="libOpen">Open in 3D</button></div>
    <div id="libOut"></div>
    <table class="ptable"><thead><tr>${f.columns.map(c => `<th>${esc(c)}</th>`).join('')}<th></th></tr></thead><tbody>
    ${f.rows.map((r, i) => `<tr>${r.map(v => `<td>${esc(v)}</td>`).join('')}<td>${famCode(f, r, i) ? `<button class="ghost" data-row="${i}">3D</button>` : ''}</td></tr>`).join('')}</tbody></table>`;
  const open = async code => { try { await plugAct({ action: 'open-part', code }); toast('Opened ' + code + ' as a model tab.'); } catch (e) { toast(e.message, true); } };
  $('libOpen').onclick = () => open($('libCode').value.trim());
  $('libInfo').onclick = async () => {
    try { const r = await plugAct({ action: 'part-info', code: $('libCode').value.trim() }); $('libOut').innerHTML = `<div class="pinfo">${esc(JSON.stringify(r.info, null, 1))}</div>`; }
    catch (e) { $('libOut').innerHTML = `<div class="pinfo">${esc(e.message)}</div>`; }
  };
  $('libMain').querySelectorAll('[data-row]').forEach(b => b.onclick = () => open(famCode(f, f.rows[+b.dataset.row], +b.dataset.row)));
}
$('libQ').oninput = () => { if (plugCat) renderLibs(); };
function renderCands() {
  const live = c => c.status === 'suggested' || c.status === 'new';
  const cs = (plugCat.candidates || []).slice().sort((a, b) => (live(a) ? 0 : 1) - (live(b) ? 0 : 1) || b.count - a.count);
  $('sp-cands').innerHTML = `<div class="muted">Parts in your models that could become a library family (found locally after each export, no tokens). Accept = a family skeleton is created in <span class="mono">~/.CAD4Ai/library/families</span>; then ask Claude to fill it in.</div>`
    + (cs.length ? `<table class="ptable"><thead><tr><th>Candidate</th><th>Why</th><th>Examples</th><th>Status</th><th></th></tr></thead><tbody>${cs.map(c => `<tr>
      <td><b>${esc(c.title)}</b><div class="muted mono" style="font-size:10.5px">${esc(c.id.slice(0, 60))}</div></td>
      <td>${esc(c.kind)} · ${c.count}× · ${c.models.length} model(s)</td><td>${esc(c.examples.slice(0, 3).join(', '))}</td>
      <td><span class="badge ${c.status === 'accepted' ? 'ok' : c.status === 'dismissed' ? '' : 'warn'}">${esc(c.status)}</span></td>
      <td style="white-space:nowrap">${live(c) ? `<button class="primary" data-c="${esc(c.id)}" data-d="accept">Accept</button> <button class="ghost" data-c="${esc(c.id)}" data-d="dismiss">Dismiss</button>` : `<button class="ghost" data-c="${esc(c.id)}" data-d="reset">Reset</button>`}</td></tr>`).join('')}</tbody></table>`
      : '<div class="muted" style="margin-top:10px">Nothing yet. Candidates appear after models are exported.</div>');
  $('sp-cands').querySelectorAll('[data-c]').forEach(b => b.onclick = async () => {
    try { const r = await plugAct({ action: 'candidate', id: b.dataset.c, decision: b.dataset.d }); if (r.family_file) toast('Family skeleton: ' + r.family_file); await loadCatalog(true); renderCands(); }
    catch (e) { toast(e.message, true); }
  });
}
function renderRules() {
  const groups = [...new Set(plugCat.rules.map(r => r.group))];
  $('sp-rules').innerHTML = `<div class="muted">Rules and conventions the tools apply locally. <span class="badge bad">mandatory</span> must hold · <span class="badge info">check</span> verified automatically · <span class="badge ok">default</span> used unless you say otherwise · <span class="badge warn">convention</span> how things are represented.</div>`
    + groups.map(g => `<div class="rulegrp">${esc(g)}</div>` + plugCat.rules.filter(r => r.group === g).map(r => `<div class="rule"><div class="row" style="margin:0;gap:8px"><b>${esc(r.title)}</b>${lvBadge(r.level)}</div><div>${esc(r.text)}</div><div class="w mono">${esc(r.where)}</div></div>`).join('')).join('');
}
function renderTools() {
  $('sp-tools').innerHTML = `<div class="muted">Local tools Claude calls instead of writing scripts: <span class="mono">python …/viewer/cad4ai.py &lt;command&gt;</span>. Heavy work on this PC, a few lines of JSON back.</div>
    <table class="ptable"><thead><tr><th>Command</th><th>Arguments</th><th>What it does</th></tr></thead><tbody>${plugCat.tools.map(t => `<tr><td class="mono">${esc(t.cmd)}</td><td class="mono">${esc(t.args)}</td><td>${esc(t.what)}</td></tr>`).join('')}</tbody></table>`;
}
function renderSkills() {
  $('sp-skills').innerHTML = `<div class="rulegrp">Skills (instructions Claude loads only when the task needs them)</div>`
    + plugCat.skills.map(k => `<details class="skill"><summary><b>${esc(k.name)}</b> — <span class="muted">${esc(k.description.slice(0, 160))}${k.description.length > 160 ? '…' : ''}</span></summary>${k.scripts.length ? `<div class="muted mono">scripts: ${esc(k.scripts.join(', '))}</div>` : ''}<pre>${esc(k.body)}</pre></details>`).join('')
    + `<div class="rulegrp">Hooks (run automatically around Claude's tool calls)</div><table class="ptable"><thead><tr><th>Event</th><th>On</th><th>What</th><th>Timeout</th></tr></thead><tbody>${plugCat.hooks.map(h => `<tr><td>${esc(h.event)}</td><td class="mono">${esc(h.matcher)}</td><td>${esc(h.what)}</td><td>${h.timeout ?? ''} s</td></tr>`).join('')}</tbody></table>`;
}
function renderData() {
  const d = plugCat.data;
  $('sp-data').innerHTML = `<div class="muted">Everything CAD4Ai keeps lives in <span class="mono">${esc(d.home)}</span>. The app folder (<span class="mono">${esc(d.app_folder)}</span>) holds no project data.</div>
    <table class="ptable"><thead><tr><th>Folder</th><th>Size</th><th>Files</th><th>What</th><th></th></tr></thead><tbody>${d.folders.map(f => `<tr><td class="mono">${esc(f.name)}</td><td>${f.mb} MB</td><td>${f.files}</td><td>${esc(f.what)}</td><td><button class="ghost" data-rev="${esc(f.path)}">Open</button></td></tr>`).join('')}</tbody></table>
    <div class="row" style="margin-top:10px;gap:6px"><button class="ghost" id="dTrim">Trim cache now</button><button class="ghost" id="dIndex">Rebuild script index</button><button class="ghost" id="dReload">Refresh</button></div>`;
  $('sp-data').querySelectorAll('[data-rev]').forEach(b => b.onclick = () => plugAct({ action: 'reveal', path: b.dataset.rev }).catch(e => toast(e.message, true)));
  $('dTrim').onclick = async () => { try { const r = await plugAct({ action: 'trim-cache' }); toast(`Cache trimmed: ${r.removed} files removed.`); await loadCatalog(true); renderData(); } catch (e) { toast(e.message, true); } };
  $('dIndex').onclick = async () => { try { await plugAct({ action: 'rebuild-index' }); toast('Script index is being rebuilt in the background.'); } catch (e) { toast(e.message, true); } };
  $('dReload').onclick = async () => { await loadCatalog(true); renderData(); };
}

$('setClose').onclick = $('setOk').onclick = () => $('settings').classList.remove('open');
$('settings').onclick = e => { if (e.target.id === 'settings') $('settings').classList.remove('open'); };
$('setReset').onclick = async () => {
  try { appSettings = (await api('/api/settings', { values: appDefaults })).values; renderSettings(); toast('Settings back to defaults.'); } catch (e) { toast(e.message, true); }
};
loadSettings();

/** Parts near some points (bounding boxes, exploded positions included): what a note is about. */
function nearPartNames(points) {
  const pts = points.filter(p => Array.isArray(p) && p.length === 3).map(p => new THREE.Vector3(...p));
  if (!pts.length || model.parts.length <= 25) return null;
  const r = Math.max(model.radius * 0.08, 30);
  const scored = model.parts.map(p => {
    const b = p.bbox.clone().translate(p.group.position);
    return { p, d: Math.min(...pts.map(q => b.distanceToPoint(q))) };
  }).filter(x => x.d <= r).sort((a, b) => a.d - b.d);
  return [...new Set(scored.map(x => x.p.name))].slice(0, 40);
}

/** Sizes of the clicked face that may equal a parameter (Ø, R, length). */
function faceValues(h) {
  const fa = model.parts[h.part]?.an.faces[h.faceId];
  if (!fa || fa.type !== 'cylinder') return [];
  return [2 * fa.radius, fa.radius, fa.length].map(r2);
}
function fetchRelated(h) {
  return api('/api/related', { parts: [model.parts[h.part].name], values: faceValues(h) });
}
async function showRelated(h) {
  const p = model.parts[h.part];
  try {
    const r = await fetchRelated(h);
    if (r.error && !r.params.length) return toast('Related parameters: ' + r.error, true);
    const known = new Set(params.map(x => x.name));
    const list = r.params.filter(x => known.has(x.name) && x.score >= 0.15).slice(0, 30);
    if (!list.length) return toast(`No parameter found that drives ${p.name}.`);
    relState = { label: p.name, list };
    paramGrpClosed.delete(REL_G);
    $('paramSearch').value = '';
    paramFilter = 'all';
    openTab('params'); renderParams();
    $('paramList').scrollIntoView({ block: 'start' });
  } catch (e) { toast('Related parameters failed: ' + e.message, true); }
}

// ---- quick change: one face, related parameters, one sentence; few tokens
let quickCtx = null;
async function openQuick(h) {
  const p = model.parts[h.part], fa = p.an.faces[h.faceId];
  quickCtx = { h, part: p.name, desc: fa ? describeFace(fa) : '', rel: [] };
  $('qWhere').textContent = `${p.name}${fa ? ` · face #${h.faceId}: ${quickCtx.desc}` : ''}`;
  $('qChips').innerHTML = '<span class="muted">Looking for related parameters…</span>';
  $('qText').value = '';
  $('qInfo').textContent = appSettings['quick.screenshot'] ? 'A screenshot is sent too (Settings).' : 'No screenshot: the face, the point and the parameters say where (cheapest).';
  $('quick').classList.add('open'); $('qText').focus();
  try {
    const r = await fetchRelated(h);
    const known = new Map(params.map(x => [x.name, x]));
    quickCtx.rel = r.params.filter(x => known.has(x.name)).slice(0, 8);
    $('qChips').innerHTML = quickCtx.rel.length
      ? quickCtx.rel.map(x => `<button class="ghost" data-n="${x.name}" title="${esc(x.why)} · click to add it to the request">${esc(x.name)} = ${esc(String(known.get(x.name).value))}</button>`).join('')
      : '<span class="muted">No related parameter found.</span>';
    $('qChips').querySelectorAll('[data-n]').forEach(b => b.onclick = () => {
      const t = $('qText'); t.value = (t.value ? t.value.replace(/\s*$/, ' ') : '') + b.dataset.n + ' '; t.focus();
    });
  } catch { $('qChips').innerHTML = ''; }
}
function closeQuick() { $('quick').classList.remove('open'); quickCtx = null; }
$('qCancel').onclick = closeQuick;
$('quick').onclick = e => { if (e.target.id === 'quick') closeQuick(); };
$('qText').onkeydown = e => {
  e.stopPropagation();
  if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); $('qSend').click(); } else if (e.key === 'Escape') closeQuick();
};
$('qSend').onclick = async () => {
  const comment = $('qText').value.trim();
  if (!comment) { $('qText').focus(); return toast('Write what should change.', true); }
  const { h, part, desc } = quickCtx;
  const point = h.local.map(r2);
  const payload = {
    kind: 'quick', model: model.info.path, name: model.info.name, step: model.info.step || null, comment,
    features: [{ index: 1, type: 'face', part, title: `Face #${h.faceId} of ${part}`, description: desc, point }],
    strokes: [], measurements: [], markers: [], paint: [], anchor: point, anchorPart: part,
    parts: model.parts.map(p => p.name), nearParts: nearPartNames([h.world.toArray()]) || [part], source: model.source,
    image: appSettings['quick.screenshot'] ? composeShot().toDataURL('image/png') : '',
  };
  $('qSend').disabled = true;
  try { await api('/api/annotate', payload); closeQuick(); toast('Sent to Claude ✔'); loadNotes(true); }
  catch (e) { toast('Sending failed: ' + e.message, true); }
  finally { $('qSend').disabled = false; }
};

// ---- checks after a parameter rebuild (on this computer, no tokens)
let lastCheck = null;
async function afterRebuildChecks() {
  const mode = appSettings['checks.afterRebuild'] || 'basic';
  const el = $('paramCheck');
  if (mode === 'off') { el.textContent = ''; return; }
  el.style.color = ''; el.textContent = 'Checking the model…';
  const out = [];
  try {
    const r = await api('/api/check');
    if (!r.ok) out.push(`✗ check failed: ${r.error || '?'}`);
    else {
      out.push(r.invalid.length ? `✗ invalid B-rep: ${r.invalid.slice(0, 6).join(', ')}${r.invalid.length > 6 ? '…' : ''}` : `✓ all ${r.parts} solids valid`);
      if (lastCheck && lastCheck.path === model.info.path) {
        const dv = r.volume - lastCheck.volume;
        const changed = Object.keys(r.vols).filter(k => Math.abs((lastCheck.vols[k] ?? 0) - r.vols[k]) > Math.max(1, r.vols[k] * 1e-4));
        out.push(`volume ${fmtn(r.volume / 1000, 1)} cm³ (${dv >= 0 ? '+' : ''}${fmtn(dv / 1000, 2)})${changed.length ? ` · changed: ${changed.slice(0, 5).join(', ')}${changed.length > 5 ? ` +${changed.length - 5}` : ''}` : ''}`);
      } else out.push(`volume ${fmtn(r.volume / 1000, 1)} cm³`);
      lastCheck = { path: model.info.path, volume: r.volume, vols: r.vols };
      out.push(`${r.seconds} s`);
    }
    if (mode === 'full' && model.parts.length > 1) {
      runCollisions();  // mesh check: highlights pairs in the Analyze tab
      el.textContent = out.join(' · ') + ' · exact collisions…';
      try {
        const c = await api('/api/collide');  // exact B-rep check (cad4ai collide, all cores)
        if (!c.ok) out.push(`✗ collision check failed: ${c.error || '?'}`);
        else {
          const n = c.collisions.length;
          out.push(n ? `✗ ${n} colliding pair${n > 1 ? 's' : ''}: ${c.collisions.slice(0, 3).map(x => `${x.a}×${x.b} ${fmtn(x.overlap_mm3, 1)} mm³`).join(', ')}`
                     : `✓ no collisions (${c.pairs_checked} pairs, B-rep)`);
          if (c.expected_fastener_overlaps) out.push(`${c.expected_fastener_overlaps} fastener overlaps ignored`);
        }
      } catch (e) {
        const n = anaState.colliding?.length ?? 0;
        out.push(n ? `✗ ${n} colliding pair${n > 1 ? 's' : ''} (Analyze tab)` : '✓ no collisions');
      }
    }
    el.textContent = out.join(' · ');
    el.style.color = el.textContent.includes('✗') ? 'var(--bad)' : '';
  } catch (e) { el.textContent = 'Check failed: ' + e.message; }
}

// ---- variants from one parameter (no Claude)
function renderSweep() {
  const nums = params.filter(p => p.type !== 'bool');
  $('sweepBox').style.display = nums.length ? '' : 'none';
  const cur = $('swName').value;
  $('swName').innerHTML = nums.map(p => `<option value="${p.name}">${esc(p.name)} = ${p.value}${p.unit ? ' ' + esc(p.unit) : ''}</option>`).join('');
  if (nums.some(p => p.name === cur)) $('swName').value = cur;
  swFill();
}
function swFill() {
  const p = params.find(x => x.name === $('swName').value);
  if (!p) return;
  const st = p.type === 'int' ? 1 : paramStep(p) * 10;
  $('swFrom').value = r2(p.value - 2 * st); $('swTo').value = r2(p.value + 2 * st); $('swStep').value = r2(st);
  swCount();
}
function swValues() {
  const a = +$('swFrom').value, b = +$('swTo').value, st = Math.abs(+$('swStep').value);
  if (!isFinite(a) || !isFinite(b) || !st) return [];
  const out = [];
  for (let v = Math.min(a, b); v <= Math.max(a, b) + 1e-9 && out.length < 13; v += st) out.push(r2(v));
  return out;
}
function swCount() { const n = swValues().length; $('swInfo').textContent = n > 12 ? 'too many values (max 12)' : `${n} variant${n === 1 ? '' : 's'}`; $('swRun').disabled = !n || n > 12; }
$('swName').onchange = swFill;
for (const id of ['swFrom', 'swTo', 'swStep']) $(id).oninput = swCount;
$('swRun').onclick = async () => {
  const vals = swValues(), name = $('swName').value;
  if (!confirm(`Rebuild the model ${vals.length}× (${name} = ${vals.join(', ')}) and save each as a variant next to the model?`)) return;
  $('swRun').disabled = true; $('swInfo').textContent = 'Rebuilding…';
  try {
    const r = await api('/api/sweep', { name, values: vals });
    $('swInfo').textContent = `${r.made.length} variant${r.made.length === 1 ? '' : 's'} saved${r.errors.length ? `, ${r.errors.length} failed` : ''}`;
    if (r.errors.length) toast('Some values failed: ' + r.errors.join(' | '), true);
    loadVariants();
  } catch (e) { $('swInfo').textContent = 'Failed: ' + e.message; }
  finally { $('swRun').disabled = false; }
};


// ============================================================== windows: Checks · Compute · System
// Full-size pages over the 3D view, opened from the Window tabs at the top; the 3D model stays loaded.
const ovGroup = new THREE.Group(); ovGroup.renderOrder = 20; scene.add(ovGroup);
function ovClear() { for (const o of [...ovGroup.children]) { ovGroup.remove(o); o.geometry?.dispose(); o.material?.dispose(); } $('ovBar').style.display = 'none'; }
function ovShow(label) { $('ovBar').style.display = ''; $('ovText').textContent = label; }
function ovMarker(p, color = 0xe5655a, size = 14) {
  const g = new THREE.BufferGeometry().setAttribute('position', new THREE.Float32BufferAttribute(p, 3));
  const m = new THREE.Points(g, new THREE.PointsMaterial({ color, size, sizeAttenuation: false, depthTest: false }));
  m.renderOrder = 21; ovGroup.add(m);
}
function heat(t) { // blue → cyan → green → yellow → red
  t = Math.max(0, Math.min(1, t));
  const c = [[0.2, 0.3, 1], [0, 0.9, 1], [0.2, 0.9, 0.2], [1, 0.9, 0.1], [1, 0.15, 0.1]];
  const x = t * 4, i = Math.min(3, Math.floor(x)), f = x - i;
  return c[i].map((v, k) => v + (c[i + 1][k] - v) * f);
}
function flyToPoint(p, r) {
  fitTo(new THREE.Sphere(new THREE.Vector3(p[0], p[1], p[2]), Math.max(r || 0, model.radius * 0.08)));
}
function showWin(name) {
  document.querySelectorAll('.pages [data-win]').forEach(a => a.classList.toggle('on', a.dataset.win === name));
  document.querySelector('.pages a[href="/"]').classList.toggle('on', !name);
  $('win').style.display = name ? '' : 'none';
  if (name) ({ checks: renderChecksWin, compute: renderComputeWin, system: renderSystemWin })[name]();
}
document.querySelectorAll('.pages [data-win]').forEach(a => a.onclick = e => { e.preventDefault(); showWin(a.dataset.win); });
document.querySelector('.pages a[href="/"]').addEventListener('click', e => { if ($('win').style.display !== 'none') { e.preventDefault(); showWin(null); } });
$('ovClear').onclick = ovClear;
const back3d = () => showWin(null);
async function runJob(body, el, label) {
  el.innerHTML = `<div class="muted">${esc(label || 'Computing')} on this computer… <span class="spin"></span></div>`;
  const r = await api('/api/job', body);
  if (!r.ok) throw new Error(r.error || 'could not start');
  for (;;) {
    await new Promise(res => setTimeout(res, 900));
    const j = await api('/api/job?id=' + r.id);
    if (j.state === 'gone') throw new Error('job lost (server restarted?)');
    if (j.state === 'done') { if (j.result && j.result.ok === false) throw new Error(j.result.error || 'failed'); return { ...j.result, _s: j.seconds }; }
    el.querySelector('.muted').firstChild.textContent = `${label || 'Computing'} on this computer… ${Math.round((Date.now() / 1000) - j.t0)} s `;
  }
}
const card = (title, body, open = true) => `<details class="wcard" ${open ? 'open' : ''}><summary>${title}</summary><div class="wc">${body}</div></details>`;
const tokens = chars => Math.round(chars / 3.6);

// ---- Checks
let lastReport = null;
async function renderChecksWin(force) {
  const w = $('winBody');
  if (!model.info) { w.innerHTML = '<div class="muted">No model open.</div>'; return; }
  w.innerHTML = `<div class="whead"><h3>Checks</h3><span class="muted">${esc(model.info.name || '')}</span><span class="grow"></span><button class="ghost" id="wcRefresh">Refresh</button><button class="primary" id="wcBack">3D model</button></div><div id="wcOut"></div><div id="wcLog"></div>`;
  $('wcBack').onclick = back3d;
  $('wcRefresh').onclick = () => { lastReport = null; renderChecksWin(true); };
  renderHookLog();
  try {
    if (!lastReport || lastReport.model !== (model.info.step || model.info.path) || force) lastReport = await runJob({ tool: 'report' }, $('wcOut'), 'Reading the checks');
  } catch (e) { if ($('wcOut')) $('wcOut').innerHTML = `<div class="muted">${esc(e.message)}</div>`; return; }
  if (!$('wcOut')) return; // the window was switched meanwhile
  const r = lastReport, c = r.collisions || {};
  const coll = (c.collisions || []).map((x, i) => `<tr><td>${esc(x.a)} × ${esc(x.b)}</td><td>${x.overlap_mm3} mm³</td><td>${esc(x.note || '')}</td><td><button class="ghost" data-cp="${i}">Show</button></td></tr>`).join('');
  const ok = b => `<span class="badge ${b ? 'ok' : 'bad'}">${b ? 'OK' : 'FAIL'}</span>`;
  let html = `<div class="kpis"><div><b>${r.parts_n}</b><span>parts</span></div><div><b>${r.size.map(v => fmtn(v, 1)).join(' × ')}</b><span>mm</span></div><div><b>${fmtn(r.mass_g / 1000, 2)}</b><span>kg</span></div>
    <div><b>${(c.collisions || []).length}</b><span>collisions</span></div><div><b>${r.invalid.length}</b><span>invalid solids</span></div><div><b>${r.expect ? r.expect.ok + '/' + r.expect.n : '—'}</b><span>expect()</span></div></div>`;
  html += card(`Collisions ${ok(!(c.collisions || []).length)}`, (coll ? `<table class="ptable"><thead><tr><th>Parts</th><th>Overlap</th><th>Note</th><th></th></tr></thead><tbody>${coll}</tbody></table>` : '<div class="muted">No collisions.</div>')
    + `<div class="muted" style="margin-top:6px">${c.pairs_checked ?? 0} pairs checked (${c.pairs_reused ?? 0} reused) · ${c.expected_fastener_overlaps ?? 0} thread engagements (expected) · ${c.expected_flexible_contacts ?? 0} cable/strap contacts · ${Object.keys(c.self_overlaps || {}).length} parts made of overlapping solids · ${c.touching_n ?? 0} touching pairs</div>`
    + ((c.fastener_overlaps || []).length ? `<div style="margin-top:6px"><button class="ghost" id="wcThreads">Show thread engagements in 3D</button></div>` : ''));
  const ex = r.expect;
  html += card(`Design intent – expect() ${ex ? ok(ex.ok === ex.n && (r.expect_deferred || []).every(d => d.ok)) : ''}`, ex
    ? `<pre class="wpre">${esc(ex.text)}</pre>${(r.expect_deferred || []).map(d => `<div>${ok(d.ok)} ${esc(d.rule)} ${esc(d.bad.join('; '))}</div>`).join('')}`
    : '<div class="muted">The script has no expect() lines (or this file was not exported by it). Ask Claude to add them for the sizes you care about.</div>', !!ex);
  html += card('Change since the previous version', r.diff.length ? `<pre class="wpre">${esc(r.diff.join('\n'))}</pre>` : '<div class="muted">No previous version to compare (or nothing changed).</div>', r.diff.length > 0);
  if ((r.guard || []).length) html += card('<span class="badge warn">Unexpected changes</span>', `<pre class="wpre">${esc(r.guard.join('\n'))}</pre>`);
  if (r.lint) html += card(`Script lint ${ok(!r.lint.filter(l => l.level !== 'info').length)}`, r.lint.length
    ? `<div class="muted mono">${esc(r.script)}</div><table class="ptable"><tbody>${r.lint.map(l => `<tr><td>${l.line}</td><td><span class="badge ${l.level === 'error' ? 'bad' : l.level === 'warn' ? 'warn' : ''}">${esc(l.level)}</span></td><td>${esc(l.msg)}</td></tr>`).join('')}</tbody></table>`
    : '<div class="muted">No issues.</div>', r.lint.some(l => l.level !== 'info'));
  if ((r.candidates || []).length) html += card('Library candidates from this model', r.candidates.map(k => `<div>• <b>${esc(k.title)}</b> <span class="muted">${esc(k.kind)} · ${k.count}× · ${esc(k.examples.slice(0, 3).join(', '))}</span></div>`).join('') + '<div class="muted" style="margin-top:4px">Accept or dismiss in Settings → Candidates.</div>', false);
  // parts.json editor
  const pj = r.parts_json || {}, TYPES = ['', 'custom', 'fastener', 'bearing', 'seal', 'spring', 'purchased', 'electrical', 'other'];
  const pnames = [...new Set(r.parts.map(p => p.name.replace(/(#\d+)?(~\d+)?$/, '')))].slice(0, 400);
  html += card('Part data (parts.json)', `<div class="muted">Type, material and standard of each part: the viewer groups by type, masses use the material, fastener / bearing types steer the collision check.</div>
    <input id="pjQ" placeholder="Filter parts…" style="margin:6px 0;width:100%;box-sizing:border-box">
    <table class="ptable" id="pjTable"><thead><tr><th>Part</th><th>Type</th><th>Material</th><th>Standard</th></tr></thead><tbody>${pnames.map(n => { const e = pj[n] || {}; return `<tr data-n="${esc(n)}"><td>${esc(n)}</td><td><select data-k="type">${TYPES.map(t => `<option ${e.type === t ? 'selected' : ''}>${t}</option>`).join('')}</select></td><td><input data-k="material" value="${esc(e.material || '')}" placeholder="S235, AlMgSi, PETG…"></td><td><input data-k="standard" value="${esc(e.standard || '')}"></td></tr>`; }).join('')}</tbody></table>
    <div class="row" style="margin-top:6px"><button class="primary" id="pjSave">Save parts.json</button><span class="muted" id="pjMsg"></span></div>`, false);
  $('wcOut').innerHTML = html;
  $('wcOut').querySelectorAll('[data-cp]').forEach(b => b.onclick = () => {
    const x = c.collisions[+b.dataset.cp]; ovClear(); ovMarker(x.at, 0xe5655a, 18); ovShow(`Collision ${x.a} × ${x.b}`); back3d(); flyToPoint(x.at, (x.len || 10) * 2);
  });
  if ($('wcThreads')) $('wcThreads').onclick = () => { ovClear(); ovMarker(c.fastener_overlaps.flatMap(x => x.at), 0x5ac87a, 12); ovShow(`${c.fastener_overlaps.length} thread engagements`); back3d(); };
  $('pjQ').oninput = () => { const q = $('pjQ').value.toLowerCase(); $('pjTable').querySelectorAll('tbody tr').forEach(tr => tr.style.display = tr.dataset.n.toLowerCase().includes(q) ? '' : 'none'); };
  $('pjSave').onclick = async () => {
    const parts = {};
    $('pjTable').querySelectorAll('tbody tr').forEach(tr => { const e = {}; tr.querySelectorAll('[data-k]').forEach(i => e[i.dataset.k] = i.value.trim()); const o = pj[tr.dataset.n] || {}; if (Object.keys(e).some(k => (o[k] || '') !== e[k])) parts[tr.dataset.n] = e; });
    if (!Object.keys(parts).length) { $('pjMsg').textContent = ' nothing changed'; return; }
    try { const res = await api('/api/partsjson', { parts }); $('pjMsg').textContent = ` saved ${Object.keys(parts).length} part(s) → ${res.file}`; Object.assign(pj, parts); } catch (e) { toast(e.message, true); }
  };
}
async function renderHookLog() {
  let items = [];
  try { items = (await api('/api/hooklog?n=150')).items; } catch { /* old server */ }
  const sum = items.reduce((a, i) => a + i.chars, 0);
  if (!$('wcLog')) return;
  $('wcLog').innerHTML = card(`Hook log <span class="muted">— what the hooks handed to Claude (last ${items.length}, ≈${tokens(sum)} tokens)</span>`,
    items.length ? `<table class="ptable"><thead><tr><th>When</th><th>Kind</th><th>≈ tokens</th><th>Folder</th><th>Text</th></tr></thead><tbody>${items.map(i => `<tr><td style="white-space:nowrap">${new Date(i.t * 1000).toLocaleString()}</td><td><span class="badge">${esc(i.kind)}</span></td><td>${tokens(i.chars)}</td><td class="mono" style="font-size:10.5px">${esc((i.cwd || '').split(/[\\/]/).slice(-2).join('/'))}</td><td><details><summary class="muted">${esc(i.text.split('\n')[0].slice(0, 90))}</summary><pre class="wpre">${esc(i.text)}</pre></details></td></tr>`).join('')}</tbody></table>
      <div class="muted" style="margin-top:6px">Tokens are estimated from the text length (≈3.6 characters per token). Each report replaces work Claude would otherwise do itself: a check script, a screenshot, trial-and-error fixes.</div>`
      : '<div class="muted">Nothing logged yet. Entries appear when Claude works in a CAD folder (hooks of plugin 0.31+).</div>', false);
}

// ---- Compute
let lastParts = null;
async function partNames() {
  const key = model.info.step || model.info.path;
  if (lastReport?.parts && lastReport.model === key) return lastReport.parts.map(p => p.name);
  if (!lastParts || lastParts.key !== key) {
    let names;
    try { names = (await runJob({ tool: 'report' }, $('cmpParts'), 'Reading the parts')).parts.map(p => p.name); } catch { names = model.parts.map(p => p.name); }
    lastParts = { key, names };
    if ($('cmpParts')) $('cmpParts').innerHTML = '';
  }
  return lastParts.names;
}
async function renderComputeWin() {
  const w = $('winBody');
  if (!model.info) { w.innerHTML = '<div class="muted">No model open.</div>'; return; }
  w.innerHTML = `<div class="whead"><h3>Compute</h3><span class="muted">${esc(model.info.name || '')} — runs on this computer, no tokens</span><span class="grow"></span><button class="primary" id="wcBack">3D model</button></div><div id="cmpParts"></div><div id="cmpBody"></div>`;
  $('wcBack').onclick = back3d;
  const names = await partNames();
  if (!$('cmpBody')) return;
  const opts = names.map(n => `<option>${esc(n)}</option>`).join('');
  const REG = ['xmin', 'xmax', 'ymin', 'ymax', 'zmin', 'zmax'];
  $('cmpBody').innerHTML =
    card('Strength – voxel FEM', `<div class="fgrid">
      <label>Part<select id="fPart">${opts}</select></label>
      <label>Fixed at<input id="fFix" list="regList" value="zmin" title="xmin…zmax, plane:Z=20, box:x0,y0,z0,x1,y1,z1, hole:6.6"></label>
      <label>Load [N]<input id="fLoad" value="zmax=0,0,-100" title="region=Fx,Fy,Fz; several separated by ;"></label>
      <label>Material<input id="fMat" placeholder="from parts.json, else steel" list="matList"></label>
      <label>Elements<input id="fEl" type="number" value="40000" min="2000" max="400000"></label></div>
      <datalist id="regList">${REG.map(r => `<option>${r}</option>`).join('')}</datalist><datalist id="matList">${['steel', 'S355', 'stainless', 'al', '7075', 'PLA', 'PETG', 'ABS', 'PA12', 'POM'].map(m => `<option>${m}</option>`).join('')}</datalist>
      <div class="row"><button class="primary" id="fRun">Run FEM</button><span class="muted">Comparison tool (±10–30 %); more elements = finer and slower.</span></div><div id="fOut"></div>`)
    + card('Manufacturability – DFM', `<div class="fgrid"><label>Part<select id="dPart">${opts}</select></label><label>Process<select id="dProc"><option value="print">3D print</option><option value="mill">milling</option><option value="mould">moulding</option></select></label></div>
      <div class="row"><button class="primary" id="dRun">Check</button><span class="muted">Wall thickness by rays on the exact B-rep, overhangs, draft, radii.</span></div><div id="dOut"></div>`, false)
    + card('Optimise parameters', '<div id="oBody" class="muted">Loading the script parameters…</div>', false)
    + card('Compare design variants', `<div class="row"><button class="primary" id="vRun">Compare</button><span class="muted">All name@label.step variants of this model side by side.</span></div><div id="vOut"></div>`, false);
  $('fRun').onclick = async () => {
    try {
      const r = await runJob({ tool: 'fem', part: $('fPart').value, fix: $('fFix').value.split(';').map(s => s.trim()).filter(Boolean), load: $('fLoad').value.split(';').map(s => s.trim()).filter(Boolean), material: $('fMat').value.trim(), elements: +$('fEl').value }, $('fOut'), 'FEM');
      $('fOut').innerHTML = `<div class="kpis"><div><b>${fmtn(r.max_disp_mm, 3)}</b><span>max deflection mm</span></div><div><b>${fmtn(r.vm_p99_5_MPa, 1)}</b><span>stress p99.5 MPa</span></div><div><b>${fmtn(r.vm_max_MPa, 1)}</b><span>stress max MPa</span></div><div><b>${r.safety_vs_yield_p99_5 ?? '—'}</b><span>safety vs yield</span></div><div><b>${r.elements}</b><span>elements</span></div><div><b>${r._s} s</b><span>time</span></div></div>
        <div class="muted">${esc(r.material)} · E ${r.E} MPa · yield ${r.yield} MPa · ${r.converged ? 'converged' : 'NOT converged'} · ${esc(r.note)}</div>
        ${r.image ? `<img class="wimg" src="/api/cachefile?p=${encodeURIComponent(r.image)}">` : ''}
        <div class="row"><button class="primary" id="fShow">Show stress in 3D</button></div>`;
      $('fShow').onclick = async () => {
        const d = await (await fetch('/api/cachefile?p=' + encodeURIComponent(r.points))).json();
        ovClear();
        const n = d.v.length, col = new Float32Array(n * 3);
        for (let i = 0; i < n; i++) col.set(heat(d.v[i] / (d.vmax || 1)), i * 3);
        const g = new THREE.BufferGeometry().setAttribute('position', new THREE.Float32BufferAttribute(d.p, 3)).setAttribute('color', new THREE.BufferAttribute(col, 3));
        const m = new THREE.Points(g, new THREE.PointsMaterial({ size: 4, sizeAttenuation: false, vertexColors: true, depthTest: true }));
        m.renderOrder = 21; ovGroup.add(m);
        ovShow(`FEM ${r.part}: von Mises 0 (blue) … ${fmtn(d.vmax, d.vmax < 10 ? 2 : 0)} MPa (red, p99.5) · white dot = maximum`);
        ovMarker(r.vm_max_at, 0xffffff, 16);
        back3d();
      };
    } catch (e) { $('fOut').innerHTML = `<div class="muted">${esc(e.message)}</div>`; }
  };
  $('dRun').onclick = async () => {
    try {
      const r = await runJob({ tool: 'dfm', part: $('dPart').value, process: $('dProc').value }, $('dOut'), 'DFM');
      const ws = r.wall.thin_spots || [];
      $('dOut').innerHTML = `<div class="kpis"><div><b>${r.wall.min ?? '—'}</b><span>min wall mm</span></div><div><b>${r.wall.p5 ?? '—'}</b><span>wall p5 mm</span></div><div><b>${r.wall.median ?? '—'}</b><span>median wall mm</span></div><div><b>${ws.length}</b><span>thin spots &lt; ${r.min_wall_limit}</span></div>${r.overhang ? `<div><b>${fmtn(r.overhang.support_area_mm2, 0)}</b><span>support area mm²</span></div>` : ''}</div>
        <div class="muted">Smallest inner radius ${r.radii.min_inner_radius ?? '—'} mm · holes ${esc((r.radii.hole_diameters || []).join(', '))}${r.mill_note ? ' · ' + esc(r.mill_note) : ''}</div>
        ${ws.length ? `<table class="ptable"><tbody>${ws.map((t, i) => `<tr><td>${t.t_min} mm</td><td class="mono">${t.at.join(', ')}</td><td>${t.samples} samples</td><td><button class="ghost" data-ts="${i}">Show</button></td></tr>`).join('')}</tbody></table>` : ''}
        <div class="row"><button class="primary" id="dShow">Show all in 3D</button></div>`;
      const showAll = () => { ovClear(); if (ws.length) ovMarker(ws.flatMap(t => t.at), 0xe5655a, 14); if (r.overhang?.worst_at?.length) ovMarker(r.overhang.worst_at.flat(), 0xd0a020, 12); ovShow(`DFM ${r.part}: red = thin walls, yellow = overhangs`); back3d(); };
      $('dShow').onclick = showAll;
      $('dOut').querySelectorAll('[data-ts]').forEach(b => b.onclick = () => { const t = ws[+b.dataset.ts]; ovClear(); ovMarker(t.at, 0xe5655a, 18); ovShow(`Thin wall ${t.t_min} mm`); back3d(); flyToPoint(t.at, 15); });
    } catch (e) { $('dOut').innerHTML = `<div class="muted">${esc(e.message)}</div>`; }
  };
  $('vRun').onclick = async () => {
    try {
      const r = await runJob({ tool: 'variants' }, $('vOut'), 'Comparing variants');
      const best = Math.min(...r.variants.filter(v => !v.error).map(v => v.mass_g));
      $('vOut').innerHTML = `<table class="ptable"><thead><tr><th>Variant</th><th>Mass</th><th>Size [mm]</th><th>Parts</th><th>Collisions</th><th>Invalid</th><th>expect()</th><th></th></tr></thead><tbody>${r.variants.map(v => v.error ? `<tr><td>${esc(v.label)}</td><td colspan="7">${esc(v.error)}</td></tr>` : `<tr><td><b>${esc(v.label)}</b></td><td>${fmtn(v.mass_g, 1)} g${v.mass_g === best ? ' <span class="badge ok">lightest</span>' : ''}</td><td>${v.size.map(x => fmtn(x, 1)).join(' × ')}</td><td>${v.parts}</td><td>${v.collisions ? `<span class="badge bad">${v.collisions}</span>` : '0'}</td><td>${v.invalid || 0}</td><td>${esc(v.expect || '—')}</td><td><button class="ghost" data-vo="${esc(v.file)}">Open</button></td></tr>`).join('')}</tbody></table>`;
      $('vOut').querySelectorAll('[data-vo]').forEach(b => b.onclick = () => plugAct({ action: 'open-model', path: b.dataset.vo }).then(back3d).catch(e => toast(e.message, true)));
    } catch (e) { $('vOut').innerHTML = `<div class="muted">${esc(e.message)}</div>`; }
  };
  // optimisation form from the script parameters
  let pr = { params: [] };
  try { pr = await api('/api/params'); } catch { /* none */ }
  if (!$('oBody')) return;
  const nums = (pr.params || []).filter(p => p.type !== 'bool');
  if (!nums.length) { $('oBody').innerHTML = '<div class="muted">The model has no parametric script with numeric parameters.</div>'; return; }
  $('oBody').innerHTML = `<div class="muted">Tick the parameters to vary and their range. Each evaluation rebuilds a throw-away copy of the script (the model is not touched until you apply).</div>
    <table class="ptable"><thead><tr><th></th><th>Parameter</th><th>Now</th><th>From</th><th>To</th></tr></thead><tbody>${nums.slice(0, 80).map(p => `<tr><td><input type="checkbox" data-o="${esc(p.name)}"></td><td class="mono">${esc(p.name)}</td><td>${p.value}${p.unit ? ' ' + esc(p.unit) : ''}</td><td><input type="number" step="any" data-lo="${esc(p.name)}" value="${p.min ?? +(p.value * 0.5).toFixed(3)}" style="width:80px"></td><td><input type="number" step="any" data-hi="${esc(p.name)}" value="${p.max ?? +(p.value * 1.5).toFixed(3)}" style="width:80px"></td></tr>`).join('')}</tbody></table>
    <div class="fgrid"><label>Goal<select id="oObj"><option value="mass">minimum mass</option><option value="volume">minimum volume</option><option value="size.z">minimum height</option><option value="fem.max_disp_mm">minimum deflection (needs FEM)</option><option value="fem.vm_p99_5_MPa">minimum stress (needs FEM)</option></select></label>
      <label>Budget (runs)<input id="oBudget" type="number" value="20" min="4" max="200"></label></div>
    <label class="muted">Conditions, one per line (e.g. <span class="mono">collisions==0</span>, <span class="mono">size.z&lt;=120</span>, <span class="mono">fem.max_disp_mm&lt;0.2</span>)<textarea id="oSub" rows="3" style="width:100%;box-sizing:border-box"></textarea></label>
    <label class="muted">FEM for fem.* metrics (optional): <input id="oFem" placeholder="part=Bracket fix=zmin load=zmax=0,0,-200" style="width:100%;box-sizing:border-box"></label>
    <div class="row"><button class="primary" id="oRun">Optimise</button></div><div id="oOut"></div>`;
  $('oRun').onclick = async () => {
    const vary = [...$('oBody').querySelectorAll('[data-o]:checked')].map(c => `${c.dataset.o}=${$('oBody').querySelector(`[data-lo="${c.dataset.o}"]`).value}..${$('oBody').querySelector(`[data-hi="${c.dataset.o}"]`).value}`);
    if (!vary.length) { toast('Tick at least one parameter.', true); return; }
    try {
      const r = await runJob({ tool: 'optimize', vary, objective: $('oObj').value, subject: $('oSub').value.split('\n').map(s => s.trim()).filter(Boolean), budget: +$('oBudget').value, fem: $('oFem').value.trim() || null }, $('oOut'), 'Optimising');
      if (!r.best) { $('oOut').innerHTML = `<div class="muted">No working variant. ${esc((r.errors || []).join('; '))}</div>`; return; }
      $('oOut').innerHTML = `<div class="muted">${r.runs} runs (${r.failed_runs} failed) · ${r.feasible ? 'all conditions met' : '<b>no variant met every condition</b> – best compromise shown'}</div>
        <table class="ptable"><thead><tr><th>Parameters</th><th>${esc(r.objective)}</th></tr></thead><tbody>${r.top5.map(t => `<tr><td class="mono">${esc(Object.entries(t.params).map(([k, v]) => `${k} = ${v}`).join(', '))}</td><td>${Object.values(t).slice(-1)[0]}</td></tr>`).join('')}</tbody></table>
        <pre class="wpre">${esc(JSON.stringify(r.best.metrics, null, 1))}</pre><div class="row"><button class="primary" id="oApply">Apply the best values and rebuild</button></div>`;
      $('oApply').onclick = async () => { try { await api('/api/params', { values: r.best.params }); toast('Applied – the model is rebuilding.'); back3d(); } catch (e) { toast(e.message, true); } };
    } catch (e) { $('oOut').innerHTML = `<div class="muted">${esc(e.message)}</div>`; }
  };
}

// ---- System
async function renderSystemWin() {
  const w = $('winBody');
  w.innerHTML = `<div class="whead"><h3>System</h3><span class="grow"></span><button class="primary" id="wcBack">3D model</button></div><div id="syBody" class="muted">Loading…</div>`;
  $('wcBack').onclick = back3d;
  let s = {}, md = { text: '', path: '' }, ret = { head: [], rows: [] };
  try { [s, ret] = await Promise.all([api('/api/system'), api('/api/retro')]); } catch (e) { $('syBody').textContent = e.message; return; }
  try { md = await api('/api/claudemd'); } catch { md = null; }
  if (!$('syBody')) return;
  const yes = (b, t = 'yes', f = 'no') => `<span class="badge ${b ? 'ok' : 'bad'}">${b ? t : f}</span>`;
  const verOk = s.installed_version && s.installed_version === s.running_version;
  $('syBody').classList.remove('muted');
  $('syBody').innerHTML = card('This computer and the plugin', `<div class="kv2">
      <span>Plugin running</span><span>${esc(s.running_version || '?')} <span class="muted mono">${esc(s.app_folder)}</span></span>
      <span>Plugin installed</span><span>${esc(s.installed_version || '?')} ${verOk ? yes(true, 'same') : '<span class="badge warn">different – update the plugin or restart</span>'}</span>
      <span>Helpers ~/.CAD4Ai/lib</span><span>${yes(s.lib_in_sync, 'in sync', 'stale: ' + (s.lib_stale || []).join(', '))}</span>
      <span>Hooks last active</span><span>${s.hooks_last_run ? new Date(s.hooks_last_run * 1000).toLocaleString() : '<span class="badge warn">never</span>'}</span>
      <span>Python</span><span>${esc(s.python)} · CadQuery ${esc(s.cadquery || 'missing')} · OCP ${esc(s.ocp || 'missing')}</span>
      <span>Computer</span><span>${s.cpus} logical CPUs · RAM ${s.ram_gb ?? '?'} GB (${s.ram_free_gb ?? '?'} free) · disk free ${s.disk_free_gb ?? '?'} GB</span>
      <span>Data</span><span class="mono">${esc(s.app_home)}</span></div>`)
    + card('Your standing instructions for Claude (CLAUDE.md)', md ? `<div class="muted mono">${esc(md.path)} — saved with a .bak copy of the previous text</div><textarea id="mdText" rows="14" style="width:100%;box-sizing:border-box;font-family:var(--mono,monospace);font-size:12px">${esc(md.text)}</textarea><div class="row"><button class="primary" id="mdSave">Save</button><span class="muted" id="mdMsg"></span></div>` : '<div class="muted">Only on this computer.</div>', false)
    + card(`Model retro log <span class="muted">— which model and effort each task needed (${ret.rows.length})</span>`, ret.rows.length ? `<table class="ptable"><thead><tr>${ret.head.map(h => `<th>${esc(h)}</th>`).join('')}</tr></thead><tbody>${ret.rows.map(r => `<tr>${r.map(c => `<td>${esc(c)}</td>`).join('')}</tr>`).join('')}</tbody></table>` : '<div class="muted">Empty.</div>', false)
    + card('Find in your CadQuery scripts', `<div class="row"><input id="fsQ" placeholder="e.g. bearing housing 6204, hinge, příruba" style="flex:1"><button class="primary" id="fsRun">Find</button></div><div id="fsOut"></div>`, true);
  if ($('mdSave')) $('mdSave').onclick = async () => { try { const r = await api('/api/claudemd', { text: $('mdText').value }); $('mdMsg').textContent = ' saved (previous text in ' + r.backup + ')'; } catch (e) { toast(e.message, true); } };
  const find = async () => {
    try {
      const r = await plugAct({ action: 'find-scripts', q: $('fsQ').value });
      $('fsOut').innerHTML = r.hits.length ? `<table class="ptable"><tbody>${r.hits.map((h, i) => `<tr><td><b>${esc(h.name)}</b><div class="muted mono" style="font-size:10.5px">${esc(h.where)}</div>${h.doc ? `<div class="muted">${esc(h.doc)}</div>` : ''}</td><td>${h.score}</td><td style="white-space:nowrap"><button class="ghost" data-fm="${i}">Open model</button> <button class="ghost" data-fs="${i}">Open script</button></td></tr>`).join('')}</tbody></table><div class="muted">Index age ${r.index_age_h} h (rebuilt daily; Settings → Data to rebuild now).</div>` : '<div class="muted">Nothing found.</div>';
      $('fsOut').querySelectorAll('[data-fm]').forEach(b => b.onclick = () => plugAct({ action: 'model-of-script', path: r.hits[+b.dataset.fm].where }).then(back3d).catch(e => toast(e.message, true)));
      $('fsOut').querySelectorAll('[data-fs]').forEach(b => b.onclick = () => plugAct({ action: 'open-script', path: r.hits[+b.dataset.fs].where }).catch(e => toast(e.message, true)));
    } catch (e) { toast(e.message, true); }
  };
  $('fsRun').onclick = find; $('fsQ').onkeydown = e => { if (e.key === 'Enter') find(); };
}
