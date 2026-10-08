import { expect, test } from 'claude-code/testing'

const COMMON = {
  'rules/common/communication-style.md': '## Communication style & output hygiene\n\n- Direct answers.\n',
  'rules/common/finish-the-task.md': '## Finish the task\n',
  'rules/common/language-rules-pointer.md': 'stale pointer\n',
}
const LANG = {
  'rules/typescript/style.md': 'TS-RULE\n',
  'rules/react/hooks.md': 'REACT-RULE\n',
  'rules/python/style.md': 'PY-RULE\n',
}
const RULES_INJECT_TEXT =
  'SessionStart:startup hook success: <persisted-output>\nOutput too large (12.5KB). Full output saved to: /tmp/x.txt\n\n' +
  'Preview (first 2KB):\n## Communication style & output hygiene\n\n- Direct answers.\n</persisted-output>'
const CACHE_CORE = 'fake/cache/herow/herow-core/64e5'

type World = {
  files?: Record<string, string> | null
  layout?: 'sibling' | 'registry'
  // Settings per source (user, project, local, flag, policy); herow-core is enabled at user scope by default.
  settings?: Record<string, unknown>
  registry?: Array<Record<string, unknown>>
  logs?: string[]
  invalidated?: string[]
  sections?: Array<{ id: string; text: string; scope: string }>
  readFails?: boolean
}

let compactSkip = false

const normalize = (path: string) => {
  const out: string[] = []
  for (const part of path.split('/')) {
    if (part === '..') out.pop()
    else if (part && part !== '.') out.push(part)
  }
  return out.join('/')
}

