---
name: qa-setup
description: >-
  (herow) Set up config-driven live-app QA for this repo — resolves the project root,
  detects services/repos/gates from the codebase, writes config.yml under the herow
  project store, seeds or adopts a knowledge store, and proves the config with a live
  Playwright smoke walk. Run once per project (safely re-runnable).
  Use on "set up QA for this repo", "/herow-dev:qa-setup", or as the fix pointed to by a
  qa-run "[no-config]" stop.
---

# qa-setup

Writes `<QA>/config.yml`, seeds or adopts `<QA>/knowledge/`, and proves the whole config
with a live smoke walk (login + first navigation). `<QA>` is an absolute path under
`$HEROW_HOME/projects/<id>/qa/` (`HEROW_HOME` defaults to `~/.herow`), resolved once via
`herow-project.sh` — see step 1. This is the one-time (re-runnable) setup that
`/herow-dev:qa-run` then reads every project constant from — see
`plugins/herow-dev/skills/qa-run/SKILL.md`.

Read `reference.md` **in this skill's directory** for: the commented `config.yml`
template, knowledge seed contents (including the fresh-store tool-quirk seeds), the
probe/detection catalogue, and the stop-code table. Load it now — most steps below point
back into it.

## Constraints (always true)

- Memory lives under the herow project store, resolved once via `${CLAUDE_PLUGIN_ROOT}/scripts/herow-project.sh qa --ensure` (prints `<QA>`) — **never** under `.claude/` (write-prevention hooks trigger there, and in at least one real project content under `.claude/` leaks to an external log aggregator) and never loose in the repo. Shell vars don't persist between Bash calls: use the **printed literal absolute path** in every later command/Write, never a bare `<QA>` carried over from an earlier call. The one exception is a frozen spec (Phase 5c of `qa-run`) — Node's own module resolution requires it to live in-repo, at `<freeze.repo>/.qa/frozen/`, gitignored there; qa-setup never writes anything there itself.
- Credentials are **never** written into `config.yml`, and **never** pass through this
  session. They live in `<QA>/login.json` (mode 600). The user writes that file with a
  command they run themselves (step 3), and only `qa-login.mjs` reads it. **Never** Read,
  cat, grep or `browser_*` that file, or the state file under `<HEROW_HOME>/browser/state/`,
  and never ask for the value in chat. Env-var names under `credentials_env` remain a
  fallback, and their values are never `echo`ed or `printenv`ed. Reports and knowledge always print
  `[REDACTED]` in place of a credential.
- Prefer the headless Playwright MCP server (`mcp__playwright-headless__*`); use the
  headed one (`mcp__playwright__*`) only when headless is blocked — that is a per-project
  fact (`browser.headed_required`) proved by the smoke walk, not a preference you guess.
- Drive the browser **in this session**, never through a subagent — a subagent starts
  cold and loses the open tabs and snapshots this walk builds up.
- **`qa-setup` is the only writer of `config.yml`.** `qa-run` never edits it.
- All generated content (config comments, reports, knowledge seeds) is in English.

## 1. Resolve the store and existing state

**Convention used throughout this skill:** shell variables never survive between separate
Bash tool calls, and this skill spans many (every `AskUserQuestion` is a turn boundary).
Whenever a later step's command needs the store or checkout root, **re-run the exact
resolution command below in that same call** rather than trust an earlier call's `<QA>` or
`<CHECKOUT_ROOT>` to still be set — both commands are cheap and idempotent. `<QA>` and
`<CHECKOUT_ROOT>` in prose (angle brackets) mean "the absolute value you resolved," never a
literal shell variable name.

Resolve `<QA>` once — this also runs the one-shot legacy migration (moves an existing
`<checkout-root>/.qa/{config.yml,knowledge,reports}` and `.claude/plans/*` in this repo
into the store; a git-tracked `.qa` or `.claude/plans` is left in place with a warning
printed to stderr — surface that warning to the user if it appears):

```bash
QA="$(bash "${CLAUDE_PLUGIN_ROOT}/scripts/herow-project.sh" qa --ensure)"
echo "QA=$QA"
```

