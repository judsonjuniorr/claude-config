# claude-config · the **herow** plugin marketplace

Personal Claude Code toolkit — slash commands, skills, agents, guardrail hooks, and
always-on rules — packaged as a **Claude Code plugin marketplace**. No clone, no
symlinks, no install script: two commands and it auto-updates from this repo.

## Install

Inside Claude Code:

```
/plugin marketplace add judsonjuniorr/claude-config
/plugin install herow-core@herow
```

Then pick the suites you want:

```
/plugin install herow-dev@herow       # dev workflows
/plugin install herow-seo@herow       # SEO/GEO suite
/plugin install herow-finance@herow   # finance automation
/plugin install herow-extras@herow    # standalone utilities
```

### Auto-update (do this once)

`/plugin` → **Marketplaces** → `herow` → **Enable auto-update**

Plugins are versioned by **commit SHA** (no pinned `version` in any plugin.json), so
every push to `main` is a new version — with auto-update enabled, it applies at the
next session start. As a fallback, `herow-core` ships a silent SessionStart check
(throttled to once/hour, network-failure-safe) that tells you when you're behind,
and `/herow-core:upgrade` force-updates on demand.

## Plugins

| Plugin | What you get |
|---|---|
| **herow-core** | Guardrail hooks (doc-file warning, config protection, destructive-op confirmation, stop-guard, batched format+typecheck at Stop, console.log checks, git-guard), graphify auto-engage + auto-freshen hooks (`graphify-inject.sh` announces the graph at session start and steers toward `graphify query`/`path`/`explain` when one exists, `graphify-freshen.sh` keeps `graphify-out/` synced to HEAD in the background), always-on coding rules injected at session start (terse "caveman" output **by default** — `/herow-core:uncompress` restores full prose), the `github-ops` skill (token-efficient git/gh/glab via scripts), `code-reviewer` + `debugger` agents, the `jev` skill (typed decisions + on-demand skill/agent routing via OpenRouter, see below), `/herow-core:upgrade`, `/herow-core:doctor` (config doctor: audits security, token-cost, and hygiene and applies fixes with explicit approval; also bootstraps a fresh machine via its install branch — gstack + the herow-dev flow commands, removes OMEGA & conflicts, prompted), and `/herow-core:setup-claude` (interview-driven author of personal `CLAUDE.local.md` / shared `CLAUDE.md` project instructions — a high-signal friction log, not a codebase overview; picks the target, guards `CLAUDE.local.md` privacy via the global excludes, and optionally scaffolds skills + hooks) |
| **herow-dev** | Commands: `/herow-dev:blueprint·quick·execute` (gstack plan→worktree→ship flow, graphify-integrated), `/herow-dev:code:review·refactor·generate-tests` (**`code:review` is the single review door** — auto-detects the changed-file language and dispatches specialist reviewers: `.tsx`/`.jsx` → react + typescript, `.ts`/`.js` → typescript, `.py` (FastAPI-aware) → fastapi + python — running them in parallel, each carrying a dedicated memory-management lane (leaks, retention, unbounded caches/state) for Python and React, then a second-opinion pass — the session's `advisor` tool first, falling back to Codex/Agy/a Claude subagent — that CONFIRM/DISPUTE/ESCALATEs findings; `--fix` runs can end by committing + pushing the applied fixes via `github-ops`), `/herow-dev:git:pr·fix-conflicts·release-notes`, `/herow-dev:react:test·validate-ui`, `/herow-dev:fix-cves` (finds dependency CVEs across Node/TS and Python, upgrades to the minimum patched version — including transitive-only fixes via overrides/resolutions/constraints — and proves no regression with the full lint/type-check/test/build gate before committing). Skills: `/herow-dev:qa-setup` + `/herow-dev:qa-run` (config-driven live-app QA — setup writes a per-project `config.yml` to the `~/.herow` project store, seeds or adopts a knowledge store, and proves it with a live Playwright smoke walk; run QAs a ticket from Jira/Brain/GitHub/free text against the live app with interaction-proof discipline, capped regression + probe passes, staleness checks, a draft ticket comment, and optional Playwright-spec freezing of a passing walk), error-handling, prompt-optimizer, research, exa-search, jira-integration. 17 specialist agents (fullstack, python-pro, reviewers, tdd-guide, ui-ux, …) |
| **herow-seo** | 11 commands (`/herow-seo:weekly-audit`, `ctr-tune`, `indexation-check`, `content-sprint`, `geo-optimize`, `report`, …) + `seo-strategist`, `technical-seo-auditor`, `content-engineer` agents + the GSC data-contract reference |
| **herow-finance** | `/herow-finance:organizze` (Organizze API analysis with the `financial-analyst` agent), `/herow-finance:organizze-create` (create transactions — dry-run + confirm + read-back verify), `context`/`goal`/`profile` helpers, `/herow-finance:nf-tomada` (Contabilizei NF registration). Data lives in `~/.herow/finance/` and survives updates |
| **herow-extras** | `/herow-extras:brainstorm` (any idea → concrete result: PRD, plan, research, an inline brief, or a Claude artifact), `/herow-extras:create-prd`, `/herow-extras:file-organizer`, `/herow-extras:graphify-install`. Skill: `design` (any prompt → a finished graphic image — post, cover, banner, OG — built as typographic HTML/SVG with a saved brand profile, on a Claude Design canvas by default, a shareable Artifact page, or an exact-size PNG via headless Playwright; two directions, pick, iterate) |

### Jev: typed decisions and routing (herow-core)

`herow-core:jev` asks Jev (`typesafe/jev-1.13` on OpenRouter) narrow typed questions
(choice, score, yes/no) and, through `jev-route`, suggests a subagent and a skill per
task from what you have installed. It costs about $0.00007 per routed task.

Setup, once per machine:

1. Run `/herow-core:doctor`. It installs `~/.herow/bin/jev` and `~/.herow/bin/jev-route`
   and lists the key under **Manual steps**.
2. Create a key at https://openrouter.ai/keys (needs credits) and store it in a separate
   terminal:
   ```bash
   security add-generic-password -a "$USER" -s openrouter-api-key -w
   ```
   Without macOS Keychain, add `export OPENROUTER_API_KEY=...` to your shell profile instead.
3. Start a new session or `/clear`. A routing block appears in the session context.

Try it: `~/.herow/bin/jev-route "commit these changes and open a pull request"`
(expect `skill=herow-core:github-ops`). Optional files in `~/.herow/jev/`
(`$HEROW_HOME/jev/` when overridden): `config.json` (`extra_command_dirs`, `rewrites`,
`routing_assist`), `consents.md` (`routing: project-names` allows names in routing
summaries) and `cases.local.json` (your own eval cases for `jev-route --eval --gate 0.9`).

Old install.sh profiles map to: `minimal` → core · `dev` → core+dev · `seo` → core+seo · `finance` → core+finance.

## Migrating from the legacy symlink install

If you previously ran `install.sh` (symlinks into `~/.claude/` + hooks merged into
`settings.json`), run this **before** installing the plugins — otherwise every hook
fires twice:

```bash
./migrate.sh
```

It removes the repo's symlinks from `~/.claude/{agents,commands,skills,rules}`,
strips the merged hook entries from `settings.json` (markers
`claude-config-hooks/` and `github-ops/hooks/`), and prints the install commands.
Idempotent; touches nothing it didn't create.

### Command renames

Plugin commands are namespaced by plugin name (imposed by Claude Code):

| Before | After |
|---|---|
| `/code:review` | `/herow-dev:code:review` |
| `/git:pr` | `/herow-dev:git:pr` |
| `/seo:weekly-audit` | `/herow-seo:weekly-audit` |
| `/finance:organizze` | `/herow-finance:organizze` |
| `/contabilizei:nf-tomada` | `/herow-finance:nf-tomada` |
| `/create-prd` | `/herow-extras:create-prd` |

## Structure

```
claude-config/
├── .claude-plugin/marketplace.json   # the "herow" marketplace (5 plugins)
├── plugins/
│   ├── herow-core/
│   │   ├── .claude-plugin/plugin.json
│   │   ├── hooks/hooks.json          # auto-registered when the plugin is enabled
│   │   ├── scripts/                  # hook scripts + rules-inject.sh + update-check.sh
│   │   ├── rules/                    # common/ (injected at SessionStart) + per-language
│   │   ├── skills/{github-ops,jev}/
│   │   ├── commands/upgrade.md
│   │   └── agents/
│   ├── herow-dev/        # commands/{code,git,react,python}/ + skills/ + agents/
│   ├── herow-seo/        # commands/ + agents/ + reference/gsc-data-contract.md
│   ├── herow-finance/    # commands/ + scripts/{organizze,finance,contabilizei}/ + agents/
│   └── herow-extras/     # commands/ + skills/design/
├── docs/                 # relocated namespace docs + MCP server templates (docs/mcp/)
├── migrate.sh            # legacy symlink install → plugin migration
└── .github/workflows/plugin-ci.yml
```

### How the unsupported pieces work

- **Rules** are not a plugin component type. `herow-core` injects `rules/common/*.md`
  into context via a SessionStart hook (`scripts/rules-inject.sh`), which also prints
  a pointer to the per-language rule sets (`rules/<language>/`) with the resolved
  plugin path — Claude reads those on demand per project.
- **Paths**: plugins are cache-copied, so everything uses `${CLAUDE_PLUGIN_ROOT}`
  (plugin files) or one per-user store, `~/.herow/` (override `HEROW_HOME`):
  `finance/`, `core/`, `seo/`, and `projects/<owner-repo>-<hash>/{plans,qa}` for
  per-repo blueprint plans and QA state. Legacy locations migrate on first run;
  `/herow-core:doctor` offers the `settings.json` access rules for `~/.herow`.
- **MCP servers** are intentionally not bundled (credentials / heavy startup);
  templates live in `docs/mcp/registry.json`.

## (herow) tagging convention

Commands and skills are marked `(herow)` at the start of their `description:`
frontmatter — identifies assets curated by this repo when mixed with other plugins.

## Developing

Repo edits don't live-apply (plugins run from a cache). For iteration, point the
marketplace at your checkout:

```
/plugin marketplace add /path/to/claude-config
```

(Re-add the GitHub form when done — one marketplace per name.) CI
(`plugin-ci.yml`) validates the marketplace + every plugin, blocks hardcoded
`/Users/` paths, legacy template markers, stray command-dir READMEs, and pinned
versions. Validate locally with `claude plugin validate .`.
