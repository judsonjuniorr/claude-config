# qa-setup reference

Read alongside `SKILL.md`; each section below is referenced from a specific step there.

## `config.yml` template (schema_version 1)

```yaml
schema_version: 1
project: app                                   # project name, confirmed at step 3
envs: [local, staging, production, any]        # Env: tag vocabulary for knowledge entries
services:                                      # preflight only; qa-run never starts them
  - name: web
    url: http://localhost:3000/
    expect_status: [200]
    start_hint: "bun dev"                      # exact command to start it, printed on preflight failure
browser:
  headed_required: false     # written only by qa-setup: true when the smoke walk proved
                              # headless is blocked, or login is sso/magic-link
  viewport: [1440, 900]
session:
  env: local                 # one of envs[]; the Env: tag the smoke walk and Phase 6 write
  start_url: http://localhost:3000/
  login: form                 # form | sso | magic-link | none — see "Login types" below
  login_detect: "a form with a password field"   # model-evaluated against the snapshot
  credentials_env: { user: QA_USER, password: QA_PASSWORD }   # names only; login: form only
  auto_fill: true             # form only. true = automated fill (value reaches the transcript,
                               # see "Login types"); false = manual headed login
  entry_target: "Dashboard (heading 'Dashboard')"        # module + visible landmark
  entry_recipe: "Log in and reach Dashboard"             # navigation.md entry heading; set by the smoke walk
setup:
  smoke: pending              # pending | verified
  smoke_date: null
ticket:                       # per-project ticket sources — only what this project uses
  default: jira                # name of the source used for no-argument runs and bare ids
  sources:
    - name: jira
      kind: mcp                # mcp | cli | text
      server: atlassian        # MCP server name -> tools mcp__atlassian__*
      preset: jira              # built-in adapter: fetch getJiraIssue (description + comments)
      status: verified          # verified | pending (unverified sources are refused by qa-run)
      id_pattern: "[A-Z]+-\\d+"  # routes an argument to this source; also used for branch inference
      params: { site: example.atlassian.net, cloud_id: "00000000-0000-0000-0000-000000000000", project: PROJ }
    - name: brain
      kind: mcp
      server: brain
      preset: brain              # fetch get_task(id); list list_tasks(project_id, status)
      status: verified
      id_pattern: "[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"
      params: { project_id: "00000000-0000-0000-0000-000000000000", pick_statuses: [doing, validation] }
    - name: github
      kind: cli
      command: gh                # preset github: gh issue view, falling back to gh pr view
      status: verified
      id_pattern: "#\\d+|https://github.com/.+/(issues|pull)/\\d+"
      params: { repo: owner/name }
    - name: text
      kind: text                 # always available; free-text ACs, no comment reconciliation
    # any other connected MCP server (generic adapter, confirmed at setup with one sample fetch):
    # - name: linear
    #   kind: mcp
    #   server: linear
    #   status: verified
    #   fetch: { tool: get_issue, id_param: id }
    #   list: { tool: list_issues, args: { team: ENG } }
    #   fields: { title: title, body: description, comments: comments }
    #   id_pattern: "[A-Z]+-\\d+"
repos:                          # change surface, finding tags, per-repo gates
  - name: app
    path: .                     # relative to `herow-project.sh checkout-root`: the workspace
                                 # root for a multi-repo workspace, else the checkout you're
                                 # in (so a worktree run diffs the worktree)
    bug_tag: app-bug
    remote: owner/name          # recorded from `git remote get-url origin`
    base: null                  # optional: overrides change-surface.sh's own base resolution
    gates:
      always: ["bun run type-check", "bun run lint"]
      when_tests_touched: ["bun run test"]
freeze:                          # omitted unless a repo has node_modules/@playwright/test,
  repo: app                      # or the user opts out at confirm time
  runner: "bunx playwright"      # package-manager exec + playwright; specs live in <repo>/.qa/frozen/
gotchas: []                      # e.g. "e2e/ runs on mocks — never reuse its selectors or auth"
```

