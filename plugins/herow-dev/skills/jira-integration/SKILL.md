---
name: jira-integration
description: (herow) Use this skill when retrieving Jira tickets, analyzing requirements, updating ticket status, adding comments, or transitioning issues. Provides Jira API patterns via MCP or direct REST calls.
model: sonnet
effort: medium
---

# Jira Integration Skill

Retrieve, analyze, and update Jira tickets directly from your AI coding workflow. Supports both **MCP-based** (recommended) and **direct REST API** approaches.

> Setup (MCP server config, API tokens, env vars), the MCP tools table, REST `curl`
> examples, comment templates, and troubleshooting live in `reference.md` **in this
> skill's directory** — read it when you need them.

## When to Activate

- Fetching a Jira ticket to understand requirements
- Extracting testable acceptance criteria from a ticket
- Adding progress comments to a Jira issue
- Transitioning a ticket status (To Do → In Progress → Done)
- Linking merge requests or branches to a Jira issue
- Searching for issues by JQL query

## Choosing the approach

1. If `jira_*` MCP tools are available in the session, use them (`jira_search`, `jira_get_issue`, `jira_add_comment`, `jira_transition_issue`, …).
2. Otherwise use the Jira REST API v3 via `curl` with `$JIRA_URL`, `$JIRA_EMAIL`, `$JIRA_API_TOKEN` from the environment — exact commands in `reference.md`. Validate the variables are set before calling; fail fast with a clear message.
3. Always fetch available transitions before transitioning — transition IDs vary per project workflow.

## Analyzing a Ticket

When retrieving a ticket for development or test automation, extract:

1. **Testable requirements** — functional requirements, acceptance criteria, testable behaviors, user roles, data requirements, integration points.
2. **Test types needed** — unit, integration, E2E, API.
3. **Edge cases & error scenarios** — invalid inputs, unauthorized access, network failures, race conditions, boundary conditions, missing/null data, state transitions.
4. **Structured output** — use the analysis template in `reference.md` (ticket, requirements, acceptance criteria checklist, test scenarios, test data, dependencies).

## Updating Tickets

Update as you go, not all at once at the end. Comment templates in `reference.md`.

| Workflow Step | Jira Update |
|---|---|
| Start work | Transition to "In Progress" |
| Tests written | Comment with test coverage summary |
| Branch created | Comment with branch name |
| PR/MR created | Comment with link, link issue |
| Tests passing | Comment with results summary |
| PR/MR merged | Transition to "Done" or "In Review" |

## Security Guidelines

- **Never hardcode** Jira API tokens in source code or skill files — environment variables or a secrets manager only
- **Add `.env`** to `.gitignore`; rotate tokens immediately if exposed in git history
- **Use least-privilege** API tokens scoped to required projects

## Best Practices

- Keep comments concise but informative; link rather than copy (PRs, test reports, dashboards)
- Use @mentions if you need input from others
- Check linked issues to understand full feature scope before starting
- If acceptance criteria are vague, ask for clarification before writing code
