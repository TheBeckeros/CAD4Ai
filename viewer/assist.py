"""Token-saving helpers of the viewer: app-wide settings, the shape of a note for Claude, model hints,
local checks after a rebuild and parameter sweeps (variants without Claude).

Everything the app keeps for itself lives in one folder, ~/.CAD4Ai (CAD4AI_HOME overrides it):
settings.json (whole app) and history/<model key>/<version> (versions of every model, trimmed to
history.keep). Model files, their variants and side files (.parts.json, .motion.json...) stay next to
the model; per-session notes and screenshots stay in the session's .CAD4Ai/s-xxx folder.
"""
import json
import os
import re
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
APP_HOME = os.environ.get("CAD4AI_HOME") or os.path.join(os.path.expanduser("~"), ".CAD4Ai")
SETTINGS_FILE = os.path.join(APP_HOME, "settings.json")
_OLD_SETTINGS = os.path.join(os.path.expanduser("~"), ".CAD4Ai-settings.json")
if not os.path.isfile(SETTINGS_FILE) and os.path.isfile(_OLD_SETTINGS):
    os.makedirs(APP_HOME, exist_ok=True)
    os.replace(_OLD_SETTINGS, SETTINGS_FILE)

DEFAULTS = {
    "note.parts": "nearby",       # all | nearby | none
    "note.params": "related",     # all | related | none
    "note.scriptMap": True,
    "note.screenshot": True,
    "note.modelHint": True,
    "note.contextFile": False,
    "related.byValue": True,
    "related.max": 12,
    "checks.afterRebuild": "basic",   # off | basic | full
    "quick.screenshot": False,
    "history.keep": 30,               # versions kept per model
}


