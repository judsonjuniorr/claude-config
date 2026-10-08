export type RuleFile = { name: string; text: string }

const CORE_ID = 'herow-core@herow'

// rules-inject.sh generates its own pointer, so a checked-in copy is never injected.
const SKIPPED = new Set(['language-rules-pointer.md'])

export const LANG_SETS = ['typescript', 'react', 'python', 'rust', 'swift', 'csharp', 'web'] as const

const SETS_BY_EXT: Record<string, readonly string[]> = {
  ts: ['typescript'],
  mts: ['typescript'],
  cts: ['typescript'],
  js: ['typescript'],
  mjs: ['typescript'],
  cjs: ['typescript'],
  tsx: ['typescript', 'react'],
  jsx: ['typescript', 'react'],
  vue: ['typescript', 'web'],
  svelte: ['typescript', 'web'],
  astro: ['typescript', 'web'],
  py: ['python'],
  pyi: ['python'],
  rs: ['rust'],
  swift: ['swift'],
  cs: ['csharp'],
  html: ['web'],
  htm: ['web'],
  css: ['web'],
  scss: ['web'],
  sass: ['web'],
  less: ['web'],
}

const byName = (a: RuleFile, b: RuleFile) => (a.name < b.name ? -1 : a.name > b.name ? 1 : 0)

// Mirrors rules-inject.sh: each common file in name order, followed by a blank line.
export function buildCommon(files: readonly RuleFile[]): string {
  return files
    .filter((f) => f.name.endsWith('.md') && !SKIPPED.has(f.name))
    .sort(byName)
    .map((f) => f.text + '\n')
    .join('')
}

export function buildLangSet(set: string, files: readonly RuleFile[]): string {
  const body = files
    .filter((f) => f.name.endsWith('.md'))
    .sort(byName)
    .map((f) => f.text.trimEnd())
    .join('\n\n')
  return body ? `# herow ${set} rules (apply while working on ${set} code)\n\n${body}\n` : ''
}

export function languageNote(root: string, delivered: readonly string[]): string {
  return (
    '## Language-specific rules\n\n' +
    `herow language rules (${delivered.join(', ')}) arrive automatically with the first file you read ` +
    'or write in that language. If you work on code in a language whose rules have not arrived ' +
    `(for example only through Bash), read \`${root}/rules/<language>/\` before writing code. ` +
    `For backend/API work, read \`${root}/rules/backend/\`.\n`
  )
}

export function fingerprint(common: string): string {
  return common.split('\n').find((line) => line.trim() !== '')?.trim() ?? ''
}

// The rules-inject attachment may be wrapped (hook-success prefix, persisted-output preview),
// so match the fingerprint as a whole line anywhere in the text.
export function isRulesInjectText(text: string, fp: string): boolean {
  return fp !== '' && text.split('\n').some((line) => line.trim() === fp)
}

export function langSetsFor(path: string): string[] {
  const ext = /\.([A-Za-z0-9]+)$/.exec(path)?.[1]?.toLowerCase()
  return ext ? [...(SETS_BY_EXT[ext] ?? [])] : []
}

// A repo checkout or --plugin-dir load keeps herow-core beside this plugin.
export function siblingRoot(pluginRoot: string): string {
  return `${pluginRoot.replace(/[\\/]+$/, '')}/../herow-core`
}

// Marketplace installs live at <plugins>/cache/<marketplace>/<plugin>/<version>.
export function registryPath(pluginRoot: string): string {
  return `${pluginRoot.replace(/[\\/]+$/, '')}/../../../../installed_plugins.json`
}

type InstallEntry = { scope?: string; projectPath?: string; installPath?: unknown }

// Install paths that apply to this session: user-scope installs, or project/local ones for this checkout.
export function installPathsFrom(registry: unknown, cwd: string): string[] {
  const entries = (registry as { plugins?: Record<string, unknown> })?.plugins?.[CORE_ID]
  if (!Array.isArray(entries)) return []
  return entries
    .filter((e: InstallEntry) => typeof e?.installPath === 'string')
    .filter((e: InstallEntry) => e.scope === 'user' || (typeof e.projectPath === 'string' && isWithin(cwd, e.projectPath)))
    .map((e: InstallEntry) => e.installPath as string)
}

function isWithin(path: string, dir: string): boolean {
  const base = dir.replace(/[\\/]+$/, '')
  return path === base || path.startsWith(base + '/') || path.startsWith(base + '\\')
}

// The last settings source (lowest precedence first) that mentions herow-core decides; undefined when none does.
export function coreEnabledSetting(sources: readonly unknown[]): boolean | undefined {
  let value: boolean | undefined
  for (const src of sources) {
    const v = (src as { enabledPlugins?: Record<string, unknown> })?.enabledPlugins?.[CORE_ID]
    if (typeof v === 'boolean') value = v
  }
  return value
}

export function agentKey(agentId: string | undefined): string {
  return agentId ?? 'main'
}

// Marks the sets as delivered before the caller awaits, so concurrent calls never deliver twice.
export function claimSets(delivered: Map<string, Set<string>>, agent: string, sets: readonly string[]): string[] {
  if (sets.length === 0) return []
  let seen = delivered.get(agent)
  if (!seen) {
    seen = new Set()
    delivered.set(agent, seen)
  }
  const fresh = sets.filter((s) => !seen.has(s))
  for (const s of fresh) seen.add(s)
  return fresh
}

export function releaseSets(delivered: Map<string, Set<string>>, agent: string, sets: readonly string[]): void {
  const seen = delivered.get(agent)
  for (const s of sets) seen?.delete(s)
}
