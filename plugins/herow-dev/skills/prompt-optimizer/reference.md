# Prompt Optimizer — Reference Tables, Output Format & Examples

Supporting material for the pipeline in SKILL.md.

> **Catalog scope:** the tables below list **herow** plugin components. The installed
> plugin set varies per user (core / dev / seo / finance / extras) and the environment
> may add others (e.g. gstack). Before recommending a component, verify it exists in the
> session's available skills/commands/agents; substitute the closest real equivalent.

## Phase 0 — Tech-stack detection signals

2. Detect tech stack from project files:
   - `package.json` → Node.js / TypeScript / React / Next.js
   - `go.mod` → Go
   - `pyproject.toml` / `requirements.txt` → Python
   - `Cargo.toml` → Rust
   - `build.gradle` / `pom.xml` → Java / Kotlin (then check for `quarkus` in build file → Quarkus, or `spring-boot` → Spring Boot)
   - `Package.swift` → Swift
   - `Gemfile` → Ruby
   - `composer.json` → PHP
   - `*.csproj` / `*.sln` → .NET
   - `Makefile` / `CMakeLists.txt` → C / C++
   - `cpanfile` / `Makefile.PL` → Perl

## Phase 1 — Intent categories

| Category | Signal Words | Example |
|----------|-------------|---------|
| New Feature | build, create, add, implement | "Build a login page" |
| Bug Fix | fix, broken, not working, error | "Fix the auth flow" |
| Refactor | refactor, clean up, restructure | "Refactor the API layer" |
| Research | how to, what is, explore, investigate | "How to add SSO" |
| Testing | test, coverage, verify | "Add tests for the cart" |
| Review | review, audit, check | "Review my PR" |
| Documentation | document, update docs | "Update the API docs" |
| Infrastructure | deploy, CI, docker, database | "Set up CI/CD pipeline" |
| Design | design, architecture, plan | "Design the data model" |

## Phase 3 — Component matching tables

> All commands are namespaced by plugin (`/herow-dev:…`, `/herow-finance:…`, `/herow-seo:…`).
> Names below assume herow-core + herow-dev are installed; validate against the live session.

#### By Intent Type

| Intent | Commands | Skills | Agents |
|--------|----------|--------|--------|
| New Feature | `/herow-dev:code:generate-tests`, `/herow-dev:code:review` | — | fullstack-developer, backend-architect, tdd-guide |
| Bug Fix | `/herow-dev:code:generate-tests`, `/herow-dev:code:review` | — | debugger, tdd-guide |
| Refactor | `/herow-dev:code:refactor`, `/herow-dev:code:review` | — | code-simplifier, code-reviewer |
| Research | — | deep-research, exa-search | search-specialist |
| Testing | `/herow-dev:code:generate-tests`, `/herow-dev:react:test` | — | tdd-guide, pr-test-analyzer |
| Review | `/herow-dev:code:review`, `/herow-dev:python:review`, `/herow-dev:react:review` | — | code-reviewer, security-reviewer, silent-failure-hunter, comment-analyzer, type-design-analyzer |
| Documentation | `/herow-dev:git:release-notes` | — | comment-analyzer |
| Infrastructure / API design | — | — | backend-architect |
| Design (data model / API) | — | — | backend-architect |
| Design (UI/UX) | `/herow-dev:react:validate-ui` | — | ui-ux-designer |
| Requirements / PRD | `/herow-extras:create-prd` | — | — |
| Git / PR ops | `/herow-dev:git:pr`, `/herow-dev:git:fix-conflicts` | github-ops | — |
| Finance analysis | `/herow-finance:organizze` | — | financial-analyst |
| SEO / GEO | `/herow-seo:weekly-audit`, `/herow-seo:ctr-tune`, `/herow-seo:content-sprint`, … | — | seo-strategist, content-engineer, technical-seo-auditor |

#### By Tech Stack

