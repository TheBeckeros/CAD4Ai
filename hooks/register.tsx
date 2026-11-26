import { atom, read, update } from 'claude-code'
import type { Register } from 'claude-code'

import type { Model, View } from '../types'

// ---------------------------------------------------------------------------
// CAD4Ai: when Claude writes a .step (or .stl), the interactive 3D viewer shows it.
// The fallback pane renders an SVG (orthographic projection, painter's algorithm,
// highlighted sharp edges). Large meshes are simplified by vertex clustering.
// ---------------------------------------------------------------------------

const PANE = 'CAD4Ai'
const ISO: View = { yaw: -35, pitch: 28, zoom: 1 }

const model = atom({ plugin: 'CAD4Ai', key: 'model' } as const, null, { shape: 'model-1' })
const view = atom({ plugin: 'CAD4Ai', key: 'view' } as const, ISO, { shape: 'view-1' })

const WATCHED = /^(Bash|PowerShell|Write|Edit|MultiEdit|NotebookEdit)$/
const SKIP_DIRS = /^(\.|node_modules$|__pycache__$|venv$|\.venv$)/
const MAX_BYTES = 64 * 1024 * 1024
const CHUNK = 4 * 1024 * 1024
const SVG_BUDGET = 125_000
const BASE = [122, 138, 106] // olive "military" green

// ---------------------------------------------------------------- mesh ----

type Mesh = {
  verts: Float64Array // xyz per vertex
  idx: Uint32Array // 3 indices per triangle
  normals: Float64Array // normal per triangle
  sharp: Uint8Array // bits: edge 0-1, 1-2, 2-0 is sharp
  center: [number, number, number]
  radius: number
}

type Loaded = {
  key: string
  raw: Float64Array // 9 numbers per triangle
  triCount: number
  dims: [number, number, number]
  levels: Map<number, Mesh>
}

let cache: Loaded | undefined

const joinPath = (dir: string, name: string): string => {
  const sep = dir.includes('\\') ? '\\' : '/'
  return dir.endsWith(sep) ? dir + name : dir + sep + name
}

const baseName = (path: string): string => path.split(/[\\/]/).pop() ?? path

function parseBinary(bytes: Uint8Array): Float64Array | undefined {
  if (bytes.length < 84) return undefined
  const dv = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength)
  const n = dv.getUint32(80, true)
  if (84 + n * 50 !== bytes.length) return undefined
  const out = new Float64Array(n * 9)
  for (let t = 0; t < n; t++) {
    const o = 84 + t * 50 + 12
    for (let k = 0; k < 9; k++) out[t * 9 + k] = dv.getFloat32(o + k * 4, true)
  }
  return out
}

function parseAscii(text: string): Float64Array {
  const nums: number[] = []
  const re = /vertex\s+([-+0-9.eE]+)\s+([-+0-9.eE]+)\s+([-+0-9.eE]+)/g
  let m: RegExpExecArray | null
  while ((m = re.exec(text)) !== null) nums.push(+m[1], +m[2], +m[3])
  return new Float64Array(nums.slice(0, nums.length - (nums.length % 9)))
}

async function loadStl($: any, path: string, mtimeMs: number, size: number): Promise<Loaded> {
  const key = `${path}|${mtimeMs}|${size}`
  if (cache?.key === key) return cache
  if (size > MAX_BYTES) throw new Error(`file is too large (${Math.round(size / 1e6)} MB)`)

  const bytes = new Uint8Array(size)
  for (let off = 0; off < size; off += CHUNK) {
    const { base64 } = await $.fs.read(path, { as: 'bytes', offset: off, length: Math.min(CHUNK, size - off) })
    bytes.set(Uint8Array.fromBase64(base64), off)
  }
  let raw = parseBinary(bytes)
  if (raw === undefined) raw = parseAscii(await $.fs.read(path))
  if (raw.length === 0) throw new Error('the file contains no triangles')

  const lo = [Infinity, Infinity, Infinity]
  const hi = [-Infinity, -Infinity, -Infinity]
  for (let i = 0; i < raw.length; i += 3) {
    for (let a = 0; a < 3; a++) {
      lo[a] = Math.min(lo[a], raw[i + a])
      hi[a] = Math.max(hi[a], raw[i + a])
    }
  }
  cache = {
    key,
    raw,
    triCount: raw.length / 9,
    dims: [hi[0] - lo[0], hi[1] - lo[1], hi[2] - lo[2]],
    levels: new Map(),
  }
  return cache
}

