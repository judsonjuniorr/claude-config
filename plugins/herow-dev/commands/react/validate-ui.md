---
description: (herow) Audit UI/UX against the Vercel Web Interface Guidelines (accessibility, focus, forms, animation, performance, semantics).
argument-hint: <file-or-glob-pattern | url>
allowed-tools: WebFetch, Read, Glob, Grep, Bash, mcp__playwright-headless, mcp__context7
model: sonnet
effort: medium
---

# Validate UI

> **AUDIT ONLY.** This command NEVER edits files — it only reads, fetches the official rules, and reports. If the user wants fixes, they ask afterward. `Bash` is used solely to detect/start a dev server and locate files; never to modify source.

Audits the UI files in `$ARGUMENTS` against a **consolidated** set of UI/UX guidelines, fetches the rules fresh on every run, validates on screen when possible, and produces a terse prioritized report.

## STEP 1 — Fetch the up-to-date rules (all sources)

`WebFetch` **every** source below (always `raw.githubusercontent.com` — do not use GitHub `blob` URLs):

1. **Web Interface Guidelines (Vercel)** — primary source for accessibility, focus, forms, and interaction:
   `https://raw.githubusercontent.com/vercel-labs/web-interface-guidelines/main/command.md`
2. **Frontend Design** — anti-generic aesthetic direction (distinctive typography, color, motion, composition):
   `https://raw.githubusercontent.com/davila7/claude-code-templates/main/cli-tool/components/skills/creative-design/frontend-design/SKILL.md`
3. **UI/UX Pro Max** — tiered rules (CRITICAL→LOW) and pre-delivery checklist:
   `https://raw.githubusercontent.com/davila7/claude-code-templates/main/cli-tool/components/skills/creative-design/ui-ux-pro-max/SKILL.md`
4. **UI Design System** — consistency via design tokens (color, typography, 8pt spacing, shadows, animation):
   `https://raw.githubusercontent.com/davila7/claude-code-templates/main/cli-tool/components/skills/creative-design/ui-design-system/SKILL.md`

Fetch rules:
- Always fetch **fresh** on every run — do not reuse a cached copy or rules from memory.
- If **source 1 (Vercel)** fails: **warn and stop** — it is the mandatory base of the audit; do not substitute it with assumptions.
- If one of sources 2–4 fails: **warn which one failed and continue** with the rest (do not invent the missing source's content).

## STEP 1b — Consolidate the strategy

Before auditing, merge the sources into **a single ruleset**, without duplication and resolving overlaps:

- **Vercel = base** for accessibility/focus/keyboard/forms/interaction. On any detail conflict, Vercel wins.
- **UI/UX Pro Max** supplies the **concrete thresholds** (contrast ≥ 4.5:1, touch target ≥ 44×44px, transitions 150–300ms, breakpoints 375/768/1024) and the pre-delivery checklist (visible focus rings, `cursor-pointer` on clickables, hover with no layout shift, no emoji as icons, descriptive alt, `label for`, tab order = visual order, readable light/dark).
- **UI Design System** supplies the **token-consistency** axis (color/typography/spacing on the 8pt grid/shadows/animation centralized — flag magic values and hardcoded values that should be tokens).
- **Frontend Design** supplies the **anti-generic aesthetic** axis (typography/color/layout without an "AI default" look: avoid Inter/Arial/system as the only choice, cliché purple gradients, predictable layout; value a clear differentiator).
- Map each rule to a severity (see STEP 4): accessibility/touch → tends to `CRITICAL`; performance/responsive layout → `HIGH`; typography/animation/style → `MEDIUM`; data/charts and aesthetic refinement → `LOW`/`MEDIUM`.

## STEP 2 — Determine the files to audit

- Use `$ARGUMENTS` as a file path or glob pattern (or a URL — see STEP 3b).
- If `$ARGUMENTS` is **empty**, `Glob` the common UI files and **list what you found before auditing**:
  - `src/**/*.{tsx,jsx,vue,svelte,html,css}`
  - Fallbacks when `src/` does not exist: `app/**/*.{tsx,jsx,vue,svelte}`, `components/**/*.{tsx,jsx,vue,svelte}`, `**/*.{html,css}`
- If nothing is found, warn and stop.

## STEP 2b — Lib/framework best practices (Context7)

Identify the stack in use and fetch its specific guidelines via Context7, adding them to the consolidated ruleset from STEP 1b:

1. **Detect the stack** — read `package.json` (deps), or infer from the imports/extensions of the STEP 2 files: React, Next.js, Vue, Svelte, Angular, Tailwind, Chakra/MUI/shadcn, etc.
2. For each relevant UI framework/lib, use `mcp__context7__resolve-library-id` (with the name, e.g. "next.js", "tailwindcss") and then `mcp__context7__query-docs` with a focused question — e.g. *"accessibility, semantic markup, focus management and UI best practices"* or *"recommended patterns for accessible forms"*. Use the versioned ID when the version is in `package.json`.
3. Fold the lib's official recommendations into the rules to audit (e.g. `next/image` for images, `next/link` for navigation, the lib component's accessibility guidance).
4. If Context7 returns nothing useful or the lib is undetectable, **proceed without it** — do not block the audit.

