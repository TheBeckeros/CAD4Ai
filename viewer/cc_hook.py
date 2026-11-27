"""Claude Code hooks of CAD4Ai (token savers). Reads the hook JSON on stdin, prints the hook answer.

  start  SessionStart: one line telling Claude where the cad4ai tools are.
  pre    PreToolUse(Read): refuse reading .step/.stp/.stl/.iges/.brep as text (huge, useless tokens);
         point to `cad4ai summary` instead.
  post   PostToolUse(Bash|PowerShell): if a command just wrote/changed .step files under the working folder,
         run `cad4ai after` on them (diff to the previous version, B-rep validity, collisions) and hand
         Claude the few-line result, so it needs no screenshot or check script to see what changed.
Set CAD4AI_HOOKS=0 to switch them off.
"""
import hashlib
import json
import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
CLI = os.path.join(HERE, "cad4ai.py")
APP_HOME = os.environ.get("CAD4AI_HOME") or os.path.join(os.path.expanduser("~"), ".CAD4Ai")
CAD_EXT = (".step", ".stp", ".stl", ".iges", ".igs", ".brep", ".3mf", ".obj")
SKIP = {".git", "node_modules", "__pycache__", "venv", ".venv", ".CAD4Ai", "history"}


def out(obj):
    sys.stdout.write(json.dumps(obj, ensure_ascii=False))


def start(_):
    out({"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext":
         f'CAD4Ai local tools (heavy work on this PC, short JSON back): python "{CLI}" <summary|diff|collide|holes|dist|'
         'section|mass|verify|doctor|std|vendor|fem|dfm|optimize|views|find> ... (skill cad-tools). '
         'After a script exports a .step, a hook already reports diff/validity/collisions.'}})


def pre(ev):
    p = (ev.get("tool_input") or {}).get("file_path", "")
    if p.lower().endswith(CAD_EXT):
        out({"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny",
             "permissionDecisionReason": f'CAD files are not read as text (tokens). Use: python "{CLI}" summary "{p}" '
                                         '(or holes/dist/section/views).'}})


def _state_file(cwd):
    return os.path.join(APP_HOME, "cache", "hook", hashlib.sha1(cwd.lower().encode()).hexdigest()[:16] + ".json")


def _recent_steps(cwd, since, limit=4000):
    found, seen = [], 0
    base_depth = cwd.rstrip("\\/").count(os.sep)
    for root, dirs, files in os.walk(cwd):
        dirs[:] = [d for d in dirs if d not in SKIP and not d.startswith(".")]
        if root.count(os.sep) - base_depth >= 4:
            dirs[:] = []
        for f in files:
            seen += 1
            if f.lower().endswith((".step", ".stp")) and "@" not in f:
                p = os.path.join(root, f)
                try:
                    if os.path.getmtime(p) > since:
                        found.append(p)
                except OSError:
                    pass
        if seen > limit:
            break
    return sorted(found, key=os.path.getmtime, reverse=True)


def post(ev):
    cwd = ev.get("cwd") or os.getcwd()
    home = os.path.expanduser("~")
    if os.path.abspath(cwd).lower() in (home.lower(), os.path.abspath(os.sep).lower()):
        return
    sf = _state_file(cwd)
    try:
        with open(sf, encoding="utf-8") as f:
            since = json.load(f)["t"]
    except (OSError, ValueError, KeyError):
        since = time.time() - 120
    now = time.time()
    steps = _recent_steps(cwd, since)
    os.makedirs(os.path.dirname(sf), exist_ok=True)
    with open(sf, "w", encoding="utf-8") as f:
        json.dump({"t": now}, f)
    if not steps:
        return
    reports = []
    for p in steps[:2]:
        try:
            r = subprocess.run([sys.executable, "-B", CLI, "after", p], capture_output=True, text=True, encoding="utf-8",
                               errors="replace", timeout=150, creationflags=0x08000000 if os.name == "nt" else 0)
            txt = r.stdout.strip() or r.stderr.strip()[-300:]
        except subprocess.TimeoutExpired:
            txt = f"[CAD4Ai] {os.path.basename(p)}: check took too long; run cad4ai verify manually"
        reports.append(txt)
    if len(steps) > 2:
        reports.append(f"[CAD4Ai] +{len(steps) - 2} more changed STEP files not checked")
    out({"hookSpecificOutput": {"hookEventName": "PostToolUse", "additionalContext": "\n".join(reports)[:3000]}})


def main():
    if os.environ.get("CAD4AI_HOOKS") == "0":
        return
    mode = sys.argv[1] if len(sys.argv) > 1 else ""
    try:
        ev = json.load(sys.stdin)
    except ValueError:
        ev = {}
    {"start": start, "pre": pre, "post": post}.get(mode, lambda e: None)(ev)


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:  # noqa: BLE001
        pass
    try:
        main()
    except Exception:  # noqa: BLE001 - a hook must never break Claude's work
        pass
