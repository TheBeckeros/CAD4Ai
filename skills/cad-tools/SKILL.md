---
name: cad-tools
description: Use whenever you work on a CAD model (STEP, CadQuery script) and would otherwise write a check/measure script, look at a screenshot, debug a failing fillet/boolean, look up standard part sizes, compute stress/deflection, wall thickness, optimise a parameter, or look for a similar part built before. The cad4ai CLI does it locally and returns a few lines of JSON.
---

# cad4ai: local CAD tools (save tokens, spend PC power)

Keep modelling natively: a Python CadQuery script that exports STEP. These tools only check and help.

## Writing a model script
- New model: `cad4ai new model.py` writes a skeleton (parameter block, assembly, export, imports below).
- Import the helpers from the stable copy, never from the plugin folder (its path has a version in it):
  `import os, sys; sys.path.insert(0, os.path.expanduser("~/.CAD4Ai/lib"))`.
- Parameters stay plain numbers with a comment (`HOLE = 5.5  # clearance M5 [mm] 3..20`); a computed value
  (`hole("M5")[...]`) is not editable in the viewer - look the number up with `cad4ai std hole M5` instead.
- At the end of the script state the intent; it is checked on the exported STEP after every run:
  ```python
  from cadtools.expect import expect
  expect("plate").size(100, 60, 5).holes(4, d=5.5, pitch=(80, 40)).mass(max=300)
  expect("shaft", "bearing").clearance(min=0)     # min/max distance, negative = overlap
  expect("bolt").count(4); expect("lid").inside(zmax=120); expect.no_collisions()
  ```
  Write expect() lines for every dimension or relation the user asked for. A FAIL means the model is wrong
  even though the script ran. Size/hole/mass/clearance rules run at the end of the script (only the named
  parts are measured); `no_collisions()` is checked by the hook after the export (all cores, incremental).
- `@cached_part` (from cadtools.cache) on functions that build a finished part: unchanged parts load from
  disk in milliseconds on the next run (key = source + arguments + every global/parameter they use).
- Threads (convention, always): screw / stud / external thread = NOMINAL diameter (M4 -> 4.0); tapped hole /
  nut / internal thread = TAP DRILL hole (M4 -> 3.3, `tap_drill("M4")`), always a real drill bit size
  (M3 2.5, M4 3.3, M5 4.2, M6 5.0, M8 6.8, M10 8.5, M12 10.2; fine `tap_drill("M10x1.25")` 8.8), never a
  computed minor diameter such as 4.134; lint warns about one. Their overlap is then an expected
  thread engagement, not a collision. Clearance holes: `cad4ai std hole M4` (4.5). Name screws with their size
  (`SROUB_M4x12`, `ISO 4762 M4x12`) so the check knows the thread.
- `part("ISO 4762 M5x16")`, `tap_drill`, `nominal` from cadtools.std instead of typed numbers.
- Library parts are real geometry 1:1 except the thread (screws: underhead fillet, washer face, chamfers,
  socket with drill point, thread length b by the standard; nuts: double chamfer, countersinks). The thread
  surface is split into P/2 rings. Call `apply_colors(assy)` right before `assy.export()`: body colour by
  family, seals / nylon inserts / balls coloured, every other thread ring dark. Never model a helix thread.
- parts.json: missing entries are added automatically after each export (type, standard, subassembly);
  write only what cannot be guessed (material, special types).
- Moving parts: put one word in parts.json while modelling, nothing else:
  `"BTN_": {"motion": "press"}`, `"KNOB": {"motion": "rotate"}`, `"LID": {"motion": "hinge"}`,
  `"DRAWER": {"motion": "slide"}` (keys are name prefixes, so one line covers all buttons).
  The PC derives axis, pivot, stroke and limits from the geometry and writes `<model>.motion.json` after every
  rebuild (also when the user changes a parameter in the viewer): no motion file to write, no tokens.
  Optional overrides in a dict: `axis` ("X"/"-Z"/[x,y,z]), `origin`, `range` [min,max], `travel`, `max`, `on`
  (carrier part), `drive` {"part", "ratio"}, `group`. The hook prints the derived joints in one line; check it.
  Doors and lids: `"with": ["DOOR_"]` carries the leaf, lock, screws, seal (or give them the door's own
  `subassembly`); `"home": 80` when the STEP is exported open; `"pin": "HINGE_PIN"` only if the axis comes out
  wrong (it is found from the knuckle bore on the fixed pin). Buttons: put `press` on the cap, not the switch.
  All solids of one part (`KNOB#1`, `KNOB#2`) move as one joint.