## Detection catalogue (prose, model-driven)

No `detect.sh` in this version — read these files directly, from `<CHECKOUT_ROOT>` and
every child repo in a workspace:

- `package.json` — `scripts.dev`/`scripts.start` (look for `--port`/`PORT=`), and
  `type-check`/`typecheck`/`lint`/`test` scripts.
- The lockfile — which package manager runs those scripts (`bun`, `pnpm`, `npm`, `yarn`).
- `docker-compose*.yml` — published ports.
- `pyproject.toml` / `manage.py` — Python dev server, `ruff`/`mypy`/`pytest`.
- `Makefile` targets that start a server or run checks.
- `node_modules/@playwright/test` (existence, not just a `playwright.config.*`) — freeze
  eligibility, one repo at most is proposed as `freeze.repo`.
- `git remote get-url origin` per repo.
- Candidate knowledge stores: `.claude/knowledge/*/navigation.md`,
  `.claude/skills/*/knowledge/navigation.md` (resolve symlinks; `<QA>/knowledge` itself is
  never a candidate).
- This session's own tool list, for `mcp__atlassian__*`, `mcp__brain__*`, any other
  `mcp__<server>__*`, and `mcp__playwright*__*` — read-only, no probing.

**The only live signal is a `curl --max-time 3` against a port a file above actually
named.** Never propose a service from a listening socket alone — that could belong to an
unrelated project running on the same machine.

## Login types and credentials

The Playwright MCP run-code sandbox has no `process` (confirmed by probe), a generated
login file run by filename echoes its own code back into the result, and a snapshot taken
after filling a password field prints the value in plain text. So every automated fill
puts the credential in the transcript — there is no path that avoids this entirely. Per
project, `session.auto_fill` makes that trade-off explicit and opt-in:

- **`login: form`, `auto_fill: true`.** Env vars must already be exported **before**
  Claude Code starts (shell profile, direnv, or `settings.json`'s `env` block — exporting
  from inside a Bash tool call reaches neither Claude Code nor the MCP server). Read them
  with Bash, then fill **and submit in one call** to whichever run-code tool this
  session's Playwright MCP exposes (`browser_run_code` or `browser_run_code_unsafe` — read
  the schema, the name has changed across versions). **Take no snapshot until the page has
  navigated away from the login form.** State once, in the setup report, that the value
  reached the tool-call transcript. Every report and knowledge entry writes `[REDACTED]`
  in place of the value.
- **`login: form`, `auto_fill: false`.** No automated fill at all: `headed_required` is
  set `true`; the user logs in once by hand in the headed browser; the persistent
  `--user-data-dir` profile keeps the session across runs. On expiry, stop with "log in
  again in the headed browser, then re-run."
- **`login: sso`** or **`login: magic-link`.** Same manual flow as `auto_fill: false` —
  these never fill a form (`headed_required: true`).
- **`login: none`.** No login step at all.

Headless and headed profiles never share a session — a manual login always happens in the
headed profile, once, and then persists.

**Headed fallback prerequisites** (document these; they're specific to this machine's
setup, not shipped by the plugin): `~/.claude/mcp-restore.sh` and a `playwright` entry in
its stash, and two MCP server names, `playwright-headless` and `playwright`. When the
script or that stash entry is missing, print the generic instruction instead: "add a
headed Playwright MCP server named `playwright` and restart Claude Code."

## Knowledge seeds

A **fresh** store (no adoption) gets all four files, headers only plus the seeds below.
An **adopted** store is seeded only with the files it's missing — never touched otherwise.

`navigation.md` / `actions.md` / `probes.md` — headers plus the `Env:` tag legend (`local`
= this workspace's dev stack, `staging`/`production` = that deployed environment, `any` =
holds regardless of environment). `probes.md` also gets the seven generic probe classes
below (see qa-run's Phase 1b in `qa-run/reference.md` for how they're used):