| Tech Stack | Commands / Skills | Agent |
|------------|-------------------|-------|
| TypeScript / JavaScript | `/herow-dev:code:review` | typescript-reviewer, code-reviewer |
| React / Next.js | `/herow-dev:react:review`, `/herow-dev:react:test`, `/herow-dev:react:validate-ui` | react-reviewer, fullstack-developer, ui-ux-designer |
| Python | `/herow-dev:python:review` | python-pro, python-reviewer |
| Python / FastAPI | `/herow-dev:python:fastapi-review` | fastapi-reviewer |
| Mobile (React Native / iOS / Android) | — | mobile-developer |
| Backend / API (any language) | — | backend-architect |
| Error handling (TS / Python) | error-handling skill | — |
| Other / unlisted | `/herow-dev:code:review` | code-reviewer |

## Phase 5 — Model recommendation & multi-prompt splitting

**Model recommendation** (include in output):

| Scope | Recommended Model | Rationale |
|-------|------------------|-----------|
| TRIVIAL | Haiku | Cheapest tier for mechanical, single-file edits |
| LOW–MEDIUM | Sonnet | Best coding model for standard work |
| HIGH | Sonnet (impl) + Opus (planning) | Opus for architecture, Sonnet for implementation |
| EPIC | Opus (planning) + Sonnet (execution) | Deep reasoning for multi-session planning |

**Multi-prompt splitting** (for HIGH/EPIC scope):

For tasks that exceed a single session, split into sequential prompts:
- Prompt 1: Research + plan (use the `deep-research` skill for unknowns, then sketch phases)
- Prompt 2–N: Implement one phase per prompt (each ends with `/herow-dev:code:review`)
- Final Prompt: Integration test + review across all phases
- If your environment provides a planning skill (e.g. `blueprint`), use it to persist the
  phase plan and resume between sessions.

## Output Format (full spec)

### Section 1: Prompt Diagnosis

**Strengths:** List what the original prompt does well.

**Issues:**

| Issue | Impact | Suggested Fix |
|-------|--------|---------------|
| (problem) | (consequence) | (how to fix) |

**Assumptions & resolved clarifications:** List the answers collected via
`AskUserQuestion` in Phase 4 and any non-material defaults applied (e.g.
"Auth: JWT — no auth specified, defaulting to JWT"). Do **not** list open,
unanswered questions here. The optimized prompt is generated **only after** all
material questions from Phase 4 are answered; unanswered must-answer questions
must never appear alongside a generated prompt.

### Section 2: Recommended Components

| Type | Component | Purpose |
|------|-----------|---------|
| Agent | fullstack-developer | Implement the feature end-to-end |
| Command | /herow-dev:code:review | Post-implementation review |
| Skill | deep-research | Research unknowns with cited sources |
| Model | Sonnet | Recommended for this scope |

### Section 3: Optimized Prompt — Full Version

Present the complete optimized prompt inside a single fenced code block.
The prompt must be self-contained and ready to copy-paste. Include:
- Clear task description with context
- Tech stack (detected or specified)
- /command invocations at the right workflow stages
- Acceptance criteria
- Verification steps
- Scope boundaries (what NOT to do)

For multi-session work, write: "Use a planning skill (e.g. blueprint) to..." if one is
available in the environment — do not assume a specific planning command exists.

### Section 4: Optimized Prompt — Quick Version

A compact version for experienced users. Vary by intent type:

| Intent | Quick Pattern |
|--------|--------------|
| New Feature | `Implement [feature]. Generate tests with /herow-dev:code:generate-tests. /herow-dev:code:review.` |
| Bug Fix | `Use the debugger agent to root-cause [bug]. Add a failing test, fix to green, /herow-dev:code:review.` |
| Refactor | `/herow-dev:code:refactor [scope]. /herow-dev:code:review.` |
| Research | `Use the deep-research skill for [topic]; cite sources.` |
| Testing | `/herow-dev:code:generate-tests for [module]` (React: `/herow-dev:react:test`). |
| Review | `/herow-dev:code:review` (Python: `/herow-dev:python:review`; React: `/herow-dev:react:review`). |
| Docs | `/herow-dev:git:release-notes since the last tag.` |
| Git/PR | `/herow-dev:git:pr` (conflicts: `/herow-dev:git:fix-conflicts`). |
| Planning (EPIC) | `Plan "[objective]" in phases with a review gate between each; use a planning skill if available.` |

### Section 5: Enhancement Rationale

| Enhancement | Reason |
|-------------|--------|
| (what was added) | (why it matters) |