## Standard parts: never model them, one call from the library (cadtools.parts)
```python
from cadtools.parts import place, cut, bolt_joint, drill, apply_colors
s = place("DIN 933 M8x30", at=(10, 0, 8))              # any code, ISO / DIN synonyms; head seated on the point
b = place("6204-2RS", at=(0, 0, 30), up=(1, 0, 0))     # any axis; anchor= picks the point (std info lists them)
beam = place("IPE 200", at=(0, 0, 0), up=(1, 0, 0), L=1500)   # keyword args go to the family
shaft = cut(shaft, "DIN 6885 A 8x7x40", "shaft", at=(0, 0, 20), up=(0, 0, 1))  # counterpart tools:
shaft = cut(shaft, "DIN 471 20", "groove", at=(0, 0, 35))      #  screws clearance|tap|cbore|csk, keys shaft|hub,
j = bolt_joint("M6", grip=12, at=(-25, 0, 12))         #  circlips groove, seals housing, bearings *_seat
plate = j.cut(plate, "clearance"); j.add_to(assy, "J1")
apply_colors(assy); assy.export("m.step")
```
Library (127 families, `cad4ai std find "<Czech or English words>"` gives the code, `std info CODE` the
dimensions, anchors, tools, source): Šrouby - hex 4017/4014/fine 8765/8676/HV 14399-4/flange 4162, socket
4762/7984/10642/7380, slotted 1207/1580/2009/2010, cross 7045/7046, Torx 14580/14583/14581, square DIN 478/479,
wing DIN 316, eye DIN 580, shoulder 7379, set screws 4026-4029 / 4766, 7434-7436, studs DIN 938/939/835/940,
rod DIN 976, self-tapping 7049/7050/1479 (ST4.2x16). Matice - 4032/4035/4033, fine 8673/8675, HV, nyloc
7040/985/10512, all-metal 7042, cap DIN 1587/917, square 557/562, flange 6923, wing 315, coupling 6334,
T-slot 508, KM. Podložky - 7089/7090/7092/7093, HV DIN 6916, spring DIN 127, tooth 6797/6798, tab 93/463/432,
MB, taper 434/435, timber 436/440. Čepy - 2338/8734/8735, taper 2339, spring 8752/13337, grooved 8740,
rivets 1051/661/15977, clevis 2341 A/B, split pin 1234, fork DIN 71752. Pera DIN 6885 A/B/C, Woodruff 6888.
Kroužky DIN 471/472/6799. Těsnění O-ring, DIN 3760, DIN 7603. Profily IPE/HEA/HEB/HEM/IPN/UPN/UPE, L, RHS/SHS/
CHS, FL, KR, ICUSTOM, ALU 4040. Ložiska 60/62/63/618/619/6xx (-2RS/-2Z), 72/73 B, 12/22, 511/512, NU/NJ/N,
302/303/322, HK. Převody GEAR m z b d [beta x] (involute), RACK, SPROCKET 08B-1 z17; gear_pair() in
cadtools.lib_gears. Values are "unverified" (typed from general knowledge; profiles checked by kg/m): fine
for design, say so when the user needs exact catalogue values.

## Growing the library
- After an export the hook may report `[library] candidate '<title>' ...`: parts the library lacks (profiles,
  rails, hinges, springs...) or a custom shape repeated 8x / used in 2 models. Ask the user ONCE, in one
  short question, whether to create that library family; then `cad4ai lib accept "<id>"` (writes a skeleton
  ~/.CAD4Ai/library/families/<id>.py) or `cad4ai lib dismiss "<id>"`. Do not ask again for the same id.
- Filling a family: put the sizes the user uses into FAMILY["rows"] with the real source of the values
  (catalogue, drawing; status "unverified" until checked), write dims() and part() in the library
  convention (main axis local +Z, bottom at Z=0). It is then found by place()/part()/std info and listed
  in the viewer's Settings -> Libraries tab. `cad4ai lib families` lists own families.
