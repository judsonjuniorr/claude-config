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

Aspect ratio <w:h>. Size via a wrapper only; never edit, recolor, crop, or redraw.
Wordmark: <text + font, or none>. No vector logo → write `Logo: none` and omit the block.

```svg
<svg viewBox="…" …sanitized (SKILL.md Step 3a)…></svg>
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

The server only ever sees a fresh temp dir holding the generated HTML — never a path the
user gave. Shell state doesn't persist between Bash calls, so keep `R`, `PORT` and the PID
in files under `R`.

1. Write each direction as a self-contained HTML file: `<meta charset>`, Google Fonts
   `<link>`, inline CSS/SVG, `html,body{margin:0;width:Wpx;height:Hpx;overflow:hidden}`.
2. Stage and serve:
   ```bash
   R=$(mktemp -d) && cp <html files> "$R"/ && echo "$R"
   PORT=$(python3 -c 'import socket;s=socket.socket();s.bind(("127.0.0.1",0));print(s.getsockname()[1])')
   python3 -m http.server "$PORT" --bind 127.0.0.1 --directory "$R" >"$R/.server.log" 2>&1 &
   echo $! >"$R/.server.pid"; echo "$PORT" >"$R/.port"
   for i in $(seq 20); do curl -sf -o /dev/null "http://127.0.0.1:$PORT/" && break; sleep 0.25; done \
     || { cat "$R/.server.log"; kill "$(cat "$R/.server.pid")"; echo SERVER_FAILED; }
   ```
   `SERVER_FAILED` → stop and report the log.
3. `mcp__playwright-headless__browser_resize` → `width:W, height:H`.
4. `mcp__playwright-headless__browser_navigate` → `http://127.0.0.1:<PORT>/<slug>-a.html`.
5. `mcp__playwright-headless__browser_evaluate` with `m` = the safe margin as a fraction:
   ```js
   async () => { await document.fonts.ready; const W = innerWidth, H = innerHeight, m = 0.06;
     const fonts = [...document.fonts].filter(f => f.status === 'loaded').map(f => f.family);
     const out = [], w = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT), rg = document.createRange();
     while (w.nextNode()) { const n = w.currentNode; if (!n.textContent.trim()) continue; rg.selectNodeContents(n);
       const r = rg.getBoundingClientRect();
       if (r.left < m*W || r.top < m*H || r.right > W - m*W || r.bottom > H - m*H) out.push(n.textContent.trim().slice(0, 40)); }
     return { fonts, out, scroll: [document.documentElement.scrollWidth, document.documentElement.scrollHeight] } }
   ```
   It measures text glyph boxes (ranges), not element boxes, so padding doesn't trip it.
   Gates — any failure means fix the HTML and re-render, never screenshot: every brand family
   is in `fonts`; `out` is empty (use the format's own margin, e.g. 0.14 for story top/bottom);
   `scroll` equals `[W, H]`.
6. `mcp__playwright-headless__browser_take_screenshot` → `scale:"css"` (exact `W×H`; `"device"`
   multiplies by the pixel ratio), `type:"png"`, no `filename`. The MCP only writes inside the
   workspace or its output dir, so an absolute path elsewhere is denied. Delete any old
   `<out>/<slug>-a.png` first, then `mv` the path the result reports there.
7. Repeat 4–6 for `-b`.
8. `sips -g pixelWidth -g pixelHeight <file>` must equal `W×H`; a mismatch means the wrong
   `scale`.
9. Stop the server on success **and** on any failure: `kill "$(cat "$R/.server.pid")"`.
   Each iteration round in Step 7 repeats from step 2.