// A virtual herow-core: beside the plugin ("sibling") or only through installed_plugins.json ("registry").
function world(on, w: World = {}) {
  const files = w.files === undefined ? { ...COMMON, ...LANG } : w.files
  const layout = w.layout ?? 'sibling'
  compactSkip = false
  const rel = (path: string): string | null => {
    const norm = normalize(path)
    if (layout === 'sibling') {
      const at = norm.indexOf('plugins/herow-core')
      return at < 0 ? null : norm.slice(at + 'plugins/herow-core'.length).replace(/^\//, '')
    }
    return norm.startsWith(CACHE_CORE) ? norm.slice(CACHE_CORE.length).replace(/^\//, '') : null
  }
  const isRegistry = (path: string) => layout === 'registry' && normalize(path).endsWith('installed_plugins.json')
  const keys = () => Object.keys(files ?? {})
  const settings = w.settings ?? { user: { enabledPlugins: { 'herow-core@herow': true } } }
  on('settings.read', async ($, e) => ({ value: settings[e.source] ?? {} }))
  on('session.cwd', async () => ({ value: '/repo' }))
  on('fs.exists', async ($, e) => {
    if (isRegistry(e.path)) return { value: true }
    const r = rel(e.path)
    if (!files || r === null) return { value: false }
    return { value: r === '' || keys().some((k) => k === r || k.startsWith(r + '/')) }
  })
  on('fs.list', async ($, e) => {
    const r = rel(e.path) ?? ''
    const names = new Set(keys().filter((k) => k.startsWith(r + '/')).map((k) => k.slice(r.length + 1).split('/')[0]))
    return {
      value: [...names].map((name) => ({
        name,
        kind: name.startsWith('link-') ? 'other' : name.endsWith('.md') ? 'file' : 'dir',
        size: 0,
        mtimeMs: 0,
        isLink: name.startsWith('link-'),
      })),
    }
  })
  on('fs.stat', async ($, e) => {
    if (e.path.endsWith('link-broken.md')) throw new Error('ENOENT')
    return { value: { kind: 'file', size: 1, mtimeMs: 0, isLink: false } }
  })
  on('fs.read', async ($, e) => {
    if (w.readFails) throw new Error('disk gone')
    if (isRegistry(e.path)) {
      const entries = w.registry ?? [{ scope: 'user', installPath: `/${CACHE_CORE}` }]
      return { value: JSON.stringify({ plugins: { 'herow-core@herow': entries } }) }
    }
    return { value: files?.[rel(e.path) ?? ''] ?? '' }
  })
  on('ui.log', async ($, e) => {
    w.logs?.push(e.text)
    return { value: undefined }
  })
  on('ui.invalidate', async ($, e) => {
    w.invalidated?.push(e.event)
    return { value: undefined }
  })
  on('session.start', async ($, e) => ({ cwd: e.cwd }))
  on('prompt.compose', async () => ({ sections: w.sections ?? [{ id: 'intro', text: 'You are Claude.', scope: 'shared' }] }))
  on('prompt.attachment', async ($, e) => ({ text: e.text }))
  on('tool.call', async ($, e) => (String(e.file_path).includes('missing') ? { result: 'no such file', isError: true } : { result: 'file body' }))
  on('session.compact', async () =>
    compactSkip ? { skip: 'blocked' } : { messages: [{ role: 'user', text: 'summary', toolUses: [] }] },
  )
  on('session.end', async ($, e) => ({ sessionId: e.sessionId }))
}

// The kit's compact call carries no transcript of its own, so the test hands it one.
const COMPACT = { messages: [{ role: 'user', text: 'hi', toolUses: [] }] } as never
const attachment = (text: string, event = 'SessionStart') => ({ type: 'hook_success', text, origin: { kind: 'hook', event } })
const read = (file_path: string, agentId?: string) => ({ tool: 'Read', file_path, ...(agentId ? { agentId } : {}) })
const composeInput = { model: 'm', promptModel: 'm', surfaces: [], tools: [], outputStyle: null, traits: [] }
const rulesSection = (r) => r.sections.filter((s) => s.id === 'herow-mods:rules')

test('adds the common rules to the main system prompt, byte-identical across renders', async ($, on) => {
  const logs: string[] = []
  world(on, { logs })
  const first = await $.prompt.compose(composeInput)
  const second = await $.prompt.compose(composeInput)
  const [section] = rulesSection(first)
  expect(section.scope).toBe('session')
  expect(section.text.startsWith('## Communication style & output hygiene\n\n- Direct answers.\n\n## Finish the task\n\n')).toBe(true)
  expect(section.text).toContain('herow language rules (typescript, react, python) arrive automatically')
  expect(section.text.includes('stale pointer')).toBe(false)
  expect(second).toEqual(first)
  expect(logs.some((l) => l.startsWith('herow-mods: rules ready ('))).toBe(true)
})

test('replaces a rules section already in the list instead of duplicating it', async ($, on) => {
  world(on, { sections: [{ id: 'herow-mods:rules', text: 'stale', scope: 'session' }] })
  const [section, ...rest] = rulesSection(await $.prompt.compose(composeInput))
  expect(rest.length).toBe(0)
  expect(section.text).not.toBe('stale')
})

test('finds herow-core through installed_plugins.json when it is not beside the plugin', async ($, on) => {
  const logs: string[] = []
  world(on, { layout: 'registry', logs })
  expect(rulesSection(await $.prompt.compose(composeInput)).length).toBe(1)
  expect(logs.some((l) => l.includes(`chars from /${CACHE_CORE})`))).toBe(true)
})

test('follows symlinked rule files like rules-inject.sh does', async ($, on) => {
  world(on, { files: { ...COMMON, 'rules/common/link-extra.md': '## Linked rule\n' } })
  const [section] = rulesSection(await $.prompt.compose(composeInput))
  expect(section.text).toContain('## Linked rule')
})

test('drops the rules-inject attachment only after the section is composed', async ($, on) => {
  const invalidated: string[] = []
  world(on, { invalidated })
  expect((await $.prompt.attachment(attachment(RULES_INJECT_TEXT))).text).toBe(RULES_INJECT_TEXT)
  await $.prompt.compose(composeInput)
  await $.prompt.compose(composeInput)
  expect(invalidated).toEqual(['prompt.attachment'])
  expect((await $.prompt.attachment(attachment(RULES_INJECT_TEXT))).text).toBe(null)
  const jev = 'SessionStart:startup hook success: ## Jev routing assist'
  expect((await $.prompt.attachment(attachment(jev))).text).toBe(jev)
  expect((await $.prompt.attachment(attachment(RULES_INJECT_TEXT, 'UserPromptSubmit'))).text).toBe(RULES_INJECT_TEXT)
})

test('with herow-core missing, everything passes through unchanged and the mod says it is idle', async ($, on) => {
  const logs: string[] = []
  world(on, { files: null, logs })
  expect((await $.prompt.compose(composeInput)).sections.map((s) => s.id)).toEqual(['intro'])
  expect((await $.prompt.attachment(attachment(RULES_INJECT_TEXT))).text).toBe(RULES_INJECT_TEXT)
  expect((await $.tool.call(read('/repo/App.tsx'))).context).toBe(undefined)
  expect(logs.some((l) => l.startsWith('herow-mods: idle, herow-core rules not found (looked in: '))).toBe(true)
})

test('stays idle when herow-core is disabled, even with its files on disk', async ($, on) => {
  const logs: string[] = []
  world(on, { settings: { user: { enabledPlugins: { 'herow-core@herow': false } } }, logs })
  expect((await $.prompt.compose(composeInput)).sections.map((s) => s.id)).toEqual(['intro'])
  expect(logs).toContain('herow-mods: idle, herow-core@herow is disabled. Enable it in /plugin to get herow rules.')
})

test('stays idle when rules/common holds only the pointer', async ($, on) => {
  const logs: string[] = []
  world(on, { files: { 'rules/common/language-rules-pointer.md': 'p\n' }, logs })
  expect((await $.prompt.compose(composeInput)).sections.map((s) => s.id)).toEqual(['intro'])
  expect(logs.some((l) => l.includes('/rules/common has no rules'))).toBe(true)
})

test('a failed load leaves every hook passing through', async ($, on) => {
  const logs: string[] = []
  world(on, { logs, readFails: true })
  expect((await $.prompt.compose(composeInput)).sections.map((s) => s.id)).toEqual(['intro'])
  expect((await $.prompt.attachment(attachment(RULES_INJECT_TEXT))).text).toBe(RULES_INJECT_TEXT)
  expect((await $.tool.call(read('/repo/App.tsx'))).context).toBe(undefined)
  expect(logs.some((l) => l.startsWith('herow-mods: idle, failed to load herow-core rules'))).toBe(true)
})

test('keeps an unrecognised large SessionStart output and logs the fingerprint', async ($, on) => {
  const logs: string[] = []
  world(on, { logs })
  await $.prompt.compose(composeInput)
  const other = 'SessionStart:startup hook success: <persisted-output>\nOutput too large (20KB).\n## Something else\n</persisted-output>'
  expect((await $.prompt.attachment(attachment(other))).text).toBe(other)
  expect(logs).toContain('herow-mods: shell rules not recognised; kept them (rules may appear twice). Fingerprint: "## Communication style & output hygiene".')
})

test('delivers each language once per agent through the result context', async ($, on) => {
  const logs: string[] = []
  world(on, { logs })
  const first = await $.tool.call(read('/repo/App.tsx'))
  expect(first.result).toBe('file body')
  expect(first.context?.length).toBe(2)
  expect(first.context?.[0]).toContain('TS-RULE')
  expect(first.context?.[1]).toContain('REACT-RULE')
  expect((await $.tool.call(read('/repo/Other.tsx'))).context).toBe(undefined)
  const py = await $.tool.call(read('/repo/app.py'))
  expect(py.context?.length).toBe(1)
  expect(py.context?.[0]).toContain('PY-RULE')
  expect(logs).toContain('herow-mods: delivered typescript, react rules')
})

test('a subagent reading first does not use up the main thread delivery', async ($, on) => {
  const logs: string[] = []
  world(on, { logs })
  expect((await $.tool.call(read('/repo/App.tsx', 'a1'))).context?.length).toBe(2)
  expect((await $.tool.call(read('/repo/App.tsx'))).context?.length).toBe(2)
  expect(logs).toContain('herow-mods: delivered typescript, react rules [a1]')
})

test('failed and denied calls deliver nothing and leave the rules for the next call', async ($, on) => {
  on('tool.call', { file_path: /denied/ }, async () => ({ deny: 'blocked' }))
  world(on)
  const failed = await $.tool.call(read('/repo/missing.tsx'))
  expect(failed.isError).toBe(true)
  expect(failed.context).toBe(undefined)
  expect((await $.tool.call(read('/repo/denied.tsx'))).context).toBe(undefined)
  expect((await $.tool.call(read('/repo/App.tsx'))).context?.length).toBe(2)
})

test('files outside the language sets get nothing', async ($, on) => {
  world(on)
  expect((await $.tool.call(read('/repo/README.md'))).context).toBe(undefined)
  expect((await $.tool.call(read('/repo/main.rs'))).context).toBe(undefined)
})

test('two concurrent reads deliver once, in either completion order', async ($, on) => {
  const waiting: Array<() => void> = []
  on('tool.call', { file_path: /slow/ }, async () => {
    await new Promise<void>((resolve) => waiting.push(resolve))
    return { result: 'file body' }
  })
  world(on)
  for (const [agent, firstDone] of [['x', 0], ['y', 1]] as const) {
    waiting.length = 0
    const a = $.tool.call(read('/repo/slow-a.tsx', agent))
    const b = $.tool.call(read('/repo/slow-b.tsx', agent))
    while (waiting.length < 2) await new Promise((r) => setTimeout(r, 1))
    waiting[firstDone]()
    waiting[1 - firstDone]()
    const delivered = (await Promise.all([a, b])).filter((r) => r.context?.length)
    expect(delivered.length).toBe(1)
  }
})

test('compaction re-arms only the compacted conversation; a skipped one re-arms nothing', async ($, on) => {
  world(on)
  await $.tool.call(read('/repo/App.tsx'))
  await $.tool.call(read('/repo/App.tsx', 'a1'))
  compactSkip = true
  await $.session.compact(COMPACT)
  expect((await $.tool.call(read('/repo/App.tsx'))).context).toBe(undefined)
  compactSkip = false
  await $.session.compact(COMPACT)
  expect((await $.tool.call(read('/repo/App.tsx'))).context?.length).toBe(2)
  expect((await $.tool.call(read('/repo/App.tsx', 'a1'))).context).toBe(undefined)
})

test('/clear and resume re-arm every agent; other session ends keep delivery state', async ($, on) => {
  world(on)
  await $.tool.call(read('/repo/App.tsx'))
  await $.tool.call(read('/repo/App.tsx', 'a1'))
  await $.session.end({ reason: 'other', sessionId: 's1', resume: 's1' } as never)
  expect((await $.tool.call(read('/repo/App.tsx'))).context).toBe(undefined)
  await $.session.end({ reason: 'clear', sessionId: 's1', resume: 's1' } as never)
  expect((await $.tool.call(read('/repo/App.tsx'))).context?.length).toBe(2)
  expect((await $.tool.call(read('/repo/App.tsx', 'a1'))).context?.length).toBe(2)
  await $.session.end({ reason: 'resume', sessionId: 's2', resume: 's2' } as never)
  expect((await $.tool.call(read('/repo/App.tsx'))).context?.length).toBe(2)
})

test('a project install from another checkout is ignored; a stale entry falls through to the next', async ($, on) => {
  const logs: string[] = []
  world(on, {
    layout: 'registry',
    logs,
    registry: [
      { scope: 'project', projectPath: '/other-repo', installPath: '/elsewhere/herow-core' },
      { scope: 'user', installPath: '/stale/herow-core' },
      { scope: 'local', projectPath: '/repo', installPath: `/${CACHE_CORE}` },
    ],
  })
  expect(rulesSection(await $.prompt.compose(composeInput)).length).toBe(1)
  expect(logs.some((l) => l.includes(`chars from /${CACHE_CORE})`))).toBe(true)
})

test('a marketplace install is not used unless herow-core is explicitly enabled', async ($, on) => {
  const logs: string[] = []
  world(on, { layout: 'registry', settings: {}, logs })
  expect((await $.prompt.compose(composeInput)).sections.map((s) => s.id)).toEqual(['intro'])
  expect(logs.some((l) => l.startsWith('herow-mods: idle, herow-core rules not found'))).toBe(true)
})

test('the highest-precedence settings source decides whether herow-core is enabled', async ($, on) => {
  const logs: string[] = []
  world(on, {
    layout: 'registry',
    settings: {
      user: { enabledPlugins: { 'herow-core@herow': true } },
      project: { enabledPlugins: { 'other@x': true } },
      local: { enabledPlugins: { 'herow-core@herow': false } },
    },
    logs,
  })
  expect((await $.prompt.compose(composeInput)).sections.map((s) => s.id)).toEqual(['intro'])
  expect(logs).toContain('herow-mods: idle, herow-core@herow is disabled. Enable it in /plugin to get herow rules.')
})

test('a dangling symlink is skipped instead of idling the mod', async ($, on) => {
  world(on, { files: { ...COMMON, 'rules/common/link-broken.md': 'x' } })
  expect(rulesSection(await $.prompt.compose(composeInput)).length).toBe(1)
})

test('/clear retries a failed load and never reloads a good one', async ($, on) => {
  const logs: string[] = []
  const w: World = { logs, readFails: true }
  world(on, w)
  expect((await $.prompt.compose(composeInput)).sections.map((s) => s.id)).toEqual(['intro'])
  w.readFails = false
  await $.session.end({ reason: 'clear', sessionId: 's1', resume: 's1' } as never)
  expect(rulesSection(await $.prompt.compose(composeInput)).length).toBe(1)
  await $.session.end({ reason: 'clear', sessionId: 's2', resume: 's2' } as never)
  await $.prompt.compose(composeInput)
  expect(logs.filter((l) => l.startsWith('herow-mods: rules ready (')).length).toBe(1)
})

test('a tool call that throws releases the claim for the next call', async ($, on) => {
  on('tool.call', { file_path: /throws/ }, async () => {
    throw new Error('interrupted')
  })
  world(on)
  await $.tool.call(read('/repo/throws.tsx')).catch(() => undefined)
  expect((await $.tool.call(read('/repo/App.tsx'))).context?.length).toBe(2)
})

test('a precompute compaction keeps delivery state', async ($, on) => {
  world(on)
  await $.tool.call(read('/repo/App.tsx'))
  await $.session.compact({ ...(COMPACT as object), trigger: 'precompute' } as never)
  expect((await $.tool.call(read('/repo/App.tsx'))).context).toBe(undefined)
})
