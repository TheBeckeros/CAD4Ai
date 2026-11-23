"""Send a snap proposal to the cad-preview sketch pad.

python proposal.py <snap-id> <items.json | -> [--space world|rect|image] [--note "one line for the user"] [--port 8766]

items.json holds a JSON list of items (or {"items": [...], "note": ...}); see the cad-sketch skill for the schema.
The pad shows the proposal as a ghost inside the snap box; the user accepts or rejects it there.
"""
import argparse
import json
import sys
import urllib.error
import urllib.request


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("snap")
    ap.add_argument("items")
    ap.add_argument("--space", default=None, choices=("world", "rect", "image"))
    ap.add_argument("--note", default=None)
    ap.add_argument("--port", type=int, default=8766)
    a = ap.parse_args()
    data = json.load(sys.stdin if a.items == "-" else open(a.items, encoding="utf-8"))
    body = data if isinstance(data, dict) else {"items": data}
    body["snap"] = a.snap
    if a.space:
        body["space"] = a.space
    if a.note is not None:
        body["note"] = a.note
    req = urllib.request.Request(f"http://127.0.0.1:{a.port}/api/sketch/proposal", data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"}, method="POST")
    try:
        print(urllib.request.urlopen(req, timeout=10).read().decode())
    except urllib.error.HTTPError as e:
        sys.exit(f"rejected ({e.code}): {e.read().decode()}")


if __name__ == "__main__":
    main()
