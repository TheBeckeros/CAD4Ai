import { expect, mock, test } from 'claude-code/testing'

const CUBE = 'U1RMIEV4cG9ydGVkIGJ5IE9wZW4gQ0FTQ0FERSBUZWNobm9sb2d5IFtkZXYub3BlbmNhc2NhZGUub3JnXQAAAAAAAAAAAAAAAAAAAAAAAAAsAAAAAACAvwAAAAAAAAAAAAAgwQAAEMEAAJhBAAAgwQAAEEEAAIA/AAAgwQAAEMEAAIA/AAAAAIC/AAAAAAAAAAAAACDBAAAQwQAAmEEAACDBAAAQQQAAmEEAACDBAAAQQQAAgD8AAPMENb/zBDW/AAAAAAAAEMEAACDBAACYQQAAIMEAABDBAACYQQAAIMEAABDBAACAPwAA8wQ1v/MENb8AAACAAAAQwQAAIMEAAJhBAAAgwQAAEMEAAIA/AAAQwQAAIMEAAIA/AADzBDW/AAAAgPMENb8AABDBAAAQQQAAwCUAABDBAAAQwQAAwCUAACDBAAAQwQAAgD8AAPMENb8AAAAA8wQ1vwAAEMEAABBBAADAJQAAIMEAABDBAACAPwAAIMEAABBBAACAPwAA8wQ1vwAAAADzBDU/AAAgwQAAEEEAAJhBAAAgwQAAEMEAAJhBAAAQwQAAEMEAAKBBAADzBDW/AAAAAPMENT8AABDBAAAQQQAAoEEAACDBAAAQQQAAmEEAABDBAAAQwQAAoEEAAPMENb/zBDU/AAAAAAAAIMEAABBBAACYQQAAEMEAACBBAACAPwAAIMEAABBBAACAPwAA8wQ1v/MENT8AAAAAAAAQwQAAIEEAAJhBAAAQwQAAIEEAAIA/AAAgwQAAEEEAAJhBAAA6zRO/Os0TvzrNE78AABDBAAAgwQAAgD8AACDBAAAQwQAAgD8AABDBAAAQwQAAwCUAADrNE786zRO/Os0TPwAAEMEAACDBAACYQQAAEMEAABDBAACgQQAAIMEAABDBAACYQQAAAAAAgAAAgL8AAAAAAAAQQQAAIMEAAJhBAAAQwQAAIMEAAJhBAAAQwQAAIMEAAIA/AAAAAAAAAACAvwAAAIAAABBBAAAgwQAAmEEAABDBAAAgwQAAgD8AABBBAAAgwQAAgD8AAAAAAIAAAAAAAACAvwAAEEEAABBBAADAJQAAEMEAABDBAADAJQAAEMEAABBBAADAJQAAAAAAAAAAAIAAAIC/AAAQQQAAEEEAAMAlAAAQQQAAEMEAAMAlAAAQwQAAEMEAAMAlAAA6zRO/Os0TPzrNE78AABDBAAAgQQAAgD8AABDBAAAQQQAAwCUAACDBAAAQQQAAgD8AAAAAAAAAAAAAAACAPwAAEEEAABBBAACgQQAAEMEAABBBAACgQQAAEMEAABDBAACgQQAAAAAAAAAAAAAAAIA/AAAQQQAAEEEAAKBBAAAQwQAAEMEAAKBBAAAQQQAAEMEAAKBBAAA6zRO/Os0TPzrNEz8AABDBAAAQQQAAoEEAABDBAAAgQQAAmEEAACDBAAAQQQAAmEEAAAAAAAAAAIA/AAAAAAAAEEEAACBBAACYQQAAEMEAACBBAACAPwAAEMEAACBBAACYQQAAAAAAAAAAgD8AAAAAAAAQQQAAIEEAAJhBAAAQQQAAIEEAAIA/AAAQwQAAIEEAAIA/AAAAAACA8wQ1v/MENb8AABBBAAAQwQAAwCUAABDBAAAgwQAAgD8AABDBAAAQwQAAwCUAAAAAAADzBDW/8wQ1vwAAEEEAABDBAADAJQAAEEEAACDBAACAPwAAEMEAACDBAACAPwAAAAAAAPMENb/zBDU/AAAQQQAAIMEAAJhBAAAQwQAAEMEAAKBBAAAQwQAAIMEAAJhBAAAAAAAA8wQ1v/MENT8AABBBAAAQwQAAoEEAABDBAAAQwQAAoEEAABBBAAAgwQAAmEEAAPMENT/zBDW/AAAAAAAAIEEAABDBAACYQQAAEEEAACDBAACAPwAAIEEAABDBAACAPwAA8wQ1P/MENb8AAAAAAAAQQQAAIMEAAJhBAAAQQQAAIMEAAIA/AAAgQQAAEMEAAJhBAAAAAAAA8wQ1P/MENb8AABBBAAAQQQAAwCUAABDBAAAQQQAAwCUAABDBAAAgQQAAgD8AAAAAAADzBDU/8wQ1vwAAEEEAABBBAADAJQAAEMEAACBBAACAPwAAEEEAACBBAACAPwAA8wQ1PwAAAADzBDW/AAAQQQAAEEEAAMAlAAAgQQAAEMEAAIA/AAAQQQAAEMEAAMAlAADzBDU/AAAAAPMENb8AABBBAAAQQQAAwCUAACBBAAAQQQAAgD8AACBBAAAQwQAAgD8AAAAAAADzBDU/8wQ1PwAAEEEAABBBAACgQQAAEMEAACBBAACYQQAAEMEAABBBAACgQQAAAAAAAPMENT/zBDU/AAAQQQAAEEEAAKBBAAAQQQAAIEEAAJhBAAAQwQAAIEEAAJhBAADzBDU/AAAAAPMENT8AABBBAAAQQQAAoEEAABBBAAAQwQAAoEEAACBBAAAQwQAAmEEAAPMENT8AAAAA8wQ1PwAAEEEAABBBAACgQQAAIEEAABDBAACYQQAAIEEAABBBAACYQQAA8wQ1P/MENT8AAAAAAAAQQQAAIEEAAJhBAAAgQQAAEEEAAJhBAAAgQQAAEEEAAIA/AADzBDU/8wQ1PwAAAAAAABBBAAAgQQAAmEEAACBBAAAQQQAAgD8AABBBAAAgQQAAgD8AADrNEz86zRO/Os0TvwAAEEEAACDBAACAPwAAEEEAABDBAADAJQAAIEEAABDBAACAPwAAOs0TPzrNE786zRM/AAAQQQAAIMEAAJhBAAAgQQAAEMEAAJhBAAAQQQAAEMEAAKBBAAAAAIA/AAAAAAAAAAAAACBBAAAQwQAAmEEAACBBAAAQwQAAgD8AACBBAAAQQQAAgD8AAAAAgD8AAACAAAAAAAAAIEEAABDBAACYQQAAIEEAABBBAACAPwAAIEEAABBBAACYQQAAOs0TPzrNEz86zRO/AAAQQQAAIEEAAIA/AAAgQQAAEEEAAIA/AAAQQQAAEEEAAMAlAAA6zRM/Os0TPzrNEz8AABBBAAAQQQAAoEEAACBBAAAQQQAAmEEAABBBAAAgQQAAmEEAAA=='
const SIZE = 2284