## STEP 3a — Static audit (always)

Read each file with `Read` and check against the **consolidated ruleset** from STEP 1b **plus** the lib/framework best practices from STEP 2b. Minimum coverage:

- **Accessibility / ARIA** — roles, labels, `aria-*`, accessible names, landmarks, descriptive alt on images.
- **Semantic HTML** — `<button>` vs clickable `<div>`, `<nav>`/`<main>`/`<header>`, correct lists and tables.
- **Visible focus** — no `outline: none` without a replacement; `:focus-visible`; focus ring on every interactive element.
- **Keyboard navigation** — tab order = visual order, no focus traps, keyboard handlers on interactive elements.
- **Forms** — `label` associated via `for`, `autocomplete`, `name`, correct input types, associated error messages.
- **Heading hierarchy** — one `h1`, no skipped levels.
- **Touch & interaction** — touch target ≥ 44×44px and spacing; `cursor-pointer` on clickables; hover with **no** layout shift.
- **Animation** — respects `prefers-reduced-motion`; micro-interactions at 150–300ms.
- **Contrast** — text/background ≥ 4.5:1, disabled states, **readable in light and dark mode** (borders and glass distinguishable in both themes).
- **Responsive layout** — works at 375/768/1024px; nothing hidden behind fixed elements.
- **Performance** — sized/lazy images, avoid layout shift, no heavy work in render.
- **Consistency / tokens** (UI Design System) — color, typography, spacing (8pt grid), shadows, and animation coming from centralized tokens/variables; flag magic values and hardcoded values that should be tokens.
- **Anti-generic aesthetic** (Frontend Design) — avoid an "AI default" look: typography limited to Inter/Arial/system only, cliché purple gradients, predictable cookie-cutter layout, emoji used as icons (prefer SVG from a consistent set); value a clear differentiator.
- **UX** — loading/error/empty states, action feedback.

## STEP 3b — Live validation (opportunistic)

Trigger on-screen validation when **any** condition is true:

- `$ARGUMENTS` contains a URL (`http://` or `https://`); **or**
- A dev server is detectable — `package.json` with a `dev`, `start`, or similar script.

Procedure:

1. **URL provided:** navigate directly with `mcp__playwright-headless__browser_navigate`.
2. **Local dev server:** start it via `Bash` in the background (e.g. `npm run dev`), wait for the port to come up, then navigate.
3. Validate on screen what is hard to verify statically:
   - **Real visible focus** — `mcp__playwright-headless__browser_press_key` with repeated `Tab`, confirming a visible indicator at each stop.
   - **Accessibility tree** — `mcp__playwright-headless__browser_snapshot`.
   - **Contrast and touch targets** — `mcp__playwright-headless__browser_take_screenshot`.
   - **Reduced-motion** — animation behavior.
4. **Shut the dev server down** at the end (kill the background process).
5. If none of this is possible (no URL and no dev script), warn **"live validation skipped"** and proceed with the STEP 3a result only.

## STEP 4 — Report

Use the terse format, **grouped by file**:

```
file:line — [SEVERITY] rule: description of the problem → how to fix
```

- **Severities:** `CRITICAL`, `HIGH`, `MEDIUM`, `LOW`.
- Each violation cites the corresponding rule from STEP 1.

At the end, produce a **SUMMARY**:

1. Total violations per severity (`CRITICAL: N · HIGH: N · MEDIUM: N · LOW: N`).
2. Prioritized list of the **5 most important items** to fix first.

**Do not modify any file.** Only report. If the user wants the fixes applied, they ask afterward.
