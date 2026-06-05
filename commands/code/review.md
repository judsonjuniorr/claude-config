---
description: (herow) Multi-agent code review for local changes or a PR — dispatches specialist reviewers, dedupes, ranks by severity.
argument-hint: [pr-number | pr-url | blank-for-local]
allowed-tools: Bash, Read, Grep, Glob, Task
---

# Code Review

**Input**: `$ARGUMENTS`

---

## Mode Selection

Parse `$ARGUMENTS`:
- If blank → **Local Review Mode**
- If it contains a number, URL (`github.com/.../pull/N`), or branch name → **PR Review Mode**

---

## Local Review Mode

### Phase 1 — GATHER

```bash
git diff --name-only HEAD
```

If no changed files, stop: "Nothing to review."

Get the diff:
```bash
git diff HEAD
```

### Phase 2 — DISPATCH

Run each of these agents via the Task/Agent tool in parallel against the diff:

1. `code-reviewer` — security, correctness, performance, test coverage
2. `comment-analyzer` — comment accuracy, rot, and completeness
3. `pr-test-analyzer` — behavioral coverage gaps
4. `silent-failure-hunter` — swallowed errors and dangerous fallbacks
5. `type-design-analyzer` — type encapsulation and invariant enforcement
6. `code-simplifier` — clarity and maintainability
7. `security-reviewer` — OWASP Top 10, secrets, SSRF, injection

### Phase 3 — DEDUPE AND RANK

After all agents report:
1. Group findings by file and line range
2. Deduplicate overlapping findings (same location, same issue class)
3. Keep only findings with confidence >= 80%
4. Rank by severity:
   - **Critical** — bugs, security vulnerabilities, data loss risk
   - **Important** — missing tests, quality problems, correctness issues
   - **Advisory** — style and maintainability suggestions

### Phase 4 — REPORT

Output findings grouped by severity. For each issue:

```
[SEVERITY] Short title
File: path/to/file.ts:42
Issue: One-sentence description.
Why: Impact.
Fix: Concrete change.
```

End with a summary count: `Critical: N, Important: N, Advisory: N`

---

## PR Review Mode

### Phase 1 — FETCH

Parse input to determine PR:

| Input | Action |
|---|---|
| Number (e.g. `42`) | Use as PR number |
| URL (`github.com/.../pull/42`) | Extract PR number |
| Branch name | Find PR via `gh pr list --head <branch>` |

```bash
gh pr view <NUMBER> --json number,title,body,author,baseRefName,headRefName,changedFiles
gh pr diff <NUMBER>
```

If PR not found, stop with an error message.

### Phase 2 — CHECK READINESS

```bash
gh pr view <NUMBER> --json mergeStateStatus,statusCheckRollup
```

If CI checks are red or there are merge conflicts, report and stop. Do not review a broken PR.

### Phase 3 — DISPATCH

Run each of these agents via the Task/Agent tool in parallel against the PR diff:

1. `code-reviewer` — security, correctness, performance, test coverage
2. `comment-analyzer` — comment accuracy, rot, and completeness
3. `pr-test-analyzer` — behavioral coverage gaps
4. `silent-failure-hunter` — swallowed errors and dangerous fallbacks
5. `type-design-analyzer` — type encapsulation and invariant enforcement
6. `code-simplifier` — clarity and maintainability
7. `security-reviewer` — OWASP Top 10, secrets, SSRF, injection

### Phase 4 — DEDUPE AND RANK

Same as Local Review Phase 3.

### Phase 5 — DECIDE

| Condition | Decision |
|---|---|
| Zero Critical/Important, checks pass | **APPROVE** |
| Only Advisory issues | **APPROVE with comments** |
| Any Important issues | **REQUEST CHANGES** |
| Any Critical issues | **BLOCK** |

### Phase 6 — REPORT

Output findings grouped by severity (Critical, Important, Advisory), then recommendation:

```
PR #<NUMBER>: <TITLE>
Decision: APPROVE | REQUEST CHANGES | BLOCK

Critical: N, Important: N, Advisory: N

[grouped findings]

Next steps:
  - gh pr review <NUMBER> --approve    (if approved)
  - gh pr review <NUMBER> --request-changes --body "<summary>"  (if changes needed)
```

---

## Confidence Rule

Only surface findings with confidence >= 80%:
- Critical: bugs, security, data loss
- Important: missing tests, quality problems, correctness issues
- Advisory: suggestions — only when >= 80% confident they improve the code