const PANE = {
  plugin: 'cad-preview',
  component: 'Pane',
  requestId: 'cad-preview',
  props: {
    title: '3D',
    isFocused: false,
    bodyColumns: 60,
    placement: 'dock',
    scroll: { offset: 0, bodyRows: 40 },
    view: {},
  },
} as const

test('a new STL updates the viewer model and never opens the old pane', async ($, on) => {
  let written = false
  let opened = 0
  const writes: { path: string; text: string }[] = []
  on('command.register', () => ({ value: { command: 'cad-preview' } }))
  on('ui.open', () => {
    opened += 1
    return { value: { isPlaced: true } }
  })
  on('session.start', (_, e) => ({ cwd: e.cwd }))
  on('session.cwd', () => ({ value: '/w' }))
  on('process.run', () => ({ value: { exitCode: 0, stdout: 'started', stderr: '', isStdoutTruncated: false, isStderrTruncated: false } }))
  on('store.get', () => ({ value: undefined }))
  on('store.set', () => ({ value: undefined }))
  on('fs.list', (_, e) => ({
    value:
      written && /w$/.test((e as { path: string }).path)
        ? [{ name: 'cube.stl', kind: 'file', size: SIZE, mtimeMs: 2000, isLink: false }]
        : [],
  }))
  on('fs.stat', () => ({ value: { kind: 'file', size: SIZE, mtimeMs: 2000, isLink: false } }))
  on('fs.write', (_, e) => {
    writes.push(e as { path: string; text: string })
    return { value: undefined }
  })
  on('prompt.compose', () => ({ sections: [{ id: 'intro', text: 'x', scope: 'shared' }] }))
  on('tool.call', () => {
    written = true
    return { result: {} }
  })

  await $.session.start({ cwd: '/w', surface: 'desktop', isInteractive: true })
  await $.tool.call({ tool: 'Bash', command: 'python cube.py' })
  expect(opened).toBe(0)
  const latest = writes.find(w => /latest\.json$/.test(w.path))
  expect(latest).toBeDefined()
  expect(JSON.parse(latest!.text).name).toBe('cube.stl')

  const composed = await $.prompt.compose({ model: 'claude-opus-5-5', promptModel: 'claude-opus-5-5', surfaces: ['desktop'], tools: [], outputStyle: null, traits: [] })
  expect(composed.sections.some(sec => sec.id === 'cad-preview:viewer' && sec.text.includes('/cad-preview'))).toBe(true)
})

