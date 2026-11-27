"""Unintended-change guard: after a rebuild, parts that changed although nothing that drives them changed.

The script's parameter values are remembered per model. When only parameters changed (the code outside
the parameter block is the same), every part that changed is checked against the parameters that drive it
(related.py: name lookup + backward slice). A changed part none of whose driving parameters changed is
reported as "unexpected". When the code itself changed, only an unusually broad change is reported
(more than half of the parts and at least 4).
"""
import hashlib
import json
import os
import re

from . import core

PARAM_LINE = re.compile(r"^[A-Z][A-Z0-9_]*\s*=\s*[-+]?[\d.eE+-]+(\s*#.*)?$|^[A-Z][A-Z0-9_]*\s*=\s*(True|False)(\s*#.*)?$")


def _script_for(step):
    folder = os.path.dirname(os.path.abspath(step))
    stem = os.path.splitext(os.path.basename(step))[0].split("@", 1)[0]
    best = None
    for n in os.listdir(folder):
        if n.endswith(".py") and not n.startswith(".cad4ai_"):
            p = os.path.join(folder, n)
            try:
                with open(p, encoding="utf-8", errors="replace") as f:
                    src = f.read()
            except OSError:
                continue
            if stem + ".step" in src or f'"{stem}' in src:
                m = os.path.getmtime(p)
                if best is None or m > best[0]:
                    best = (m, p)
    return best[1] if best else None


def _snapshot(script):
    with open(script, encoding="utf-8", errors="replace") as f:
        src = f.read()
    vals, body = {}, []
    for line in src.split("\n"):
        s = line.strip()
        if PARAM_LINE.match(s):
            k, v = s.split("=", 1)
            vals[k.strip()] = v.split("#", 1)[0].strip()
        else:
            body.append(line)
    return vals, hashlib.sha1("\n".join(body).encode()).hexdigest()


def _state(step):
    return os.path.join(core.CACHE, "guard", core.model_key(step.split("@", 1)[0]) + ".json")


def check(step, diff_lines, parts_n):
    """-> list of warning lines (may be empty). Call after the diff of this rebuild was computed."""
    script = _script_for(step)
    if not script:
        return []
    vals, body = _snapshot(script)
    sp = _state(step)
    try:
        with open(sp, encoding="utf-8") as f:
            old = json.load(f)
    except (OSError, ValueError):
        old = None
    key = core.file_key(step)
    if old and old.get("key") == key:
        return old.get("result", [])  # this version was already judged (hook and manual call)
    res = _judge(step, script, vals, body, old, diff_lines, parts_n)
    os.makedirs(os.path.dirname(sp), exist_ok=True)
    with open(sp, "w", encoding="utf-8") as f:
        json.dump({"vals": vals, "body": body, "script": script, "key": key, "result": res}, f)
    return res


def _judge(step, script, vals, body, old, diff_lines, parts_n):
    if not old or old.get("script") != script:
        return []
    changed_parts = [m.group(1) for m in (re.match(r"^[~+-] (.+?):", l) for l in diff_lines) if m]
    if not changed_parts:
        return []
    if old["body"] != body:
        if parts_n >= 4 and len(changed_parts) > parts_n / 2:
            return [f"note: {len(changed_parts)} of {parts_n} parts changed by this code edit - check it was meant to be that broad"]
        return []
    changed_params = {k for k in set(vals) | set(old["vals"]) if vals.get(k) != old["vals"].get(k)}
    if not changed_params:
        return [f"UNEXPECTED: geometry of {', '.join(changed_parts[:6])} changed but the script did not (external file/module?)"]
    import sys
    sys.path.insert(0, core.HERE)
    from related import related
    warn = []
    for part in changed_parts[:30]:
        try:
            r = related(script, part, (), set(vals), None)
            drivers = {p["name"] for p in r.get("params", [])}
        except Exception:  # noqa: BLE001
            continue
        if not r.get("found"):
            continue  # cannot tell which parameters drive it
        if drivers and not (drivers & changed_params):
            warn.append(part)
    if warn:
        return [f"UNEXPECTED change: {', '.join(warn[:8])} - not driven by the changed parameters "
                f"({', '.join(sorted(changed_params)[:6])}); check side effects"]
    return []
