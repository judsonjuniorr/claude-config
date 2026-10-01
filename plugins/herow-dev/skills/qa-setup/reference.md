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
  # executable_path: "/abs/path/to/chromium"   # optional; unset, qa-login.mjs tries playwright-headless's
                                                # --executable-path, then the chrome channel, then the bundled build
session:
  env: local                 # one of envs[]; the Env: tag the smoke walk and Phase 6 write
  start_url: http://localhost:3000/
  login: form                 # form | sso | magic-link | none — see "Login types" below
  login_detect: "a form with a password field"   # model-evaluated against the snapshot
  auto_fill: true             # form only. true = scripted login by qa-login.mjs, outside the
                               # MCP browser (value never in the transcript); false = manual headed
  password_file: login.json   # form only; a bare *.json name directly in <QA>. JSON {user,password},
                               # mode 600, written by `qa-login.mjs save` — never the value
  # login_origins: ["https://idp.example.com"]   # extra origins the credential may be typed into
                               # (an IdP); default is start_url's origin only. http only for local hosts
  credentials_env: { user: QA_USER, password: QA_PASSWORD }   # fallback env-var names, used when
                               # the password file doesn't exist; must be exported before launch
  # login_fields:             # optional Playwright selectors when the heuristic can't find the form;
                               # always quote them (an unquoted [..] would parse as a list)
  #   user: "input[name=email]"
  #   password: "input[name=password]"
  #   submit: "role=button[name=\"Sign in\"]"
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

**Never fill a credential through an MCP browser tool.** A run-code tool echoes its
input, `browser_type` and `browser_fill_form` put the value in the tool input, and a
snapshot of a filled password field prints it in plain text. Instead, the login happens in
a separate headless browser driven by `qa-run/scripts/qa-login.mjs`. Only the resulting
session cookies cross over, as a storageState **file path**.

- **`login: form`, `auto_fill: true`** (scripted login):
  1. **Bash:** `node "${CLAUDE_PLUGIN_ROOT}/skills/qa-run/scripts/qa-login.mjs" login "<QA>"`,
     with `<QA>` as a literal absolute path.
     - The script reads `config.yml` itself. The credential comes from
       `session.password_file`, or else the `credentials_env` vars.
     - It fills the form (`login_fields`, or a heuristic: the visible password field plus
       the email/text input in the same form; two-step forms work too) and submits.
     - It types the credential only into `start_url`'s origin or a `session.login_origins`
       entry, and uses plain `http` only for local hosts (`localhost`, loopback,
       `*.localhost`/`.test`/`.local`).
     - It verifies that the password field is gone, then writes
       `<HEROW_HOME>/browser/state/<project-id>.json` (mode 600).
     - stdout is exactly `ok <state path>` or `error <code>[ <key>]`. Nothing else is
       printed, ever.
  2. **`browser_set_storage_state({filename: "<state path>"})`**, passing exactly the path
     the script printed.
  3. **Bash:** `node "${CLAUDE_PLUGIN_ROOT}/skills/qa-run/scripts/qa-login.mjs" clear "<QA>"`.
     This deletes the state file, which is a bearer credential. **Always run it once step 1
     printed `ok`**, even if step 2 failed or the walk is about to stop. `login` also deletes
     any stale state file before it starts.
  4. **`browser_navigate(session.start_url)`**, then take a snapshot. If it still matches
     `login_detect`, stop `[session-not-transferred]`. This means the app keeps its session
     in sessionStorage, or binds it to the browser fingerprint. Fix: set `auto_fill: false`
     (manual headed login).
- **`login: form`, `auto_fill: false`.** No automated fill at all: `headed_required` is
  set `true`; the user logs in once by hand in the headed browser; the persistent
  `--user-data-dir` profile keeps the session across runs. On expiry, stop with "log in
  again in the headed browser, then re-run."
- **`login: sso`** or **`login: magic-link`.** Same manual flow as `auto_fill: false` —
  these never fill a form (`headed_required: true`).
- **`login: none`.** No login step at all.

Headless and headed profiles never share a session — a manual login always happens in the
headed profile, once, and then persists.

**Password file.**
- **Location and format:** `<QA>/login.json`, or `session.password_file` (a bare `*.json`
  file name directly in `<QA>`), holding JSON `{"user": "...", "password": "..."}`.
  - `check`, `login` and `save` refuse any other location, and a symlink
    (`unsafe-path`).
  - That keeps it out of `knowledge/`, `reports/` and `config.yml`, which are read into
    the model's context.
- **Permissions:** mode 600, in a 700 directory. `login`/`check` refuse a file with any
  group or other bit set (`file-mode`).
- **Placement:** it lives under the herow store, outside every git repo, and its name
  matches none of the `settings.json` Read deny globs (`*secret*`, `*credentials*`, `.env`,
  `.env.*`). `save` refuses either case (`unsafe-path`). It is also outside the MCP
  `--output-dir`. No `browser_*` tool can load or upload it unless `<HEROW_HOME>` is
  also an MCP workspace root. Don't add `~/.herow` as a Claude Code working directory in a
  QA session.
