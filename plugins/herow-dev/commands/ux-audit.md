---
description: (herow) Walk a live user flow with Playwright MCP as a real user and deliver a complete, detailed document on what to improve and how to improve the flow's usability — with an optional fix-and-verify loop.
argument-hint: <task scenario / user flow> [url] [--quick|--deep] [--fix]
allowed-tools: Bash, Read, Write, Glob, Grep, mcp__playwright-headless, mcp__playwright
effort: high
---

# UX Audit

Walk a live app **as a real user performing a specific task** — typing, clicking, watching results — not a static code read. A result without real interaction (typed input, triggered action, observed outcome) is not a pass; it's `Incomplete`.

**The deliverable is a document, not a badge.** The output of this command is a complete, detailed write-up of what's wrong with the informed flow and exactly how to fix it — a plan a developer or designer can pick up and act on. The interaction manifest, hard gates, and verdict in the steps below exist to keep that document honest (proof a real walkthrough happened, not a guess dressed up as a report) — they are not themselves the point of the exercise.

## STEP 1 — Parse `$ARGUMENTS`

- **Task scenario / user flow** (required). Free text describing the job, e.g. "sign up, add a payment method, and complete checkout" or "create a new patient and book them for surgery." If missing, ask: *"What's the user flow to audit? Describe it like a support ticket — the task, not the screens."*
- **URL** — the first `http://`/`https://` token in `$ARGUMENTS`, if present.
- **Depth flag**:
  - `--quick` — walkthrough + hard gates only (console/network/layout), single viewport, ~5 min.
  - `--deep` — adds the responsive sweep (375/768/1024/1920), axe-core + perf budget, and the Phase 5 stress passes.
  - default (**Standard**, no flag) — walkthrough + hard gates + axe-core + perf on one representative route, plus a quick 375px check.
- `--fix` — after the document, patch Critical/High findings and re-verify (STEP 8). Without it, still *offer* the loop at the end.

If no URL was given: look for a running dev server (`package.json` `dev`/`start` script + `lsof -i :PORT` on common ports — 3000, 5173, 8080, 4321, 8000) or a deployed URL in `CLAUDE.md`/`README.md`. Ask if neither resolves.

## Ground rules

- **Browser tool: Playwright MCP only.** Default to `mcp__playwright-headless__*`. If the flow needs a real login session, 2FA, or a CAPTCHA that headless can't clear, stop and tell the user: *"This needs headed Playwright — run `~/.claude/mcp-restore.sh playwright`, restart, and I'll use `mcp__playwright__*`."* Never fall back to a Chrome extension/CDP tool.
- **Drive it yourself, in this session.** Don't delegate the walkthrough to a sub-agent — it starts cold and misses state built up across steps (what was typed, what the console already showed).
- **Interaction-first.** A button "having an onClick" is not evidence it works. Click it, watch the network log, watch the DOM, watch the console.
- **Never round up.** No reproduction + evidence + suspected `file:line` = the finding is dropped, not published as a vague "consider improving X." No manifest = the verdict is `Incomplete`, not Pass, even if everything you saw looked fine.

## STEP 2 — Persona + capability check

1. **Lock a persona.** If the user didn't give one, ask once: *"Who's doing this task, and how comfortable are they with software?"* Default if declined: "first-time user, moderate tech comfort, mildly distracted, wants to finish and move on." Write it at the top of the report — every finding must be defensible from this persona's eyes, not "a developer would know...". Regardless of the locked persona, also apply the **first-time-user lens** below — it's the single biggest blind spot for internal/AI-built tooling.
2. **Capability check** — one `browser_navigate`, one `browser_snapshot`, one `browser_console_messages` call before starting. If any fails, stop and fix the connection; an audit blind to the console is worthless.
3. **Viewport** — `browser_resize` to 1440×900 as the baseline. `--deep` (or Standard, for the final check) additionally sweeps 375px.

## STEP 3 — Interaction Manifest (mandatory, log as you go)

This is what separates a real audit from a vibe check. Required per screen touched in the flow:

- ≥ 1 real value typed into an input (`browser_type`) — not just clicked
- ≥ 1 primary action triggered (submit / save / send / confirm) via `browser_click`
- ≥ 1 console read (`browser_console_messages`) immediately after the primary action
- ≥ 1 screenshot before **and** after the primary action (`browser_take_screenshot`)
- Verification of the expected post-action state (input cleared, toast shown, route changed, list updated) — via `browser_snapshot` or a targeted `browser_evaluate`