def load_settings():
    try:
        with open(SETTINGS_FILE, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        data = {}
    return {**DEFAULTS, **{k: v for k, v in data.items() if k in DEFAULTS}}


def save_settings(values):
    cur = load_settings()
    for k, v in (values or {}).items():
        if k not in DEFAULTS:
            continue
        d = DEFAULTS[k]
        if isinstance(d, bool):
            v = bool(v)
        elif isinstance(d, int):
            v = int(v)
        else:
            v = str(v)
        cur[k] = v
    os.makedirs(APP_HOME, exist_ok=True)
    tmp = SETTINGS_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(cur, f, indent=1)
    os.replace(tmp, SETTINGS_FILE)
    return cur


# ---------------------------------------------------------------- notes

def _rel(script, part, values, params, settings):
    from related import related
    names = {p["name"] for p in params}
    vals = {p["name"]: p["value"] for p in params}
    return related(script, part, values if settings["related.byValue"] else (), names, vals)


def related_for(script, parts, values, params, settings):
    """Merged related parameters and script lines for several parts (best score wins)."""
    best, lines = {}, []
    for part in (parts or [None])[:4]:
        r = _rel(script, part, values, params, settings)
        for p in r["params"]:
            if p["score"] > best.get(p["name"], {}).get("score", 0):
                best[p["name"]] = p
        lines += r["lines"]
    seen, uniq = set(), []
    for ln in lines:
        k = (ln["file"], ln["from"], ln["to"])
        if k not in seen:
            seen.add(k)
            uniq.append(ln)
    return sorted(best.values(), key=lambda x: -x["score"]), uniq


def _note_parts(body):
    """Parts the note is about (selected features, strokes, markers, paint, the anchor)."""
    out = []
    for key in ("features", "strokes", "markers", "paint"):
        for x in body.get(key) or []:
            p = x.get("part")
            if isinstance(p, str) and p and p not in out:
                out.append(p)
    if isinstance(body.get("anchorPart"), str) and body["anchorPart"] not in out:
        out.insert(0, body["anchorPart"])
    return out


def _note_values(body):
    vals = []
    for f in body.get("features") or []:
        for k in ("diameter", "radius", "length", "width", "height"):
            if isinstance(f.get(k), (int, float)):
                vals.append(f[k])
    for m in body.get("measurements") or []:
        if isinstance(m.get("value"), (int, float)):
            vals.append(m["value"])
    return vals[:12]


def _script_lines(script):
    try:
        with open(script, encoding="utf-8") as f:
            return sum(1 for _ in f)
    except OSError:
        return 0


def model_hint(body, script, n_lines, n_parts, quick=False):
    """A rough guide to the cheapest model that should do the request on the first try."""
    text = (body.get("comment") or "").lower()
    big = n_lines > 400 or n_parts > 50
    new_geo = re.search(r"\b(přidej|pridej|nový|novy|navrhni|add|new|design|redesign|předělej|predelej|sestav|assembly)\b", text)
    number = re.search(r"\d", text) and len(text) < 120
    if quick and number and not new_geo:
        return "a small edit (a value or one feature): Haiku or Sonnet at low effort is enough"
    if new_geo or (big and len(text) > 200):
        return "new or structural geometry" + (" in a large script" if big else "") + ": Opus at medium effort"
    if big:
        return "a local change in a large model: Sonnet at medium effort; read only the script map lines"
    return "a local change in a small model: Sonnet at low effort is enough"


def shape_note(body, cur, params_all, settings, quick=False):
    """Trim and enrich an annotation before it goes to the inbox, according to the settings."""
    script = cur.get("script")
    hints = []
    parts_all = body.get("parts") or []
    near = body.pop("nearParts", None)
    mode = settings["note.parts"]
    if mode == "none" and len(parts_all) > 1:
        body["parts"] = []
        hints.append(f"Assembly of {len(parts_all)} parts (names left out to save tokens; see the parts tree or the .step).")
    elif mode == "nearby" and near is not None and len(parts_all) > 25:
        body["parts"] = near[:40]
        if len(parts_all) > len(body["parts"]):
            hints.append(f"Parts listed: only the {len(body['parts'])} near the marked place; the assembly has {len(parts_all)}.")
    note_parts = _note_parts(body)
    if script:
        pm = settings["note.params"]
        rel, lines = ([], [])
        if pm == "related" or settings["note.scriptMap"]:
            try:
                rel, lines = related_for(script, note_parts, _note_values(body), params_all, settings)
            except Exception as e:  # noqa: BLE001 - a script that does not parse must not lose the note
                hints.append(f"(related parameters not found: {type(e).__name__})")
        fmt = {p["name"]: f"{p['name']} = {p['value']}" + (f" [{p['unit']}]" if p.get("unit") else "") for p in params_all}
        if pm == "all":
            body["params"] = list(fmt.values())[:60]
        elif pm == "none":
            body["params"] = []
            hints.append(f"Parameters: {len(params_all)} at the top of the script (left out to save tokens).")
        else:
            top = [p for p in rel if p["score"] >= 0.3][: settings["related.max"]]
            body["params"] = [fmt[p["name"]] for p in top if p["name"] in fmt]
            rest = len(params_all) - len(body["params"])
            if rest > 0:
                hints.append(f"Parameters: listed only the ones related to the marked place; {rest} more at the top of the script.")
        if settings["note.scriptMap"] and lines:
            sd = os.path.dirname(script)
            spans = ", ".join(f"{os.path.relpath(l['file'], sd)}:{l['from']}-{l['to']}" for l in lines[:12])
            hints.append(f"Script map (where these parts are built; read these lines first, not the whole script): {spans}")
        if settings["note.contextFile"]:
            ctx = os.path.splitext(script)[0] + ".context.md"
            if os.path.isfile(ctx):
                hints.append(f"Project context: {ctx} (read it before the script; keep it up to date in a few lines when the structure changes)")
            elif _script_lines(script) > 300:
                hints.append(f"Project context: none yet. After this change write {ctx}: max ~40 lines, what each function/module builds and its line ranges, naming rules.")
    if settings["note.modelHint"]:
        hints.append("Suggested model: " + model_hint(body, script, _script_lines(script) if script else 0, len(parts_all), quick))
    if hints:
        body["hints"] = hints
    return body


# ---------------------------------------------------------------- checks after a rebuild

CHECK_CACHE = {}


def check_model(step):
    """B-rep validity and volume of every part (subprocess, CadQuery). Cached by file time."""
    key = (os.path.abspath(step), os.path.getmtime(step))
    if key in CHECK_CACHE:
        return CHECK_CACHE[key]
    if len(CHECK_CACHE) >= 16:
        CHECK_CACHE.pop(next(iter(CHECK_CACHE)))
    r = subprocess.run([sys.executable, "-B", os.path.join(HERE, "checks.py"), step], capture_output=True, text=True,
                       timeout=600, encoding="utf-8")
    try:
        res = json.loads(r.stdout.strip().splitlines()[-1])
    except (ValueError, IndexError):
        res = {"ok": False, "error": (r.stderr or r.stdout or "check failed")[-400:]}
    CHECK_CACHE[key] = res
    return res


# ---------------------------------------------------------------- sweeps

def sweep(cur, name, values, write_params, run_script, parse_params):
    """Rebuild the model for each value of one parameter, saving <model>@<NAME>=<v>.step; then restore."""
    script, step = cur.get("script"), cur.get("step") or cur.get("path")
    if not script or not step or not step.lower().endswith((".step", ".stp")):
        raise ValueError("needs a parametric script that exports a .step")
    p = next((x for x in parse_params(script) if x["name"] == name), None)
    if not p or p["type"] == "bool":
        raise ValueError(f"no numeric parameter {name}")
    if not 1 <= len(values) <= 12:
        raise ValueError("1 to 12 values")
    base = os.path.splitext(step)[0].split("@", 1)[0]
    ext = os.path.splitext(step)[1]
    made, errors = [], []
    try:
        for v in values:
            write_params(script, {name: v})
            res = run_script(script)
            if not res.get("ok"):
                errors.append(f"{v}: {(res.get('error') or res.get('stderr') or 'failed')[-200:]}")
                continue
            label = f"{name}={('%g' % v)}"
            out = f"{base}@{label}{ext}"
            shutil.copy2(step, out)
            made.append(out)
    finally:
        write_params(script, {name: p["value"]})
        run_script(script)
    return {"ok": bool(made), "made": made, "errors": errors}