### Footer

> Not what you need? Tell me what to adjust, or make a normal task request
> if you want execution instead of prompt optimization.

## Examples

### Trigger Examples

- "Optimize this prompt"
- "Rewrite this prompt so Claude Code uses the right commands"
- "How should I prompt for this task?"

### Example 1: Vague Prompt (Project Detected)

**User input:**
```
Build a user login page
```

**Phase 0 detects:** `package.json` with Next.js 16, TypeScript, Tailwind CSS

**Phase 4 classifies gaps:**
- Tech stack → **non-material** (detected from project files).
- Auth strategy → **non-material** (project's existing auth approach used as default; JWT if none found).
- Scope → **non-material** (login page is the explicit request; excluded items noted in "Do not").

No material gaps — no `AskUserQuestion`. Proceeds directly to Phase 5.

**Section 1 — Assumptions & resolved clarifications:**
- Tech stack: Next.js 16 + TypeScript + Tailwind CSS (detected from `package.json`)
- Auth: reuse existing project auth approach (defaulting to JWT if none found)

**Optimized Prompt (Full):**
```
Implement a user login page using the project's existing tech stack (Next.js 16 + TypeScript + Tailwind CSS).

Requirements:
- Follow the project's existing component structure and routing conventions
- Use the project's existing form-validation approach (check whether Zod/Yup/other is already in use)
- Auth: reuse the project's existing auth approach (default to JWT if none exists)
- Include: email/password login form, form validation, error messages, loading state, responsive layout

Workflow:
1. Sketch the component structure and auth flow first, referencing existing page patterns (delegate to the backend-architect agent if the auth/data model is non-trivial)
2. Generate tests first with /herow-dev:code:generate-tests — unit tests for the login form, integration tests for the auth flow
3. Implement the login page and auth logic (fullstack-developer agent)
4. /herow-dev:react:review and /herow-dev:code:review
5. Confirm all tests pass and the page renders correctly

Security:
- Never transmit passwords in plaintext
- Prevent brute force (rate limiting)
- XSS protection
- CSRF token

Acceptance criteria:
- All tests pass, 80%+ coverage
- Page renders correctly on mobile and desktop
- Successful login redirects to dashboard; failure shows an error message

Do not:
- Implement the registration page
- Implement forgot-password
- Change the existing routing structure
```

### Example 1b: Material gap → AskUserQuestion → generate (no project files)

**User input:**
```
Build a login page
```

**Phase 0 detects:** no project files — tech stack unknown.

**Phase 4 classifies gaps:**
- Tech stack → **material** (determines components, commands, and agent).
- Auth strategy → **material** (JWT vs OAuth vs Session changes the whole prompt).
- Target scope (registration? forgot-password?) → **material**.

**Skill calls AskUserQuestion (3 questions batched, before any output):**

```
Q1 "What tech stack are you using?"
  Options: Next.js + TypeScript | React + Vite | Python + FastAPI (server-rendered) | Other

Q2 "Which authentication strategy should the login page use?"
  Options: JWT (stored in httpOnly cookie) | OAuth2 / social login | Session cookie (server-side) | Other

Q3 "What is in scope for this task?"
  Options: Login form only | Login + registration | Login + registration + forgot-password | Other
```

**User answers:** Next.js + TypeScript · JWT · Login form only

**Skill folds answers in, runs Phase 5, then emits full output:**

**Section 1 — Assumptions & resolved clarifications:**
- Tech stack: Next.js + TypeScript (user confirmed; no project files present)
- Auth: JWT stored in httpOnly cookie (user confirmed)
- Scope: Login form only — registration and forgot-password excluded

**Optimized Prompt (Full):**
```
Implement a user login page in Next.js + TypeScript using JWT authentication
(httpOnly cookie, no registration or forgot-password in scope).

Requirements:
- Route: /login (use the App Router convention if Next.js 13+)
- Form fields: email, password; include validation (Zod preferred)
- On success: exchange credentials for a JWT, set it as an httpOnly cookie,
  redirect to /dashboard
- On failure: display an inline error message; never reveal which field is wrong
- Loading state during submission
- Responsive layout (mobile + desktop)

Workflow:
1. Detect and reuse existing form/auth utilities in the codebase
2. Generate tests first with /herow-dev:code:generate-tests — unit tests for the
   form, integration tests for the JWT exchange and cookie-setting flow
3. Implement the page and auth logic (fullstack-developer agent)
4. /herow-dev:react:review and /herow-dev:code:review
5. Confirm all tests pass and the page renders on mobile and desktop

Security:
- JWT in httpOnly cookie only — never expose to JS
- Rate-limit login attempts (or note if a middleware already does this)
- CSRF token on the form
- XSS: sanitize all user inputs

Acceptance criteria:
- All tests pass, 80%+ coverage
- Successful login → /dashboard; failure → inline error with no field disclosure
- Responsive layout verified

Do not:
- Implement registration or forgot-password
- Implement OAuth or social login
- Change the existing routing structure
```

---

### Example 2: Moderate English Prompt

**User input:**
```
Add a REST API endpoint for user profile updates with validation
```

**Phase 0 detects:** `pyproject.toml` with FastAPI + SQLAlchemy

**Phase 4 classifies gaps:**
- Tech stack → **non-material** (detected from project files).
- Auth strategy → **non-material** (endpoint requires a valid token; project's existing auth approach applies).
- Scope → **non-material** (PATCH /users/{id} is the explicit request; excluded items noted in "Do not").

No material gaps — no `AskUserQuestion`. Proceeds directly to Phase 5.

**Optimized Prompt (Full):**
```
Add a REST API endpoint for user profile updates (PATCH /api/users/{id}).

Tech stack: Python + FastAPI + SQLAlchemy (detected from project)

Requirements:
- PATCH /api/users/{id} — partial update of user profile
- Pydantic validation for fields: name, email, avatar_url, bio
- Auth: require valid token, users can only update own profile
- Return 200 with updated user on success
- Return 422 with validation errors on invalid input
- Return 401/403 for auth failures
- Follow existing router/dependency patterns in the codebase

Workflow:
1. Sketch the endpoint contract and dependency chain (backend-architect agent if the schema is non-trivial)
2. Generate tests first with /herow-dev:code:generate-tests — success, validation failure, auth failure, not-found
3. Implement following existing handler patterns (python-pro agent)
4. /herow-dev:python:fastapi-review
5. Run the full test suite, confirm no regressions

Do not:
- Modify existing endpoints
- Change the database schema (use existing user table)
- Add new dependencies before checking existing ones (use the exa-search or deep-research skill to confirm)
```

### Example 3: EPIC Project

**User input:**
```
Migrate our monolith to microservices
```

**Phase 0 detects:** no project files — tech stack unknown.

**Phase 4 classifies gaps:**
- Tech stack → **non-material** (EPIC planning prompt intentionally leaves implementation details to the planning phase; the generated prompt embeds those as questions for the executor to resolve, not questions this skill needs answered now).
- Scope → **non-material** (full migration is the explicit request; phased breakdown is in the prompt itself).

No material gaps — no `AskUserQuestion`. Proceeds directly to Phase 5.

**Optimized Prompt (Full):**
```
Plan: "Migrate monolith to microservices architecture" (use a planning skill such as blueprint if available in your environment).

Before executing, answer these questions in the plan:
1. Which domain boundaries exist in the current monolith?
2. Which service should be extracted first (lowest coupling)?
3. Communication pattern: REST APIs, gRPC, or event-driven (Kafka/RabbitMQ)?
4. Database strategy: shared DB initially or database-per-service from start?
5. Deployment target: Kubernetes, Docker Compose, or serverless?

Recommended phases:
- Phase 1: Identify service boundaries and create a domain map (backend-architect agent)
- Phase 2: Set up infrastructure (API gateway, service mesh, CI/CD per service)
- Phase 3: Extract first service (strangler fig pattern)
- Phase 4: Verify with integration tests, then extract next service
- Phase N: Decommission monolith

Each phase = 1 PR, with a /herow-dev:code:review gate between phases.
Use the deep-research skill for unknowns (e.g. service-mesh choice).
Use git worktrees for parallel service extraction when dependencies allow.

Recommended: Opus for planning, Sonnet for phase execution.
```

---
