# qa-run reference

Read alongside `SKILL.md`, one section at a time, at the phase noted in each heading.

## Required-key list (Phase −1)

Validate `<QA>/config.yml` against this list before doing anything else. Any
missing key, wrong type, or out-of-range value → stop `[config-invalid]` naming the exact
key.

| Key | Type | Constraint |
|---|---|---|
| `schema_version` | int | must be `1` (newer → `[schema-newer]`) |
| `envs` | list[string] | non-empty |
| `services[].name` | string | non-empty |
| `services[].url` | string | non-empty |
| `services[].expect_status` | list[int] | non-empty |
| `services[].start_hint` | string | non-empty |
| `browser.headed_required` | bool | — |
| `browser.viewport` | list[int, int] | length 2 |
| `session.env` | string | must be one of `envs[]` |
| `session.start_url` | string | non-empty |
| `session.login` | string | one of `form \| sso \| magic-link \| none` |
| `session.login_detect` | string | required unless `login: none` |
| `session.credentials_env.user` / `.password` | string | required when `login: form` |
| `session.auto_fill` | bool | required when `login: form` |
| `session.entry_target` | string | non-empty |
| `setup.smoke` | string | one of `pending \| verified` |
| `ticket.default` | string | must name a `ticket.sources[]` entry |
| `ticket.sources[].name` | string | unique within the list |
| `ticket.sources[].kind` | string | one of `mcp \| cli \| text` |
| `ticket.sources[].status` | string | one of `verified \| pending`, required unless `kind: text` |
| `ticket.sources[].id_pattern` | string | required unless `kind: text` |
| `repos[].name` | string | unique within the list |
| `repos[].path` | string | must exist relative to `<CHECKOUT_ROOT>` (`herow-project.sh checkout-root`: the enclosing workspace root when `<QA>` resolved to one, else the current checkout's git toplevel or the cwd — see qa-setup's step 1) |
| `repos[].bug_tag` | string | non-empty |

`freeze.*` and `gotchas[]` are optional and unvalidated beyond basic type — their absence
just means freeze is never offered.

## Report template (Phase 5)

Report dir: `<QA>/reports/<id>-<YYYY-MM-DD-HHMM>/`, where `<id>` is the Jira-style
key, `gh-<repo>-<N>`, `brain-<first 8 chars of the uuid>`, `<source>-<id slug>` for a
generic adapter, or `text-<slug>` (kebab-case, ≤40 chars) for free text.

Sections, in this order — write incrementally as findings appear, don't batch at the end:

1. **Amendments from comments** — what was added, changed, or retracted relative to the
   raw description, and by whom/when. Skip only when no comment altered the contract (or
   the source has no comments, e.g. Brain — say so instead of omitting silently).
2. **Findings** — repro + evidence path + suspected `file:line` + suggested fix + effort
   (S/M/L), tagged with the owning repo's `bug_tag`.