/** Welds vertices into a grid of `res` cells along the longest dimension (clustering). */
function cluster(raw: Float64Array, res: number): Mesh {
  const lo = [Infinity, Infinity, Infinity]
  const hi = [-Infinity, -Infinity, -Infinity]
  for (let i = 0; i < raw.length; i += 3) {
    for (let a = 0; a < 3; a++) {
      lo[a] = Math.min(lo[a], raw[i + a])
      hi[a] = Math.max(hi[a], raw[i + a])
    }
  }
  const span = Math.max(hi[0] - lo[0], hi[1] - lo[1], hi[2] - lo[2]) || 1
  const cell = span / res
  const ids = new Map<string, number>()
  const sums: number[] = []
  const counts: number[] = []
  const vid = (x: number, y: number, z: number): number => {
    const k = `${Math.round((x - lo[0]) / cell)},${Math.round((y - lo[1]) / cell)},${Math.round((z - lo[2]) / cell)}`
    let id = ids.get(k)
    if (id === undefined) {
      id = counts.length
      ids.set(k, id)
      sums.push(0, 0, 0)
      counts.push(0)
    }
    sums[id * 3] += x
    sums[id * 3 + 1] += y
    sums[id * 3 + 2] += z
    counts[id] += 1
    return id
  }

  const tris: number[] = []
  const seen = new Set<string>()
  for (let i = 0; i < raw.length; i += 9) {
    const a = vid(raw[i], raw[i + 1], raw[i + 2])
    const b = vid(raw[i + 3], raw[i + 4], raw[i + 5])
    const c = vid(raw[i + 6], raw[i + 7], raw[i + 8])
    if (a === b || b === c || a === c) continue
    const k = [a, b, c].sort((p, q) => p - q).join(',')
    if (seen.has(k)) continue
    seen.add(k)
    tris.push(a, b, c)
  }

  const verts = new Float64Array(sums.length)
  for (let v = 0; v < counts.length; v++) {
    for (let a = 0; a < 3; a++) verts[v * 3 + a] = sums[v * 3 + a] / counts[v]
  }
  const idx = Uint32Array.from(tris)
  const n = idx.length / 3

  // orientation: negative volume = triangles facing inwards
  let vol = 0
  for (let t = 0; t < n; t++) {
    const [a, b, c] = [idx[t * 3] * 3, idx[t * 3 + 1] * 3, idx[t * 3 + 2] * 3]
    vol +=
      verts[a] * (verts[b + 1] * verts[c + 2] - verts[b + 2] * verts[c + 1]) -
      verts[a + 1] * (verts[b] * verts[c + 2] - verts[b + 2] * verts[c]) +
      verts[a + 2] * (verts[b] * verts[c + 1] - verts[b + 1] * verts[c])
  }
  if (vol < 0) {
    for (let t = 0; t < n; t++) {
      const s = idx[t * 3 + 1]
      idx[t * 3 + 1] = idx[t * 3 + 2]
      idx[t * 3 + 2] = s
    }
  }

  const normals = new Float64Array(n * 3)
  for (let t = 0; t < n; t++) {
    const [a, b, c] = [idx[t * 3] * 3, idx[t * 3 + 1] * 3, idx[t * 3 + 2] * 3]
    const ux = verts[b] - verts[a], uy = verts[b + 1] - verts[a + 1], uz = verts[b + 2] - verts[a + 2]
    const vx = verts[c] - verts[a], vy = verts[c + 1] - verts[a + 1], vz = verts[c + 2] - verts[a + 2]
    let nx = uy * vz - uz * vy, ny = uz * vx - ux * vz, nz = ux * vy - uy * vx
    const len = Math.hypot(nx, ny, nz) || 1
    normals[t * 3] = nx / len
    normals[t * 3 + 1] = ny / len
    normals[t * 3 + 2] = nz / len
  }

  // sharp edges: boundary or angle between faces > 30°
  const nv = counts.length
  const edges = new Map<number, number[]>()
  for (let t = 0; t < n; t++) {
    for (let e = 0; e < 3; e++) {
      const p = idx[t * 3 + e], q = idx[t * 3 + ((e + 1) % 3)]
      const k = Math.min(p, q) * nv + Math.max(p, q)
      const list = edges.get(k)
      if (list) list.push(t * 3 + e)
      else edges.set(k, [t * 3 + e])
    }
  }
  const sharp = new Uint8Array(n)
  const COS = Math.cos((30 * Math.PI) / 180)
  for (const list of edges.values()) {
    let isSharp = list.length !== 2
    if (!isSharp) {
      const [t1, t2] = [Math.floor(list[0] / 3), Math.floor(list[1] / 3)]
      const dot =
        normals[t1 * 3] * normals[t2 * 3] +
        normals[t1 * 3 + 1] * normals[t2 * 3 + 1] +
        normals[t1 * 3 + 2] * normals[t2 * 3 + 2]
      isSharp = dot < COS
    }
    if (isSharp) for (const te of list) sharp[Math.floor(te / 3)] |= 1 << te % 3
  }

  const center: [number, number, number] = [(lo[0] + hi[0]) / 2, (lo[1] + hi[1]) / 2, (lo[2] + hi[2]) / 2]
  let radius = 0
  for (let v = 0; v < nv; v++) {
    radius = Math.max(
      radius,
      Math.hypot(verts[v * 3] - center[0], verts[v * 3 + 1] - center[1], verts[v * 3 + 2] - center[2]),
    )
  }
  return { verts, idx, normals, sharp, center, radius: radius || 1 }
}

const RESOLUTIONS = [4096, 512, 256, 160, 112, 80, 56, 40, 28, 20]

function meshAt(loaded: Loaded, level: number): Mesh {
  let mesh = loaded.levels.get(level)
  if (mesh === undefined) {
    mesh = cluster(loaded.raw, RESOLUTIONS[level])
    loaded.levels.set(level, mesh)
  }
  return mesh
}

