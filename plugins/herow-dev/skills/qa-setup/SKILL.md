---
name: qa-setup
description: >-
  (herow) Set up config-driven live-app QA for this repo — resolves the project root,
  detects services/repos/gates from the codebase, writes .qa/config.yml, seeds or adopts
  a knowledge store, ensures .qa/ is covered by the global gitignore, and proves the
  config with a live Playwright smoke walk. Run once per project (safely re-runnable).
  Use on "set up QA for this repo", "/herow-dev:qa-setup", or as the fix pointed to by a
  qa-run "[no-config]" stop.
---

# qa-setup

Writes `<root>/.qa/config.yml`, seeds or adopts `<root>/.qa/knowledge/`, makes sure that
directory is covered by git's **global** excludesfile, and proves the whole config with a
live smoke walk (login + first navigation). This is the one-time (re-runnable) setup that
`/herow-dev:qa-run` then reads every project constant from — see
`plugins/herow-dev/skills/qa-run/SKILL.md`.

Read `reference.md` **in this skill's directory** for: the commented `config.yml`
template, knowledge seed contents (including the fresh-store tool-quirk seeds), the
probe/detection catalogue, and the stop-code table. Load it now — most steps below point
back into it.

## Constraints (always true)

- Memory lives at `<root>/.qa/{config.yml,knowledge/,reports/}` — **never** under
  `.claude/` (write-prevention hooks trigger there, and in at least one real project
  content under `.claude/` leaks to an external log aggregator). These paths are fixed,
  not configurable, so a single ignore rule (`.qa/`) covers all of it.
- Credentials are **never** written into `config.yml` — only the names of the env vars
  that hold them. Reports and knowledge always print `[REDACTED]` in their place.
- Prefer the headless Playwright MCP server (`mcp__playwright-headless__*`); use the
  headed one (`mcp__playwright__*`) only when headless is blocked — that is a per-project
  fact (`browser.headed_required`) proved by the smoke walk, not a preference you guess.
- Drive the browser **in this session**, never through a subagent — a subagent starts
  cold and loses the open tabs and snapshots this walk builds up.
- **`qa-setup` is the only writer of `config.yml`.** `qa-run` never edits it.
- All generated content (config comments, reports, knowledge seeds) is in English.

## 1. Resolve the root and existing state

