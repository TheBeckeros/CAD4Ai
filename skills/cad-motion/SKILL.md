---
name: cad-motion
description: Use only when the user asks for motion, animation, kinematics, range of motion or to "make it move" for a CAD assembly in the CAD4Ai viewer (including the "Create motion" request from the viewer's Motion tab). Writes <model>.motion.json next to the model.
---

# Motion and kinematics for the CAD4Ai viewer

Only on request: never write a motion file unasked, and do not start it while the design is still
being worked out. Mention it at most once, in one line, and only after the user has confirmed the
design; it costs a lot of tokens, so wait for a clear yes. `<model>.motion.json` next to `<model>.step` gives
the viewer's **Motion** tab joint sliders, Play / Pause, scrubbing and the joint axes.

Start with the geometry dump instead of writing your own inspection code:
```
python "<this skill's folder>/scripts/joints.py" info <model>.step
```
It prints the STEP part names, each solid's bounding box and its cylinder axes (pins, shafts, bores).

If the request came from the viewer button (it has a `Note ID`), mark it done afterwards:
`curl -s -X POST <viewer URL>api/annotations/status -H "Content-Type: application/json" -d "{\"id\":\"<Note ID>\",\"status\":\"done\"}"`

## Deriving the joints from the assembly

Read the geometry and the design intent, not just the names:

| What you see | Joint |
|---|---|
| Pin in a hole, shaft in a bearing, coaxial cylinder pair with clearance, hinge knuckles | `revolute` about the common axis |
| Lid or door with knuckles along one edge | `revolute` about the knuckle axis, `min`/`max` from where it hits the base (usually 0 … 90–120°) |
| Part in a slot, on a rail, dovetail, drawer in a cabinet, piston in a cylinder | `prismatic` along the slot or rail, range = free travel |
| Two meshing gears | the driven gear gets `drive: {joint: <driver>, ratio: -z_driver / z_driven}` |
| Rack and pinion | rack `prismatic` with `drive: {joint: <pinion>, ratio: π·m·z / 360}` (mm per degree) |
| Part carried by a moving part (knob on a lid, wheel on an arm) | its own joint with `parent: <carrier joint>` |
| Crank-slider (piston engine, pump) | `joints.py slider-crank` writes the whole file (see below) |
| Four-bar linkage | `joints.py four-bar` writes the whole file |
| Other closed loop (scissor, …) | solve the positions yourself and write `animations[].keyframes` (see below) |

Take origins, axes and limits from the **same parameters** the CAD script uses
(`HINGE_R`, `TRAVEL`, …), and write the motion file **from that script** in the same run that
exports the STEP. Then a change in the Parameters tab keeps the motion in sync.
Compute the limits from geometry (clearance to the base, slot length). If a limit is a guess,
say so in the joint's `note`.

## File format

All coordinates are model coordinates in mm, Z up, in the **home pose**: the pose in which the
STEP is exported. Revolute values are in degrees (right-hand rule about `axis`); prismatic values are in mm along `axis`.

```json
{
  "joints": [
    {"name": "lid hinge", "type": "revolute", "parts": ["lid"], "origin": [0, 28, 30], "axis": [-1, 0, 0],
     "min": 0, "max": 110, "home": 0, "note": "stops on the back wall"},
    {"name": "knob", "type": "revolute", "parts": ["knob"], "parent": "lid hinge",
     "origin": [0, 0, 33], "axis": [0, 0, 1], "min": -180, "max": 180},
    {"name": "gear B", "type": "revolute", "parts": ["gear_b"], "origin": [40, 0, 0], "axis": [0, 0, 1],
     "drive": {"joint": "gear A", "ratio": -0.5}}
  ],
  "animations": [
    {"name": "Open and close", "duration": 4, "keyframes": [
      {"t": 0, "values": {"lid hinge": 0}}, {"t": 0.5, "values": {"lid hinge": 110}}, {"t": 1, "values": {"lid hinge": 0}}]}
  ]
}
```

- `parts`: solid names exactly as in the STEP assembly (`cq.Assembly().add(..., name=...)`),
  or 0-based indexes. List a part only in its innermost joint; that joint moves it, together
  with all parent joints.
- `home` (default 0): the joint value at which the geometry was exported.
- `parent`: the joint that carries this one. Its `origin`/`axis` are still given in home coordinates.
- `drive`: a dependent joint with value = driver × `ratio` + `offset`. It gets no slider.
- `animations` (optional): keyframes with `t` from 0 to 1, interpolated linearly per joint.
  The viewer always adds "Full range (all joints)" (home → max → min → home).
- Closed loops: the viewer has no constraint solver, the followers move by keyframes.
  The two common ones are solved for you (points and vectors `x,y,z` in the home pose, parts comma separated):
  ```
  joints.py slider-crank <model>.motion.json --center 0,0,0 --axis 1,0,0 --pin <crank pin> --wrist <wrist pin> --slide 0,0,1 --crank <parts> --slider <parts> --rod <parts>
  joints.py four-bar <model>.motion.json --axis 0,0,1 --a <crank pivot> --b <crank-coupler pin> --c <coupler-rocker pin> --d <rocker pivot> --crank <parts> --coupler <parts> --rocker <parts> [--min --max]
  ```
  Each one prints the range of every joint. For other loops, sample the driver (e.g. 36 steps),
  solve the followers in Python, write keyframes and give the followers wide `min`/`max`.

## Checks before you reply

1. Every name in `parts`, `parent` and `drive.joint` exists. The Motion tab lists anything that
   does not match in red.
2. Rotating to `min` and `max` does not cause a collision with the rest of the assembly.
   If unsure, export the assembly at both limits and run `cad4ai collide <step> --limit 0` (skill
   cad-tools): exact, all cores, cables and screw threads already filtered.
3. Reply with a table: joint, type, parts, range, and how you derived it (e.g. "pin Ø6 in hole Ø6.4, coaxial").

Selection, measurement and pen notes in the viewer always work in the home pose: the viewer
returns there before picking. So notes keep the same coordinates as the STEP.
