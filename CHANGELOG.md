# Changelog

All notable changes to CAD4Ai are documented here.
The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project uses
[Semantic Versioning](https://semver.org/) (0.x: the plugin is still evolving, minor versions may change behaviour).

## [Unreleased]

### Added
- English README with feature overview and screenshots, this changelog, MIT `LICENSE` file.
- **Automatic motion** from one-word `motion` keys in `parts.json` (`press`, `rotate`, `hinge`, `slide`):
  the PC derives axis, stroke and collision limits from the geometry and regenerates `<model>.motion.json`
  after every rebuild.
- Motion generator: hinge axis from the fixed pin, one joint per STEP instance, carried parts (`with`),
  `home` pose for models exported open, press stroke from the cap.
- Claude writes `parts.json` motion keys while modelling, unasked; hand-written motion, exploded views and
  drawings stay on request.
- **Standard-part library with 127 families** and ISO / DIN synonyms: screws, nuts, washers, pins, rivets,
  keys, retaining rings, seals, structural profiles, ball / roller / tapered / needle bearings, involute
  gears, racks, sprockets. Counterpart tools for clearance / tap / counterbore / countersink holes, keyseats,
  ring grooves, bearing and seal seats. Library browser as a category tree with a 3D preview per size.
- Viewer: orbit about the point under the cursor; zoom to the cursor at 15 % per notch; grab-pan that
  keeps the grabbed point under the cursor.

### Changed
- Tap drill holes always at real drill bit sizes (M2.5 → 2.1); M18–M30 and common fine threads added;
  `tap_drill("M10x1.25")`.
- Bearings: rolling elements and cage are one solid, so a bearing is 2–4 parts.

### Fixed
- Cap nuts: dome centred on the axis, valid after STEP export.
- Tapered roller bearings: raceways no longer overlap the rollers.
- Library preview for codes without spaces.

## [0.31.0] - 2026-11-27

### Added
- **Checks**, **Compute** and **System** windows as tabs at the top: collisions with "show in 3D",
  `expect()`, diff, lint, unexpected changes, library candidates, `parts.json` editor, hook log; voxel FEM
  with stress on the model, DFM markers, optimisation with "apply", variant comparison; plugin versions,
  Python / CadQuery, RAM / disk, CLAUDE.md editor, script search.

### Changed
- Right-panel tools (Select, Measure, Section, Analyze, Notes, Versions, Params, Motion) moved to a thin
  icon rail with badge counters.

### Fixed
- Optimisation conditions such as `collisions==0` were not recognised.

## [0.30.0] - 2026-11-27

### Added
- Standard-part library V1: `place(code, at, up, anchor, spin)`, named anchors, `bolt_joint()` with stock
  length, washers, nut or tapped hole, `drill()` in any direction, catalogue search in Czech and English.
- Library growth: parts the library lacks are suggested once after an export; accepting writes a family
  skeleton to `~/.CAD4Ai/library/families`.
- Settings tabs: presets, libraries, candidates, rules, tools, skills & hooks, data.

## [0.28.2] - 2026-11-27

### Changed
- Collisions: no false alarms from solids of one part, cables / straps / hoses or thread engagements.
- Thread convention: external thread = nominal diameter, tapped hole / nut = tap drill.
- Incremental collision check (re-check 53 s → 8.6 s); shared cache with a lock.
- Model scripts import helpers from the stable `~/.CAD4Ai/lib`.
- Older history STEPs are gzip-compressed; the cache is trimmed; the script index is refreshed daily.

## [0.27.0] - 2026-11-27

### Added
- `expect()` design-intent rules (size, holes, pitch, mass, clearance, count, inside, no collisions),
  checked on the exported STEP after every run.
- Automatic `doctor` on a failing script and `lint` after writing one.
- `@cached_part` disk cache, automatic `parts.json`, `cad4ai new` skeleton, change guard.

## [0.26.0] - 2026-11-27

### Added
- `cad4ai` local CAD tools: digest and diff, all-pairs B-rep collisions, holes, distance, sections, mass,
  verify levels, script doctor, standard parts, vendor part interface, voxel FEM, DFM, optimisation,
  labelled 4-view render, search index of own scripts.
- Token-saving hooks: CAD files are not read as text; diff / validity / collisions are reported after
  a STEP export.
- `cad-tools` skill.

## [0.25.0] - 2026-11-26

### Added
- **Save project**: model, variants, script, history, notes, browser state and an offline copy of the
  viewer in one folder with `Open model.bat`.
- `start-viewer.bat` runs the viewer without Claude.

### Added later the same day (no version bump)
- Model tabs at the bottom; each tab keeps its camera.
- Right-click **Show related parameters** and **Quick change**.
- App-wide settings with explanations; checks after a parameter rebuild; parameter sweeps.
- STEP instance and per-solid colours via OCCT XCAF; axis pitch measuring; merged-face STEP export.
- **Open** button with a native file dialog.

### Changed
- One app home (`~/.CAD4Ai`) for history, settings and cache; the app folder stays clean.
- Motion, exploded views and other extras are only generated on request.

## [0.24.0] - 2026-11-26

### Added
- **Paint** tool for faces or whole parts; notes carry the painted faces with colour names.

## [0.23.0] - 2026-11-26

### Added
- Warm CadQuery process for parameter rebuilds (~3 s → ~0.2 s).
- Parameter groups, ranges, search, filters, pins and reset.

## [0.22.0] - 2026-11-26

### Added
- Dimensions with constant on-screen size, single-feature and min-distance modes, snapping,
  ΔX ΔY ΔZ legs, draggable and deletable labels.

## [0.21.0] - 2026-11-26

### Added
- Parts tree with sub-assemblies, part types and `<model>.parts.json`; group by Assembly / Type / Flat.

## [0.20.0] - 2026-11-26

### Added
- Notes for Claude carry a screenshot with labels, the script and its parameters; markers go through
  the same dialog.

## [0.19.0] - 2026-11-26

### Added
- Per-face STEP colours, axis triad, dark scrollbars.

### Changed
- Grid off by default; parts tree rows scroll sideways for long names.

## [0.18.0] - 2026-11-26

### Changed
- Renamed the plugin from `cad-preview` to **CAD4Ai** (plugin, marketplace, slash command, data folder).

## [0.17.0] and earlier - 2026-11-23

### Added
- First public version as `cad-preview`: STEP / STL viewer pane for Claude Code with parts panel,
  navigation, measurement and a marketplace manifest.

[Unreleased]: https://github.com/TheBeckeros/CAD4Ai/compare/v0.31.0...HEAD
[0.31.0]: https://github.com/TheBeckeros/CAD4Ai/releases/tag/v0.31.0
[0.30.0]: https://github.com/TheBeckeros/CAD4Ai/commit/95c8958
[0.28.2]: https://github.com/TheBeckeros/CAD4Ai/commit/fb29ced
[0.27.0]: https://github.com/TheBeckeros/CAD4Ai/commit/6adc0f7
[0.26.0]: https://github.com/TheBeckeros/CAD4Ai/commit/02dcc3c
[0.25.0]: https://github.com/TheBeckeros/CAD4Ai/commit/f7839bc
[0.24.0]: https://github.com/TheBeckeros/CAD4Ai/commit/b85e1b2
[0.23.0]: https://github.com/TheBeckeros/CAD4Ai/commit/3ee0091
[0.22.0]: https://github.com/TheBeckeros/CAD4Ai/commit/b26bea2
[0.21.0]: https://github.com/TheBeckeros/CAD4Ai/commit/838b8b2
[0.20.0]: https://github.com/TheBeckeros/CAD4Ai/commit/af3c3ae
[0.19.0]: https://github.com/TheBeckeros/CAD4Ai/commit/0480827
[0.18.0]: https://github.com/TheBeckeros/CAD4Ai/commit/2075451
[0.17.0]: https://github.com/TheBeckeros/CAD4Ai/commit/647df5a