- **Why JSON:** a misdirected `setStorageState` parses it without quoting the content
  back in an error.
- **Who writes it:** only the user, via
  `! node "<plugin>/skills/qa-run/scripts/qa-login.mjs" save "<QA>"`.
  - It prompts with muted input on a TTY.
  - With no TTY (the `!` prefix) on macOS it opens a native hidden-answer dialog.
  - Elsewhere it prints `error no-tty` — run it from a terminal instead.

**MCP server prerequisites (scripted login).** `playwright-headless` must run with
`--caps=storage` (adds `browser_set_storage_state`) and `--output-dir <HEROW_HOME>/browser`
(the server only reads files inside its output dir or workspace, so the state file must
live there). `--isolated --storage-state` is not used: it is fixed at server start, one
path for every project. Reconfigure once, with every path resolved, then restart Claude
Code:

```
cfg=$(jq -ce --arg h "<HEROW_HOME>" '.mcpServers["playwright-headless"] | select(. != null) | .args as $a | ([$a[] | select(startswith("--caps=")) | ltrimstr("--caps=") | split(",")[]] + ["storage"] | unique | join(",")) as $caps | .args = [range($a|length) as $i | select(($a[$i] | startswith("--caps=") | not) and $a[$i] != "--output-dir" and ($i == 0 or $a[$i-1] != "--output-dir")) | $a[$i]] + ["--caps=" + $caps, "--output-dir", ($h + "/browser")]' ~/.claude.json) && claude mcp remove playwright-headless -s user && claude mcp add-json playwright-headless "$cfg" -s user
```

It's idempotent: it merges any existing `--caps=` and replaces any `--output-dir`. If `jq`
finds no user-scope server, the chain stops before removing anything. If there
is no `playwright-headless` server at all, add one with `@playwright/mcp@latest --headless
--caps=storage --output-dir <HEROW_HOME>/browser`. Once the server is reconfigured, the
following apply.

- **Side effect: every restore clears the profile.** `browser_set_storage_state` clears
  **every** cookie and the cache of the headless profile before it restores. That logs
  out any other site that profile was signed into, for other skills as well. They log in
  again on their next use.
- **Forbidden tools.** `--caps=storage` also exposes tools that print cookie and storage
  values. **Never** call `browser_storage_state`, `browser_cookie_*`,
  `browser_localstorage_*`, or `browser_sessionstorage_*`.
- **The only allowed state path.** Call `browser_set_storage_state` only with the path
  `qa-login.mjs` printed. Never pass the password file to any browser tool. That includes
  `browser_run_code_unsafe`, which skips the server's file-root check.

**Residual risks**
- The password file and the state file can be read by the model's own Read tool. Only the
  rules above guard them. Optional hardening is out of scope here: user-level
  `Read`/`Bash(cat …)` deny rules for `~/.herow/projects/*/qa/login.json` and
  `~/.herow/browser/state/**`.
- The env-var fallback reaches the script only if it was exported before Claude Code
  started. Every Bash call then inherits it too, so **never** `echo`/`printenv`/`env` the
  `credentials_env` names. Prefer the password file.

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
- Never call the cookie/localStorage/sessionStorage tools or `browser_storage_state` —
  they print session values. `browser_set_storage_state` takes only the path
  `qa-login.mjs login` printed.
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
| `login-file-missing` | `qa-login.mjs check` → `login-missing`: no password file and no `credentials_env` value | Run the printed `! node … qa-login.mjs save "<QA>"`, re-run — resumes at the smoke walk (or export the env vars before launching Claude Code) |
| `login-file-mode` | `check`/`login` → `file-mode` | `chmod 600 "<QA>/login.json"` |
| `login-file-invalid` | `check`/`login` → `file-invalid` (not JSON, or `user`/`password` empty) | Re-run the `save` command |
| `browser-caps-missing` | scripted login, but `browser_set_storage_state` isn't in this session | Run the reconfig command under "MCP server prerequisites", restart |
| `login-engine-missing` | `login` → `engine-missing` (no `playwright-core` resolvable) | Run any Playwright MCP tool once (populates the npx cache), or `npm install --prefix "<HEROW_HOME>/tools/playwright" playwright-core` |
| `login-failed` | `login` → `browser-missing`, `unreachable`, `no-form`, `field-missing <key>`, `rejected`, `origin-mismatch`, `insecure-origin`, `unsafe-path`, `state-write`, `config-unreadable <key>`, or `internal` | `browser-missing`: set `browser.executable_path` (the script already tried the MCP's `--executable-path` and the `chrome` channel). `no-form`/`field-missing`: set `session.login_fields`. `rejected`: re-run `save` with the right credentials. `origin-mismatch`: the form lives on another origin; add it to `session.login_origins` only if it's the app's own IdP. `insecure-origin`: use https. `unsafe-path`: `password_file` must be a bare `*.json` name in `<QA>`, not a symlink. Otherwise fix the named key or service |
| `session-not-transferred` | the login succeeded, but `login_detect` still matches after the restore | Set `auto_fill: false` and log in by hand, headed |
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