// -------------------------------------------------------------- render ----

const f = (x: number): string => {
  const r = Math.round(x * 10) / 10
  return Number.isInteger(r) ? String(r) : r.toFixed(1)
}

const hex = (k: number): string =>
  '#' +
  BASE.map(c =>
    Math.max(0, Math.min(255, Math.round(c * k)))
      .toString(16)
      .padStart(2, '0'),
  ).join('')

function drawSvg(mesh: Mesh, v: View, W: number, H: number): string | undefined {
  const yaw = (v.yaw * Math.PI) / 180
  const pit = (v.pitch * Math.PI) / 180
  const cy = Math.cos(yaw), sy = Math.sin(yaw), cp = Math.cos(pit), sp = Math.sin(pit)
  // camera: right = (cy, -sy, 0)·R, up/toward from rotation about Z and tilt
  const toCam = (x: number, y: number, z: number): [number, number, number] => {
    const x1 = x * cy - y * sy
    const y1 = x * sy + y * cy
    return [x1, y1 * sp + z * cp, -y1 * cp + z * sp] // [right, up, near]
  }
  const scale = ((Math.min(W, H) * 0.42) / mesh.radius) * v.zoom
  const [ox, oy] = [W / 2, H / 2]
  const nv = mesh.verts.length / 3
  const sx = new Float64Array(nv), syy = new Float64Array(nv), near = new Float64Array(nv)
  for (let i = 0; i < nv; i++) {
    const [r, u, d] = toCam(
      mesh.verts[i * 3] - mesh.center[0],
      mesh.verts[i * 3 + 1] - mesh.center[1],
      mesh.verts[i * 3 + 2] - mesh.center[2],
    )
    sx[i] = ox + r * scale
    syy[i] = oy - u * scale
    near[i] = d
  }

  const L = [-0.35, 0.55, 0.76]
  const n = mesh.idx.length / 3
  const vis: number[] = []
  const shade = new Float64Array(n)
  for (let t = 0; t < n; t++) {
    const [r, u, d] = toCam(mesh.normals[t * 3], mesh.normals[t * 3 + 1], mesh.normals[t * 3 + 2])
    if (d <= 1e-6) continue
    shade[t] = 0.45 + 0.65 * Math.max(0, r * L[0] + u * L[1] + d * L[2])
    vis.push(t)
  }
  const depth = (t: number): number =>
    near[mesh.idx[t * 3]] + near[mesh.idx[t * 3 + 1]] + near[mesh.idx[t * 3 + 2]]
  vis.sort((a, b) => depth(a) - depth(b))

  const parts: string[] = [
    `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ${W} ${H}" width="${W}" height="${H}">`,
    '<style>path{fill:currentColor;stroke:currentColor;stroke-width:1;stroke-linejoin:round}path.e{fill:none;stroke:#141614;stroke-width:1.1}</style>',
    `<rect width="${W}" height="${H}" fill="#1e2126"/>`,
  ]
  let len = parts.join('').length
  const pt = (i: number): string => `${f(sx[i])} ${f(syy[i])}`
  for (const t of vis) {
    const a = mesh.idx[t * 3], b = mesh.idx[t * 3 + 1], c = mesh.idx[t * 3 + 2]
    let s = `<path color="${hex(shade[t])}" d="M${pt(a)}L${pt(b)}L${pt(c)}Z"/>`
    const m = mesh.sharp[t]
    if (m) {
      const ends = [a, b, c]
      let d = ''
      for (let e = 0; e < 3; e++) if (m & (1 << e)) d += `M${pt(ends[e])}L${pt(ends[(e + 1) % 3])}`
      s += `<path class="e" d="${d}"/>`
    }
    len += s.length
    if (len > SVG_BUDGET) return undefined
    parts.push(s)
  }

  // axis triad bottom left
  const axes: [string, number, number, number][] = [
    ['#e06666', 1, 0, 0],
    ['#6aa84f', 0, 1, 0],
    ['#6fa8dc', 0, 0, 1],
  ]
  const [ax, ay] = [34, H - 30]
  for (const [col, x, y, z] of axes) {
    const [r, u] = toCam(x, y, z)
    parts.push(
      `<line x1="${ax}" y1="${ay}" x2="${f(ax + r * 22)}" y2="${f(ay - u * 22)}" stroke="${col}" stroke-width="2"/>`,
    )
  }
  parts.push('</svg>')
  return parts.join('')
}

function render(loaded: Loaded, v: View, W: number, H: number): { svg: string; shown: number } {
  // start at a level with a sensible triangle count, then coarsen to fit the budget
  let level = 0
  while (level < RESOLUTIONS.length - 1 && meshAt(loaded, level).idx.length / 3 > 6000) level++
  for (; level < RESOLUTIONS.length; level++) {
    const mesh = meshAt(loaded, level)
    const svg = drawSvg(mesh, v, W, H)
    if (svg !== undefined) return { svg, shown: mesh.idx.length / 3 }
  }
  throw new Error('model is too complex for the preview')
}

// ------------------------------------------------------------ watching ----

type Found = { path: string; mtimeMs: number; size: number }

