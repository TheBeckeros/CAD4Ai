"""Library candidates: parts in your models that would be worth turning into a library family.

Runs locally after each export (hook `cad4ai after`), no tokens unless something new is found:
- keyword families: parts whose names say what they are (aluminium profile, linear rail, spring, pulley,
  gear, hinge, DIN rail, terminal...) and that the library does not cover yet;
- repeated parts: one custom shape used >= 3 times in a model, or the same shape in >= 2 models;
- long prismatic parts (one side >= 5x the others, constant section): profiles, bars, tubes.
Everything is counted in ~/.CAD4Ai/library/candidates.json across models. A candidate is reported once
("new" -> "suggested"); the user accepts (a family skeleton is created) or dismisses it in the viewer's
Libraries tab or by `cad4ai lib accept|dismiss <id>`.
"""
import json
import os
import re
import time

from . import core

FILE = os.path.join(core.APP_HOME, "library", "candidates.json")

KEYWORDS = [
    ("alu_profile", "Aluminium slot profiles (own sizes / makers)", r"profil|extrusion|item|bosch|v-?slot|t-?slot|\b[234]0[234]0\b|\b4545\b"),
    ("linear_rail", "Linear rails and carriages", r"line[aá]rn|linear|rail|vedeni|vedení|mgn|hgr|hiwin|voz[ií]k|carriage"),
    ("spring", "Springs", r"pru[zž]in|spring"),
    ("pulley_belt", "Pulleys and belts", r"[rř]emen|belt|[rř]emenic|pulley|gt2|htd"),
    ("gear", "Gears", r"ozuben|gear|pastork|pinion|[sš]nek|worm"),
    ("hinge", "Hinges", r"pant|hinge|z[aá]v[eě]s"),
    ("handle_knob", "Handles and knobs", r"rukoje|handle|madl|knob|hlavic|kn[oó]flik"),
    ("din_rail", "DIN rail and rail devices", r"din.?li[sš]t|din.?rail|ts35|jisti[cč]|breaker|stykac|rel[eé]"),
    ("terminal", "Terminals and connectors", r"svork|terminal|konektor|connector|wago|phoenix"),
    ("cable_gland", "Cable glands", r"pr[uů]chodk|gland|vyvodk"),
    ("bushing", "Plain bushings", r"pouzdr|bushing|kluzn|igus"),
    ("magnet", "Magnets", r"magnet"),
    ("foot_leveler", "Feet and levelers", r"no[zž]k|foot|feet|leveler|stavitel"),
    ("lock_latch", "Locks and latches", r"z[aá]mek|lock|latch|z[aá]padk|uz[aá]v[eě]r"),
    ("shaft", "Shafts and axles", r"h[rř][ií]del|shaft|osa_|axle"),
    ("bracket", "Brackets and angles", r"konzol|bracket|[uú]heln[ií]k|angle_"),
    ("caster", "Wheels and casters", r"kole[cč]k|wheel|caster|kladk"),
    ("motor", "Motors (other than NEMA)", r"motor|servo|stepper"),
]
REPEAT_MIN = 8        # copies in one model (fewer: only when the shape shows up in another model)
MODELS_MIN = 2        # models with the same shape


def _load():
    try:
        with open(FILE, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {"candidates": {}}


def _save(d):
    os.makedirs(os.path.dirname(FILE), exist_ok=True)
    tmp = FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False, indent=1)
    os.replace(tmp, FILE)


def _known(inst):
    """Covered by the built-in library or a user family already?"""
    from . import std
    nm = re.sub(r"(#\d+)?(~\d+)?$", "", inst.name)
    try:
        std.dims(nm)
        return True
    except Exception:  # noqa: BLE001
        return False


def _stem(name):
    s = re.sub(r"(#\d+)?(~\d+)?$", "", name)
    s = re.sub(r"[_\-\s]*\d+$", "", s)
    return s.lower()


def _shape_sig(inst):
    vol, area, _ = core.props(inst.shape)
    bb = core.bbox(inst.shape, False) or [0] * 6
    dims = sorted(round(bb[i + 3] - bb[i], 1) for i in range(3))
    return f"{round(vol, 0)}|{round(area, 0)}|{dims}", dims, vol