```
INTERACTION MANIFEST — <flow name>
 [✓] 14:32:01 Typed "..." into <selector>
 [✓] 14:32:03 Clicked <label> (<selector>)
 [✓] 14:32:04 Console read: 0 errors, 0 warnings
 [✓] 14:32:05 Verified <expected post-action state>
 [✓] Screenshots: before.png, after.png
```

Fabricated or batch-timestamped entries (gaps < 0.5s between steps) mean the walkthrough was rushed, not real — treat that as `Incomplete`, don't paper over it.

## STEP 4 — Walk the flow

Start from the app's real entry point (not mid-flow — a real user lands at `/` or `/login`, not on step 3 of your task). At each screen:

**Screen checklist** — first impression orients me / findable in ≤3 clicks / labels make sense to a first-timer / primary action is visually obvious / form validation is immediate and field-specific / every action gets feedback (toast, state change) / errors are recoverable / destructive actions are guarded and styled distinctly from safe ones.

**Visual scan** (screenshot + eyeball — catches what "works" but looks broken): clipped or truncated text, elements overlapping (sidebar over content, modal under nav), unexpected horizontal scroll, misaligned grid/cards, poor contrast especially in dark mode, invisible elements (same color as background), inconsistent spacing, touch targets < 44×44px.

**Track the cost**: click count, decision points (moments you stop and think), dead ends, and whether state survives an interruption (navigate away or refresh mid-form — did it recover or silently lose input?).

**First-time-user lens** (always): could someone complete this with zero prior context — no source, no docs, no tribal knowledge? Flag internal vocabulary leaking into labels (`agentClass`, `webhook_id`, raw enum values), pickers showing IDs instead of meaning, required fields with no sensible default, settings you'd click "Skip" on because you don't understand them.

At the end of the flow, answer as the persona: *Did it end clearly? Would I come back? What's the one change that would make this twice as easy?*

## STEP 5 — Hard gates (mandatory, auto-fail if red)

| Gate | Threshold | Severity |
|---|---|---|
| Console errors during the walkthrough | > 0 | Critical |
| Console warnings during the walkthrough | > 0 | High |
| Network 5xx | > 0 | Critical |
| Network 403/404 on pages that should already be authenticated | > 0 | High |
| Layout collapse / overlap at any tested viewport | > 0 | High |
| axe-core Critical violations (below) | > 0 | Critical |
| axe-core Serious violations | > 0 | High |
| LCP on the representative route | > 4.0s | High |
| CLS on the representative route | > 0.25 | High |

There is no "Medium console warning" — a console warning is High *at minimum*, a 5xx is Critical *automatically*.

**Accessibility (axe-core)** — skip under `--quick`. Otherwise, inject once per page via `mcp__playwright-headless__browser_evaluate`:

```js
if (!window.axe) {
  await new Promise((resolve, reject) => {
    const s = document.createElement('script')
    s.src = 'https://cdnjs.cloudflare.com/ajax/libs/axe-core/4.10.0/axe.min.js'
    s.onload = resolve; s.onerror = reject
    document.head.appendChild(s)
  })
}
const r = await window.axe.run()
r.violations.map(v => ({ id: v.id, impact: v.impact, help: v.help, nodes: v.nodes.length }))
```
Map axe `impact` → severity: `critical`→Critical, `serious`→High, `moderate`→Medium, `minor`→Low.

**Performance** — skip under `--quick`. One representative route only (the page real users hit most, not every page). Use `browser_evaluate` with `performance.getEntriesByType('paint'|'largest-contentful-paint'|'layout-shift')` to pull LCP and CLS. These are pragmatic app-interior thresholds, not a marketing-page Core Web Vitals bar — don't hold an internal dashboard to the same standard as a landing page.

## STEP 6 — Stress passes (`--deep` only)

Run whichever apply to the flow, one line each in the report:

1. **Interrupted workflow** — start the task, navigate away or refresh mid-form. State survives?
2. **Wrong-turn recovery** — deliberately click the wrong thing. How many steps to recover?
3. **Keyboard only** — repeat the flow with Tab/Enter/Escape only. Focus visible at every stop? Logical order? Escape closes modals?
4. **Heavy data** — if the flow touches a list/table, does it hold up at 100+/1000+ rows (virtualization, search, pagination)?
5. **Destructive confidence** — for any delete/send/publish/pay step: is the confirmation copy specific, styled as dangerous, and is there an undo? **Ask the user before actually triggering a real destructive action.**
6. **Round-trip integrity** — for any A→B→A flow (list → detail → back), does A reflect the change made on B without a manual refresh? This is the single biggest "the app looks empty when I go back" bug source.

