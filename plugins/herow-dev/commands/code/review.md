---
description: (herow) Multi-agent code review for local changes or a PR — color-ranked findings, optional --fix or --comment.
argument-hint: "[pr-number | pr-url | branch] [low|medium|high|max] [--fix] [--comment]"
allowed-tools: Bash, Read, Write, Edit, Grep, Glob, Task
---

# Code Review

**Input**: `$ARGUMENTS`

---

## Argument Parsing

Split `$ARGUMENTS` into tokens and classify each:

| Token | Meaning |
|---|---|
| A number, a `github.com/.../pull/N` or `gitlab.com/.../merge_requests/N` URL, or a branch name | **target** → PR Review Mode |
| `low` \| `medium` \| `high` \| `max` | **effort** (default `high`) |
| `--fix` | apply concrete fixes to the working tree after review |
| `--comment` | post findings to the PR/MR (PR Review Mode only) |

If no **target** token is present → **Local Review Mode**.
`--fix` and `--comment` may be combined. `--comment` is ignored (with a warning) in Local Mode.

> **GitHub vs GitLab.** PR Review Mode works on both. Detect the platform once (see *Platform
> Detection* in PR Review Mode) and use the matching CLI: **`gh`** for GitHub pull requests,
> **`glab`** for GitLab merge requests. "PR" below means pull request *or* merge request.

---

## Effort → Dispatch

Run these agents via the Task tool **in parallel** against the diff. Higher effort = more agents
and a lower confidence cutoff:

| Effort | Agents | Confidence cutoff |
|---|---|---|
| `low` | `code-reviewer`, `security-reviewer` | ≥ 90 |
| `medium` | above + `silent-failure-hunter`, `pr-test-analyzer` | ≥ 85 |
| `high` *(default)* | above + `comment-analyzer`, `type-design-analyzer`, `code-simplifier` (all 7) | ≥ 80 |
| `max` | all 7, then a **verification pass** (see below) | ≥ 80 |

Agent focus areas:
1. `code-reviewer` — security, correctness, performance, test coverage
2. `security-reviewer` — OWASP Top 10, secrets, SSRF, injection
3. `silent-failure-hunter` — swallowed errors and dangerous fallbacks
4. `pr-test-analyzer` — behavioral coverage gaps
5. `comment-analyzer` — comment accuracy, rot, and completeness
6. `type-design-analyzer` — type encapsulation and invariant enforcement
7. `code-simplifier` — clarity and maintainability

**Verification pass (`max` only):** after dedupe, launch one Task agent per surviving finding that
tries to **refute** it — is it a false positive, a pre-existing issue, or on a line not in the
diff? Drop any finding the refuter cannot confirm. Mirrors the confidence-scoring step in the
built-in reviewer.

---

## Severity Scale

Rank every surviving finding into one of four levels:

| | Level | Meaning |
|---|---|---|
| 🔴 | **Critical** | bug, security vulnerability, data-loss risk |
| 🟠 | **High** | correctness issue, missing test for a risky path |
| 🟡 | **Medium** | quality, maintainability, or type-design problem |
| 🟢 | **Low** | nit, style, optional simplification |

---

## Local Review Mode

### Phase 1 — GATHER

```bash
git diff --name-only HEAD
```

If no changed files, stop: "Nothing to review."

```bash
git diff HEAD
```

### Phase 2 — DISPATCH

Run the agents selected by **effort** (see *Effort → Dispatch*) in parallel against the diff.

### Phase 3 — DEDUPE & RANK

1. Group findings by file and line range.
2. Deduplicate overlapping findings (same location, same issue class).
3. Drop findings below the effort's confidence cutoff.
4. On `max`, run the verification pass.
5. Assign each survivor a 🔴/🟠/🟡/🟢 level.

### Phase 4 — REPORT

Output findings grouped by level, most severe first:

```
🔴 Critical — Short title
   path/to/file.ts:42
   Issue: one sentence. Why: impact. Fix: concrete change.
```

End with a count line: `🔴 1  🟠 2  🟡 3  🟢 0`

### Phase 5 — FIX *(only if `--fix`)*

See *Applying Fixes* below.

---

## PR Review Mode

### Phase 0 — PLATFORM DETECTION

Detect the host from the remote, then use the matching CLI (`gh` for GitHub, `glab` for GitLab)
in every later phase:

```bash
git remote get-url origin
```

- URL contains `github.com` (or `gh auth status` succeeds) → **GitHub** → use `gh`.
- URL contains `gitlab` (or `glab auth status` succeeds) → **GitLab** → use `glab`.

### Phase 1 — FETCH

| Input | GitHub | GitLab |
|---|---|---|
| Number (e.g. `42`) | use as PR number | use as MR IID |
| URL | extract `N` from `.../pull/N` | extract `N` from `.../merge_requests/N` |
| Branch name | `gh pr list --head <branch>` | `glab mr list --source-branch <branch>` |

**GitHub:**
```bash
gh pr view <NUMBER> --json number,title,body,author,baseRefName,headRefName,headRefOid,changedFiles
gh pr diff <NUMBER>
```

**GitLab:**
```bash
glab mr view <NUMBER>            # title, author, source/target branch, SHA
glab mr diff <NUMBER>
```

If the PR/MR is not found, stop with an error message. Keep the head SHA (`headRefOid` on GitHub,
the `sha`/diff_refs `head_sha` on GitLab) — `--comment` needs it.

