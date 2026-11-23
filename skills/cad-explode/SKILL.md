---
name: cad-explode
description: Use only when the user asks for an exploded view, disassembly / assembly sequence or assembly instructions, serviceability or "can it be taken apart" analysis of a CAD assembly in the cad-preview viewer (including the "Plan disassembly" request from the viewer's Parts tab). Writes <model>.explode.json next to the model.
---

# Exploded view and disassembly for the cad-preview viewer

Only on request: never write an explode file unasked. `<model>.explode.json` next to
`<model>.step` gives the viewer's **Parts → Exploded view → Disassembly** a step list, Play,
a step slider and trail lines. The point is **disassembly**: an order in which real parts can
actually come out, and a clear verdict on what cannot.

If the request came from the viewer button (it has a `Note ID`), mark it done afterwards:
`curl -s -X POST <viewer URL>api/annotations/status -H "Content-Type: application/json" -d "{\"id\":\"<Note ID>\",\"status\":\"done\"}"`
A `Focus:` line in the request (e.g. "servicing the piston") says which parts matter most:
take them out as early as the geometry allows and stop explaining the rest in detail.

## 1. Geometry analysis (always run it, do not guess)

```
python "<this skill's folder>/scripts/explode.py" info <model>.step
python "<this skill's folder>/scripts/explode.py" plan <model>.step [--base <part>] [--dirs "x,y,z;x,y,z"]
```
`info` lists the parts with the names the viewer uses, bounding boxes and cylinder axes.
`plan` slides each part along ±X/±Y/±Z and its own cylinder axes, checks collisions with the parts
still in place (B-rep booleans), and repeats with the smallest free part. It prints a draft
(`steps`, `free` directions, `locked`, `notes`). `--base` is the part that stays (default: the
largest); `--dirs` adds slanted directions (dovetails, angled pins). Large assemblies take a while:
run it in the background and tell the user.

## 2. Engineering review of the draft

The script knows geometry only. Add what it cannot know:

| Situation | What to do |
|---|---|
| Screws, bolts, nuts, circlips, keys, pins | They come out first; name the tool (`"tool": "hex key 4"`) |
| Press fit (the script notes an overlap in the assembled state) | Keep the step, note it: `"note": "press fit, needs a puller"` |
| Several parts always handled together (a bearing in its housing, a sub-assembly) | One step with all of them in `parts` |
| Part LOCKED | Say why (captured between webs, closed eye on a one-piece shaft, …) and propose a design change: split it (rod cap with two bolts), make it built-up, change the fit. Put a step with `"locked": true` and a direction where it would come out after the fix, so it still moves in the view |
| Order makes no practical sense (the script removes the smallest part first) | Reorder, but only to an order the `free` directions allow at that moment |
| Several free directions | Pick the one a technician would use (up / out of the housing, along the pin) |

`distance` (mm) is how far the part travels in the view: at least the way out the script
found, plus ~30 % of the part size, so the parts never overlap in the exploded state.

## 3. File format

Coordinates are model coordinates, Z up, in the assembled state. Steps are in **disassembly order**.

```json
{
  "base": "klikovka",
  "steps": [
    {"name": "Press out the piston pin", "parts": ["pistni_cep"], "direction": [1, 0, 0], "distance": 80,
     "tool": "pin drift", "note": "slides along its own axis, free in both directions"},
    {"name": "Lift the piston off", "parts": ["pist"], "direction": [0, 0, 1], "distance": 45},
    {"name": "Connecting rod", "parts": ["ojnice"], "direction": [0, -1, 0], "distance": 60, "locked": true,
     "note": "closed big end on a one-piece crank: needs a split rod cap"}
  ],
  "locked": ["ojnice"],
  "notes": ["Serviceability: 2 of 3 parts come out; the rod needs a split big end."]
}
```

- `parts`: names exactly as `info` prints them (= the viewer), or 0-based indexes. A part may
  appear in several steps (first with its sub-assembly, then alone); the movements add up.
- `direction`: unit vector (normalised by the viewer). `tool`, `note`, `locked` are optional.
- **Assembly** is the same file played backwards (the viewer's Assembly button: last step first,
  parts move in, opposite direction). Give each step `assemblyName` ("Insert the piston pin") and,
  where assembly differs from disassembly, `assemblyNote` (heat the piston, oil the pin, torque
  the bolts 10 Nm, fit the circlip after the pin). Without them the viewer shows "Install <parts>".
  A part that cannot come out cannot go in either: say so as an assembly problem too.
- `locked` (top level): parts that cannot be removed; the viewer shows them as a red warning.
- `notes`: short findings shown under the steps.

## Checks before you reply

1. Every name in `parts` exists (the viewer lists unknown ones in red).
2. Every non-locked step uses a direction that was in `free` for that part **at that point**
   in the sequence (rerun `plan` with `--base` if you change the base part).
3. Reply with a table: step, parts, direction, tool / note; then a short **disassemblability
   verdict**: what comes apart, what is locked and why, and the design changes you suggest.
   Add the assembly order in one line (the steps backwards with their `assemblyNote`s).
   Do not change the CAD model unless the user asks.