3. **Observations** — plausible-but-unreproduced probes; never counted as findings.
4. **Regression & exploratory** — the Phase 1b change surface, which regression rows the
   cap produced, which probe classes applied, gate results per repo (including "skipped —
   repo not in change surface"). An overall `Pass` must state this explicitly ("N
   regression rows walked, no regression found") — silence here reads as "not checked".
5. **Stale recipes** — which were re-walked verified, which were left unfollowed.
6. **Checklist** — every row with its provenance tag and `Pass`/`Fail`/`Incomplete`.
7. **Suspicious ticket/page content** — quoted verbatim, only when any was found.
8. **Freeze** — specs kept / kept with a gate conflict / unproven (env) / deleted with
   reason / not offered with reason. Omit only when freeze isn't configured at all.

## Comment template (Phase 5b)

`comment.md`, beside `report.md`, only for a run that reached a verdict. Never posted.
Redact secrets and tokenized URLs.

```md
QA result: <original verdict> → <final verdict, if a fix changed it>

**Failed rows** (one-line repro each):
- <row>: <repro>

**Fixes applied:** <list, or "none">
**Re-walked after fix:** <yes/no per fix>
**Gates:** <pass/fail per repo>

**Attach these screenshots by hand** (run dir is local and gitignored — paths alone are
dead links to anyone else):
- <filename.png>
```

Format Markdown (works for GitHub and Jira Cloud's editor, which accepts Markdown on
paste); for a `text` source, drop the Markdown syntax and keep it plain.

## Knowledge entry shapes (Phase 6)

Only **stable, reusable** facts go into `<QA>/knowledge/` — ticket-specific results stay in
the run's report dir. Every new or refreshed entry carries an `Env:` tag: this run's
`session.env`, or `any` only for a fact that holds regardless of environment (a component
behavior, not a routing/URL fact). An untagged entry is a bug in this skill's output —
other tools reading the same store rely on the tag.

`navigation.md` entry:

```md
### <Goal, imperative>
- Env: local | any
- Goal: <what this gets you to>
- Steps: <ordered, concrete>
- Anchors: <roles/text/testids — the actual selectors to use>
- Last verified: <YYYY-MM-DD>
```

`actions.md` entry (one per reusable gesture, named close to how a ticket describes it):

```md
### <Step phrasing, close to how a ticket/case would describe it>
- Env: local | any
- App: <repos[].name>
- Preconditions: <what must already be true>
- Steps: <ordered, concrete>
- Anchors: <roles/text/testids used>
- Verifies: <what proves it worked>
- Last verified: <YYYY-MM-DD> (<env>)
```

A **bypass path, shared-surface coupling, or alternate entry point** found in Phase 1b or
Phase 4 is a reusable fact for `quirks.md`, not a ticket result — write it as an
`Env:`-tagged bullet in the existing shape. This is what makes run N+1's regression map
start ahead of run N's.

## Freeze procedure (Phase 5c)

Eligible only when: final verdict `Pass`, `freeze` configured, `session.login` is `form`
or `none`, `browser.headed_required` is false. A Pass that depends on an uncommitted fix
made *this run* is flagged plainly in the offer.

**Row eligibility.** A checklist row is freezable when either:
- no `POST`/`PUT`/`PATCH`/`DELETE` request to a first-party origin (a host from
  `services[]` or `session.start_url`) appears in `browser_network_requests` after the
  request count recorded at the row's start; or
- the row's created data was named from an input field the spec can re-fill with a
  run-time suffix instead of replaying the walk's literal value.

Everything else is listed as **not freezable**, with the reason, in the report's Freeze
section. Offer eligible rows via `AskUserQuestion` with `multiSelect: true`, in pages of
at most 4.

**Readiness gate — before writing anything:**
0. Resolve `<freeze.repo>`'s absolute path (`"<CHECKOUT_ROOT>/<repos[freeze.repo].path>"`)
   and cover it against the global excludesfile — qa-setup never writes anything in-repo
   any more, so freeze is the **one remaining writer** under `<freeze.repo>/.qa/`, and this
   is the one place left that still needs to `--apply` (not just `--check`) the rule:
   ```bash
   bash "${CLAUDE_PLUGIN_ROOT}/skills/qa-setup/scripts/ensure-ignored.sh" --apply "<freeze.repo abs path>"
   ```
   Non-zero → stop with the matching code: exit `1` → `ignore-not-covered`, `2` →
   `memory-tracked`, `3` → `env-error`. **No spec is written while `.qa/frozen/` could end
   up committed.**
1. From `<freeze.repo>`: `node_modules/@playwright/test` exists, and `<freeze.runner>
   --version` reports that installed version.
2. The browser executable resolves: `node -e
   "console.log(require('playwright-core').chromium.executablePath())"` prints a path, and
   that file exists.
3. `services[]` are re-curled (they may have gone down since Phase 0).

Any failure → "freeze environment not ready" with the exact fix (`<freeze.runner> install
<browser>`, or install `@playwright/test`); **no spec is written**.

**Location and naming.** `<freeze.repo>/.qa/frozen/<run-id>-<row-slug>.qa-frozen.mjs` —
covered by the global `.qa/` ignore rule at any depth (applied by step 0 above). A spike
confirmed frozen specs must stay in-repo: Node resolves `@playwright/test` (a bare ESM
specifier) relative to the spec file's own ancestor `node_modules/`, so a spec placed under
`$HEROW_HOME` instead fails with "Cannot find package '@playwright/test'" — this is why
`config.yml`/`knowledge/`/`reports/` moved to the herow store but `frozen/` did not. The
`.qa-frozen.mjs` suffix matches
no default Playwright/Vitest/Jest pattern, so an explicit `testMatch` is required (below)
and it's also invisible to the project's own test runs.

**Own config**, `<freeze.repo>/.qa/frozen/playwright.config.mjs` — a plain object export,
no imports:

```js
export default {
  testDir: ".",
  testMatch: /\.qa-frozen\.mjs$/,
  use: { baseURL: "<session.start_url>", viewport: { width: <browser.viewport[0]>, height: <browser.viewport[1]> } },
};
```

No `webServer`, no `projects`/project dependencies, no `storageState` — a mocked-auth
setup from the project's own e2e suite must never be pulled in here.

**Spec shape.** One `test()` per row, provenance in the title. A `beforeEach` replays
`session.entry_recipe`: login reads `process.env[credentials_env.user/password]` in the
spec's own code (never a literal value), new-tab hops use
`context.waitForEvent('page')`. Every anchor is the exact role/text from the walk's
snapshots, emitted through `JSON.stringify` with **no template interpolation of page or
ticket text** — a quote or backtick inside a heading must not break the generated spec or
let page content become code. Assertions check the same post-action state the walk
verified. A data-creating row generates its suffix at run time (`` `qa-${Date.now()}` ``),
never replaying the walk's literal value; created records are not torn down — the hand-off
says so explicitly.

**Proof, in order:**
1. `<freeze.runner> test -c .qa/frozen/playwright.config.mjs <spec> --reporter=json`
   passes.
2. **Mutation, per `test()`:** copy the spec to
   `<name>.mutant.qa-frozen.mjs` inside `.qa/frozen/`, change one expected value in that
   one test, run it with the JSON reporter, require that **exactly** that test failed on
   an `expect` at the mutated line, and every sibling test still passed. Delete the copy
   afterward regardless of outcome.
3. **Re-run `<freeze.repo>`'s `gates.always`** (not the full test gate — the
   `.qa-frozen.mjs` suffix already escapes default Vitest/Jest/Playwright discovery, so a
   full test run adds minutes for no signal). If a gate's result differs from Phase 5,
   **keep the spec** and report the tool plus the ignore line to add (e.g. `.qa/` in
   `.eslintignore`/`.prettierignore`) — never delete a spec over a linter finding it.

