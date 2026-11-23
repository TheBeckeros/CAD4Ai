"""python viewer/test_batch_server.py : self-check of POST /api/annotate-batch (all viewer markers as one inbox note)."""
import json
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import server as S  # noqa: E402

with tempfile.TemporaryDirectory() as t:
    S.STATE["data"] = t
    model = os.path.join(t, "kostka.step")
    body = {"model": model, "name": "kostka", "step": model, "parts": ["kostka"],
            "camera": {"position": [1, 2, 3], "target": [0, 0, 0], "up": [0, 0, 1], "viewDir": [0, 0, -1], "ortho": False},
            "markers": [
                {"label": "A", "type": "point", "points": [[10, 0, 50]], "faceNormal": [0, 0, 1], "part": "kostka", "note": "M8 thread here"},
                {"label": "B", "type": "line", "points": [[0, 0, 50], [0, 0, 0]], "faceNormal": [0, 0, 1], "part": "kostka", "note": "hole A to B"},
                {"label": "C", "type": "area", "points": [[0, 0, 0], [5, 0, 0], [5, 5, 0]], "faceNormal": [0, 0, -1], "part": None},
            ]}
    sid = S.annotate_batch(body)
    path = os.path.join(t, "inbox", f"{sid}.json")
    a = json.load(open(path, encoding="utf-8"))
    assert a["kind"] == "batch" and a["id"] == sid and a["model"] == model and a["step"] == model
    assert [m["label"] for m in a["markers"]] == ["A", "B", "C"]
    assert a["markers"][1]["points"] == [[0.0, 0.0, 50.0], [0.0, 0.0, 0.0]] and a["markers"][2]["note"] == "" and a["markers"][2]["part"] is None
    assert a["comment"] == "A: M8 thread here; B: hole A to B; C: (no note)"
    assert a["anchor"] == [10.0, 0.0, 50.0] and a["camera"]["viewDir"] == [0, 0, -1] and "created" in a
    listed = S.annotations_for(model)
    assert len(listed) == 1 and listed[0]["markers"][0]["note"] == "M8 thread here" and listed[0]["status"] == "open"

    # a bad marker rejects the whole batch and writes nothing
    for bad in ([], [{"type": "line", "points": [[0, 0, 0]]}], [{"type": "blob", "points": [[0, 0, 0]]}],
                [{"type": "point", "points": [[0, 0]]}], [{"type": "point", "points": [[0, 0, float("nan")]]}], "x"):
        try:
            S.annotate_batch({**body, "markers": bad})
            raise AssertionError(f"accepted {bad!r}")
        except (ValueError, TypeError):
            pass
    assert len(os.listdir(os.path.join(t, "inbox"))) == 1
print("test_batch_server: ok")