Walk up from the cwd looking for `.qa/config.yml`. If one is found, that config's
directory **is** the root — reuse it (never propose a different root once a config
exists, so a child repo's `.qa/frozen/` can never become a root by accident).

If none is found, propose a root and confirm it:
- the git toplevel of the cwd, when the cwd is inside a git repo;
- otherwise, if the cwd holds one or more child git repos (a multi-repo workspace, no
  git repo at the workspace root itself), propose the cwd itself as the root.

`repos[].path` in the config is always relative to this root.

**If `.qa/config.yml` already exists:**
- `schema_version` newer than this skill understands → stop `[schema-newer]` (see the
  stop-code table in `reference.md`).
- Never overwrite silently. Offer, via `AskUserQuestion`:
  - `setup.smoke: pending` → recommend **"resume the smoke walk"** (skip straight to
    step 7);
  - otherwise offer **re-detect** (a merge — see below) or **edit specific keys**.
- **Re-detect is a merge, not a rewrite.** Detected keys (services, repos, gates,
  detected ticket sources) are shown as a diff against the current config and applied
  only on confirmation. Hand-set and smoke-derived keys are **always kept** regardless of
  re-detect: `gotchas`, `browser.headed_required`, `session.entry_recipe`, `setup.*`, and
  any `ticket.sources[]` entry already `verified` with its resolved params. Reset
  `setup.smoke` to `pending` only when a `session.*` or `services[]` key actually
  changes — an unrelated key changing (e.g. a repo's gates) does not invalidate a proven
  login/navigation recipe.

## 1b. Ignore first — before any file under `.qa/` is written

Run this **before** step 2, on every run (including re-detect and resume), even in a
workspace root that isn't itself a git repo yet (a later `git init` there, or a child
repo, would otherwise start tracking `.qa/`):

```bash
bash "${CLAUDE_PLUGIN_ROOT}/skills/qa-setup/scripts/ensure-ignored.sh" --apply "<root>"
```

- Exit `0` → continue.
- Exit `1` or `3` → stop `[ignore-not-covered]` / `[env-error]`: print the manual fix line
  the script gave and the resolved excludesfile path. Nothing under `.qa/` gets written or
  moved.
- Exit `2` → stop `[memory-tracked]`: print the exact `git rm -r --cached .qa` command the
  script printed, per affected repo.

## 2. Detect

No deterministic `detect.sh` in this version — read the project's own files (all curl
probes below are the *only* live signals; never trust a listening socket that no file
names, so an unrelated project's dev server is never proposed):

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
  `.claude/skills/*/knowledge/navigation.md` (resolve symlinks), excluding `.qa/knowledge`
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
- For `login: form` only: the **credential env-var names** (`credentials_env.user`,
  `credentials_env.password`) and **`auto_fill`** — recommend `true` only when
  `session.env` is `local`, and state plainly in the option text that a `true` answer
  means the credential value reaches the tool-call transcript (see *Login types and
  credentials* in `reference.md`).
- Any group detection had no confident value for.

Right after the answers, if `login: form`, check that the **confirmed**
`credentials_env.user` / `credentials_env.password` names actually have a value set,
without ever printing it — e.g. for `credentials_env: { user: QA_USER, password:
QA_PASSWORD }`:

```bash
[ -n "${QA_USER+x}" ] && [ -n "${QA_PASSWORD+x}" ]
```

If either is missing: write the config anyway with `setup.smoke: pending`, print the
exact copy-paste export lines (shell profile, or `<root>/.envrc` for direnv — already
globally ignored), and stop `[env-var-missing]`: "restart Claude Code, then re-run
`/herow-dev:qa-setup` — it resumes at the smoke walk." A var set inside this session's
Bash tool never reaches Claude Code itself or the MCP server, so this is not optional.

## 3b. Ticket sources

A `multiSelect` `AskUserQuestion` lists every candidate ticket source together with its
detected state. Built-in presets: **Jira** (via an Atlassian-style MCP server), **Brain**
(via the `brain` MCP), **GitHub** (via the `gh` CLI), and **free text** (always
available). Any other connected MCP server is offered too, via the generic adapter below.

Run detection from `<root>` (project-scoped MCP config is cwd-sensitive) in this order,
per candidate:
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

Write `<root>/.qa/config.yml` from the template in `reference.md`, `schema_version: 1`,
`setup.smoke: pending`. `mkdir -p <root>/.qa/reports`.

## 5. Knowledge — seed or adopt

Decide from the current state of `<root>/.qa/knowledge`:

| State | Action |
|---|---|
| Symlink to the store picked this run, or an already-populated directory | Leave it; seed only the files it's missing. |
| Empty directory | Seed all four files. |
| Dangling symlink | Report the missing target; ask: re-point to a detected store, or seed fresh. |
| Symlink to a store **other than** this run's pick | Ask before re-pointing. |
| Absent, and no candidate stores were detected | Create `.qa/knowledge/` and seed `navigation.md`, `quirks.md`, `actions.md`, `probes.md` — see *Knowledge seeds* in `reference.md`. |
| Absent, and ≥1 candidate store was detected (`.qa/knowledge` itself is never a candidate) | Two questions, in order: **(1)** which store to adopt, or seed fresh; **(2)** confirm moving the picked store into `.qa/knowledge` with a relative symlink left at the old path (exact paths shown) — this is the only adoption path (see below). |

**A store whose files are git-tracked is never moved.** Check with `git -C <store-repo>
ls-files` inside the store's own repo; if non-empty, explain that moving it would delete
shared, committed files from the working tree and leave teammates with a dangling path —
offer **seed fresh** instead, never the move.

**Safe move**, for an untracked store only:
1. Same-filesystem check: `stat -f %d "$a" 2>/dev/null || stat -c %d "$a"` must equal for
   the store and `.qa/knowledge`'s parent. Different filesystems → refuse, offer seed
   fresh (a cross-filesystem `mv` is a non-atomic copy+delete that can leave a half-moved
   store on failure).
2. Record the pre-move file count and total byte size.
3. `mv <store> <root>/.qa/knowledge` (same filesystem, atomic rename).
4. Recount files and bytes at the new location; **on any mismatch, rename back
   immediately and stop** `[store-move-refused]`.
5. Create the reverse symlink at the old path pointing at the new location, so anything
   still reading the old path (another skill, another tool) keeps working.
6. Print the exact undo command in the setup report: `rm <old-path symlink>; mv
   <root>/.qa/knowledge <old-path>`.

After a successful adoption, seed **only** the files the adopted store is missing (e.g.
it has `navigation.md`/`quirks.md`/`actions.md` but no `probes.md`) — never touch files
the store already has.

**Smoke-walk recipe merge (adopted stores).** When the smoke walk in step 7 would write a
navigation entry, and the adopted store already holds one for the same target and `Env:`,
update that entry's `Last verified` in place instead of appending a near-duplicate.

## 6. Ignore re-check

After writing the config (and moving any store), re-run:

```bash
bash "${CLAUDE_PLUGIN_ROOT}/skills/qa-setup/scripts/ensure-ignored.sh" --check "<root>"
```

Non-zero → stop and report exactly which code came back (same codes as step 1b).

## 7. Smoke walk

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
3. Navigate to `session.start_url`, snapshot. If the snapshot matches
   `session.login_detect`, log in per *Login types and credentials* in `reference.md`.
4. Navigate toward `session.entry_target`.
5. **Pass condition:** the `entry_target` landmark is visible in a snapshot — regardless
   of whether a login form was shown (the persistent browser profile usually keeps you
   signed in across runs). On pass: write (or update in place, for an adopted store) the
   first `navigation.md` recipe with today's date and `Env: <session.env>`; set
   `session.entry_recipe` to that entry's exact heading; set `setup.smoke: verified` and
   `smoke_date`.
6. **Failure paths** (both leave `setup.smoke: pending`, write no recipe):
   - **Credentials rejected** — the login form is still shown after a fill attempt.
   - **Landmark not found, no login form ever seen** — most likely the wrong app/URL; do
     not fall back to guessing, report which check failed with the snapshot evidence.
   In either case, offer via `AskUserQuestion`: edit the offending config key and retry
   now, or stop and resume later (`/herow-dev:qa-setup` picks up at this step).
7. **Headless blocked mid-walk** (2FA, CAPTCHA, an SSO consent screen), or `session.login`
   is `sso`/`magic-link`: set `browser.headed_required: true` in the config, run
   `~/.claude/mcp-restore.sh playwright` (or print the generic instruction when that
   script or its `playwright` entry is missing), and stop: "restart Claude Code, then
   re-run `/herow-dev:qa-setup` — it resumes here, now headed."

## 8. Report

Write `<root>/.qa/reports/setup-<YYYY-MM-DD-HHMM>.md` (so two setup runs can be diffed
for detection drift later) and print a summary with:
- root, the config path;
- detected values next to what was actually confirmed (services, repos + gates, freeze,
  ticket sources — including anything saved `pending` and its fix);
- knowledge state (seeded / moved+linked with the undo command / linked as-is);
- the exact ignore line and file from step 1b;
- the smoke-walk result;
- `started_at`, `verified_at`, `elapsed`, `questions_asked`, and `resumes` (each
  smoke-pending re-run and why) — local-only measurements, not sent anywhere;
- the **next command**: if the current branch of the root, or of any `repos[]` entry,
  matches a **verified** source's `id_pattern`, print `next: /herow-dev:qa-run <matched
  id>` filled in (e.g. `next: /herow-dev:qa-run PROJ-123`); otherwise
  `next: /herow-dev:qa-run <ticket>`.

## Stop messages

Every stop in this skill uses the code table in `reference.md`: `QA setup stopped
[<code>]: <problem>. Cause: <cause>. Fix: <exact command or config key>.` plus a resume
hint when one applies.