async function newestModel($: any, extra?: string): Promise<Found | undefined> {
  const root: string = await $.session.cwd()
  const dirs = [root]
  try {
    for (const ent of await $.fs.list(root)) {
      if (ent.kind === 'dir' && !SKIP_DIRS.test(ent.name)) dirs.push(joinPath(root, ent.name))
    }
  } catch {
    return undefined
  }
  let best: Found | undefined
  for (const dir of dirs) {
    const list = await $.fs.list(dir).catch(() => [])
    for (const ent of list) {
      if (ent.kind !== 'file' || !MODEL_RE.test(ent.name)) continue
      if (!best || ent.mtimeMs > best.mtimeMs) best = { path: joinPath(dir, ent.name), mtimeMs: ent.mtimeMs, size: ent.size }
    }
  }
  if (extra && MODEL_RE.test(extra)) {
    const st = await $.fs.stat(extra).catch(() => undefined)
    if (st && (!best || st.mtimeMs >= best.mtimeMs)) best = { path: extra, mtimeMs: st.mtimeMs, size: st.size }
  }
  return best
}

// ---------------------------------------------- interactive viewer ----

// Every chat gets its own viewer server (free random port) and its own data folder, so a model
// opened in one chat never shows up in another. shortcut: history/notes are per chat, not per project.
let PORT = 8766
let VIEWER_URL = `http://127.0.0.1:${PORT}/`
const MODEL_RE = /\.(step|stp|stl)$/i
let dataDir: string | undefined
let serverUp = false
let inboxBusy = false
const inboxSent = new Set<string>() // filled in this run even if storing 'done' failed: never appended twice
const inboxFails = new Map<string, number>()

const problems: string[] = []
const note = ($: any, step: string, err: unknown): void => {
  const msg = `${step}: ${String((err as Error)?.message ?? err).slice(0, 300)}`
  problems.push(msg)
  problems.splice(0, Math.max(0, problems.length - 6))
  void Promise.resolve()
    .then(() => $.store.set('lastProblems', [...problems]))
    .catch(() => undefined)
  $.ui.status(`CAD4Ai: ${msg}`)
}

async function getDataDir($: any): Promise<string> {
  if (dataDir === undefined) {
    const cwd: string = await $.session.cwd()
    const dir = joinPath(joinPath(cwd, '.CAD4Ai'), `s-${Math.random().toString(36).slice(2, 8)}`)
    for (let i = 0; i < 30; i++) {
      const port = 8767 + Math.floor(Math.random() * 2000)
      if (!(await $.http.fetch(`http://127.0.0.1:${port}/api/ping`).catch(() => undefined))?.ok) {
        PORT = port
        break
      }
    }
    VIEWER_URL = `http://127.0.0.1:${PORT}/`
    dataDir = dir
  }
  return dataDir
}

const PYTHONS: string[][] = [['python'], ['py', '-3'], ['python3']]

// One viewer server is shared by all sessions; notes go to the data folder it currently serves.
// The session the user actually works in takes it over (on each prompt and model export), so a
// session merely started in the background (another project, a pre-warmed spare) never steals notes.
async function claimViewer($: any): Promise<void> {
  const dir = await getDataDir($)
  const r = await $.http
    .fetch(`${VIEWER_URL}api/data`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ data: dir }) })
    .catch(() => undefined)
  if (r?.ok) {
    serverUp = true
    return
  }
  serverUp = false
  await ensureServer($)
}

async function viewerRunning($: any): Promise<boolean> {
  const r = await $.http.fetch(`${VIEWER_URL}api/ping`).catch(() => undefined)
  return !!r?.ok
}

async function ensureServer($: any): Promise<void> {
  if (serverUp) return
  const dir = await getDataDir($)
  const script = joinPath(joinPath($.plugin.root, 'viewer'), 'server.py')
  let last = ''
  for (const py of PYTHONS) {
    try {
      const r = await $.process.run([...py, script, '--port', String(PORT), '--data', dir, '--detach'], {
        timeoutMs: 20000,
      })
      if (r.exitCode === 0) {
        serverUp = true
        return
      }
      last = `${py[0]} exit ${r.exitCode}: ${r.stderr.slice(0, 200)}`
    } catch (err) {
      last = `${py[0]}: ${String((err as Error)?.message ?? err)}`
    }
  }
  throw new Error(`server did not start (${last})`)
}