```
1. Cancel/abort is client-only and leaves server-side state open.
2. An alternate entry point bypasses a newly added gate.
3. A branch has several exits and only one was updated.
4. An error branch swallows a real failure.
5. Client state lies — reload and read the value back from the server, not the store.
6. Reopen/remount after cancel leaves stale reducer/component state.
7. Double-submit or rapid re-click of the primary action.
```

`quirks.md` in a **fresh** store additionally gets these version-stable, `Env: any`,
`(seed)`-marked Playwright-MCP tool quirks (no `Last verified` date — they're not
app-specific facts, they're reminders about the tool):

```
### Playwright MCP tool quirks (seed)
- Env: any
- A click that opens a new tab needs the tabs tool: list tabs, then select the new one —
  don't assume the current page navigated.
- Anchor on roles, labels, or visible text from the snapshot — never CSS selectors.
- Pass the element-reference parameter under whatever name the tool's schema uses for it
  — it has changed across @playwright/mcp versions. Read the schema, not memory.
- To read console messages at warning level, use whatever parameter name the schema
  gives for the level filter, and confirm once per app that a real warning is actually
  captured — some dev servers wrap `console` and swallow it.
- Never snapshot a filled login form — a password textbox's value is printed in plain
  text in the snapshot result.
```

## Probe catalogue (for `services[]` detection)

A candidate service is confirmed with exactly one HTTP probe against the port a file
already named:

```bash
curl -s -o /dev/null -w "%{http_code}" --max-time 3 <url>
```

Record the status code actually returned as `expect_status`; don't assume `200` — a dev
server that redirects (`302`) or requires auth (`401`/`403`) unauthenticated is still
"up" for preflight purposes.

## Stop-code table (setup)

Every stop prints: `QA setup stopped [<code>]: <problem>. Cause: <cause>. Fix: <exact
command or config key>.` plus a resume hint when one applies.

| Code | Problem | Fix |
|---|---|---|
| `schema-newer` | `config.yml`'s `schema_version` is newer than this skill | Update the plugin, or edit the config by hand |
| `store-error` | `herow-project.sh` itself failed (git missing, `HOME` unset, the store path unwritable) | Print its stderr diagnostic verbatim; fix the named cause |
| `env-var-missing` | a `credentials_env` var isn't set | Export it (shell profile or `.envrc`), restart Claude Code, re-run — resumes at the smoke walk |
| `browser-tools-missing` | the chosen Playwright MCP server's tools aren't in this session | Restore/add that server (see "Headed fallback prerequisites"), restart |
| `headless-blocked` | 2FA/CAPTCHA/SSO consent blocked headless mid-walk | Restart headed (see above), re-run — resumes at the smoke walk |
| `services-down` | a `services[]` preflight curl failed | Start the service with its printed `start_hint`, re-run |
| `smoke-failed` | credentials rejected, or the entry-target landmark was never found | Edit the offending config key and retry, or stop and resume later |
| `store-move-refused` | a post-move file count/byte mismatch (cross-filesystem moves are allowed and expected — `<QA>` is usually a different filesystem from the repo — this is only the verification failing) | Nothing lost — the store was renamed back; pick seed fresh instead |
| `source-unavailable` | a selected ticket source's MCP server isn't connected this session | Enable via `/mcp`, `mcp-restore.sh <name>` + restart, or re-run qa-setup |
| `gh-auth` | `gh auth status` fails for the GitHub ticket source | `gh auth login`, then re-run |

`ignore-not-covered`, `memory-tracked`, and `env-error` (the `ensure-ignored.sh` codes) no
longer belong to this skill — qa-setup never writes anything in-repo any more. They now
surface only from `qa-run`'s freeze procedure (Phase 5c), the one remaining in-repo
writer (`<freeze.repo>/.qa/frozen/`) — see `qa-run/reference.md`'s stop-code table.

Dogfooding should trigger each reachable code at least once.