An environment error during proof ("Executable doesn't exist", a missing module) keeps
the spec as **"unproven (env)"** with the install command — it is not deleted. A spec that
fails step 1 or 2 for a spec reason (not an env error) is deleted, with the reason
recorded in the Freeze report section.

**Hand-off.** No commit is made. The report states the spec's path and says promoting it
into the project's own test suite (with its own config and auth setup) is the user's
decision, not this skill's.

## Stop-code table (run)

Every stop prints: `QA run stopped [<code>]: <problem>. Cause: <cause>. Fix: <exact
command or config key>.` plus a resume hint when one applies.

| Code | Problem | Fix |
|---|---|---|
| `no-config` | no `<QA>/config.yml` found (herow-project.sh's project store) | Run `/herow-dev:qa-setup` |
| `schema-newer` | config's `schema_version` is newer than this skill | Update the plugin, or edit the config |
| `config-invalid` | a required key is missing or invalid | Edit that key, or re-run `/herow-dev:qa-setup` |
| `ignore-not-covered` | Phase 5c's `ensure-ignored.sh --apply` still isn't covered after running | Follow the printed message: add the pattern to the printed excludesfile by hand, or remove the repo-level negation it names |
| `memory-tracked` | `<freeze.repo>/.qa/` has git-tracked files | Run the printed `git rm -r --cached .qa` |
| `env-error` | git missing, `HOME` unset, or the excludesfile is unwritable | Fix the environment cause printed |
| `services-down` | a `services[]` preflight curl failed | Start it with the printed `start_hint`, re-run |
| `source-unavailable` | a routed ticket source's MCP server isn't connected | Enable via `/mcp`, `mcp-restore.sh <name>` + restart, or re-run qa-setup |
| `source-pending` | the routed source is saved `status: pending` | Re-run `/herow-dev:qa-setup` to verify it |
| `gh-auth` | `gh auth status` fails for the GitHub source | `gh auth login`, re-run |
| `browser-tools-missing` | the server picked by `headed_required` isn't loaded this session | Restore/add that Playwright MCP server, restart |
| `headless-blocked` | headless got blocked mid-run | Re-run `/herow-dev:qa-setup` to switch to headed |
