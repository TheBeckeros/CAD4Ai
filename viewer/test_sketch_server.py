"""python viewer/test_sketch_server.py : self-check of the sketch store (ops, revs, merge, long-poll) and the snap / proposal flow."""
import base64
import json
import os
import sys
import tempfile
import threading
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import server as S  # noqa: E402

PNG = "data:image/png;base64," + base64.b64encode(bytes.fromhex(
    "89504e470d0a1a0a0000000d4948445200000001000000010806000000"
    "1f15c4890000000d49444154789c6360000002000154a24f5d0000000049454e44ae426082")).decode()


def stroke(i, *pts, **kw):
    return {"id": i, "t": "stroke", "w": 2, "z": 1, "pts": [list(p) for p in pts], **kw}


with tempfile.TemporaryDirectory() as t:
    S.STATE["data"] = t
    with open(os.path.join(t, "sketch.json"), "w") as f:
        json.dump({"rev": 3, "views": {}}, f)  # a sketch from the old pad
    assert S.sketch_changes(0)["rev"] == 0 and os.path.isfile(os.path.join(t, "sketch.v1.json")), "old sketch kept aside"

    # two devices add items independently: both survive, revs grow, `since` returns only newer changes
    r1 = S.sketch_ops([stroke("a", (0, 0, 0.5), (10, 0, 0.7))], by="ipad")
    r2 = S.sketch_ops([{"id": "t", "t": "text", "x": 5, "y": 5, "s": "hinge", "size": 12}], by="pc")
    assert r2 == r1 + 1
    ch = S.sketch_changes(0)
    assert {i["id"] for i in ch["items"]} == {"a", "t"} and ch["rev"] == r2
    assert [i["id"] for i in S.sketch_changes(r1)["items"]] == ["t"], "since"
    assert S.sketch_changes(0)["items"][0]["pts"][1] == [10.0, 0.0, 0.7]

    # a bad item rejects the whole batch, nothing half-applied
    try:
        S.sketch_ops([stroke("b", (1, 1)), {"id": "x", "t": "stroke", "pts": [[1, "y"]]}])
        raise AssertionError("should fail")
    except ValueError:
        pass
    assert "b" not in S.load_sketch()["items"] and S.load_sketch()["rev"] == r2
    for bad in ({"id": "../x", "t": "text", "x": 0, "y": 0, "s": ""}, {"id": "i", "t": "image", "src": "file:///etc/passwd", "x": 0, "y": 0, "w": 1, "h": 1},
                {"id": "c", "t": "stroke", "pts": [[0, 0]], "color": "red;"}):
        try:
            S.clean_item(bad)
            raise AssertionError(f"accepted {bad}")
        except ValueError:
            pass

    # deletion = tombstone seen by others, hidden from a fresh load
    r3 = S.sketch_ops(dels=["a"], by="pc")
    assert [i for i in S.sketch_changes(r2)["items"] if i["id"] == "a"][0]["deleted"]
    assert all(i["id"] != "a" for i in S.sketch_changes(0)["items"])

    # long-poll wakes up on a change from another thread
    out = {}
    th = threading.Thread(target=lambda: out.update(S.sketch_changes(r3, wait=5)))
    th.start()
    time.sleep(0.2)
    S.sketch_ops([stroke("c", (50, 50))], by="ipad")
    th.join(3)
    assert out and [i["id"] for i in out["items"]] == ["c"], "long-poll"
    t0 = time.time()
    S.sketch_changes(S.load_sketch()["rev"], wait=0.3)
    assert time.time() - t0 >= 0.25, "long-poll waits when nothing changed"

    # pasted images go to files, not into the JSON
    name = S.save_data_url(PNG, "sketch-images")
    assert S.IMG_RE.match(name) and os.path.isfile(os.path.join(t, "sketch-images", name))
    S.sketch_ops([{"id": "im", "t": "image", "src": "/api/sketch/image?f=" + name, "x": 0, "y": 0, "w": 10, "h": 10}])

    # snap request: request file, PNG and inbox note for the chat
    sid = S.sketch_snap({"rect": [0, 0, 100, 50], "text": "make it a hinge", "ids": ["t", "nope"], "image": PNG, "scale": 2,
                         "outside": [[200, 0, 10, 10]]})
    req = json.load(open(os.path.join(t, "snaps", f"{sid}.json"), encoding="utf-8"))
    assert [i["id"] for i in req["items"]] == ["t"] and req["scale"] == 2 and os.path.isfile(req["image"])
    note = json.load(open(os.path.join(t, "inbox", f"{sid}.json"), encoding="utf-8"))
    assert note["kind"] == "snap" and note["sketch"].endswith(f"{sid}.json") and note["comment"] == "make it a hinge"
    assert S.load_sketch()["snaps"][sid]["status"] == "pending"

    # proposal in image pixels (scale 2): converted to world units, things fully outside dropped, shorthands expanded
    n = S.sketch_proposal(sid, [
        {"t": "stroke", "pts": [[0, 0], [100, 50]], "w": 4},
        {"t": "rect", "x": 10, "y": 10, "w": 40, "h": 20},
        {"t": "text", "x": 20, "y": 60, "s": "pin", "size": 24},
        {"t": "stroke", "pts": [[400, 400], [500, 400]]},  # outside the region
    ], "image", "two pins")
    snap = S.load_sketch()["snaps"][sid]
    assert n == 3 and snap["status"] == "proposed" and snap["note"] == "two pins"
    p = snap["proposal"]
    assert p[0]["pts"][1][:2] == [50.0, 25.0] and p[0]["w"] == 2.0 and len(p[1]["pts"]) == 5 and p[1]["w"] == 1.0 and p[2]["size"] == 12.0
    S.sketch_proposal(sid, [{"t": "line", "a": [1, 1], "b": [9, 9]}], "rect")
    assert S.load_sketch()["snaps"][sid]["proposal"][0]["pts"][0][:2] == [1.0, 1.0]
    try:
        S.sketch_proposal(sid, [{"t": "circle"}])
        raise AssertionError("bad type accepted")
    except ValueError:
        pass
    S.sketch_ops(snaps=[{"id": sid, "status": "accepted"}])
    try:
        S.sketch_proposal(sid, [])
        raise AssertionError("proposal after accept")
    except ValueError:
        pass
    try:
        S.sketch_proposal("snap-none", [])
        raise AssertionError("unknown snap")
    except KeyError:
        pass

    # whole-canvas brief
    bid = S.sketch_send({"image": PNG, "text": "what do you think"})
    b = json.load(open(os.path.join(t, "inbox", f"{bid}.json"), encoding="utf-8"))
    assert b["kind"] == "sketch" and "text at (5, 5): hinge" in b["summary"] and os.path.isfile(b["screenshot"])

    # survives a restart (the file is the truth)
    S.STATE.pop("sk")
    assert S.load_sketch()["snaps"][sid]["status"] == "accepted" and "c" in S.load_sketch()["items"]
print("test_sketch_server.py: all ok")
