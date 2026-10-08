import { describe, expect, test } from 'claude-code/testing'
import {
  buildCommon,
  buildLangSet,
  claimSets,
  fingerprint,
  installPathFrom,
  isCoreDisabled,
  isRulesInjectText,
  langSetsFor,
  languageNote,
  registryPath,
  releaseSets,
  siblingRoot,
} from '../hooks/rules.ts'

describe('buildCommon', () => {
  test('orders by name and ends each file with a blank line, like rules-inject.sh', () => {
    const out = buildCommon([
      { name: 'b.md', text: '## B\nbody\n' },
      { name: 'a.md', text: '## A\n' },
    ])
    expect(out).toBe('## A\n\n## B\nbody\n\n')
  })

  test('keeps a file without a trailing newline glued to its blank line, as cat + echo does', () => {
    expect(buildCommon([{ name: 'a.md', text: 'no newline' }, { name: 'b.md', text: 'B\n' }])).toBe('no newline\nB\n\n')
  })

  test('skips the checked-in pointer and non-markdown files', () => {
    const out = buildCommon([
      { name: 'language-rules-pointer.md', text: 'pointer' },
      { name: 'notes.txt', text: 'txt' },
      { name: 'a.md', text: 'kept' },
    ])
    expect(out).toBe('kept\n')
  })

  test('is empty when there are no rule files', () => {
    expect(buildCommon([])).toBe('')
  })
})

describe('buildLangSet and languageNote', () => {
  test('heads the set and joins its files in name order', () => {
    const out = buildLangSet('react', [
      { name: 'hooks.md', text: 'H\n' },
      { name: 'a11y.md', text: 'A' },
    ])
    expect(out).toBe('# herow react rules (apply while working on react code)\n\nA\n\nH\n')
  })

  test('is empty for a set with no files', () => {
    expect(buildLangSet('rust', [])).toBe('')
  })

  test('the note lists only loaded sets and keeps a pointer for anything else', () => {
    const note = languageNote('/core', ['python'])
    expect(note).toContain('herow language rules (python) arrive automatically')
    expect(note).toContain('read `/core/rules/<language>/`')
    expect(note).toContain('read `/core/rules/backend/`')
  })
})

describe('fingerprint and isRulesInjectText', () => {
  test('fingerprint is the first non-blank line', () => {
    expect(fingerprint('\n\n  ## Communication style  \nrest')).toBe('## Communication style')
  })

  test('matches the rules-inject text even inside a persisted-output preview', () => {
    const text =
      'SessionStart:startup hook success: <persisted-output>\nOutput too large (12.5KB).\n\n' +
      'Preview (first 2KB):\n## Communication style\n\n- Direct answers\n</persisted-output>'
    expect(isRulesInjectText(text, '## Communication style')).toBe(true)
  })

  test('does not match other hooks or a partial line', () => {
    expect(isRulesInjectText('SessionStart:startup hook success: ## Jev routing assist', '## Communication style')).toBe(false)
    expect(isRulesInjectText('see ## Communication style docs', '## Communication style')).toBe(false)
    expect(isRulesInjectText('## Communication style', '')).toBe(false)
  })
})

describe('langSetsFor', () => {
  test('maps extensions to language sets', () => {
    const cases: Array<[string, string[]]> = [
      ['/x/Button.tsx', ['typescript', 'react']],
      ['/x/Card.jsx', ['typescript', 'react']],
      ['/x/util.MJS', ['typescript']],
      ['/x/mod.cts', ['typescript']],
      ['/x/App.vue', ['typescript', 'web']],
      ['/x/Page.svelte', ['typescript', 'web']],
      ['/x/app.py', ['python']],
      ['/x/types.pyi', ['python']],
      ['/x/main.rs', ['rust']],
      ['/x/View.swift', ['swift']],
      ['/x/Program.cs', ['csharp']],
      ['/x/index.htm', ['web']],
      ['/x/site.less', ['web']],
      ['C:\\repo\\src\\app.ts', ['typescript']],
    ]
    for (const [path, sets] of cases) expect(langSetsFor(path)).toEqual(sets)
  })

  test('returns nothing for unknown or missing extensions', () => {
    expect(langSetsFor('/x/README.md')).toEqual([])
    expect(langSetsFor('/x/Makefile')).toEqual([])
    expect(langSetsFor('/a.b/Makefile')).toEqual([])
    expect(langSetsFor('')).toEqual([])
  })
})

describe('herow-core resolution', () => {
  test('sibling and registry paths follow the repo and marketplace cache layouts', () => {
    expect(siblingRoot('/repo/plugins/herow-mods/')).toBe('/repo/plugins/herow-mods/../herow-core')
    expect(registryPath('/h/.claude/plugins/cache/herow/herow-mods/abc')).toBe(
      '/h/.claude/plugins/cache/herow/herow-mods/abc/../../../../installed_plugins.json',
    )
  })

  test('installPathFrom reads herow-core from installed_plugins.json', () => {
    const registry = { plugins: { 'herow-core@herow': [{ scope: 'user', installPath: '/c/herow-core/64e5' }] } }
    expect(installPathFrom(registry)).toBe('/c/herow-core/64e5')
    expect(installPathFrom({ plugins: {} })).toBe(undefined)
    expect(installPathFrom(null)).toBe(undefined)
    expect(installPathFrom({ plugins: { 'herow-core@herow': 'bad' } })).toBe(undefined)
  })

  test('isCoreDisabled is true only for an explicit false', () => {
    expect(isCoreDisabled({ enabledPlugins: { 'herow-core@herow': false } })).toBe(true)
    expect(isCoreDisabled({ enabledPlugins: { 'herow-core@herow': true } })).toBe(false)
    expect(isCoreDisabled({})).toBe(false)
  })
})

describe('claimSets', () => {
  test('claims each set once per agent and keeps agents independent', () => {
    const delivered = new Map<string, Set<string>>()
    expect(claimSets(delivered, 'main', ['typescript', 'react'])).toEqual(['typescript', 'react'])
    expect(claimSets(delivered, 'main', ['typescript'])).toEqual([])
    expect(claimSets(delivered, 'a1', ['typescript'])).toEqual(['typescript'])
  })

  test('nothing wanted records nothing', () => {
    const delivered = new Map<string, Set<string>>()
    expect(claimSets(delivered, 'main', [])).toEqual([])
    expect(delivered.size).toBe(0)
  })

  test('released sets can be claimed again', () => {
    const delivered = new Map<string, Set<string>>()
    claimSets(delivered, 'main', ['python'])
    releaseSets(delivered, 'main', ['python'])
    expect(claimSets(delivered, 'main', ['python'])).toEqual(['python'])
  })
})