## STEP 7 — Write the improvement document

Write to `docs/ux-audit-<YYYY-MM-DD>-<flow-slug>.md` (get the date via `Bash`: `date +%F`). Write incrementally as you go through Steps 4-6 — don't try to reconstruct everything from memory at the end. The document has five required sections, in order. Every one of them must exist and have real content; a document missing a section is incomplete, not done.

### 1. Executive Summary (3-5 sentences)

Plain language, no jargon. What flow was tested, as whom. The overall state of the experience. The two or three things that matter most. The single highest-leverage change — the one fix that, if nothing else got done, would move the needle most.

### 2. Health Snapshot (compact — proof, not the point)

```
VERDICT: <Pass / Conditional Pass / Fail / Incomplete>
Persona: <locked persona, one line>
Flow: <the task scenario audited>
Depth: <quick / standard / deep>
Hard gates: console errors [N] · warnings [N] · network 5xx [N] · 403/404 [N] · layout collapse [N] · axe Critical [N] · axe Serious [N]
Performance (/<route>): LCP [N]s · CLS [N]
Findings: Critical [N] · High [N] · Medium [N] · Low [N]
```

Verdict is exactly one of:
- **Pass** — hard gates all green, Interaction Manifest complete, Critical = 0, High = 0.
- **Conditional Pass** — hard gates green, Critical = 0, High = 0, but Medium/Low findings exist.
- **Fail** — any Critical/High finding or a red hard gate.
- **Incomplete** — the manifest is missing required entries, or a phase was skipped without saying so. Never round this up to Pass because "it looked fine."

### 3. What to Improve, and How (the core of the document — one entry per finding, ranked by impact)

Every finding answers both halves — what's broken AND the concrete plan to fix it. A finding with only the "what" is a bug report, not an improvement document; write the "how" with the same care.

```
[severity-letter+N] Title
Surface: <route/screen>                    Persona: <who>
What's wrong: <the problem, in plain language, from the persona's point of view>
Why it matters: <the UX cost — confusion, lost trust, a stalled task, an abandoned flow — tied to this persona, not a generic "bad practice" citation>
Reproduce: 1. ... 2. ... 3. ...
Evidence: <screenshot path(s)> · <console/network excerpt>
Suspected location: <file:line>
How to fix it: <the concrete change — specific enough to hand to a developer. If there's a genuine tradeoff between two reasonable approaches, name both and recommend one; don't hide the decision.>
Effort: <S (hours) / M (a day or two) / L (needs its own plan)>
```

No reproduction + evidence + suspected `file:line` = the finding is dropped, not published as a vague "consider improving X." "How to fix it" must be committable, never "consider" or "improve" or "look into."

### 4. Improvement Roadmap (how to sequence the work)

Group every finding from Section 3 into exactly one bucket — this is what turns a findings list into an actionable plan:

- **Quick Wins** — Effort S/M, ship this week. Copy fixes, single-component changes, CSS/token tweaks.
- **Structural** — Effort L, or touches multiple files/routes/shared components. Needs its own scoped piece of work.
- **Advanced Polish** — real but lowest-leverage: micro-interactions, edge-case refinement, nice-to-haves that don't block the task.

### 5. Hold This In Your Hands (closing paragraph)

**One paragraph, no bullets, no template.** If this flow were a physical object, would you want to hand it to someone? What's it like to actually live with, not just complete once. This is the one place a holistic judgment call is the point — don't hedge it into a checklist.

## STEP 8 — Fix-and-verify

If `--fix` was passed, or the user says yes when you ask *"Found N Critical and M High. Fix and re-verify now?"*:

1. Group findings by file.
2. Patch each one.
3. Re-walk only the affected step(s) of the flow — same interaction, fresh screenshot + console read. Don't re-run the whole flow.
4. Update the report inline: `✓ fixed`, `✗ still present`, or `⚠ new issue introduced`.
5. Close with a one-line summary of what shipped this session vs what's deferred.

## Autonomy

- **Just do it**: navigate, click, type test data, screenshot, read console/network, inject axe, write the report file.
- **Ask first**: real destructive actions (delete/send/pay/publish), even when running Destructive Confidence.
- **Stop and confirm**: anything that would email/notify a real external person.
