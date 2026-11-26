# CAD4Ai

Interactive 3D CAD preview for Claude Code: the CAD4Ai plugin (viewer, notes, parameters, versions, motion and skills).

Install locally: claude plugin marketplace add <path to this repo> then claude plugin install CAD4Ai@CAD4Ai --scope user.

## Where data is stored

This folder holds only the app; working on models never writes into it.

| What | Where |
|---|---|
| Models, design variants (`name@label.step`), side files (`.parts.json`, `.motion.json`, `.explode.json`, `.context.md`) | next to the model |
| Versions of every model (STEP + script per rebuild or export), trimmed to *Settings → Versions kept per model* | `~/.CAD4Ai/history/<model key>/` |
| App settings | `~/.CAD4Ai/settings.json` |
| Notes for Claude and their screenshots | the Claude session's folder, `<session cwd>/.CAD4Ai/s-xxx/` |
| Open model tabs, pinned parameters | the browser (local storage) |

`CAD4AI_HOME` moves `~/.CAD4Ai` elsewhere. Version histories left in older session folders are moved to
`~/.CAD4Ai/history` when the viewer starts, and empty session folders older than 30 days are removed.
