"""Self-check of the closed-loop solvers in joints.py: python test_joints.py"""
import json
import math
import os
import subprocess
import sys
import tempfile

from joints import rot

HERE = os.path.dirname(os.path.abspath(__file__))


def run(*args):
    out = os.path.join(tempfile.mkdtemp(), "m.json")
    subprocess.run([sys.executable, os.path.join(HERE, "joints.py"), args[0], out, *args[1:]], check=True, capture_output=True)
    return [f["values"] for f in json.load(open(out))["animations"][0]["keyframes"]]


k = [0, 0, 1]
# four-bar: the coupler carried by the crank must land on the rocker pin, links keep their length
A, B0, C0, D = [0, 0, 0], [10, 0, 0], [30, 35, 0], [40, 0, 0]
for v in run("four-bar", "--axis", "0,0,1", "--a", "0,0,0", "--b", "10,0,0", "--c", "30,35,0", "--d", "40,0,0",
             "--crank", "c", "--coupler", "cp", "--rocker", "rk", "--steps", "72"):
    B, C = rot(B0, A, k, v["crank"]), rot(C0, D, k, v["rocker"])
    assert abs(math.dist(B, C) - math.dist(B0, C0)) < 1e-3, v
    assert math.dist(C, rot(rot(C0, A, k, v["crank"]), B, k, v["coupler"])) < 1e-2, v

# slider-crank r25 l90 on the Z axis: stroke = 2r, rod end stays on the crank pin
P0, W0 = [0, 16.07, 19.15], [0, 0, 107.7]
keys = run("slider-crank", "--center", "0,0,0", "--axis", "1,0,0", "--pin", "0,16.07,19.15", "--wrist", "0,0,107.7",
           "--slide", "0,0,1", "--crank", "c", "--slider", "s", "--rod", "r")
xs = [v["slider"] for v in keys]
assert abs(max(xs) - min(xs) - 2 * math.hypot(16.07, 19.15)) < 0.1, (min(xs), max(xs))
for v in keys:
    W = [0, 0, 107.7 + v["slider"]]
    end = rot([0, 16.07, 19.15 + v["slider"]], W, [1, 0, 0], v["rod"])
    assert math.dist(end, rot(P0, [0, 0, 0], [1, 0, 0], v["crank"])) < 1e-2, v
print("ok")
