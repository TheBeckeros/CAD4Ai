"""python viewer/test_motion.py : automatic motion from parts.json "motion" keys (cadtools/motion.py).

Synthetic assembly (CadQuery): a door whose own largest cylinder is a lock hole, hung on a fixed pin through a
carried hinge leaf; the same door exported 60 deg open with "home"; a knob made of two solids; a button cap on
a coaxial shank. When the real operator console exists on this PC (LADA PANEL/panel.step) it is checked against
the joints of its hand-written panel_motion.py as well (in a temp copy; the model folder is not touched).
"""
import json
import math
import os
import shutil
import sys
import tempfile
import time

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cadquery as cq  # noqa: E402
from cadtools import core, motion as M  # noqa: E402

PANEL = os.path.join(os.path.expanduser("~"), "Desktop", "LAĎA PANEL", "panel.step")


def door_model(open_deg=0.0):
    """Hinge line = Z axis through the origin. Closed door lies along +X at y 2..4, the body behind it (y > 6)."""
    a = cq.Assembly(name="M")
    # fixed: pin, frame-side leaf (two knuckles), body, a stop the door hits when it swings round
    a.add(cq.Workplane().circle(2).extrude(100), name="PIN")
    fl = (cq.Workplane().workplane(offset=20).circle(4).circle(2).extrude(20)
          .union(cq.Workplane().workplane(offset=60).circle(4).circle(2).extrude(20))
          .union(cq.Workplane().box(17, 2, 60, centered=False).translate((-20, 2, 20))))
    a.add(fl, name="FRAME_LEAF")
    a.add(cq.Workplane().box(200, 94, 100, centered=False).translate((0, 6, 0)), name="BODY")
    a.add(cq.Workplane().box(10, 20, 100, centered=False).translate((-40, -120, 0)), name="STOP")
    # moving: door plate with a lock hole (its only and largest cylinder), carried leaf + lock
    lock_bore = cq.Workplane("XZ", origin=(0, 10, 0)).center(180, 50).circle(6).extrude(20)
    door = cq.Workplane().box(180, 2, 100, centered=False).translate((20, 2, 0)).cut(lock_bore)
    leaf = (cq.Workplane().workplane(offset=40).circle(4).circle(2).extrude(20)
            .union(cq.Workplane().box(17, 2, 20, centered=False).translate((3, 2, 40))))
    lock = cq.Workplane("XZ", origin=(0, 5, 0)).center(180, 50).circle(6).extrude(7)  # y -2..5, body at 6
    rot = cq.Location(cq.Vector(0, 0, 0), cq.Vector(0, 0, 1), -open_deg)
    a.add(door, name="DOOR", loc=rot)
    a.add(leaf, name="DOOR_LEAF", loc=rot)
    a.add(lock, name="DOOR_LOCK", loc=rot)
    return a


def knob_button_model():
    a = cq.Assembly(name="K")
    a.add(cq.Workplane().box(200, 200, 10).translate((0, 0, -5)), name="DESK")
    # knob: hub R20 on a fixed shaft, crank grip R3 off-centre as a second solid of the same part
    hub = cq.Workplane().circle(20).extrude(15)
    grip = cq.Workplane().center(14, 0).circle(3).extrude(15).translate((0, 0, 15))
    a.add(cq.Workplane().add(cq.Compound.makeCompound([hub.val(), grip.val()])), name="KNOB",
          loc=cq.Location(cq.Vector(-50, 0, 0)))
    # button: housing ring (bore R11), shank R10 inside it, cap R10.5 sitting on the shank
    housing = cq.Workplane().circle(15).circle(11).extrude(12)
    shank = cq.Workplane().circle(10).extrude(8)
    cap = cq.Workplane().workplane(offset=8).circle(10.5).extrude(4)
    a.add(housing, name="BTN_HOUSING", loc=cq.Location(cq.Vector(50, 0, 0)))
    a.add(shank, name="BTN_SHANK", loc=cq.Location(cq.Vector(50, 0, 0)))
    a.add(cap, name="BTN_CAP", loc=cq.Location(cq.Vector(50, 0, 0)))
    return a


