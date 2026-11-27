"""Read-only report of a model for the viewer's Checks window: what the hooks told Claude, structured.

Nothing is recomputed that is already cached (digest, collisions); nothing is changed (no "remember",
no guard update, no parts.json writing) - so opening the window never shifts what the next diff shows.
"""
import json
import os

from . import core


def _script_for(step):
    from .guard import _script_for as sf
    try:
        return sf(step)
    except OSError:
        return None


def build(step):
    from . import digest, collide, guard, lint, libscan, expect
    d = digest.digest(step)
    prev = digest.previous(step)
    out = {"ok": True, "model": step, "name": os.path.basename(step), "parts_n": d["parts_n"], "size": d["size"],
           "mass_g": d["mass_g"], "invalid": d["invalid"], "diff": digest.diff(prev, d) if prev else [],
           "parts": [{"name": p["name"], "size": p["size"], "mass_g": p["mass_g"], "type": p.get("type", ""),
                      "material": p.get("material", ""), "holes": sum(g["n"] for g in p.get("holes", []))}
                     for p in d["parts"][:2000]]}
    # expect() results of the run that produced this file
    try:
        with open(expect.result_file(step), encoding="utf-8") as f:
            ex = json.load(f)
        if ex.get("key") == core.file_key(step):
            out["expect"] = {"text": ex["text"], "ok": ex["ok"], "n": ex["n"], "deferred": ex.get("deferred", [])}
    except (OSError, ValueError, KeyError):
        pass
    # collisions (cached; the hook computed them already in most cases)
    if 1 < d["parts_n"] <= 5000:
        c = collide.check(step, 0.0)
        out["collisions"] = {k: c[k] for k in ("collisions", "fastener_overlaps", "expected_fastener_overlaps",
                                               "flexible_contacts", "expected_flexible_contacts", "self_overlaps",
                                               "touching_n", "pairs_checked", "pairs_reused") if k in c}
        res = []
        for rule in (out.get("expect") or {}).get("deferred", []):
            names = None if rule["names"] == ["*"] else rule["names"]
            cc = c if not names else collide.check(step, 0.0, names)
            bad = cc["collisions"] + ([] if rule.get("ignore", True) else cc["fastener_overlaps"])
            res.append({"rule": ",".join(rule["names"]) + ".no_collisions", "ok": not bad,
                        "bad": [f"{x['a']} x {x['b']} {x['overlap_mm3']} mm3" for x in bad[:6]]})
        out["expect_deferred"] = res
    # guard verdict stored for exactly this version
    try:
        with open(guard._state(step), encoding="utf-8") as f:
            g = json.load(f)
        if g.get("key") == core.file_key(step):
            out["guard"] = g.get("result", [])
    except (OSError, ValueError):
        pass
    script = _script_for(step)
    if script:
        out["script"] = script
        out["lint"] = [{"line": ln, "level": lv, "msg": m} for ln, lv, m in lint.lint(script)]
    key = os.path.abspath(step).split("@", 1)[0].lower()
    out["candidates"] = [c for c in libscan.listing(("new", "suggested")) if key in c.get("models", [])][:20]
    out["parts_json"] = core.parts_info(step)
    return out


def variants(step):
    """All design variants of a model (name@label.step) side by side."""
    from . import digest, collide
    import glob
    base = os.path.splitext(step)[0].split("@", 1)[0]
    files = sorted(set([base + ".step"] + glob.glob(glob.escape(base) + "@*.step")))
    rows = []
    for f in files:
        if not os.path.isfile(f):
            continue
        try:
            d = digest.digest(f)
            c = collide.check(f, 0.0) if 1 < d["parts_n"] <= 5000 else {"collisions": []}
            ex = None
            from . import expect
            try:
                with open(expect.result_file(f), encoding="utf-8") as fh:
                    e = json.load(fh)
                ex = f"{e['ok']}/{e['n']}" if e.get("key") == core.file_key(f) else None
            except (OSError, ValueError, KeyError):
                pass
            label = os.path.splitext(os.path.basename(f))[0].split("@", 1)[1] if "@" in os.path.basename(f) else "(main)"
            rows.append({"file": f, "label": label, "parts": d["parts_n"], "size": d["size"], "mass_g": d["mass_g"],
                         "invalid": len(d["invalid"]), "collisions": len(c["collisions"]), "expect": ex})
        except Exception as e:  # noqa: BLE001
            rows.append({"file": f, "label": os.path.basename(f), "error": f"{type(e).__name__}: {e}"})
    return {"ok": True, "variants": rows}


def save_parts_json(step, updates):
    """Merge {part: {key: value}} into <model>.parts.json (empty value removes the key)."""
    p = os.path.splitext(step)[0].split("@", 1)[0] + ".parts.json"
    try:
        with open(p, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        data = {}
    parts = data.setdefault("parts", {})
    for name, kv in (updates or {}).items():
        e = parts.setdefault(name, {})
        for k, v in kv.items():
            if k not in ("type", "material", "standard", "subassembly"):
                continue
            if v in (None, ""):
                e.pop(k, None)
            else:
                e[k] = str(v)
        if not e:
            parts.pop(name, None)
    with open(p, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    return {"ok": True, "file": p, "parts": len(parts)}