test('a confirmed annotation is appended to the draft, never sent', async ($, on) => {
  const clock = mock.clock(on)
  const fills: { text: string; mode?: string }[] = []
  let submits = 0
  let draft = 'my text'
  const store = new Map<string, unknown>()
  on('command.register', () => ({ value: { command: 'cad-preview' } }))
  on('session.start', (_, e) => ({ cwd: e.cwd }))
  on('session.cwd', () => ({ value: '/w' }))
  on('process.run', () => ({ value: { exitCode: 0, stdout: 'started', stderr: '', isStdoutTruncated: false, isStderrTruncated: false } }))
  on('store.get', (_, e) => ({ value: store.get((e as { key: string }).key) }))
  on('store.set', (_, e) => {
    store.set((e as { key: string }).key, (e as { value: unknown }).value)
    return { value: undefined }
  })
  on('fs.list', (_, e) =>
    ({
      value: /inbox$/.test((e as { path: string }).path)
        ? [
            { name: 'a.json', kind: 'file', size: 10, mtimeMs: 1, isLink: false },
            { name: 'b.json', kind: 'file', size: 10, mtimeMs: 2, isLink: false },
          ]
        : [],
    }),
  )
  on('fs.read', (_, e) => ({
    value: JSON.stringify({
      model: '/w/cube.stl',
      name: 'cube.stl',
      comment: /a\.json$/.test((e as { path: string }).path) ? 'remove the chamfer' : 'M5 hole',
      strokes: [],
      id: 'a1',
      features: [{ index: 1, type: 'face', part: 'plate', title: 'plate: Face #9', description: 'cylindrical face (hole) Ø6.40 mm', point: [-22, 0, 4] }],
      measurements: [{ index: 1, text: 'centers 44.00 mm', refs: ['A', 'B'], from: [-22, 0, 4], to: [22, 0, 4] }],
    }),
  }))
  on('prompt.read', () => ({ value: { text: draft, cursor: draft.length } }))
  on('prompt.fill', (_, e) => {
    const a = e as { text: string; mode?: string }
    fills.push(a)
    draft += a.text
    return { isFilled: true, text: draft, cursor: draft.length }
  })
  on('ui.status', () => ({ value: undefined }))
  on('ui.toast', () => ({ value: undefined }))
  on('prompt.submit', () => {
    submits += 1
    return {}
  })

  await $.session.start({ cwd: '/w', surface: 'desktop', isInteractive: true })
  await clock.advance(1600)
  await clock.advance(1600)

  expect(submits).toBe(0)
  expect(fills.length).toBe(2)
  expect(fills[0]?.mode).toBe('append')
  expect(draft).toContain('Note 1: remove the chamfer')
  expect(draft).toContain('Note 2: M5 hole')
  expect(draft.startsWith('my text\n\nNote 1')).toBe(true)
})

