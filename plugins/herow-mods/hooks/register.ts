import {
  LANG_SETS,
  agentKey,
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
  type RuleFile,
} from './rules.ts'

const SECTION_ID = 'herow-mods:rules'
// Claude Code's wording when it cuts a large hook output down to a preview.
const PERSISTED_MARKERS = ['<persisted-output>', 'Output too large']

type Rules = { root: string; common: string; fp: string; lang: Map<string, string> }

let loading: Promise<Rules | null> | null = null
let composed = false
const delivered = new Map<string, Set<string>>()

async function readDir($, dir: string): Promise<RuleFile[]> {
  const files: RuleFile[] = []
  for (const entry of await $.fs.list(dir)) {
    if (!entry.name.endsWith('.md')) continue
    const path = `${dir}/${entry.name}`
    // A symlink lists as `other`; rules-inject.sh's `[ -f ]` follows it, so follow it too.
    const kind = entry.kind === 'other' ? (await $.fs.stat(path)).kind : entry.kind
    if (kind === 'file') files.push({ name: entry.name, text: String(await $.fs.read(path)) })
  }
  return files
}

async function findRoot($, tried: string[]): Promise<string | null> {
  const sibling = siblingRoot($.plugin.root)
  tried.push(sibling)
  if (await $.fs.exists(`${sibling}/rules/common`)) return sibling
  const registry = registryPath($.plugin.root)
  if (!(await $.fs.exists(registry))) return null
  const installed = installPathFrom(JSON.parse(String(await $.fs.read(registry))))
  if (!installed) return null
  tried.push(installed)
  return (await $.fs.exists(`${installed}/rules/common`)) ? installed : null
}

async function load($): Promise<Rules | null> {
  if (isCoreDisabled(await $.settings.read())) {
    $.ui.log('herow-mods: idle, herow-core@herow is disabled. Enable it in /plugin to get herow rules.')
    return null
  }
  const tried: string[] = []
  const root = await findRoot($, tried)
  if (!root) {
    $.ui.log(
      `herow-mods: idle, herow-core rules not found (looked in: ${tried.join(', ') || 'installed_plugins.json'}). ` +
        'Install herow-core@herow or run /reload-plugins.',
    )
    return null
  }
  const common = buildCommon(await readDir($, `${root}/rules/common`))
  if (!common) {
    $.ui.log(`herow-mods: idle, ${root}/rules/common has no rules. Run /reload-plugins after fixing herow-core.`)
    return null
  }
  const lang = new Map<string, string>()
  for (const set of LANG_SETS) {
    const dir = `${root}/rules/${set}`
    if (!(await $.fs.exists(dir))) continue
    const text = buildLangSet(set, await readDir($, dir))
    if (text) lang.set(set, text)
  }
  $.ui.log(`herow-mods: rules ready (${common.length} chars from ${root})`)
  return { root, common: common + languageNote(root, [...lang.keys()]), fp: fingerprint(common), lang }
}

// Shell hooks fire before session.start, so every hook shares one lazy load.
function rules($): Promise<Rules | null> {
  loading ??= load($).catch((err) => {
    $.ui.log(`herow-mods: idle, failed to load herow-core rules (${err?.message ?? err}).`)
    return null
  })
  return loading
}

export function register(on) {
  on('session.start', async ($, e, next) => {
    await rules($)
    return next(e)
  }).catch(async ($, e, next) => next(e))

  // Raised for the main session's prompt only: subagents get language rules via tool.call instead.
  on('prompt.compose', async ($, e, next) => {
    const result = await next(e)
    const loaded = await rules($)
    if (!loaded) return result
    if (!composed) {
      composed = true
      // Attachment answers are cached, so re-ask any SessionStart output kept before this point.
      $.ui.invalidate('prompt.attachment')
    }
    const sections = result.sections.filter((s) => s.id !== SECTION_ID)
    return { ...result, sections: [...sections, { id: SECTION_ID, text: loaded.common, scope: 'session' }] }
  }).catch(async ($, e, next) => next(e))

  on('prompt.attachment', { type: 'hook_success' }, async ($, e, next) => {
    if (e.origin.kind !== 'hook' || e.origin.event !== 'SessionStart') return next(e)
    const loaded = await rules($)
    // Never drop the shell copy before the mod's own copy is in the system prompt.
    if (!loaded || !composed) return next(e)
    if (isRulesInjectText(e.text, loaded.fp)) return { text: null }
    if (PERSISTED_MARKERS.every((m) => e.text.includes(m))) {
      $.ui.log(`herow-mods: shell rules not recognised; kept them (rules may appear twice). Fingerprint: "${loaded.fp}".`)
    }
    return next(e)
  }).catch(async ($, e, next) => next(e))

  on('tool.call', { tool: ['Read', 'Edit', 'Write'] }, async ($, e, next) => {
    const loaded = await rules($)
    const wanted = loaded ? langSetsFor(String(e.file_path ?? '')).filter((s) => loaded.lang.has(s)) : []
    const agent = agentKey(e.agentId)
    const fresh = claimSets(delivered, agent, wanted)
    const result = await next(e)
    if (fresh.length === 0) return result
    if (result.deny !== undefined || result.isError) {
      releaseSets(delivered, agent, fresh)
      return result
    }
    $.ui.log(`herow-mods: delivered ${fresh.join(', ')} rules${e.agentId ? ` [${e.agentId}]` : ''}`)
    return { ...result, context: [...(result.context ?? []), ...fresh.map((s) => loaded.lang.get(s))] }
  }).catch(async ($, e, next) => next(e))

  on('session.compact', async ($, e, next) => {
    const result = await next(e)
    // precompute installs nothing and a skip keeps the transcript, so rules already sent survive.
    if (e.trigger !== 'precompute' && result.skip === undefined) delivered.delete(agentKey(e.agentId))
    return result
  }).catch(async ($, e, next) => next(e))

  on('session.end', async ($, e, next) => {
    // /clear and resume continue this process with another conversation.
    if (e.reason === 'clear' || e.reason === 'resume') {
      delivered.clear()
      if (loading && !(await loading)) loading = null
    }
    return next(e)
  }).catch(async ($, e, next) => next(e))
}
