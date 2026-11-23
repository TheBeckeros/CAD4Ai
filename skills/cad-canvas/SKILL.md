---
name: cad-canvas
description: Use when a message contains "Request from the cad-preview construction canvas" or "Answers to your briefing questions on the cad-preview construction canvas", when the user wants an engineering whiteboard ("konstrukční plátno", "plátno", /cad-canvas), or asks Claude to clean up, redraw, dimension or check a hand-drawn sketch, section, schematic or mechanism on that canvas.
---

# Construction canvas (cad-preview)

`<viewer URL>canvas` is the engineer's thinking surface: an infinite canvas where the user writes and sketches freely
(pen, QuickShape+, lasso, exact lines / circles / arcs, trim, dimensions, 9 layers) and Claude turns marked areas into
clean, editable geometry. It is not a second chat: this chat is the only conversation. Claude sees nothing on the canvas
until the user sends an area: **Odeslat do AI** (Ctrl+Enter) works like a snipping tool: the user drags a box over the
area, scribbles on the shot in red to point at things, writes a comment below it, and that adds a message to the chat
draft. (The button in the panel of a selection sends the selection's area without the box step.)

## Opening it

1. `curl -s <viewer URL>api/ping`; if it fails start the server:
   `python "<plugin root>/viewer/server.py" --port <viewer port> --data "<cwd>/.cad-preview" --detach`
   (`<plugin root>` is two folders above this skill).
2. Open `<viewer URL>canvas` in the browser pane (`mcp__Claude_Browser__preview_start` with `url`).
3. One line for the user: sketch freely, press Odeslat do AI, drag a box over the area, scribble and comment.
4. Always also give the full address for a tablet on the same network: `curl -s <viewer URL>api/lan` (only from this PC)
   gives `urls[].canvas` with the token (`http://<pc-ip>:<port>/canvas?t=…`). Network mode is on when
   `%USERPROFILE%\.cad-preview-lan` exists (or `CAD_PREVIEW_LAN=1`) when the server starts; `lan: false` means it listens
   only on this PC: offer to create the file and restart the server.

## A request ("Request from the cad-preview construction canvas")

The message has the instruction, the PNG of the region (look at it with Read), the selection summary and a request ID.
Everything below uses the helper (`<viewer port>` is the port of the viewer; default 8766):

```
python "<plugin root>/skills/cad-canvas/scripts/canvas.py" --port <viewer port> <command> ...
```

1. `req <request ID>` prints the request: `autonomy`, `context`, `rect` `[x, y, w, h]` (canvas units, y grows downwards,
   1 unit is nominally 1 mm), `objects` (the selection, full data), `neighbours` (context "around") or `page` (context
   "page": per-layer counts, all texts, an outline of every object; the whole canvas is in `canvasFile`), `layers`,
   `briefs` (earlier questions and the user's answers), `marks` (the user's red scribbles on the shot as polylines in
   canvas units: they point at what the comment means, e.g. "here"; they are not canvas objects, never draw or keep
   them). `objects` are the objects the box touches. `object <id>` reads one live object and what depends on it.
2. Look at the image first, then decide:
   - **Something essential is unclear** (a diameter, which pin is fixed, whether it is a bearing seat): do not guess.
     Pin questions to the drawing with `briefing`. Ask only what changes the result; for minor details give an
     `assumption` the user can accept with one click.
   - **Clear enough**: send the result with `preview`.
3. While you work, `status <request ID> drafting` shows "Vytvářím návrh".
4. When you finish a request without a `preview` (a consult answered in the chat, a question the user dropped, nothing
   to change), close it: `status <request ID> closed`. Only open requests are shown on the canvas (region, bubbles,
   bar); applied, rejected and closed ones disappear, and so does a request whose objects the user deleted.
   Use no other state names.

### Autonomy (the user chooses it per request)

| autonomy | what you may do |
|---|---|
| `consult` | Change nothing. Answer in the chat; use `briefing` if you need to ask. `preview` is refused. |
| `propose` (default) | `preview` shows your result as a ghost (green added, orange changed, red removed); nothing changes until the user presses Přijmout. |
| `direct` | `preview` is applied at once, but only inside `rect` (new objects must have their centre in it, existing ones must be in the selection or inside it). A restore point is made first; the user can press Vrátit. |

### Briefing (questions pinned to the drawing)

`briefing <request ID> items.json [--summary "what I understood so far"]`, items as a list or `{"items": [...]}`:

```
[{"anchor": {"obj": "<object id>"}, "q": "Je to ložiskové sedlo?", "options": ["H7", "bez tolerance"], "assumption": "H7"},
 {"anchor": {"pt": [120, 40]}, "kind": "warning", "q": "Kóty 25 a 12 dávají dohromady víc než celková délka 40"}]
```

Anchor to an object id wherever you can (the bubble follows the geometry); `pt` only for a place without geometry. Never put a `pt` on the request `rect` edge (the dashed orange frame is not part of the drawing): take the point from the geometry in the image.
`kind: "warning"` is for technical alerts (collision, inconsistent dimensions, a missing tolerance): it needs no
answer. Keep `q` short (one line), `options` to 2–4 likely answers. The user answers each bubble separately and presses
**Odeslat odpovědi**, which adds a message "Answers to your briefing questions ..." to the chat draft; when it arrives
update your understanding and either ask the essentials again or `preview`. Unanswered questions come back as
"use your assumption": state what you assumed in the note of the preview.

### Preview (your result)

`preview <request ID> changes.json [--note "one line"]` with `{"put": [objects], "del": [object ids]}`.
A `put` object with an existing `id` replaces that object (a change); without `id` it is new (the server names it).
`del` removes objects. Work in canvas units (world coordinates of the request), never in image pixels.

Object schema (`id` optional for new ones; `layer` 1..9, default 2 "AI geometrie"; `color` `"ink"` or `#rrggbb`;
`w` line width in canvas units, default 1.5; `cons: true` for a construction line, dashed, layer 5):

| t | fields |
|---|---|
| `line` | `a: [x, y]`, `b: [x, y]`, `arrow: true` optional |
| `circle` | `c: [x, y]`, `r` |
| `arc` | `c`, `r`, `a0`, `a1` radians, y down, drawn clockwise from `a0` to `a1` (increasing angle) |
| `rect` | `p`, `q` opposite corners |
| `ellipse` | `c`, `rx`, `ry` |
| `dim` | `kind`: `lin` (default) / `dia` / `rad`; `ref`: id of the line or rect (lin, with `edge` 0 top, 1 right, 2 bottom, 3 left) or circle / arc (dia, rad) it measures, or free `a`, `b`; `size` text height in canvas units (default 10); `off` offset of a `lin` dim from the measured line (signed, perpendicular); `ang` radians where a `dia` / `rad` leader leaves the circle; `txt` overrides the number. Layer 4. A dim with `ref` follows its object and the user can type a new value into it, which resizes the object. |
| `text` | `x`, `y` top-left, `s` (`\n` for lines), `size`. Layer 3. |
| `stroke` | `pts: [[x, y, pressure 0..1], ...]`, `tool: "hl"` for a marker; only for something freehand |
| `mech` | a **live kinematic model** (layer 6), see below |

### Mechanisms (make it move)

When the user wants a mechanism to move ("rozhýbej", "převeď na kinematický model"), send one `mech` object instead of
static lines; it draws its own symbols (pins, links, fixed supports, slider blocks on guides, the driving crank) and gets
a floating panel on the canvas: play / pause, speed, direction, phase, a slider per link length (live, infeasible
positions are reported), and Trajectory of any joint. Several mechanisms run independently.

```
{"t": "mech", "name": "Klikový mechanismus",
 "joints": [{"id": "A", "p": [70, -98], "fixed": true}, {"id": "B", "p": [70, -203]}, {"id": "C", "p": [152, -275]}],
 "links": [["A", "B"], ["B", "C"]],
 "sliders": [{"j": "C", "a": [152, -345], "b": [152, -197]}],
 "driver": {"j": "B", "c": "A"}}
```

- `joints`: ids `[A-Za-z0-9_]{1,12}`, `p` in canvas units, `fixed: true` for ground pivots. Draw them in a pose that can
  be assembled; link lengths come from these positions (or `len`: one length per link).
- `links`: rigid members between two joints. `sliders`: joint `j` moves on the infinite line through `a`, `b` (the
  guide is drawn along `a`–`b`). `driver`: joint `j` turns about the fixed joint `c` (a link must join them).
- The solver places every other joint from two links (circle–circle, e.g. a four-bar) or from one link plus a slider
  (crank-slider); joints it cannot place make the model infeasible, so every moving joint needs one of those.
  A crank that cannot turn all the way rocks between its limits; the panel says which.
- Replace the static schematic it came from (`del` those ids) unless the user wants to keep both.

Layers: 1 Ruční náčrty, 2 AI geometrie, 3 Poznámky, 4 Kóty a značení, 5 Konstrukční prvky, 6 Mechanismy, 7 Trajektorie,
8 AI briefing, 9 Importy. Put your results on 2 (dims 4, notes 3, axes and helper lines 5 with `cons`); never touch the
user's hand sketch (layer 1) unless asked: draw the clean version next to it or on top, and delete the originals only
when the instruction says "replace". The user's own sketch stays by default; whether it is hidden or replaced after
processing is still an open design question, so offer, do not decide.

Rules of thumb: straighten and complete lines, join end points exactly (use the same coordinates), keep the user's
proportions unless told otherwise, add dimensions only when asked or clearly part of the task, and separate verified data
from your estimates (estimated values go into a briefing assumption, not silently into the drawing). Check the
selection's version: a proposal is checked against the object revisions of the request, if the user changed something
meanwhile the user is asked before it is applied.

After `preview` say in one line what you drew (and what you assumed). If the server refuses the call, the message names
the problem (unknown anchor, object outside the region in `direct`, consult-only); fix it and call again.

## Not built yet (do not promise)

Gears, cams, springs and multi-loop linkages beyond what the solver above places, comparing the motion of variants, shared parameters between geometry,
dimensions and calculations, per-object revision history, symbols for bearings / springs, variant comparison on one
canvas, strength calculations. Claude can still draw schematics, alternatives side by side (separate regions) and
calculation results as text on the canvas.

## API (server on the viewer port; the helper wraps these)

`GET /api/canvas?since=<rev>&wait=` changes; `GET /api/canvas/req?id=`; `GET /api/canvas/object?id=`;
`POST /api/canvas/ops {put, del, layers, regions, base}` direct object changes (409 when `base` revisions are stale);
`POST /api/canvas/briefing`, `/preview`, `/status`, `/decide`, `/answer`, `/snapshot`, `/restore`. Do not edit
`canvas.json` by hand while the server runs.

Sharing: the Soubor menu saves the canvas as one `*.platno.json` (`{format: "cad-preview-canvas", v, objs, layers, regions}`)
and opens one (replacing the canvas after a restore point, or adding a copy with fresh ids); `POST /api/canvas/file/save`
and `/file/open {path, mode: replace|add}` do the same without the dialog.