test('a broken inbox file is skipped, the batch after it is appended exactly once', async ($, on) => {
  const clock = mock.clock(on)
  let draft = ''
  let fills = 0
  const store = new Map<string, unknown>()
  on('command.register', () => ({ value: { command: 'cad-preview' } }))
  on('session.start', (_, e) => ({ cwd: e.cwd }))
  on('session.cwd', () => ({ value: '/w' }))
  on('process.run', () => ({ value: { exitCode: 0, stdout: 'started', stderr: '', isStdoutTruncated: false, isStderrTruncated: false } }))
  on('store.get', (_, e) => ({ value: store.get((e as { key: string }).key) }))
  on('store.set', (_, e) => {
    store.set((e as { key: string }).key, (e as { value: unknown }).value)
    return { value: undefined }
  })
  on('fs.list', (_, e) =>
    ({
      value: /inbox$/.test((e as { path: string }).path)
        ? [
            { name: '1-old.json', kind: 'file', size: 10, mtimeMs: 1, isLink: false },
            { name: '2-batch.json', kind: 'file', size: 10, mtimeMs: 2, isLink: false },
          ]
        : [],
    }),
  )
  on('fs.read', (_, e) => ({
    value: /old\.json$/.test((e as { path: string }).path)
      ? '{"model": "/w/cube.step", broken'
      : JSON.stringify({
          id: '2-batch', kind: 'batch', model: '/w/cube.step', name: 'cube.step', comment: 'A: (no note)',
          markers: [{ label: 'A', type: 'point', points: [[1, 2, 3]], faceNormal: [0, 0, 1], part: 'cube', note: '' }],
          camera: { viewDir: [0, 0, -1] }, parts: ['cube'],
        }),
  }))
  on('prompt.read', () => ({ value: { text: draft, cursor: draft.length } }))
  on('prompt.fill', (_, e) => {
    fills += 1
    draft += (e as { text: string }).text
    return { isFilled: true, text: draft, cursor: draft.length }
  })
  on('ui.status', () => ({ value: undefined }))
  on('ui.toast', () => ({ value: undefined }))
  on('prompt.submit', () => ({}))

  await $.session.start({ cwd: '/w', surface: 'desktop', isInteractive: true })
  for (let i = 0; i < 5; i++) await clock.advance(1600)

  expect(fills).toBe(1)
  expect(draft.startsWith('Note 1: Several places marked on the model')).toBe(true)
  expect(draft).toContain('A) point on part cube: [1, 2, 3]; face normal [0, 0, 1]')
  expect(draft).toContain('   note: (no note)')
})

test('the session the user writes in takes over the shared viewer, a started one does not', async ($, on) => {
  const posts: string[] = []
  on('command.register', () => ({ value: { command: 'cad-preview' } }))
  on('session.start', (_, e) => ({ cwd: e.cwd }))
  on('session.cwd', () => ({ value: '/w' }))
  on('process.run', () => ({ value: { exitCode: 0, stdout: 'started', stderr: '', isStdoutTruncated: false, isStderrTruncated: false } }))
  on('store.get', () => ({ value: undefined }))
  on('store.set', () => ({ value: undefined }))
  on('fs.list', () => ({ value: [] }))
  on('http.fetch', (_, e) => {
    const f = e as { url: string; init?: { body?: string } }
    if (/api\/data$/.test(f.url)) posts.push(f.init?.body ?? '')
    return { value: { status: 200, ok: true, headers: {}, text: '{"ok": true}' } }
  })
  on('prompt.submit', (_, e) => e)

  await $.session.start({ cwd: '/w', surface: 'desktop', isInteractive: true })
  expect(posts.length).toBe(0)
  await $.prompt.submit({ text: 'hi', wait: false })
  await new Promise(r => setTimeout(r, 0))
  expect(posts.length).toBe(1)
  expect(JSON.parse(posts[0]!).data).toContain('.cad-preview')
})

test('a STEP-only export is shown as is, no STL needed', async ($, on) => {
  let written = false
  const writes: { path: string; text: string }[] = []
  on('command.register', () => ({ value: { command: 'cad-preview' } }))
  on('session.start', (_, e) => ({ cwd: e.cwd }))
  on('session.cwd', () => ({ value: '/w' }))
  on('process.run', () => ({ value: { exitCode: 0, stdout: 'started', stderr: '', isStdoutTruncated: false, isStderrTruncated: false } }))
  on('store.get', () => ({ value: undefined }))
  on('store.set', () => ({ value: undefined }))
  on('fs.list', (_, e) => ({
    value: written && /w$/.test((e as { path: string }).path) ? [{ name: 'part.step', kind: 'file', size: 900, mtimeMs: 2000, isLink: false }] : [],
  }))
  on('fs.write', (_, e) => {
    writes.push(e as { path: string; text: string })
    return { value: undefined }
  })
  on('tool.call', () => {
    written = true
    return { result: {} }
  })

  await $.session.start({ cwd: '/w', surface: 'desktop', isInteractive: true })
  await $.tool.call({ tool: 'Bash', command: 'python part.py' })
  const latest = writes.find(w => /latest\.json$/.test(w.path))
  expect(JSON.parse(latest!.text).name).toBe('part.step')
})