Separately, resolve `<CHECKOUT_ROOT>` for this run — used only to make `repos[].path`
relative, **never** to decide where `<QA>` lives (that's `herow-project.sh`'s job, and it
deliberately maps every worktree of a repo to the same store):

```bash
CHECKOUT_ROOT="$(bash "${CLAUDE_PLUGIN_ROOT}/scripts/herow-project.sh" checkout-root)"
echo "CHECKOUT_ROOT=$CHECKOUT_ROOT"
```

`repos[].path` in the config is always relative to `<CHECKOUT_ROOT>`.

If `<CHECKOUT_ROOT>` doesn't hold a git repo and holds one or more child git repos (a
multi-repo workspace, no git repo at the workspace root itself), confirm with the user
that `<CHECKOUT_ROOT>` (the cwd) is the intended root before continuing — `herow-project.sh`
already handles the store side of this (an already-set-up ancestor workspace's `qa` store
is reused automatically), but the config's own `repos[].path` values still need the human
to confirm what "root" means here.

**If `<QA>/config.yml` already exists:**
- `schema_version` newer than this skill understands → stop `[schema-newer]` (see the
  stop-code table in `reference.md`).
- Never overwrite silently. Offer, via `AskUserQuestion`:
  - `setup.smoke: pending` → recommend **"resume the smoke walk"** (skip straight to
    step 6);
  - otherwise offer **re-detect** (a merge — see below) or **edit specific keys**.