def scan(step, model=None):
    """Update the registry with this model; -> list of newly reportable candidates."""
    model = model or core.load(step)
    if len(model) < 2:
        return []
    reg = _load()
    cands = reg.setdefault("candidates", {})
    key_model = os.path.abspath(step).split("@", 1)[0].lower()
    shapes = {}
    for i in model:
        if i.type in ("fastener", "bearing", "seal") or i.flexible or _known(i):
            continue
        sig, dims, vol = _shape_sig(i)
        shapes.setdefault(sig, {"names": [], "dims": dims, "vol": vol})["names"].append(i.name)
        nm = _stem(i.name)
        for fid, title, rx in KEYWORDS:
            if re.search(rx, nm, re.I):
                c = cands.setdefault(f"kw:{fid}", {"id": f"kw:{fid}", "kind": "keyword", "title": title,
                                                   "examples": [], "models": [], "count": 0, "status": "new",
                                                   "first": time.time()})
                c["count"] += 1
                if i.name not in c["examples"] and len(c["examples"]) < 8:
                    c["examples"].append(i.name)
                if key_model not in c["models"]:
                    c["models"].append(key_model)
                break
    for sig, s in shapes.items():
        dims = s["dims"]
        long = dims[2] >= 5 * max(dims[1], 0.1) and dims[1] > 0
        n = len(s["names"])
        cid = "shape:" + sig
        c = cands.get(cid)
        if c is None and n < REPEAT_MIN and not long:
            # remember single custom shapes cheaply: they become candidates when another model uses them
            c = cands.setdefault(cid, {"id": cid, "kind": "shape", "title": _stem(s["names"][0]) or "part",
                                       "examples": [], "models": [], "count": 0, "status": "watch",
                                       "dims": dims, "first": time.time()})
        elif c is None:
            c = cands.setdefault(cid, {"id": cid, "kind": "profile" if long else "repeated",
                                       "title": (_stem(s["names"][0]) or "part") + (" (long prismatic)" if long else ""),
                                       "examples": [], "models": [], "count": 0, "status": "new", "dims": dims,
                                       "first": time.time()})
        c["count"] = max(c.get("count", 0), n)
        for nm in s["names"][:8]:
            if nm not in c["examples"] and len(c["examples"]) < 8:
                c["examples"].append(nm)
        if key_model not in c["models"]:
            c["models"].append(key_model)
        if c["status"] == "watch" and len(c["models"]) >= MODELS_MIN:
            c["status"] = "new"
            c["kind"] = "reused"
    # trim: forget watched single shapes after 90 days
    old = time.time() - 90 * 86400
    for k in [k for k, c in cands.items() if c["status"] == "watch" and c.get("first", 0) < old]:
        del cands[k]
    ready = [c for c in cands.values() if c["status"] == "new" and not (c["kind"] == "keyword" and c["count"] < 2)]
    ready.sort(key=lambda c: (c["kind"] != "keyword", -len(c["models"]), -c["count"]))
    report = ready[:3]  # at most 3 per export; the rest come up on later exports
    for c in report:
        c["status"] = "suggested"
        c["suggested"] = time.time()
    # keep the registry small: at most 3000 watched single shapes (oldest dropped)
    watch = sorted((c for c in cands.values() if c["status"] == "watch"), key=lambda c: c.get("first", 0))
    for c in watch[:max(0, len(watch) - 3000)]:
        del cands[c["id"]]
    _save(reg)
    return report


def text(report):
    out = []
    for c in report:
        why = {"keyword": f"{c['count']}x in {len(c['models'])} model(s)", "repeated": f"{c['count']} copies",
               "profile": "long prismatic part", "reused": f"same shape in {len(c['models'])} models"}.get(c["kind"], "")
        out.append(f"[library] candidate '{c['title']}' ({why}; e.g. {', '.join(c['examples'][:3])}): "
                   f"ask the user once whether to create a library family (cad4ai lib accept \"{c['id']}\" | dismiss)")
    return out


def listing(include=("new", "suggested", "accepted", "dismissed")):
    return [c for c in _load().get("candidates", {}).values() if c["status"] in include]


def decide(cid, action):
    reg = _load()
    c = reg.get("candidates", {}).get(cid)
    if not c:
        raise ValueError(f"no candidate {cid}")
    out = {"ok": True, "id": cid}
    if action == "dismiss":
        c["status"] = "dismissed"
    elif action == "accept":
        from . import userlib
        fid = re.sub(r"[^a-z0-9_]+", "_", (c["id"].split(":", 1)[1] if c["kind"] == "keyword" else c["title"]).lower())[:30]
        try:
            out["family_file"] = userlib.new_family(fid, c["title"], note="examples: " + ", ".join(c["examples"][:4]))
        except FileExistsError as e:
            out["family_file"] = str(e)
        c["status"] = "accepted"
    elif action == "reset":
        c["status"] = "new"
    else:
        raise ValueError(action)
    _save(reg)
    return out
