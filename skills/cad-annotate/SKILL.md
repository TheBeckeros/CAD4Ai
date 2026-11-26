---
name: cad-annotate
description: Use when a message contains "3D annotation from CAD4Ai" or the user refers to a place they marked on a 3D model.
---

# Reading 3D notes from the CAD4Ai viewer

The user works in the interactive viewer in the browser pane. They orbit the model, select
faces, edges and vertices, measure, cut sections, compare versions and draw with a pen.
Then they write a request. A `Note N:` block is appended to their chat message. It contains:

| Line | Meaning |
|---|---|
| first line | the user's request |
| `Model:` | the model file the user worked on (normally the .step) |
| `Screenshot:` | PNG of what the user saw, with labels burnt in: marker letters (A, B…), orange circles with the numbers of the selected features, blue dimension labels |
| `Script:` / `Parameters:` | the parametric source of the model and its named parameters: where the change goes |
| `Annotation data:` | JSON with all the data, input for `locate.py` |
| `Note ID:` | used to mark the note as done |
| `Selected features` | **exact** features from the STEP (type, size, axis, clicked point); the number matches the circle on the screenshot |
| `Markers` | places clicked with the Markers tool: point, line A → B or area, the feature under each (`on:`) and a note each; the letter matches the screenshot |
| `Dimensions` | measured values and what they were measured between. "Dimension N … should be X" means change that size to X |
| `Section` | the section plane the user was looking at |
| `Pen drawing` | free-hand strokes drawn over the view (an 8-point outline in mm; all points are in the annotation data). Points on the model are exact; a stroke drawn next to the model lies on the plane through the view centre |

All coordinates are **model coordinates in mm, Z up** (the exploded view is not applied to
them). The screenshot says **what** the user means and where it is on the part; the lists and
`locate.py` say **exactly** which face, edge or point it is. Use both.

## Steps for every note

1. **Look first:** Read the screenshot. Find each label (letter, numbered circle, dimension) and
   understand what the user points at and what they want, in words: "the left mounting hole
   of the base plate", "the top edge of the lid". If the request is still unclear after that,
   ask (step 4) before touching geometry.
2. **Determine the target exactly:**
   ```
   python "<this skill's folder>/scripts/locate.py" --step <model>.step --annotation <Annotation data>
   ```
   - For selected features the script finds the matching B-rep face, edge or vertex by
     coordinates and prints `exact`. If it prints "deviation … (did the model change?)",
     the model changed after the note was made: say so and confirm with the user.
   - For pen strokes it prints the most likely target: a loop around a vertex is `VERTEX`,
     around several vertices `CORNER / REGION`, a loop inside one face is a spot on that `FACE`,
     a line across an edge is `EDGE`.
   - For markers run it per marker with `--points` (see Markers below); the `on:` line already
     names the feature under each point.
   - If the screenshot and the coordinates disagree, trust the coordinates for the geometry
     and say what you saw.
3. **Find it in the script** (`Script:`): which operation and which parameter make that face,
   edge or hole. Prefer changing an existing parameter (`Parameters:`) over new geometry.
4. **Combine the target with the request.** A dimension with "should be X" means change a
   parameter or the geometry so that the measured value becomes X. Additional strokes may
   define a size, e.g. a dash across an edge shows how far a feature should reach: measure
   the distance from the target. If the note can be read in several ways that lead to
   different geometry, **ask** with AskUserQuestion and concrete options. Put the
   recommended option first and include the derived dimension.
5. **Make the change in the parametric script** (following the cad-step-modeling skill if it
   is installed). Put new sizes into named parameters in the script header
   (`NAME = value  # description [mm]`). The viewer then shows them in the Parameters tab and
   the user can tune them. Select edges and vertices by coordinates, not by index.
6. **Export the STEP (no STL unless the task asks for it) and verify** (one solid per part, BRepCheck valid, volume against a hand
   calculation, face types). The viewer reloads by itself after the export and stores a new
   version, which the user can compare with the old one in the Versions tab.
7. **Mark the note as done** (its pin turns green in the viewer):
   ```
   curl -s -X POST <viewer URL>api/annotations/status -H "Content-Type: application/json" -d "{\"id\":\"<Note ID>\",\"status\":\"done\",\"note\":\"<what you did, one sentence>\"}"
   ```
8. **Reply briefly:** what you understood each label to mean (in words), which feature it is
   (coordinates), what changed, a table of the checks and the name of the parameter that tunes it.

## Markers

A `Markers` list comes from the viewer's Markers tool: several places, each with its own note, sent in
one note together with the screenshot (older notes have `kind: batch` and no screenshot). Each marker is a `point` (one click), a `line` A → B (two clicks, e.g. "hole from
A to B") or an `area` (a closed polygon of clicks on the model), with model coordinates, the face
normal and the part. The annotation data has the same list under `markers` (no strokes or features).

1. For each marker run `locate.py --step <model>.step --points "x,y,z;x,y,z;..."` with that marker's
   points (from the annotation data). A point gives the face / edge / vertex under it, a line its two
   ends, an area the region it encloses.
2. Handle each marker's note with steps 3 to 6 above, in label order unless they depend on each other.
   A line gives a direction and length (`B − A`); a hole "from A to B" runs along it.
3. Mark the one Note ID done when all markers are handled, and reply with one row per marker label.

Handle several notes in one message in order. If they affect each other, decide the order
and say it. If you do not handle a note (unclear, waiting for an answer), leave it open.

## When something is missing

- No drawing and no selection: the request applies to the whole model.
- No `Annotation data` (older note): pass the points from the message with `--points "x,y,z;x,y,z;..."`.
- No STEP: `locate.py` needs a STEP file. Export the model first, or work from the points and
  the feature description.
- The viewer can be opened manually with `/CAD4Ai [path.step]`. The server runs on `<viewer URL>`.
