"""python viewer/test_params.py : parameter groups and ranges from the script, and the warm runner."""
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import server as S  # noqa: E402

SRC = '''import sys
# --- Plate ---
PLATE_T = 6.0  # thickness [mm] 3..20
HOLE_D = 5.5  # hole [mm]
## Lid
LID_T = 4  # lid [mm] 10…1
SHOW = True  # show it 1..2
x = PLATE_T * 2  # not a parameter
print("built", PLATE_T)
if PLATE_T > 100:
    sys.exit(3)
'''

with tempfile.TemporaryDirectory() as d:
    script = os.path.join(d, "model.py")
    with open(script, "w", encoding="utf-8") as f:
        f.write(SRC)
    ps = {p["name"]: p for p in S.parse_params(script)}
    assert list(ps) == ["PLATE_T", "HOLE_D", "LID_T", "SHOW"], list(ps)
    assert ps["PLATE_T"]["group"] == "Plate" and ps["LID_T"]["group"] == "Lid", ps
    assert (ps["PLATE_T"]["min"], ps["PLATE_T"]["max"]) == (3, 20)
    assert (ps["LID_T"]["min"], ps["LID_T"]["max"]) == (1, 10), "a reversed range is sorted"
    assert "min" not in ps["HOLE_D"] and "min" not in ps["SHOW"], "no range without one / for bools"

    r = S.run_script(script)
    assert r["ok"] and "built 6.0" in r["stdout"], r
    assert r.get("warm") is True, "runs in the warm runner"
    S.write_params(script, {"PLATE_T": 150})
    r = S.run_script(script)
    assert not r["ok"] and r["code"] == 3, r
    S.write_params(script, {"PLATE_T": 7})
    r = S.run_script(script)
    assert r["ok"] and "built 7.0" in r["stdout"], "the same runner picks up the new value"
    S.RUNNER.stop()

print("test_params.py: ok")
