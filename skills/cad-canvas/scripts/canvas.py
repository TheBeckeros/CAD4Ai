"""Claude's side of the CAD4Ai construction canvas (the AI <-> editor interface).

python canvas.py [--port 8766] <command> ...
  req <req-id>                         get_selection / get_context: the request (instruction, selected objects, neighbours, layers, briefing answers)
  object <object-id>                   get_object: one live object and what depends on it (dimensions, group)
  briefing <req-id> <items.json | ->   show_briefing: questions / warnings pinned to objects or points  [--summary "what I understood"]
  preview <req-id> <changes.json | ->  preview_changes: {"put": [objects], "del": [ids]} shown as a ghost, the user accepts  [--note "one line"]
  status <req-id> drafting [--note ...] show "Vytvářím návrh" on the canvas while you work

See the cad-canvas skill for the object and briefing schemas. A rejected call prints the server's reason and exits 1.
"""
import argparse
import json
import sys
import urllib.error
import urllib.request
from urllib.parse import quote


def call(port, path, body=None):
    url = f"http://127.0.0.1:{port}{path}"
    req = urllib.request.Request(url, data=None if body is None else json.dumps(body).encode(), headers={"Content-Type": "application/json"},
                                 method="GET" if body is None else "POST")
    try:
        return json.loads(urllib.request.urlopen(req, timeout=15).read().decode())
    except urllib.error.HTTPError as e:
        sys.exit(f"rejected ({e.code}): {e.read().decode()}")
    except urllib.error.URLError as e:
        sys.exit(f"viewer server not reachable on port {port}: {e.reason}")


def load(arg):
    return json.load(sys.stdin if arg == "-" else open(arg, encoding="utf-8"))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8766)
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("req", "object"):
        sub.add_parser(name).add_argument("id")
    for name in ("briefing", "preview"):
        p = sub.add_parser(name)
        p.add_argument("req")
        p.add_argument("file")
        p.add_argument("--summary" if name == "briefing" else "--note", default="")
    p = sub.add_parser("status")
    p.add_argument("req")
    p.add_argument("status")
    p.add_argument("--note", default="")
    a = ap.parse_args()
    if a.cmd == "req":
        print(json.dumps(call(a.port, "/api/canvas/req?id=" + quote(a.id)), ensure_ascii=False, indent=1))
    elif a.cmd == "object":
        print(json.dumps(call(a.port, "/api/canvas/object?id=" + quote(a.id)), ensure_ascii=False, indent=1))
    elif a.cmd == "briefing":
        data = load(a.file)
        body = data if isinstance(data, dict) else {"items": data}
        print(json.dumps(call(a.port, "/api/canvas/briefing", {**body, "req": a.req, "summary": a.summary or body.get("summary", "")})))
    elif a.cmd == "preview":
        data = load(a.file)
        body = data if isinstance(data, dict) else {"put": data}
        print(json.dumps(call(a.port, "/api/canvas/preview", {**body, "req": a.req, "note": a.note or body.get("note", "")})))
    else:
        print(json.dumps(call(a.port, "/api/canvas/status", {"req": a.req, "status": a.status, "note": a.note})))


if __name__ == "__main__":
    main()
