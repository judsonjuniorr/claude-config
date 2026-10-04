---
name: design
description: >-
  (herow) Turn any prompt into a finished graphic image — social post, blog cover, banner,
  thumbnail, OG image, poster, flyer, invite, slide visual — built by Claude itself as
  typographic HTML/CSS/SVG with the user's brand, on a Claude Design canvas by default
  (shareable Artifact page or an exact-size PNG via headless Playwright on request or
  fallback). Use when the user says "make/create an image, post, cover, banner, thumbnail,
  OG image, poster, flyer", "crie uma arte/capa/post/banner", or names a size like
  1080x1350. Not for photoreal or AI-generated imagery (→ /imagine), not for reviewing an
  existing UI (→ design-review), not for building app or site pages (→ design-html).
---

# Design

Make any image from a prompt with Claude's own tools: graphic design (type, layout,
color, flat SVG illustration), never a raster AI. Two contrasting directions, the user
picks, then iterate. Size presets, the brand profile template, direction pairs, and the
PNG render recipe live in [reference.md](reference.md).

`$STORE` below is `${HEROW_HOME:-$HOME/.herow}/design`.

## Step 1 — Parse the prompt

Pull out: **format/purpose**, **size**, **copy** (the exact text to show), **brand**, and
any **engine hint** ("PNG", "file", "link", "canvas"). Ask with `AskUserQuestion` only for
what is missing — size and brand are the usual gaps; batch them in one card.

- Copy is the user's: never invent dates, prices, names, or claims. A missing fact is a
  question, not a placeholder.
- Photoreal or AI-art asks ("a photo of…", "realistic", "illustration in the style of a
  painter") → say this skill does graphic design and point to `/imagine`; stop unless the
  user wants a graphic version instead.

## Step 2 — Resolve the size

Match the format to the presets table in `reference.md` (IG portrait 1080×1350 when
"Instagram post" has no ratio). Custom `W×H` is fine. Note the safe margin for that format.

## Step 3 — Resolve the brand

```bash
ls "${HEROW_HOME:-$HOME/.herow}/design/brands/" 2>/dev/null
```

- **Profile exists** → `Read` it. If `verified:` is older than 90 days and it has a
  `source_url`, offer to re-check it (Step 3a) before using it.
- **No profile** → ask: *extract from a live URL* (3a) · *paste tokens* (write them into the
  template) · *use the account design system* (on the canvas path, run Step 5's quickstart
  now and offer this only if it lists one; reuse that result in Step 5) ·
  *no brand* (pick a palette and fonts that fit the topic; don't save a profile).
- New profiles are written to `$STORE/brands/<slug>.md` from the template in
  `reference.md`, with `verified:` set to today.

**Step 3a — extract from a URL** with `mcp__playwright-headless__*`: `browser_navigate` to
the URL, then `browser_evaluate` to read computed `font-family` of `h1`/`body`,
`background-color`/`color` of `body`, the primary button/link colors, and the header logo
`<svg>` `outerHTML` (or its `<img>` `src`). Convert colors to OKLCH, show the user the
token table, and save on confirmation. Never guess a token the page didn't give you.

**The logo is locked:** paste the SVG verbatim, scale only via `width`/`height` keeping its
ratio, never recolor, crop, redraw, or substitute a monogram. No logo in the profile → no
logo in the image (ask if the user expects one).

## Step 4 — Choose the engine

| Engine | When |
|---|---|
| **Design canvas** (default) | Every request unless a row below applies |
| **Artifact page** | User wants a shareable link, an interactive/animated piece, or a page to review with others |
| **PNG (Playwright)** | User asks for a file/PNG, needs it with no manual export, the canvas fails, or a batch of images |

## Step 5 — Build two directions

Pick a contrasting pair from the direction table in `reference.md` and design both at the
exact `W×H`, using only brand tokens, brand fonts (Google Fonts only), and the locked logo.
Keep all text inside the safe margin. Copy is identical in both; only layout and treatment
differ.

**Design canvas**
1. `Artifact` `action:"quickstart"`, `intent:"design"`. Use the `type_url` and design
   systems it returns — never a hardcoded URL.
2. Publish with that `type_url`, a short `title` (e.g. `Culto Jovens — IG post`), no files,
   `auto_open:"after_first_write"`.
3. Follow the instructions in the create result — they are authoritative and change by
   release. Today the content is files under `project/`: `canvas.json` (index, one
   `boards` entry per artboard at `w:W, h:H`) plus one `.dc.html` per direction
   (`Main.dc.html` = A, `B.dc.html` = B), root fixed at `W×H`, brand fonts via a Google
   Fonts `<link>` in `<helmet>`, logo as inline `<svg>`, copy as literal markup.
4. The type forbids render-checking the canvas yourself, and a canvas can publish fine yet
   open read-only (seen in arauto: `window.claude.self` absent). So after publishing, ask
   with `AskUserQuestion`: *both artboards render and Export works* · *broken/read-only*.
   Broken → say so in one line and rebuild the same two directions on the **PNG** path.
5. On success, the user exports the chosen artboard as PNG from the canvas.

If the publish itself is refused (no permission, missing runtime), go straight to **PNG** —
never stop the run.

**Artifact page** — `Artifact` `action:"quickstart"`, `intent:"other"`, follow its result,
then publish one HTML page showing both directions side by side at true size (scaled to fit
with CSS `transform`, labeled A/B).

**PNG** — follow the render recipe in `reference.md`. Output goes to the path the user gave,
else `./design-out/<slug>-a.png` and `-b.png`, with the source `.html` beside each.

## Step 6 — Self-check before showing

- PNG: `sips -g pixelWidth -g pixelHeight <file>` reports exactly `W×H` (screenshot with `scale:"css"`).
- Logo present (when the profile has one) and byte-identical to the profile's SVG.
- Only token colors (plus white/black tints of them); fonts actually loaded
  (`document.fonts.check`), no fallback serif/sans.
- No text outside the safe margin, nothing clipped, no overlap.
- No placeholder or invented copy.

Fix and re-render anything that fails before the user sees it. On the canvas path, check
the source only (sizes, tokens, logo, copy) — never render it.

## Step 7 — Pick and iterate

Show both (canvas/page URL, or the PNG paths — `Read` the PNGs to look at them yourself
first). `AskUserQuestion`: **A** · **B** · **mix** (say what to take from each). Apply
feedback to the chosen direction on the same engine and the same file/URL, re-running
Step 6 each round, until the user accepts.

Finish with one line: the final URL or file path, the size, and the brand profile used.