// Plugins cannot control the Browser pane; Claude opens it.
// The mod tells Claude via a system prompt section and the /CAD4Ai reply.
const openHint = (): string =>
  `CAD4Ai 3D viewer: ${VIEWER_URL}. CAD models: export STEP only (no STL or other format unless the task asks for it); ` +
  `the viewer shows the .step directly. The user opens the viewer with /CAD4Ai; do not open it, call it or ` +
  `screenshot it yourself unless asked: every export reloads it by itself. Design variants of one part: export each as ` +
  `<name>@<label>.step in one folder (e.g. bracket@A-light.step, bracket@B-ribbed.step); the viewer shows a switcher and the user ` +
  `picks one. Assemblies: build them with cq.Assembly, a unique name for every part, sub-assemblies as nested ` +
  `assemblies, and keep the names stable between versions (motion and explode files refer to them). Next to the .step write ` +
  `<name>.parts.json: {"parts": {"<part name>": {"type": "custom|fastener|bearing|seal|spring|purchased|electrical|other", ` +
  `"subassembly": "Frame/Cover", "standard": "ISO 4017 M5x16", "material": "S235"}}} (only the keys you know); the viewer ` +
  `groups its parts tree by it. Model scripts: sizes as UPPER_CASE parameters at the top, one per line with a comment ` +
  `("LID_T = 4.0  # lid thickness [mm] 1..10": unit in brackets, optional range), grouped under "# --- Lid ---" lines; ` +
  `the viewer's Parameters tab edits and rebuilds them. Exporting to other formats is in the viewer's Export menu. ` +
  `Build only the model and its cheap files (.step, .parts.json); never create motion, exploded view / disassembly, drawings or ` +
  `other extras by default, not even after the design is done: only when the user asks for them (or after they confirm the design and say yes to one). ` +
  `To show an existing model: ` +
  `curl -s -X POST ${VIEWER_URL}api/open -d "{\\"path\\":\\"<abs .step>\\"}". Don't mention this.`

async function show($: any, found: Found): Promise<void> {
  const next: Model = { path: found.path, name: baseName(found.path), mtimeMs: found.mtimeMs, size: found.size }
  await update($, model, () => next)
  try {
    await $.fs.write(joinPath(await getDataDir($), 'latest.json'), JSON.stringify(next))
  } catch (err) {
    note($, 'latest.json', err)
  }
  try {
    await claimViewer($)
  } catch (err) {
    note($, 'server', err)
  }
}

type Stroke = {
  index: number
  color: string
  part?: string | null
  pointCount: number
  onModel?: number
  center: number[]
  bboxMin: number[]
  bboxMax: number[]
  avgNormal: number[]
  points: number[][]
}
type Feature = {
  index: number
  type: string
  part: string
  title: string
  description: string
  point?: number[]
  centroid?: number[]
}
type Measure = { index: number; text: string; refs: string[]; from: number[]; to: number[] }
type Marker = { label: string; type: 'point' | 'line' | 'area'; points: number[][]; faceNormal: number[]; part?: string | null; note: string; features?: (string | null)[] }
type Annotation = {
  id?: string
  kind?: string
  model: string
  name: string
  step?: string | null
  comment: string
  hints?: string[]
  strokes?: Stroke[]
  features?: Feature[]
  measurements?: Measure[]
  markers?: Marker[]
  section?: { info?: string; normal: number[]; offset: number } | null
  parts?: string[]
  camera?: { viewDir: number[] }
  screenshot?: string
  script?: string
  params?: string[]
  paint?: { part: string; face: number | null; color: string; name?: string; description: string; centroid?: number[] }[]
  variants?: string[]
  sketch?: string
  req?: string
  summary?: string
  rect?: number[]
  scale?: number
}

const COLORS: Record<string, string> = {
  '#ff3b30': 'red',
  '#ffd60a': 'yellow',
  '#32d2ff': 'blue',
  '#ffffff': 'white',
}
const vec = (v: number[]): string => `[${v.join(', ')}]`
const vec1 = (v: number[]): string => `[${v.map(x => Math.round(x * 10) / 10).join(', ')}]`

function markerLines(ms: Marker[]): string[] {
  const out = ['Markers (model coordinates in mm, Z up):']
  for (const m of ms) {
    // the file is data: a short point list or a missing normal must not throw and hold up the inbox
    const at = (m.points ?? []).map(vec).join(m.type === 'line' ? ' → ' : ' ')
    out.push(`${m.label}) ${m.type}${m.part ? ` on part ${m.part}` : ''}: ${at}; face normal ${vec(m.faceNormal ?? [0, 0, 0])}`)
    const feats = [...new Set((m.features ?? []).filter(Boolean))]
    if (feats.length) out.push(`   on: ${feats.join(' | ')}`)
    out.push(`   note: ${m.note || '(no note)'}`)
  }
  return out
}

