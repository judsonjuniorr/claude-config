# /validate-ui

Audits UI/UX against a **consolidated** set of guidelines — Vercel's **Web Interface Guidelines** as the base, plus the `frontend-design`, `ui-ux-pro-max`, and `ui-design-system` skills (davila7/claude-code-templates). Fetches the rules fresh on every run, consolidates them, audits the target files statically, validates on screen when given a URL or dev server, and reports a terse prioritized report. **Read-only — never edits files.**

See [`validate-ui.md`](./validate-ui.md) for the full agent-facing procedure.

## What it does

1. Fetches all 4 sources fresh (never cached) via `WebFetch`: Vercel `web-interface-guidelines` (mandatory base — stops if it fails) + `frontend-design`, `ui-ux-pro-max`, and `ui-design-system`. If one of the 3 secondary sources fails, it warns and continues.
2. Consolidates everything into a single ruleset: Vercel as the a11y/focus/forms base; Pro Max for thresholds (contrast 4.5:1, touch 44px, transitions 150–300ms, breakpoints) and checklist; Design System for token consistency; Frontend Design for anti-generic aesthetics.
3. Determines the files to audit from the argument (path/glob/URL) or, when empty, `Glob`s common UI files and lists what it found.
4. Detects the stack (`package.json`/imports) and fetches the lib/framework's official best practices via **Context7** (React, Next.js, Vue, Tailwind, etc.), folding them into the rules. If undetectable or no docs exist, proceeds without it.
5. Consolidated static audit: accessibility/ARIA, semantic HTML, visible focus, keyboard, forms, headings, touch & interaction, reduced-motion, light/dark contrast, responsive layout, performance, token consistency, anti-generic aesthetics, and UX.
6. Opportunistic live validation: starts/uses a dev server or navigates the URL with a headless browser to check focus, contrast, touch targets, and reduced-motion on screen — shuts the server down at the end.
7. Reports in the `file:line — [SEVERITY] rule: description → how to fix` format, grouped by file, with a SUMMARY and the top-5 priorities.

## Frontmatter

- **description**: Audit UI/UX against the Vercel Web Interface Guidelines (accessibility, focus, forms, animation, performance, semantics).
- **argument-hint**: `<file-or-glob-pattern | url>`
- **allowed-tools**: WebFetch, Read, Glob, Grep, Bash, mcp__playwright-headless, mcp__context7

## Usage

```
/validate-ui
/validate-ui src/components/Button.tsx
/validate-ui "src/**/*.tsx"
/validate-ui http://localhost:3000
```

## When to use

- Before opening a UI PR, to catch accessibility and UX violations.
- To audit a specific component or page against the Vercel standard.
- To check visible focus, contrast, and touch targets on screen, not just in code.

## Notes

- **Never edits files.** `allowed-tools` does not include `Write`/`Edit` — the output is the report only. To apply fixes, ask afterward.
- The rules are always fetched fresh from the official repositories; if the fetch fails, the command stops instead of guessing.
- `Bash` is used only to detect/start the dev server and locate files.
- Prefers the `playwright-headless` MCP server (no window) for on-screen validation.
- Uses the `context7` MCP server to pull the detected lib/framework's best practices (optional — skips if absent).
