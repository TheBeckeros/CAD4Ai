"""Claude Code hooks of CAD4Ai (token savers). Reads the hook JSON on stdin, prints the hook answer.

  start  SessionStart: one line telling Claude where the cad4ai tools are.
  pre    PreToolUse(Read): refuse reading .step/.stp/.stl/.iges/.brep as text (huge, useless tokens);
         point to `cad4ai summary` instead.
  post   PostToolUse / PostToolUseFailure (Bash|PowerShell):
         - a CadQuery script the command ran ended with a traceback -> `cad4ai doctor` runs at once and
           Claude gets the failing line, the cause and a working value (no trial-and-error rounds);
         - .step files under the working folder changed -> `cad4ai after` (diff, validity, collisions,
           expect() results, unrelated changes, parts.json filled in).
  edit   PostToolUse(Write|Edit): a CadQuery script was written -> `cad4ai lint`; only warnings are reported.
Set CAD4AI_HOOKS=0 to switch them off.
"""
import hashlib
import json
import os
import re
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
CLI = os.path.join(HERE, "cad4ai.py")
APP_HOME = os.environ.get("CAD4AI_HOME") or os.path.join(os.path.expanduser("~"), ".CAD4Ai")
CAD_EXT = (".step", ".stp", ".stl", ".iges", ".igs", ".brep", ".3mf", ".obj")
SKIP = {".git", "node_modules", "__pycache__", "venv", ".venv", ".CAD4Ai", "history"}
PY_IN_CMD = re.compile(r"\"([^\"]+\.py)\"|'([^']+\.py)'|(\S+\.py)\b")


def out(obj):
    sys.stdout.write(json.dumps(obj, ensure_ascii=False))


def start(_):
    out({"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext":
         f'CAD4Ai local tools (heavy work on this PC, short JSON back): python "{CLI}" <summary|diff|collide|holes|dist|'
         'section|mass|verify|doctor|lint|new|std|vendor|fem|dfm|optimize|views|find> ... (skill cad-tools). '
         'Hooks already report: doctor on a failing script, diff/validity/collisions/expect() after a .step export, '
         'lint after writing a script.'}})


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


def _run_cli(args, timeout=150):
    try:
        r = subprocess.run([sys.executable, "-B", CLI] + args, capture_output=True, text=True, encoding="utf-8",
                           errors="replace", timeout=timeout, creationflags=0x08000000 if os.name == "nt" else 0)
        return r.stdout.strip() or r.stderr.strip()[-300:]
    except subprocess.TimeoutExpired:
        return None


def _is_cq(path):
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            return "cadquery" in f.read()
    except OSError:
        return False


def _failed_script(ev, cwd):
    """A CadQuery script the command ran, if the command output shows a Python traceback."""
    resp = ev.get("tool_response")
    text = (resp if isinstance(resp, str) else json.dumps(resp, ensure_ascii=False)) + str(ev.get("error") or "")
    if "Traceback" not in text:
        return None
    cmd = str((ev.get("tool_input") or {}).get("command", ""))
    for m in PY_IN_CMD.finditer(cmd):
        p = next(g for g in m.groups() if g)
        p = p if os.path.isabs(p) else os.path.join(cwd, p)
        if os.path.isfile(p) and not os.path.basename(p).startswith((".cad4ai_", "cad4ai", "cc_hook")) and _is_cq(p):
            return p
    return None


def _doctor_text(script):
    raw = _run_cli(["doctor", script], timeout=170)
    if not raw:
        return f"[CAD4Ai doctor] {os.path.basename(script)}: diagnosis took too long"
    try:
        d = json.loads(raw.splitlines()[-1])
    except ValueError:
        return "[CAD4Ai doctor] " + raw[-400:]
    if d.get("ok"):
        return None  # the failure was not in the model script
    L = [f"[CAD4Ai doctor] {os.path.basename(script)} line {d.get('line')}: {d.get('error')}"]
    if d.get("code"):
        L.append(f"  code: {d['code']}")
    L.append(f"  category: {d.get('category')}" + (f" - {d['hint']}" if d.get("hint") else ""))
    if d.get("fix"):
        L.append(f"  FIX: {d['fix']}")
    if d.get("without_this_line"):
        L.append(f"  without this line: {d['without_this_line']}")
    if d.get("file") and os.path.abspath(d["file"]).lower() != os.path.abspath(script).lower():
        L.append(f"  (failing line is in {d['file']})")
    return "\n".join(L)


def post(ev):
    cwd = ev.get("cwd") or os.getcwd()
    event = ev.get("hook_event_name") or "PostToolUse"
    home = os.path.expanduser("~")
    if os.path.abspath(cwd).lower() in (home.lower(), os.path.abspath(os.sep).lower()):
        return
    reports = []
    bad = _failed_script(ev, cwd)
    if bad:
        t = _doctor_text(bad)
        if t:
            reports.append(t)
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
    for p in steps[:2]:
        txt = _run_cli(["after", p])
        reports.append(txt or f"[CAD4Ai] {os.path.basename(p)}: check took too long; run cad4ai verify manually")
    if len(steps) > 2:
        reports.append(f"[CAD4Ai] +{len(steps) - 2} more changed STEP files not checked")
    if reports:
        out({"hookSpecificOutput": {"hookEventName": event, "additionalContext": "\n".join(reports)[:3500]}})


def edit(ev):
    p = (ev.get("tool_input") or {}).get("file_path", "")
    if not p.lower().endswith(".py") or not os.path.isfile(p) or not _is_cq(p):
        return
    txt = _run_cli(["lint", p], timeout=30)
    if txt and "no issues" not in txt:
        out({"hookSpecificOutput": {"hookEventName": ev.get("hook_event_name") or "PostToolUse",
                                    "additionalContext": txt[:2000]}})


def main():
    if os.environ.get("CAD4AI_HOOKS") == "0":
        return
    mode = sys.argv[1] if len(sys.argv) > 1 else ""
    try:
        ev = json.load(sys.stdin)
    except ValueError:
        ev = {}
    {"start": start, "pre": pre, "post": post, "edit": edit}.get(mode, lambda e: None)(ev)


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:  # noqa: BLE001
        pass
    try:
        main()
    except Exception:  # noqa: BLE001 - a hook must never break Claude's work
        pass
