"""python viewer/test_canvas_server.py : self-check of the canvas store (ops, revs, conflicts, snapshots) and the AI flow
(request -> briefing -> answers -> preview -> accept / reject, direct edit limited to the region)."""
import base64
import json
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import canvas as C  # noqa: E402

PNG = "data:image/png;base64," + base64.b64encode(bytes.fromhex(
    "89504e470d0a1a0a0000000d4948445200000001000000010806000000"
    "1f15c4890000000d49444154789c6360000002000154a24f5d0000000049454e44ae426082")).decode()


def line(i, a, b, **kw):
    return {"id": i, "t": "line", "a": a, "b": b, **kw}


def fails(fn, exc=ValueError):
    try:
        fn()
    except exc as e:
        return e
    raise AssertionError("expected " + exc.__name__)


with tempfile.TemporaryDirectory() as d:
    r1 = C.ops(d, [line("a", [0, 0], [100, 0]), {"id": "c1", "t": "circle", "c": [50, 50], "r": 20}], by="pc")
    r2 = C.ops(d, [{"id": "t1", "t": "text", "x": 1, "y": 2, "s": "hřídel"}], by="ipad")
    ch = C.changes(d, 0)
    assert ch["rev"] == r2 and {o["id"] for o in ch["objs"]} == {"a", "c1", "t1"} and len(ch["layers"]) == 9
    assert [o["id"] for o in C.changes(d, r1)["objs"]] == ["t1"]
    assert next(o for o in ch["objs"] if o["id"] == "t1")["layer"] == 3, "text defaults to the notes layer"
    fails(lambda: C.ops(d, [line("bad", [0, 0], ["x", 1])]))
    fails(lambda: C.ops(d, [{"id": "q", "t": "blob"}]))
    assert C.changes(d, 0)["rev"] == r2, "a rejected batch changes nothing"

    # a mechanism object: validated joints / links / slider / driver
    mech = {"id": "m1", "t": "mech", "name": "klika", "joints": [{"id": "A", "p": [0, 0], "fixed": True}, {"id": "B", "p": [20, 0]}, {"id": "C", "p": [100, 0]}],
            "links": [["A", "B"], ["B", "C"]], "sliders": [{"j": "C", "a": [-200, 0], "b": [200, 0]}], "driver": {"j": "B", "c": "A"}, "len": [20, 80]}
    C.ops(d, [mech])
    m = C.load(d)["objs"]["m1"]
    assert m["layer"] == 6 and m["driver"] == {"j": "B", "c": "A"} and m["len"] == [20.0, 80.0] and C._bounds(m)[2] == 100
    fails(lambda: C.ops(d, [{**mech, "driver": {"j": "C", "c": "B"}}]))  # B is not fixed
    fails(lambda: C.ops(d, [{**mech, "links": [["A", "Z"]]}]))
    fails(lambda: C.ops(d, [{**mech, "len": [1]}]))
    C.ops(d, dels=["m1"])

    # layers: hide, lock, opacity (clamped)
    C.ops(d, layers=[{"n": 2, "vis": False, "op": 7}])
    assert C.changes(d, 0)["layers"][1]["vis"] is False and C.changes(d, 0)["layers"][1]["op"] == 1.0

    # a dimension follows its line; deleting leaves a tombstone for other tabs
    C.ops(d, [{"id": "dm", "t": "dim", "ref": "a", "off": 12}])
    assert C.get_object(d, "a")["dependents"][0]["id"] == "dm"
    C.ops(d, dels=["dm"])
    assert any(o.get("deleted") for o in C.changes(d, 0)["objs"]) is False and any(o.get("deleted") for o in C.changes(d, r2)["objs"])

    # base revs: a write based on an old rev of an object someone else changed is a conflict
    base = {"a": C.load(d)["objs"]["a"]["rev"]}
    C.ops(d, [line("a", [0, 0], [120, 0])], by="ipad")
    e = fails(lambda: C.ops(d, [line("a", [0, 0], [90, 0])], base=base), C.Conflict)
    assert e.ids == ["a"]

    # snapshots restore as a new revision, objects made later disappear
    sid = C.snapshot(d, "v1")
    C.ops(d, [line("late", [0, 0], [1, 1])])
    C.restore(d, sid)
    live = {o["id"] for o in C.live(C.load(d))}
    assert "late" not in live and "a" in live

    # AI request: selection + context
    rid = C.send(d, {"rect": [0, 0, 120, 60], "ids": ["a", "c1", "nope"], "text": "clean this into a section", "image": PNG, "scale": 2,
                     "context": "around", "autonomy": "propose", "marks": [[[10, 10], [30, 12]]]})
    req = json.load(open(os.path.join(d, "canvas-req", rid + ".json"), encoding="utf-8"))
    assert req["ids"] == ["a", "c1"] and len(req["objects"]) == 2 and req["base"]["a"] == C.load(d)["objs"]["a"]["rev"]
    inbox = json.load(open(os.path.join(d, "inbox", rid + ".json"), encoding="utf-8"))
    assert inbox["kind"] == "canvas" and os.path.isfile(inbox["screenshot"])
    assert req["marks"] == [[[10.0, 10.0], [30.0, 12.0]]] and "1 pen marks" in inbox["summary"]
    fails(lambda: C.send(d, {"rect": [0, 0, 5, 5], "image": PNG, "marks": [[[1, "x"]]]}))
    fails(lambda: C.send(d, {"rect": [0, 0, 0, 5], "image": PNG}))

    # briefing: pinned to geometry, anchors must exist
    fails(lambda: C.briefing(d, {"req": rid, "items": [{"q": "?", "anchor": {"obj": "ghost"}}]}))
    ids = C.briefing(d, {"req": rid, "summary": "a shaft?", "items": [
        {"q": "Bearing seat?", "anchor": {"obj": "c1"}, "options": ["H7", "none"], "assumption": "H7"},
        {"q": "Which pin is fixed?", "anchor": {"pt": [10, 10]}, "kind": "warning"}]})
    assert C.load(d)["reqs"][rid]["status"] == "asking" and len(ids) == 2
    C.answer(d, ids[0], "H7", "answered")
    sid2 = C.answers_send(d, rid)
    msg = json.load(open(os.path.join(d, "inbox", sid2 + ".json"), encoding="utf-8"))
    assert "Bearing seat? -> H7" in msg["summary"] and "warning seen" in msg["summary"] and C.load(d)["reqs"][rid]["status"] == "pending"

    # proposal: ghost first, applied only on accept (with a snapshot); the user's own later edit is a conflict
    C.preview(d, {"req": rid, "note": "section", "put": [{"t": "line", "a": [0, 0], "b": [100, 10]}, {"id": "a", "t": "line", "a": [0, 0], "b": [80, 0]}], "del": ["c1"]})
    assert C.load(d)["objs"]["c1"].get("deleted") is None and C.load(d)["reqs"][rid]["status"] == "proposed"
    C.ops(d, [line("a", [0, 5], [120, 5])], by="user")  # user edits while the AI works
    e = fails(lambda: C.decide(d, rid, True), C.Conflict)
    assert e.ids == ["a"]
    sid3 = C.decide(d, rid, True, force=True)
    assert C.load(d)["objs"]["c1"].get("deleted") and C.load(d)["objs"]["a"]["b"] == [80.0, 0.0] and C.load(d)["reqs"][rid]["status"] == "applied"
    n_ai = [o for o in C.live(C.load(d)) if o["id"].startswith("ai-")]
    assert len(n_ai) == 1 and n_ai[0]["layer"] == 2, "new AI objects land on the AI layer"
    C.restore(d, sid3)
    assert not C.load(d)["objs"]["c1"].get("deleted"), "the AI change can be taken back"

    # consult-only requests refuse changes; reject keeps everything; direct edits stay inside the region
    rc = C.send(d, {"rect": [0, 0, 50, 50], "ids": [], "text": "just explain", "image": PNG, "autonomy": "consult"})
    fails(lambda: C.preview(d, {"req": rc, "put": [line("x", [0, 0], [1, 1])]}))
    rr = C.send(d, {"rect": [0, 0, 50, 50], "ids": [], "text": "x", "image": PNG})
    C.preview(d, {"req": rr, "put": [{"t": "circle", "c": [5, 5], "r": 3}]})
    C.decide(d, rr, False)
    assert C.load(d)["reqs"][rr]["status"] == "rejected" and not any(o["id"].startswith("ai-" + rr[4:]) for o in C.live(C.load(d)))
    rd = C.send(d, {"rect": [0, 0, 50, 50], "ids": [], "text": "x", "image": PNG, "autonomy": "direct"})
    fails(lambda: C.preview(d, {"req": rd, "put": [{"t": "circle", "c": [500, 500], "r": 3}]}))
    C.preview(d, {"req": rd, "put": [{"t": "circle", "c": [10, 10], "r": 3}]})
    assert C.load(d)["reqs"][rd]["status"] == "applied"

    # canvas files: save, open as a copy (new ids, refs follow), open replacing (restore point first), junk refused
    C.ops(d, [line("fl", [0, 0], [50, 0]), {"id": "fd", "t": "dim", "ref": "fl", "off": 8, "edge": 5, "size": 6}])
    f = C.file_save(d, {"path": os.path.join(d, "share.platno.json")})
    saved = json.load(open(f, encoding="utf-8"))
    assert saved["format"] == "cad-preview-canvas" and any(o["id"] == "fd" and o["edge"] == 1 and o["size"] == 6 for o in saved["objs"])
    n0 = len(C.live(C.load(d)))
    r = C.file_open(d, {"path": f, "mode": "add"})
    live2 = C.live(C.load(d))
    assert len(live2) == n0 + r["objs"]
    copy_dim = next(o for o in live2 if o["t"] == "dim" and o["id"] != "fd" and o["id"].endswith("-fd"))
    assert copy_dim["ref"].endswith("-fl") and copy_dim["ref"] in C.load(d)["objs"], "a copied dim follows the copied line"
    C.ops(d, [line("extra", [1, 1], [2, 2])])
    C.file_open(d, {"path": f})
    assert {o["id"] for o in C.live(C.load(d))} == {o["id"] for o in saved["objs"]}, "open replaces the canvas"
    assert C.load(d)["snaps"][-1]["name"].startswith("před otevřením")
    with open(os.path.join(d, "junk.json"), "w") as jf:
        json.dump({"hello": 1}, jf)
    fails(lambda: C.file_open(d, {"path": os.path.join(d, "junk.json")}))
    fails(lambda: C.file_save(d, {"path": os.path.join(d, "x.exe")}))

    # closing: a request answered without changes (or dropped) is closed and takes no preview any more
    rx = C.send(d, {"rect": [0, 0, 50, 50], "ids": [], "text": "just look", "image": PNG})
    C.set_status(d, rx, "closed")
    assert C.load(d)["reqs"][rx]["status"] == "closed"
    fails(lambda: C.preview(d, {"req": rx, "put": [line("y", [0, 0], [1, 1])]}))

    # the HTTP layer
    code, out = C.route("POST", "/api/canvas/ops", {}, {"put": [line("h", [0, 0], [1, 1])], "by": "t"}, d)
    assert code == 200 and out["rev"] > 0
    assert C.route("POST", "/api/canvas/ops", {}, {"put": [{"id": "z", "t": "nope"}]}, d)[0] == 400
    assert C.route("POST", "/api/canvas/decide", {}, {"req": "req-none", "accept": True}, d)[0] == 404
    assert C.route("GET", "/api/other", {}, None, d) is None
print("test_canvas_server.py ok")
