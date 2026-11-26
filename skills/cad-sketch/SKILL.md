---
name: cad-sketch
description: Use when the user wants to sketch, draw or brief a part or mechanism before modelling ("let me draw it", "sketch it", /cad-sketch, "náčrt", "skica"), when a message contains "Design brief from the CAD4Ai sketch pad" or "Snap request from the CAD4Ai sketch pad", or when the user asks Claude to redraw part of the sketch pad.
---

# Sketch pad (CAD4Ai)

`<viewer URL>sketch` is an infinite canvas for the early phase: pen with pressure (Apple Pencil on iPad,
mouse on the desktop), marker, eraser, lasso, text, images, shapes. Ideas pile up there; this session sees nothing
until the user presses **Send to Claude** (whole canvas) or uses the **Snap ✦** tool (one boxed region).

## Opening it from the chat

1. `curl -s <viewer URL>api/ping`; if it fails start the server:
   `python "<plugin root>/viewer/server.py" --port <viewer port> --data "<cwd>/.CAD4Ai" --detach`
   (`<plugin root>` is two folders above this skill). For an iPad on the same network the server must be in network mode
   (`%USERPROFILE%\.CAD4Ai-lan` exists, or `CAD4AI_LAN=1`); `curl -s <viewer URL>api/lan` gives the full
   address `urls[].sketch` with the token: always give it to the user.
2. Open `<viewer URL>sketch` in the browser pane (`mcp__Claude_Browser__preview_start` with `url`).
3. One line for the user: draw freely, box a region with Snap ✦ and say how it should change, Send to Claude hands over everything.

## A whole-canvas brief ("Design brief from the CAD4Ai sketch pad")

The message has the user's text, the canvas PNG (look at it with Read), the texts on the canvas and the path of
`sketch.json`. Work from the image and the texts; restate the design in 3–6 lines and wait for the go-ahead before
writing CAD code, unless the user already said to model it. Ask open questions in one short list.

## A snap request ("Snap request from the CAD4Ai sketch pad")

The user boxed a region and wrote how it should be redrawn. You get:
- the instruction, the region `[x, y, w, h]` in canvas units (y grows downwards) and its PNG (`scale` px per unit,
  PNG pixel (0, 0) = region corner `(x, y)`); always look at the PNG first;
- the request file `<data>/snaps/<snap id>.json`: `items` (the region's items, full data), `outsideBounds` (neighbours,
  only as boxes: context, never yours to change), `rect`, `scale`.

Answer with a **proposal**: the complete new content of the region. It replaces the region's items when the user
accepts; strokes crossing the border keep their outside parts, and the pad cuts anything of yours at the border, so
draw only inside. The user sees it as a ghost with Accept / Reject / Edit…; nothing changes before Accept. Then say in
one line what you drew. If the user edits the instruction, a new snap request arrives.

Write the items to a JSON file and send it:
```
python "<plugin root>/skills/cad-sketch/scripts/proposal.py" <snap id> items.json --space image --note "two pins, hinge cleaned up"
```
(or `POST <viewer URL>api/sketch/proposal` with `{"snap": id, "space": ..., "note": ..., "items": [...]}`).

`space` says what the numbers mean: `image` = PNG pixels (easiest when you work from the image), `rect` = canvas units
from the region corner, `world` = absolute canvas units (default). Item schema (all optional except `t` and the geometry):

| t | fields |
|---|---|
| `stroke` | `pts: [[x, y], ...]` or `[[x, y, pressure 0..1]]`, `w` line width (default 2), `color`, `tool: "hl"` for a marker |
| `line` | `a: [x, y]`, `b: [x, y]`, `w` line width, `color` |
| `rect` / `ellipse` | `x, y, w, h` bounding box, `lw` line width (default 2), `color` |
| `text` | `x, y` (top-left of the first line), `s` (text, `\n` for new lines), `size` (font size), `color` |

Example (`--space image`): `[{"t": "line", "a": [40, 200], "b": [600, 200], "w": 3}, {"t": "ellipse", "x": 90, "y": 170, "w": 60, "h": 60},
{"t": "text", "x": 80, "y": 240, "s": "pin Ø6", "size": 28}]`

`color` is `"ink"` (black / white with the theme, the default) or `#rrggbb`. Curves: give enough points (every few
pixels) to look smooth, straight parts as two points. Keep what the instruction does not ask to change, match the
user's style (line widths of the region's items), keep it clean and engineering-like. Widths and sizes in `image`
space are pixels too.

If `ANTHROPIC_API_KEY` is set the pad can also ask the API directly (Direct API checkbox); such requests never reach
this chat.

## API (server on the viewer port)

`GET /api/sketch?since=<rev>` items and snaps changed since that revision; `POST /api/sketch/ops {put, del}` changes
items (ids `[A-Za-z0-9_-]{1,40}`); do not edit `sketch.json` by hand while the server runs, the server keeps it in memory.