### Phase 2 — CHECK READINESS

**GitHub:**
```bash
gh pr view <NUMBER> --json mergeStateStatus,statusCheckRollup
```

**GitLab:**
```bash
glab mr view <NUMBER>            # check "Pipeline" status and merge-conflict state
```

If CI/pipeline checks are red or there are merge conflicts, report and stop. Do not review a broken PR/MR.

### Phase 3 — DISPATCH

Run the agents selected by **effort** in parallel against the PR diff.

### Phase 4 — DEDUPE & RANK

Same as Local Review Phase 3.

### Phase 5 — DECIDE

| Condition | Decision |
|---|---|
| No 🔴/🟠, checks green | **APPROVE** |
| Only 🟡/🟢 | **APPROVE with comments** |
| Any 🟠 | **REQUEST CHANGES** |
| Any 🔴 | **BLOCK** |

### Phase 6 — REPORT

```
PR #<NUMBER>: <TITLE>
Decision: APPROVE | APPROVE with comments | REQUEST CHANGES | BLOCK

🔴 1  🟠 2  🟡 3  🟢 0

[findings grouped by level]

Next steps (GitHub):
  - gh pr review <NUMBER> --approve
  - gh pr review <NUMBER> --request-changes --body "<summary>"
Next steps (GitLab):
  - glab mr approve <NUMBER>
  - glab mr note <NUMBER> --message "<summary>"   # GitLab has no "request changes"; leave a note
```

### Phase 7 — ACT *(only if `--comment` and/or `--fix`)*

- `--comment` → *Posting PR Comments* below.
- `--fix` → *Applying Fixes* below (check out the branch first: `gh pr checkout <NUMBER>` on GitHub, `glab mr checkout <NUMBER>` on GitLab).

---

## Applying Fixes (`--fix`)

For every finding whose **Fix** is concrete and unambiguous — at any severity — apply it with
Edit/Write to the working tree. Skip subjective or ambiguous findings (e.g. "consider
restructuring") and list them under **Not auto-fixed**.

In PR Review Mode, check out the branch first so edits land in the right place:

```bash
gh pr checkout <NUMBER>      # GitHub
glab mr checkout <NUMBER>    # GitLab
```

After editing, print a summary:

```
Applied (4): file.ts:42 (🔴), file.ts:88 (🟠), util.ts:10 (🟡), util.ts:30 (🟢)
Not auto-fixed (1): service.ts:12 (🟠) — needs a design decision
```

Never `git commit` or `git push` — leave that to the user.

---

## Posting PR Comments (`--comment`)

Post each finding as an **inline comment** anchored to its file and line, plus one **summary
comment**. Use the head SHA so anchors resolve to the right commit. Pick the API for the detected
platform.

### GitHub — reviews API

One call creates the whole review (summary `body` + inline `comments`):

```bash
gh api --method POST repos/{owner}/{repo}/pulls/<NUMBER>/reviews --input - <<'JSON'
{
  "commit_id": "<headRefOid>",
  "event": "COMMENT",
  "body": "Code review — 🔴 1  🟠 2  🟡 3  🟢 0\n\n<one-line decision + summary>",
  "comments": [
    { "path": "path/to/file.ts", "line": 42, "body": "🔴 Critical — <title>\n<issue>. Fix: <change>." },
    { "path": "path/to/util.ts", "line": 10, "body": "🟡 Medium — <title>\n<issue>. Fix: <change>." }
  ]
}
JSON
```

- Resolve `{owner}/{repo}` with `gh repo view --json owner,name` or from the PR URL.
- `line` is the line in the file's new version (right side of the diff). For deletions or
  context-only comments, add `"side": "LEFT"` or a `start_line`/`line` range.

### GitLab — discussions API

GitLab needs the MR `diff_refs` (`base_sha`, `start_sha`, `head_sha`) and **one POST per inline
comment**, then a separate note for the summary. `<PROJECT>` is the URL-encoded path (e.g.
`group%2Frepo`); fetch the refs from the MR JSON first:

```bash
# diff_refs once:
glab api "projects/<PROJECT>/merge_requests/<NUMBER>" | jq .diff_refs

# one inline comment (repeat per finding):
glab api --method POST "projects/<PROJECT>/merge_requests/<NUMBER>/discussions" \
  -f body="🔴 Critical — <title>\n<issue>. Fix: <change>." \
  -f position[position_type]=text \
  -f position[base_sha]=<base_sha> \
  -f position[start_sha]=<start_sha> \
  -f position[head_sha]=<head_sha> \
  -f position[new_path]=path/to/file.ts \
  -f position[new_line]=42

# summary note:
glab mr note <NUMBER> --message "Code review — 🔴 1  🟠 2  🟡 3  🟢 0
<one-line decision + summary>"
```

- For deleted/context lines use `position[old_path]` + `position[old_line]` instead of the `new_*` pair.

### Both platforms

- If a finding's line is not part of the diff, fold it into the **summary** instead of an inline
  comment (both APIs reject inline comments outside the diff).
- Without `--comment`, PR Mode only prints the report and the suggested `gh`/`glab` next-steps.

---

## Confidence Rule

Surface only findings at or above the effort's confidence cutoff. Calibrate severity honestly:
🟢/🟡 for suggestions, 🟠 for real correctness/test gaps, 🔴 only for bugs, security, or data loss.
Default invocation (`/code:review`, no args) = Local Mode, all 7 agents, ≥ 80, report only.