def run(d, name, asm, parts):
    step = os.path.join(d, name + ".step")
    asm.save(step)
    with open(os.path.join(d, name + ".parts.json"), "w", encoding="utf-8") as f:
        json.dump({"parts": parts}, f)
    core._LOADED.clear()
    joints, notes = M.build(step)
    return {j["name"]: j for j in joints}, notes, step


def parallel(a, b, sign=None):
    c = float(np.dot(np.array(a) / np.linalg.norm(a), np.array(b) / np.linalg.norm(b)))
    return abs(c - 1) < 1e-4 if sign == 1 else abs(c + 1) < 1e-4 if sign == -1 else abs(abs(c) - 1) < 1e-4


def on_line(p, origin, axis, tol=0.05):
    ax = np.array(axis, float) / np.linalg.norm(axis)
    return np.linalg.norm(np.cross(np.array(p, float) - origin, ax)) < tol


with tempfile.TemporaryDirectory() as d:
    # 1+3: closed door. Axis from the fixed pin (not the lock hole), leaf and lock carried, the frame leaf
    # touching the carried leaf must not stop it at 0
    js, notes, _ = run(d, "door", door_model(0), {"DOOR": {"motion": {"type": "door", "with": ["DOOR_"]}}})
    assert list(js) == ["DOOR"], notes
    j = js["DOOR"]
    assert set(j["parts"]) == {"DOOR", "DOOR_LEAF", "DOOR_LOCK"}, j["parts"]
    assert parallel(j["axis"], (0, 0, 1)) and on_line(j["origin"], (0, 0, 0), (0, 0, 1)), j
    assert "axis from pin" in j["note"] and "PIN" in j["note"] and "lock" not in j["note"].lower(), j["note"]
    assert "hardware not checked: FRAME_LEAF, PIN" in j["note"], j["note"]
    # opens away from the body (clockwise seen from +Z), stops on STOP after roughly 100 deg
    assert parallel(j["axis"], (0, 0, -1), sign=1), j["axis"]
    assert j["min"] == 0 and 85 < j["max"] < 112 and "STOP" in j["note"], j
    closed_axis = j["axis"]

    # 4: the same door exported 60 deg open: home 60, same opening direction, range stepped both ways
    js, notes, _ = run(d, "door_open", door_model(60),
                       {"DOOR": {"motion": {"type": "door", "home": 60, "with": ["DOOR_"]}}})
    j = js["DOOR"]
    assert j["home"] == 60 and parallel(j["axis"], closed_axis, sign=1), j
    assert j["min"] == 0 and 85 < j["max"] < 112, j

    # carrying by subassembly: the same parts without "with"
    js, notes, _ = run(d, "door_sub", door_model(0), {"DOOR": {"motion": "door", "subassembly": "Door"},
                                                       "DOOR_": {"subassembly": "Door"}})
    j = js["DOOR"]
    assert set(j["parts"]) == {"DOOR", "DOOR_LEAF", "DOOR_LOCK"} and j["max"] > 85, j

    # 2+5: knob of two solids = one joint on the hub axis; cap pressed over its shank, stopped by nothing else
    js, notes, _ = run(d, "kb", knob_button_model(), {"KNOB": {"motion": "knob"}, "BTN_CAP": {"motion": "press"}})
    assert set(js) == {"KNOB", "BTN_CAP"}, list(js)
    k = js["KNOB"]
    assert sorted(k["parts"]) == ["KNOB#1", "KNOB#2"], k["parts"]
    assert parallel(k["axis"], (0, 0, 1)) and on_line(k["origin"], (-50, 0, 0), (0, 0, 1)), k
    b = js["BTN_CAP"]
    assert parallel(b["axis"], (0, 0, -1), sign=1), b["axis"]
    assert b["max"] >= 1.0 and "BTN_SHANK" in b["note"], b

    # generated file: home kept, door animation goes home -> both ends -> home
    _, _, step = run(d, "door_open2", door_model(60),
                     {"DOOR": {"motion": {"type": "door", "home": 60, "with": ["DOOR_"]}}})
    r = M.generate(step)
    data = json.load(open(r["file"], encoding="utf-8"))
    kf = data["animations"][0]["keyframes"]
    vals = [k["values"]["DOOR"] for k in kf]
    assert vals[0] == 60 and vals[-1] == 60 and min(vals) == 0 and max(vals) > 85, vals

