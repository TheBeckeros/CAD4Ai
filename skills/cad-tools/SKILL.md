---
name: cad-tools
description: Use whenever you work on a CAD model (STEP, CadQuery script) and would otherwise write a check/measure script, look at a screenshot, debug a failing fillet/boolean, look up standard part sizes, compute stress/deflection, wall thickness, optimise a parameter, or look for a similar part built before. The cad4ai CLI does it locally and returns a few lines of JSON.
---

# cad4ai: local CAD tools (save tokens, spend PC power)

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