- The viewer shows everything, so point the user there instead of explaining it in chat: Window tabs at the
  top - Checks (collisions with "show", expect(), diff, lint, unexpected changes, parts.json editor, hook
  log), Compute (FEM / DFM with results drawn on the model, optimisation, variant comparison), System
  (versions, CLAUDE.md, retro log, script search); Settings dialog - presets, libraries with 3D preview,
  candidates, rules, tools, skills & hooks, data.

## Hooks (automatic, nothing to call)
- Script run fails -> doctor result arrives with the tool output: failing line, cause, a value that works.
  Apply it instead of guessing.
- A .step changed -> diff, validity, expect() results, collisions, unexpected changes (parts that changed
  although the parameters driving them did not). Not counted as collisions (listed apart): solids of one
  part overlapping each other, cables/straps/hoses, a thread engagement (screw at nominal diameter in a
  tap-drill hole or nut). A screw through material with no hole, or in a hole smaller than the tap drill, IS reported. This covers the "always run the collision check" rule: no own check needed.
- A CadQuery script was written/edited -> lint warnings (duplicate names, fillet without selector,
  hole(5) for M5, parameters without comment/unit, unused parameters).

## Commands

Run `python "<CAD4Ai>/viewer/cad4ai.py" <command> ...` (the SessionStart note gives the exact path).
Prefer these over writing your own analysis scripts, reading STEP files, or screenshots.
Results are cached per file version, so repeating a call is free.

| Need | Command |
|---|---|
| What is in the model (parts, sizes, mass, hole patterns with PCD/pitch) | `summary M.step` (`--json`, `--full`) |
| What my rebuild changed | `diff M.step` (the hook already reports this after a Bash run that exports a STEP) |
| Collisions / clearances (all pairs, all cores) | `collide M.step --limit 0.5` |
| Holes, shafts, planes of one part | `holes M.step PART` |
| Distance between parts, section, mass | `dist M.step A B`, `section M.step "Z=20"` (writes SVG), `mass M.step` |
| CLAUDE.md change mode 2 / 3 | `verify M.step --level 2` / `--level 3 [--fem "part=P fix=xmin load=xmax=0,0,-100"]` |
| Check a script before running | `lint S.py [--info]` |
| Fill parts.json | `partsjson M.step` (also automatic) |
| Script fails (fillet, chamfer, boolean, shell...) | `doctor S.py`: failing line, category, largest radius that works, whether removing the line helps. **Run it before trying fixes by hand.** |
| Standard parts | `std "ISO 4762 M5x16"`, `std hole M5`, `std key 30`, `std 6204`, `std NEMA17`, `std list` |
| Purchased part from a vendor STEP | `vendor V.step`: envelope, mounting faces, hole patterns, shafts |
| Stress / deflection | `fem M.step PART --fix hole:6.6 --load "zmax=0,0,-200" [--material al]` |
| Manufacturability | `dfm M.step PART --process print|mill|mould` |
| Find best parameter values | `optimize S.py --vary WALL=1..6 --minimize mass --subject "fem.max_disp_mm<0.2" --fem "..."` |
| A picture is really needed | `views M.step [--highlight A]` then Read the PNG (one image instead of several screenshots) |
| Built something similar before? | `find "bearing housing 6204"` (`index` rebuilds the index) |

Notes
- Part names: exact, or a case-insensitive substring; `*` = all.
- Standard parts in a script: `std` prints the import line; `part(code)` returns a cq.Workplane (screws: head on Z=0, shank to -Z). Threads are not modelled; fastener overlaps are listed apart from real collisions (by parts.json `type: fastener` or a name like M5x16 / ISO 4762).
- FEM regions: `xmin..zmax`, `plane:Z=20`, `box:x0,y0,z0,x1,y1,z1`, `hole:6.6`, `hole:6.6@x,y,z`. Voxel FEM: good for comparing variants (±10-30 %), not for certification; report `vm_p99_5_MPa` rather than the raw maximum.
- `doctor` and `optimize` run sandbox copies of the script: the real model files are never overwritten (exports are redirected). `optimize --apply` writes the best values into the script.
- Long jobs (fem with many elements, optimize, index): run in the background.