print("synthetic: ok")

if os.path.isfile(PANEL):
    t0 = time.time()
    with tempfile.TemporaryDirectory() as d:
        step = os.path.join(d, "panel.step")
        shutil.copy(PANEL, step)
        acc = ["DVIRKA_VYZTUHA", "TESNENI_DVIREK", "DORAZ_STLACENI", "ZAMEK_CTVRTOTACKOVY_", "PANT_LIST_DVIRKA",
               "SROUB_ISO7380_M4x10_DVIRKA", "MATICE_SLEPA_ZAVRTNA_M4", "PE_SVORNIK_KRYT", "OKO_LANKA_KRYT"]
        parts = {"ZADNI_DVERE": {"motion": {"type": "door", "home": 80, "with": ["ZD_"]}},
                 "DVIRKA_SERVISNI": {"motion": "door", "subassembly": "Servisni dvirka"},
                 "ZAS_vicko": {"motion": "lid"},
                 "KOLECKO_knoflik_": {"motion": "knob"},
                 "TL_hmatnik_": {"motion": "press"}}
        parts.update({p: {"subassembly": "Servisni dvirka"} for p in acc})
        with open(os.path.join(d, "panel.parts.json"), "w", encoding="utf-8") as f:
            json.dump({"parts": parts}, f)
        core._LOADED.clear()
        joints, notes = M.build(step)
        js = {j["name"]: j for j in joints}
        # reference: panel_motion.py (axes from ZP_PANT_CEP / PANT_CEP / ZAS_pant_vicka, knob axis, home 80)
        ref = {"ZADNI_DVERE": ((304.0, 0.0, -351.0), (0, -1, 0), 80),
               "DVIRKA_SERVISNI": ((273.5, -538.347, -310.815), (0, -0.5, 0.866025), 0),
               "ZAS_vicko": ((312.5, -215.0, 0.0), (0, 0, 1), 0),
               "KOLECKO_knoflik_2": ((-204.5, -296.25, 513.12), (0, 0.866025, 0.5), 0),
               "KOLECKO_knoflik_3": ((204.5, -296.25, 513.12), (0, 0.866025, 0.5), 0)}
        for n, (o, ax, home) in ref.items():
            j = js[n]
            assert parallel(j["axis"], ax, sign=None if n.startswith("KOLECKO") else 1), (n, j["axis"])
            assert on_line(j["origin"], np.array(o), ax, 0.1), (n, j["origin"])
            assert j["home"] == home and j["max"] - j["min"] >= 90, (n, j["min"], j["max"])
        assert len(js["KOLECKO_knoflik_2"]["parts"]) == 2
        assert len(js["ZADNI_DVERE"]["parts"]) > 15 and len(js["DVIRKA_SERVISNI"]["parts"]) > 20
        assert js["ZADNI_DVERE"]["min"] == 0 and js["ZADNI_DVERE"]["max"] >= 110
        btn = [j for n, j in js.items() if n.startswith("TL_hmatnik_")]
        assert len(btn) == 10 and all(b["max"] > 1 and parallel(b["axis"], (0, -0.866025, -0.5), 1) for b in btn)
    print(f"panel: ok ({time.time() - t0:.0f} s)")
else:
    print("panel: skipped (no LADA PANEL/panel.step on this PC)")
print("test_motion: all ok")