- **Re-detect is a merge, not a rewrite.** Detected keys (services, repos, gates,
  detected ticket sources) are shown as a diff against the current config and applied
  only on confirmation. Hand-set and smoke-derived keys are **always kept** regardless of
  re-detect: `gotchas`, `browser.headed_required`, `browser.executable_path`,
  `session.entry_recipe`, `session.password_file`, `session.login_fields`, `setup.*`, and
  any `ticket.sources[]` entry already `verified` with its resolved params. Reset
  `setup.smoke` to `pending` only when a `session.*` or `services[]` key actually
  changes — an unrelated key changing (e.g. a repo's gates) does not invalidate a proven
  login/navigation recipe.
- **Credential migration** (`login: form`, `auto_fill: true`, and no `session.password_file`
  — a config written before scripted login). Run the step-3 `check`:
  - `ok env` → the env vars still work as-is. Offer to move to a password file; don't
    force it.
  - `error login-missing` → go to the step-3 capture flow.
  - **Any** `warn literal-in <files>` (env or file) → tell the user that those files hold
    the credential in plain text. Ask them to replace it with `[REDACTED]` by hand, and
    recommend rotating it, because past transcripts may hold it too. If a config comment
    points at those files for credentials, rewrite that comment. This skill never edits
    the credential text itself.

## 2. Detect

No deterministic `detect.sh` in this version — read the project's own files, from
`<CHECKOUT_ROOT>` and every child repo in a workspace (all curl probes below are the
*only* live signals; never trust a listening socket that no file names, so an unrelated
project's dev server is never proposed):

- **Services.** `package.json` scripts (`dev`/`start`, `--port`/`PORT=` hints),
  `docker-compose*.yml` published ports, `Makefile` targets that start something,
  `pyproject.toml`/`manage.py` (Django/FastAPI dev servers). For each candidate,
  `curl -s -o /dev/null -w '%{http_code}' --max-time 3 <url>` and record the status
  actually seen as `expect_status`.
- **Package manager / gates.** The lockfile in each repo (`bun.lock(b)`, `pnpm-lock.yaml`,
  `package-lock.json`, `yarn.lock`) or `pyproject.toml` (ruff/mypy/pytest). Map
  `type-check`/`typecheck`, `lint`, `test` scripts (or their Python equivalents) to
  `repos[].gates.always` / `.when_tests_touched`, per repo.
- **Freeze eligibility.** Per repo, `node_modules/@playwright/test` present (a
  `playwright.config.*` file alone is not enough — the package must actually be
  installed). If found in exactly one repo, propose it as `freeze.repo`.
- **Git remotes.** `git -C <repo> remote get-url origin` per repo, for the GitHub ticket
  source and the setup report.
- **Knowledge stores.** `.claude/knowledge/*/navigation.md` and
  `.claude/skills/*/knowledge/navigation.md` (resolve symlinks), excluding `<QA>/knowledge`
  itself.
- **Session tools.** Check this session's tool list for `mcp__playwright*__*` and any
  ticket-related MCP server names (see step 3b) — this only reads what's already loaded,
  no probing.

## 3. Confirm — one summary, then targeted gaps

Show **one** `AskUserQuestion` summarizing the whole proposed config (services + start
hints, repos + bug tags + remotes + per-repo gates, freeze repo/runner or "off"), with
options: **accept all** (recommended) / **edit a group** / (re-detect only) **show the
diff**. Target ~3 questions total on a typical single-repo project.

Then, separately — because detection cannot know these — ask:
- **`entry_target`**: the module + a visible landmark to reach after login (e.g.
  `"Dashboard (heading 'Dashboard')"`).
- **Login type**: `form | sso | magic-link | none`, plus `login_detect` (a plain
  description the model can match against a snapshot, e.g. `"a form with a password
  field"`).
- For `login: form` only, **`auto_fill`**:
  - `true` (recommended) = scripted login by `qa-login.mjs`, outside the MCP browser. The
    value never reaches the transcript.
  - `false` = log in by hand in the headed browser.

  See *Login types and credentials* in `reference.md`.
- Any group detection had no confident value for.

For `login: form`, also read `--executable-path` from `claude mcp get playwright-headless`.
If it's present, propose it as `browser.executable_path` in the summary; the login script
then drives the same browser build as the MCP server.

Right after the answers, for `login: form` with `auto_fill: true`, write the config first
(`setup.smoke: pending`, `session.password_file: login.json`). Then check that a
credential resolves. The command takes the **literal** `<QA>` path and never prints the
value:

```bash
node "${CLAUDE_PLUGIN_ROOT}/skills/qa-run/scripts/qa-login.mjs" check "<QA>"
```

- `ok file` / `ok env` → continue. Handle a `warn literal-in` line per the credential
  migration in step 1.
- `error login-missing` → print the capture command with every path resolved. The user
  runs it with the `!` prefix: with no TTY it opens a native hidden-input dialog on macOS.
  They can also run it from a separate terminal.

  ```
  ! node "<CLAUDE_PLUGIN_ROOT>/skills/qa-run/scripts/qa-login.mjs" save "<QA>"
  ```

  Then use `AskUserQuestion`: **I ran it** / **stop and resume later**. After "I ran it",
  re-run `check`. If it's still not `ok` → stop `[login-file-missing]`. As an alternative,
  `credentials_env` vars exported **before** Claude Code starts also satisfy `check`.
- `error file-mode` / `error file-invalid` / `error unsafe-path` → print the fix from the
  stop table, then re-run `check`. If `save` printed `error cancelled` (dialog dismissed,
  or an empty value), re-run the `save` command.
- Only if the user says neither the `!` command nor a terminal can work for them, offer
  `AskUserQuestion`'s free-text "Other" as a last resort. The option text must say that the
  value will then sit in this session's transcript and should be rotated afterwards.
  - Write the file in one Bash call that sets `umask 077` first, so it's never created
    group-readable. Don't use the Write tool.
  - Write it as JSON to `<QA>/login.json`.
  - Never echo the value back.

## 3b. Ticket sources

A `multiSelect` `AskUserQuestion` lists every candidate ticket source together with its
detected state. Built-in presets: **Jira** (via an Atlassian-style MCP server), **Brain**
(via the `brain` MCP), **GitHub** (via the `gh` CLI), and **free text** (always
available). Any other connected MCP server is offered too, via the generic adapter below.

Run detection from `<CHECKOUT_ROOT>` (project-scoped MCP config is cwd-sensitive) in this
order, per candidate:
1. **Connected now** — this session's tool list already exposes `mcp__<server>__*`
   (including deferred tool names).
2. **Configured, not connected** — `claude mcp list` shows it disabled or failing → fix:
   enable it via `/mcp`.
3. **Stashed on-demand** — a matching key in `~/.claude/mcp-stash.json` → fix:
   `~/.claude/mcp-restore.sh <name>` then restart Claude Code.
4. **Absent** → tell the user how to add it (`claude mcp add …`), or they pick a
   different source.

CLI sources (GitHub): `command -v gh`, then `gh auth status`, then a remote to scope
`params.repo` to.

**Every selected source is verified with one live read before being saved:**
- Jira preset: `getAccessibleAtlassianResources` (resolves `cloud_id`), then confirm the
  project key (`ticket.sources[].params.project` — needed so a bare number can be
  prefixed into a full key).
- Brain preset: `list_projects` (user picks one → `project_id`), then one `list_tasks`
  call.
- GitHub preset: `gh issue list -L 1 --repo <owner/name>`.
- Generic adapter (any other MCP server): read the server's tool schemas, propose a fetch
  tool + id parameter, an optional list tool + filters for no-argument picks, which
  response fields hold title/body/comments, and an `id_pattern`; the user confirms, and
  one live fetch of a sample id they give proves the mapping before it's saved.

A **selected** source that fails verification (not connected, auth failing, etc.) is
still saved, but as `pending`, with its fix printed. `qa-run` refuses to route to a
`pending` source until a later `qa-setup` run verifies it.

Finish by picking `ticket.default` from among the verified sources — used for
no-argument `qa-run` runs and for a bare number under the Jira preset.

## 4. Write the config

Write `<QA>/config.yml` from the template in `reference.md`, `schema_version: 1`,
`setup.smoke: pending`. `mkdir -p "<QA>/reports"`.

## 5. Knowledge — seed or adopt

Decide from the current state of `<QA>/knowledge`:

| State | Action |
|---|---|
| Symlink to the store picked this run, or an already-populated directory | Leave it; seed only the files it's missing. |
| Empty directory | Seed all four files. |
| Dangling symlink | Report the missing target; ask: re-point to a detected store, or seed fresh. |
| Symlink to a store **other than** this run's pick | Ask before re-pointing. |
| Absent, and no candidate stores were detected | Create `<QA>/knowledge/` and seed `navigation.md`, `quirks.md`, `actions.md`, `probes.md` — see *Knowledge seeds* in `reference.md`. |
| Absent, and ≥1 candidate store was detected (`<QA>/knowledge` itself is never a candidate) | Two questions, in order: **(1)** which store to adopt, or seed fresh; **(2)** confirm moving the picked store into `<QA>/knowledge` with an absolute symlink left at the old path (exact paths shown) — this is the only adoption path (see below). |

**A store whose files are git-tracked is never moved.** Check with `git -C <store-repo>
ls-files` inside the store's own repo; if non-empty, explain that moving it would delete
shared, committed files from the working tree and leave teammates with a dangling path —
offer **seed fresh** instead, never the move.

**Safe move**, for an untracked store only:
1. Record the pre-move file count and total byte size.
2. `mv <store> "<QA>/knowledge"` — `<QA>` is under `$HEROW_HOME`, very likely a different
   filesystem from the project repo, so this may be a non-atomic copy+delete rather than a
   rename; that's fine, because the next step verifies it regardless.
3. Recount files and bytes at the new location; **on any mismatch, rename back
   immediately and stop** `[store-move-refused]`.
4. Create the reverse symlink at the old path pointing at the new location with an
   **absolute** target (`<QA>/knowledge` is outside the repo, so a relative target would be
   wrong the instant the link is read from anywhere else), so anything still reading the
   old path (another skill, another tool) keeps working.
5. Print the exact undo command in the setup report: `rm <old-path symlink>; mv "<QA>/knowledge" <old-path>`.

After a successful adoption, seed **only** the files the adopted store is missing (e.g.
it has `navigation.md`/`quirks.md`/`actions.md` but no `probes.md`) — never touch files
the store already has.

**Smoke-walk recipe merge (adopted stores).** When the smoke walk in step 6 would write a
navigation entry, and the adopted store already holds one for the same target and `Env:`,
update that entry's `Last verified` in place instead of appending a near-duplicate.

## 6. Smoke walk

1. **Preflight.** Curl every `services[]` entry. Any down → keep the config as written,
   leave `setup.smoke: pending`, print each service's `start_hint`, and stop: "start them,
   then re-run `/herow-dev:qa-setup` — it resumes here."
2. **Pick the browser server from `browser.headed_required`** (not "headless first,
   headed on failure" — this step must match whatever the config already says, so a
   headed-required project doesn't try headless again on every resume and loop). If the
   chosen server's tools aren't in this session's tool list, print the restore-and-restart
   instruction from *Login types* in `reference.md` (or, if `~/.claude/mcp-restore.sh` or
   its `playwright` stash entry doesn't exist on this machine, the generic "add a headed
   Playwright MCP server named `playwright` and restart" instruction), leave
   `setup.smoke: pending`, and stop.
   A scripted-login project (`login: form`, `auto_fill: true`) also needs
   `mcp__playwright-headless__browser_set_storage_state` in the tool list (deferred names
   count). If it's absent → print the reconfig command from *Login types and credentials*
   in `reference.md`, leave `setup.smoke: pending`, and stop `[browser-caps-missing]`.
3. Navigate to `session.start_url`, snapshot. If the snapshot matches
   `session.login_detect`, log in per *Login types and credentials* in `reference.md`. For
   a scripted login, that means the script, then `browser_set_storage_state`, then
   `qa-login.mjs clear` (always, once the script printed `ok`, even if the restore failed),
   then a re-navigate.
4. Navigate toward `session.entry_target`.
5. **Pass condition:** the `entry_target` landmark is visible in a snapshot — regardless
   of whether a login form was shown (the persistent browser profile usually keeps you
   signed in across runs). On pass: write (or update in place, for an adopted store) the
   first `navigation.md` recipe with today's date and `Env: <session.env>`; set
   `session.entry_recipe` to that entry's exact heading; set `setup.smoke: verified` and
   `smoke_date`.
6. **Failure paths** (both leave `setup.smoke: pending`, write no recipe):
   - **Login failed** — `qa-login.mjs login` printed `error <code>` (see the stop table:
     `rejected` = wrong credentials; `no-form`/`field-missing` = set `session.login_fields`).
     A related case: the script printed `ok`, but after the restore the snapshot still
     matches `login_detect` → stop `[session-not-transferred]`.
   - **Landmark not found, no login form ever seen** — most likely the wrong app/URL; do
     not fall back to guessing, report which check failed with the snapshot evidence.
   In either case, offer via `AskUserQuestion`: edit the offending config key and retry
   now, or stop and resume later (`/herow-dev:qa-setup` picks up at this step).
7. **Headless blocked mid-walk** (2FA, CAPTCHA, an SSO consent screen), or `session.login`
   is `sso`/`magic-link`: set `browser.headed_required: true` in the config, run
   `~/.claude/mcp-restore.sh playwright` (or print the generic instruction when that
   script or its `playwright` entry is missing), and stop: "restart Claude Code, then
   re-run `/herow-dev:qa-setup` — it resumes here, now headed."

## 7. Report

Write `<QA>/reports/setup-<YYYY-MM-DD-HHMM>.md` (so two setup runs can be diffed
for detection drift later) and print a summary with:
- `<QA>` (the store's absolute path) and `<CHECKOUT_ROOT>`;
- detected values next to what was actually confirmed (services, repos + gates, freeze,
  ticket sources — including anything saved `pending` and its fix);
- knowledge state (seeded / moved+linked with the undo command / linked as-is);
- the smoke-walk result;
- `started_at`, `verified_at`, `elapsed`, `questions_asked`, and `resumes` (each
  smoke-pending re-run and why) — local-only measurements, not sent anywhere;
- the **next command**: if the current branch of `<CHECKOUT_ROOT>`, or of any `repos[]`
  entry, matches a **verified** source's `id_pattern`, print `next: /herow-dev:qa-run
  <matched id>` filled in (e.g. `next: /herow-dev:qa-run PROJ-123`); otherwise
  `next: /herow-dev:qa-run <ticket>`.

## Stop messages

Every stop in this skill uses the code table in `reference.md`: `QA setup stopped
[<code>]: <problem>. Cause: <cause>. Fix: <exact command or config key>.` plus a resume
hint when one applies.