function annotationPrompt(a: Annotation, dataPath?: string): string {
  // the Motion tab button: a plain request, without the cad-annotate trigger phrase
  if (a.kind === 'motion') return [`Create motion for the assembly ${a.model} (skill cad-motion).`, a.id ? `Note ID: ${a.id}` : ''].filter(Boolean).join('\n')
  if (a.kind === 'explode')
    return [`Plan the exploded view, disassembly and assembly sequence of the assembly ${a.model} (skill cad-explode).`, a.comment && a.comment !== 'explode' ? `Focus: ${a.comment}` : '', a.id ? `Note ID: ${a.id}` : ''].filter(Boolean).join('\n')
  if (a.kind === 'newmodel')
    return [`Create a new CAD model "${a.model}" and export it as STEP (the CAD4Ai viewer shows it).`, `Description: ${a.comment || '(none, ask me what I need)'}`, a.id ? `Note ID: ${a.id}` : ''].filter(Boolean).join('\n')
  if (a.kind === 'variant')
    return [`I choose design variant "${a.comment}" (${a.model}) out of ${(a.variants ?? []).join(', ')}. Continue with this one as the final design.`, a.id ? `Note ID: ${a.id}` : ''].filter(Boolean).join('\n')
  if (a.kind === 'sketch')
    return [
      'Design brief from the CAD4Ai sketch pad (skill cad-sketch):',
      a.comment || '(no text, look at the canvas)',
      `Canvas image: ${a.screenshot} (view it with the Read tool)`,
      `On the canvas: ${a.summary || '(empty)'}`,
      `Canvas data, only if needed: ${a.sketch}`,
      a.model ? `Current model: ${a.model}` : '',
      a.id ? `Note ID: ${a.id}` : '',
    ].filter(Boolean).join('\n')
  if (a.kind === 'snap')
    return [
      'Snap request from the CAD4Ai sketch pad (skill cad-sketch): redraw only the boxed region.',
      `Instruction: ${a.comment}`,
      `Region image: ${a.screenshot} (view it with the Read tool; ${a.scale} px per canvas unit, top-left = region corner)`,
      `Region [x, y, w, h]: ${vec(a.rect ?? [])}`,
      `Request data (region items, outside only as bounds): ${a.sketch}`,
      `Answer with a proposal for snap ${a.id} (skill cad-sketch, script proposal.py); the user accepts or rejects it in the pad.`,
    ].join('\n')
  if (a.kind === 'canvas')
    return [
      'Request from the CAD4Ai construction canvas (skill cad-canvas):',
      `Instruction: ${a.comment || '(none, work out from the drawing what is wanted)'}`,
      `Region image: ${a.screenshot} (view it with the Read tool; ${a.scale} px per canvas unit, top-left = region corner)`,
      `Region [x, y, w, h]: ${vec(a.rect ?? [])}`,
      `Selection: ${a.summary}`,
      `Request ID: ${a.id} (read it with canvas.py req ${a.id}, answer with canvas.py briefing / preview, see the skill)`,
    ].join('\n')
  if (a.kind === 'canvas-answers')
    return [
      `Answers to your briefing questions on the CAD4Ai construction canvas (skill cad-canvas), request ${a.req}:`,
      a.summary,
      a.comment ? `Note from the user: ${a.comment}` : '',
      'Update your understanding; ask again with canvas.py briefing only if something essential is still open, otherwise send the result with canvas.py preview.',
    ].filter(Boolean).join('\n')
  if (a.kind === 'batch') {
    const ms = a.markers ?? []
    const out = [
      `Several places marked on the model, one note each (${ms.length} markers).`,
      '',
      `— 3D annotation from CAD4Ai, model ${a.name}`,
      `Model: ${a.model}`,
    ]
    if (dataPath) out.push(`Annotation data: ${dataPath} (skill cad-annotate, kind batch: run locate.py --points per marker)`)
    if (a.id) out.push(`Note ID: ${a.id} (mark it done when all markers are handled, see skill cad-annotate)`)
    if (a.camera?.viewDir) out.push(`Camera view direction: ${vec(a.camera.viewDir)}`)
    if (a.parts && a.parts.length > 1) out.push(`Assembly, parts: ${a.parts.join(', ')}`)
    out.push(...markerLines(ms))
    return out.join('\n')
  }
  const marks = a.markers ?? []
  const lines = [a.comment || (marks.length ? 'Changes at the marked places, see the marker notes.' : ''), '', `— 3D annotation from CAD4Ai, model ${a.name}`, `Model: ${a.model}`]
  // the screenshot shows what the user means; the lists below give the exact geometry for each label on it
  if (a.screenshot)
    lines.push(`Screenshot: ${a.screenshot} (Read it first: the letters are markers, the numbers in orange circles selected features, the blue labels dimensions; they match the lists below)`)
  if (a.script) lines.push(`Script: ${a.script} (the parametric source: make the change here)`)
  if (a.params?.length) lines.push(`Parameters: ${a.params.join(', ')}`)
  // set by the viewer's settings: script map, why lists are short, a model suggestion
  for (const h of a.hints ?? []) lines.push(h)
  if (a.kind === 'quick') lines.push('Quick change: do only this, without other improvements; no screenshot was sent, the lists below say where.')
  if (dataPath) lines.push(`Annotation data: ${dataPath} (skill cad-annotate, script locate.py)`)
  if (a.id) lines.push(`Note ID: ${a.id} (mark it done when handled, see skill cad-annotate)`)
  if (a.camera?.viewDir) lines.push(`Camera view direction: ${vec(a.camera.viewDir)}`)
  if (a.parts && a.parts.length > 1) lines.push(`Assembly, parts: ${a.parts.join(', ')}`)
  const strokes = a.strokes ?? []
  const features = a.features ?? []
  const measures = a.measurements ?? []
  if (features.length) {
    lines.push('Selected features (exact B-rep, coordinates in mm, Z up):')
    for (const f of features) {
      const at = f.point ?? f.centroid
      lines.push(`${f.index}) ${f.title}: ${f.description}${at ? `; point ${vec(at)}` : ''}`)
    }
  }
  if (measures.length) {
    lines.push('Dimensions:')
    for (const m of measures) lines.push(`${m.index}) ${m.text} (${m.refs.join(' ↔ ')}; ${vec(m.from)} → ${vec(m.to)})`)
  }
  if (marks.length) lines.push(...markerLines(marks))
  const paint = a.paint ?? []
  if (paint.length) {
    // the colours mark places: the user's request says what each colour means
    lines.push('Painted in the viewer (the colours mark places; the request says what they mean):')
    for (const x of paint)
      lines.push(`- ${x.name ? `${x.name} ` : ''}${x.color} part ${x.part}: ${x.face === null ? 'whole part' : `face #${x.face}, ${x.description}${x.centroid ? ` at ${vec(x.centroid)}` : ''}`}`)
  }
  if (a.section) lines.push(`Section: ${a.section.info ?? ''} (normal ${vec(a.section.normal)}, offset ${a.section.offset} mm)`)
  if (strokes.length) {
    lines.push('Pen drawing (model coordinates in mm, Z up):')
    for (const s of strokes) {
      lines.push(
        `${s.index}) ${COLORS[s.color] ?? s.color} stroke${s.part ? ` on part ${s.part}` : ''}: center ${vec1(s.center)}, ` +
          `face normal ≈ ${vec(s.avgNormal)}, ${s.pointCount} points` +
          (s.onModel !== undefined && s.onModel < 1
            ? `, drawn over the screen, ${Math.round(s.onModel * 100)} % on the model${s.onModel === 0 ? ' (points on the plane through the view centre, see the screenshot)' : ''}`
            : ''),
      )
      // full points are in the annotation data for locate.py; a short outline is enough here
      const step = Math.max(1, Math.ceil(s.points.length / 8))
      lines.push(`   points: ${s.points.filter((_, i) => i % step === 0).map(vec1).join(' ')}`)
    }
  }
  if (!strokes.length && !features.length && !measures.length && !marks.length && !paint.length) lines.push('No drawing or selection: the request applies to the whole model.')
  return lines.join('\n')
}

async function checkInbox($: any): Promise<void> {
  if (inboxBusy || dataDir === undefined) return
  inboxBusy = true
  try {
    const inbox = joinPath(dataDir, 'inbox')
    const files = (await $.fs.list(inbox).catch(() => []))
      .filter((f: { name: string; kind: string }) => f.kind === 'file' && f.name.endsWith('.json'))
      .map((f: { name: string }) => f.name)
      .sort()
    if (files.length === 0) return
    const done = new Set<string>(((await $.store.get('done')) as string[] | undefined) ?? [])
    for (const name of files) {
      const id = joinPath(inbox, name)
      if (done.has(id) || inboxSent.has(id)) continue
      // A file that does not read or parse (half written, or an older shape) is retried a few ticks, then skipped,
      // so it never holds up the notes after it. It stays in the inbox.
      let body: string
      try {
        body = annotationPrompt(JSON.parse(await $.fs.read(id)) as Annotation, id)
      } catch (err) {
        const n = (inboxFails.get(id) ?? 0) + 1
        inboxFails.set(id, n)
        if (n < 3) continue
        note($, `note ${name}`, `${String((err as Error)?.message ?? err)}; skipped, the file stays in the inbox`)
        done.add(id)
        await $.store.set('done', [...done].slice(-500))
        continue
      }
      // Never sent automatically: appended to the draft, the user decides when to send.
      const box = await $.prompt.read()
      const count = (box.text.match(/^— 3D annotation from CAD4Ai/gm) ?? []).length
      const head = `Note ${count + 1}: `
      const sep = box.text.trim() === '' ? '' : '\n\n'
      let filled = await $.prompt.fill({ text: sep + head + body, mode: 'append' })
      // The desktop app draws its own composer (no_composer): the draft cannot be filled, so send the note as a prompt.
      if (!filled.isFilled && filled.refusal === 'no_composer') {
        await $.prompt.submit({ text: head + body })
        filled = { ...filled, isFilled: true }
      }
      // unanswered: the text may have landed, so it is not appended again (exactly once beats a duplicate)
      if (!filled.isFilled && filled.refusal !== 'unanswered') {
        // the box refuses as a whole (a dialog holds the keys): every later note would be refused too, so retry next tick in order
        note($, 'draft message', `the message box did not accept it (${filled.refusal ?? 'unknown reason'}), will retry`)
        break
      }
      inboxSent.add(id)
      done.add(id)
      await $.store.set('done', [...done].slice(-500))
      $.ui.toast(
        filled.refusal === 'no_composer'
          ? `Note ${count + 1} sent to Claude.`
          : filled.isFilled
            ? `Note ${count + 1} added to your message, send it whenever you are ready.`
            : `Note ${count + 1} may not have reached your message; its data is in ${id}.`,
      )
    }
  } catch (err) {
    note($, 'adding to message', err)
  } finally {
    inboxBusy = false
  }
}

// ------------------------------------------------------------ register ----

export const register: Register = on => {
  on('session.start', async ($, e, next) => {
    await $.command.register({
      name: 'CAD4Ai',
      description: 'Opens the 3D viewer for the newest STEP/STL model (or the given path)',
      argumentHint: '[path.step]',
    })
    try {
      await getDataDir($)
      // start the server if nobody runs it, but do not take it over from a session in use
      if (!(await viewerRunning($))) await ensureServer($)
    } catch (err) {
      note($, 'server', err)
    }
    $.clock.every(1500, () => void checkInbox($))
    return next(e)
  })

  on('prompt.submit', async ($, e, next) => {
    void claimViewer($).catch(err => note($, 'server', err))
    return next(e)
  })

  on('command.run', { command: 'CAD4Ai' }, async ($, e) => {
    const arg = e.args.trim().replace(/^["']|["']$/g, '')
    let found: Found | undefined
    if (arg) {
      const st = await $.fs.stat(arg).catch(() => undefined)
      if (!st) return { text: `File ${arg} does not exist.` }
      found = { path: arg, mtimeMs: st.mtimeMs, size: st.size }
    } else {
      found = await newestModel($)
    }
    // no model yet is fine: the viewer waits and shows every export of this session live
    if (found) await show($, found)
    else await claimViewer($).catch(err => note($, 'server', err))
    return {
      text: found ? `3D viewer for ${baseName(found.path)} is ready at ${VIEWER_URL}.` : `3D viewer is ready at ${VIEWER_URL}; models appear as they are exported.`,
      context: `The user ran /CAD4Ai: open the viewer in the browser pane now with mcp__Claude_Browser__preview_start, url "${VIEWER_URL}". Say nothing else about it.`,
    }
  })

  on('prompt.compose', async ($, e, next) => {
    await getDataDir($)
    const res = await next(e)
    return { sections: [...res.sections, { id: 'CAD4Ai:viewer', text: openHint(), scope: 'session' as const }] }
  })

  on('tool.call', async ($, e, next) => {
    const isWatched = WATCHED.test(e.tool) || (e.tool.startsWith('mcp__') && !/^mcp__(ccd_|Claude_Browser)/.test(e.tool))
    if (!isWatched) return next(e)

    const writes = (e as { file_path?: unknown }).file_path
    const target = typeof writes === 'string' ? writes : undefined
    const before = await newestModel($).catch(() => undefined)
    const ran = await next(e)
    try {
      const after = await newestModel($, target)
      if (after && (!before || after.path !== before.path || after.mtimeMs > before.mtimeMs)) await show($, after)
    } catch {
      // the preview must never break the tool call itself
    }
    return ran
  })

  on('ui.render', { component: 'Pane', requestId: PANE }, async ($, e) => {
    if (e.surface === 'terminal') {
      const { Text } = $.ui.resolve(e)
      const m = await read($, model)
      return <Text dimColor>3D preview ({m?.name ?? 'no model'}) is drawn only in the desktop app.</Text>
    }
    const { Box, Text, Button, Svg } = $.ui.resolve(e)
    const m = await read($, model)
    const v = await read($, view)

    if (m === null) {
      return <Text dimColor>No model yet. As soon as a .step or .stl file is written, it shows up here.</Text>
    }

    const cols = e.props.bodyColumns || 60
    const W = Math.max(260, Math.min(760, Math.round(cols * 8.2)))
    const H = Math.round(W * 0.8)

    let body
    let info = ''
    try {
      const loaded = await loadStl($, m.path, m.mtimeMs, m.size)
      const { svg, shown } = render(loaded, v, W, H)
      const [dx, dy, dz] = loaded.dims.map(x => x.toFixed(2))
      info = `${dx} × ${dy} × ${dz} mm · ${loaded.triCount} triangles${shown < loaded.triCount ? ` (simplified view: ${shown})` : ''}`
      body = <Svg source={svg} alt={`3D preview of ${m.name}`} width={W} height={H} />
    } catch (err) {
      body = <Text color="red">Could not render the preview: {String((err as Error)?.message ?? err)}</Text>
    }

    const turn = (dy: number, dp: number) => () =>
      update($, view, x => ({ ...x, yaw: x.yaw + dy, pitch: Math.max(-89, Math.min(89, x.pitch + dp)) }))
    const zoom = (k: number) => () => update($, view, x => ({ ...x, zoom: Math.max(0.2, Math.min(8, x.zoom * k)) }))
    const preset = (p: View) => () => update($, view, () => p)

    return (
      <Box flexDirection="column">
        <Text bold>{m.name}</Text>
        <Text dimColor>{info}</Text>
        {body}
        <Box flexDirection="row" flexWrap="wrap" gap={1}>
          <Button key="l" label="◀" onPress={turn(-30, 0)} />
          <Button key="r" label="▶" onPress={turn(30, 0)} />
          <Button key="u" label="▲" onPress={turn(0, 15)} />
          <Button key="d" label="▼" onPress={turn(0, -15)} />
          <Button key="zi" label="+" onPress={zoom(1.25)} />
          <Button key="zo" label="−" onPress={zoom(0.8)} />
        </Box>
        <Box flexDirection="row" flexWrap="wrap" gap={1}>
          <Button key="iso" label="Iso" variant="primary" onPress={preset(ISO)} />
          <Button key="front" label="Front" onPress={preset({ yaw: 0, pitch: 0, zoom: 1 })} />
          <Button key="right" label="Right" onPress={preset({ yaw: -90, pitch: 0, zoom: 1 })} />
          <Button key="top" label="Top" onPress={preset({ yaw: 0, pitch: 89, zoom: 1 })} />
        </Box>
        <Text dimColor>{m.path}</Text>
        {problems.map((p, i) => (
          <Text key={`p${i}`} color="yellow">
            ⚠ {p}
          </Text>
        ))}
      </Box>
    )
  })
}
