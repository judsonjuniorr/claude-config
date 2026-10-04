# Design — reference

## Size presets

| Format | W×H | Safe margin |
|---|---|---|
| Instagram post, portrait (default "IG post") | 1080×1350 | 6% |
| Instagram / generic square | 1080×1080 | 6% |
| Story / Reels / TikTok cover | 1080×1920 | 14% top/bottom, 6% sides (UI overlays) |
| Blog cover / 16:9 hero | 1600×900 | 6% |
| Open Graph / link preview | 1200×630 | 8% (platforms crop edges) |
| Slide / YouTube thumbnail | 1920×1080 · 1280×720 | 5% |
| X / Twitter header | 1500×500 | 20% sides at small widths, avatar zone bottom-left |
| LinkedIn post | 1200×1200 | 6% |
| A4 poster/flyer (print preview) | 2480×3508 | 5% |

Custom `W×H` → 6% margin unless the user says otherwise.

## Brand profile template

Saved at `${HEROW_HOME:-$HOME/.herow}/design/brands/<slug>.md`. Never commit a profile to a
plugin repo.

````markdown
---
name: <Brand name>
source_url: <https://… or empty>
verified: <YYYY-MM-DD>
---

## Tokens

| Role | Value |
|---|---|
| bg | oklch(…) |
| surface | oklch(…) |
| text | oklch(…) |
| primary | oklch(…) |
| primary-dark | oklch(…) |
| accent | oklch(…) |
| glow | oklch(…) |

## Fonts

- Display: <family> <weights> — <Google Fonts css2 URL>
- Body: <family> <weights> — <Google Fonts css2 URL>

## Logo (locked)

Aspect ratio <w:h>. Scale only; never recolor, crop, or redraw. Wordmark: <text + font, or none>.

```svg
<svg …verbatim…></svg>
```

## Notes

<voice, do/don't, recurring motifs>
````

Leave a row out rather than guess it.

## Direction pairs

Pick the pair that best fits the brief so A and B differ in kind, not just color.

| A | B |
|---|---|
| Asymmetric, headline flush-left, big negative space | Centered, stacked, framed |
| Type-led: oversized headline is the image | Illustration-led: flat SVG motif carries it, short headline |
| Light ground, colored type | Dark/primary ground, light type |
| Editorial: eyebrow + serif headline + italic subtitle | Poster: one bold word/number, details small |
| Grid of info blocks (events, lists) | Single focal statement + footer with details |

Flat SVG illustrations: simple geometric shapes in token colors, no gradients-for-depth,
no stock-photo mimicry.

## PNG render recipe (headless Playwright)

1. Write each direction as a self-contained HTML file: `<meta charset>`, Google Fonts
   `<link>`, inline CSS/SVG, `html,body{margin:0;width:Wpx;height:Hpx;overflow:hidden}`.
2. Serve the output dir on a free port (localhost; `file://` may be blocked):
   ```bash
   PORT=$(python3 -c 'import socket;s=socket.socket();s.bind(("",0));print(s.getsockname()[1])')
   python3 -m http.server "$PORT" --bind 127.0.0.1 --directory <out> >/dev/null 2>&1 & echo "$PORT $!"
   ```
3. `mcp__playwright-headless__browser_resize` → `width:W, height:H`.
4. `mcp__playwright-headless__browser_navigate` → `http://127.0.0.1:$PORT/<slug>-a.html`.
5. `mcp__playwright-headless__browser_evaluate` →
   `async () => { await document.fonts.ready; return [...document.fonts].filter(f => f.status === 'loaded').map(f => f.family) }`
   — confirm the brand families are in the list.
6. `mcp__playwright-headless__browser_take_screenshot` → `scale:"css"` (exact `W×H`; `"device"`
   multiplies by the pixel ratio), `type:"png"`, no `filename`. The MCP only writes inside the
   workspace or its output dir, so an absolute path elsewhere is denied. `mv` the path the
   result reports to `<out>/<slug>-a.png`.
7. Repeat 4–6 for `-b`, then `kill <pid>`.
8. `sips -g pixelWidth -g pixelHeight <file>` must equal `W×H`; a mismatch means the layout
   overflowed or the wrong `scale` — fix and re-render.

## Example: Arauto (seed on request)

When the user asks for Arauto, offer to seed `brands/arauto.md` by extracting from
`https://arautoai.com.br` (Step 3a). The `arauto-content-prompter` repo's `arauto-post`
skill keeps the verified tokens and logo SVG if the site is unreachable: cream bg,
terracotta primary, gold accent, Merriweather display + Inter body.
