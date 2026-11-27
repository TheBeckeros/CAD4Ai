"""Save a whole CAD4Ai project into one folder (the viewer's "Save project" button).

    <dest>/<model>-project/
      model/              the .step (+ variants, .stl), the parametric script and its local modules,
                          parts.json / motion.json / explode.json: everything the viewer reads side by side
      exports/            STL of the model (needs CadQuery)
      history/            the versions kept by the viewer
      notes/              notes sent to Claude (JSON + screenshots)
      viewer/             a copy of the CAD4Ai viewer with its libraries, runs without Claude and offline
      viewer-state.json   dimensions, saved views, paint and markers from the browser
      Open model.bat      starts the viewer on this model
      README.md           what is where and how to continue

Run alone:  python project.py --ask   (prints the folder picked in a native dialog, or nothing)
"""
import ast
import json
import os
import posixpath
import re
import shutil
import subprocess
import sys

sys.dont_write_bytecode = True  # no __pycache__ inside the app folder
import time
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
CDN = "https://cdn.jsdelivr.net/npm/"
VENDOR = os.path.join(HERE, "vendor")
VIEWER_FILES = ["viewer.html", "app.js", "geom.js", "analysis.js", "lib.js", "sketch.html", "sketch.js", "ink.js",
                "canvas.html", "canvas.js", "geo.js", "server.py", "canvas.py", "export.py", "runner.py", "project.py"]
ROOTS = ["three@0.160.0/build/three.module.js", "three-mesh-bvh@0.7.6/build/index.module.js",
         "occt-import-js@0.0.23/dist/occt-import-js.js", "occt-import-js@0.0.23/dist/occt-import-js.wasm"]
PORT = 8780
NOWIN = 0x08000000 if os.name == "nt" else 0


def ask_folder():
    import tkinter
    from tkinter import filedialog
    root = tkinter.Tk()
    root.withdraw()
    root.attributes("-topmost", True)  # otherwise the dialog opens behind the Claude window
    path = filedialog.askdirectory(parent=root, title="Save the CAD4Ai project into…", mustexist=True)
    root.destroy()
    return path


def ask_model(start):
    import tkinter
    from tkinter import filedialog
    root = tkinter.Tk()
    root.withdraw()
    root.attributes("-topmost", True)
    path = filedialog.askopenfilename(parent=root, title="Open a model in CAD4Ai", initialdir=start or None,
                                      filetypes=[("3D models", "*.step *.stp *.stl"), ("All files", "*.*")])
    root.destroy()
    return path


def vendor(log):
    """Download the viewer's CDN libraries once into viewer/vendor (three.js addons import each other: crawled)."""
    with open(os.path.join(HERE, "app.js"), encoding="utf-8") as f:
        addons = re.findall(r"from 'three/addons/([^']+)'", f.read())
    todo = ROOTS + [f"three@0.160.0/examples/jsm/{a}" for a in addons]
    seen = set()
    while todo:
        rel = todo.pop()
        if rel in seen:
            continue
        seen.add(rel)
        dst = os.path.join(VENDOR, *rel.split("/"))
        if not os.path.isfile(dst):
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            with urllib.request.urlopen(CDN + rel, timeout=120) as r:
                data = r.read()
            with open(dst + ".tmp", "wb") as f:
                f.write(data)
            os.replace(dst + ".tmp", dst)
        if rel.endswith(".js") and "/examples/jsm/" in rel:
            with open(dst, encoding="utf-8") as f:
                text = f.read()
            for spec in re.findall(r"""(?:from|import)\s*['"](\.{1,2}/[^'"]+)['"]""", text):
                todo.append(posixpath.normpath(posixpath.join(posixpath.dirname(rel), spec)))
    log.append(f"viewer libraries: {len(seen)} files")
    return True


def unique_dir(path):
    out, n = path, 2
    while os.path.exists(out):
        out, n = f"{path}-{n}", n + 1
    return out


def local_modules(script):
    """Modules next to the script that it imports (import helpers / from helpers import x)."""
    folder, out = os.path.dirname(script), []
    try:
        with open(script, encoding="utf-8") as f:
            tree = ast.parse(f.read())
    except (OSError, SyntaxError):
        return out
    for node in ast.walk(tree):
        names = [a.name for a in node.names] if isinstance(node, ast.Import) else \
            [node.module] if isinstance(node, ast.ImportFrom) and node.module and not node.level else []
        for n in names:
            p = os.path.join(folder, n.split(".")[0] + ".py")
            if os.path.isfile(p) and p not in out:
                out.append(p)
    return out


def copy(src, dst_dir, name=None):
    os.makedirs(dst_dir, exist_ok=True)
    dst = os.path.join(dst_dir, name or os.path.basename(src))
    shutil.copy2(src, dst)
    return dst


def save(cur, dest_parent, history, notes, state, log):
    """Write the project; returns its folder. cur: the server's current(); history: its version folder;
    notes: annotations_for(model); state: what the browser keeps for this model."""
    path = cur["path"]
    folder, name = os.path.dirname(path), os.path.basename(path)
    stem = os.path.splitext(name)[0]
    base = stem.split("@", 1)[0]
    root = unique_dir(os.path.join(dest_parent, base + "-project"))
    mdir = os.path.join(root, "model")
    os.makedirs(mdir)

    # model folder: the model, its STEP, variants, side files and the script with its local modules
    files = set()
    for n in os.listdir(folder):
        st, ext = os.path.splitext(n)
        if ext.lower() in (".step", ".stp", ".stl") and (st == base or st.startswith(base + "@") or st == base + ".ref"):
            files.add(os.path.join(folder, n))
        if n.startswith(base) and n.endswith((".parts.json", ".motion.json", ".explode.json", ".variant.json")):
            files.add(os.path.join(folder, n))
    for k in ("step", "script"):
        if cur.get(k):
            files.add(cur[k])
    if cur.get("script"):
        files.update(local_modules(cur["script"]))
    for f in sorted(files):
        copy(f, mdir)
    log.append(f"model: {len(files)} files")
    model_rel = "model/" + os.path.basename(cur.get("step") or path)

    # exports: an STL next to the exact STEP (CadQuery needed; skipped otherwise)
    if cur.get("step"):
        try:
            out = os.path.join(root, "exports", base + ".stl")
            os.makedirs(os.path.dirname(out), exist_ok=True)
            r = subprocess.run([sys.executable, os.path.join(HERE, "export.py"), cur["step"], "stl", "--out", out],
                               capture_output=True, text=True, timeout=600, creationflags=NOWIN)
            log.append("exports: STL" if os.path.isfile(out) else f"exports: STL skipped ({(r.stderr or r.stdout).strip()[-120:]})")
        except Exception as e:  # noqa: BLE001
            log.append(f"exports: STL skipped ({e})")

    if history and os.path.isdir(history):
        shutil.copytree(history, os.path.join(root, "history"))
        log.append(f"history: {len([n for n in os.listdir(history) if not n.endswith('.json')]) or len(os.listdir(history))} entries")

    if notes:
        ndir = os.path.join(root, "notes")
        os.makedirs(ndir)
        for a in notes:
            a = dict(a)
            shot = a.get("screenshot")
            if shot and os.path.isfile(shot):
                a["screenshot"] = "notes/" + os.path.basename(copy(shot, ndir))
            with open(os.path.join(ndir, f"{a.get('id', 'note')}.json"), "w", encoding="utf-8") as f:
                json.dump(a, f, ensure_ascii=False, indent=1)
        log.append(f"notes: {len(notes)}")

    with open(os.path.join(root, "viewer-state.json"), "w", encoding="utf-8") as f:
        json.dump({"version": 1, "model": model_rel, "saved": time.strftime("%Y-%m-%d %H:%M"), **(state or {})},
                  f, ensure_ascii=False, indent=1)

    # the viewer itself, with its libraries when they can be downloaded (then it also runs offline)
    vdir = os.path.join(root, "viewer")
    for n in VIEWER_FILES:
        if os.path.isfile(os.path.join(HERE, n)):
            copy(os.path.join(HERE, n), vdir)
    offline = False
    try:
        offline = vendor(log)
        shutil.copytree(VENDOR, os.path.join(vdir, "vendor"))
    except Exception as e:  # noqa: BLE001
        log.append(f"viewer libraries not downloaded ({e}); the copy loads them from the internet")
    if offline:
        for n in ("viewer.html", "app.js"):
            p = os.path.join(vdir, n)
            with open(p, encoding="utf-8") as f:
                text = f.read()
            with open(p, "w", encoding="utf-8", newline="") as f:
                f.write(text.replace(CDN, "/vendor/"))

    model_win = model_rel.replace("/", "\\")
    with open(os.path.join(root, "Open model.bat"), "w", encoding="utf-8", newline="\r\n") as f:
        f.write(f"""@echo off
rem Opens this CAD4Ai project in the browser (needs Python 3; CadQuery for parameter rebuilds and exports).
cd /d "%~dp0"
start "CAD4Ai viewer" /min python viewer\\server.py --port {PORT} --data .viewer-data --open "%~dp0{model_win}"
timeout /t 2 /nobreak >nul
start "" http://127.0.0.1:{PORT}/
""")
    with open(os.path.join(root, "README.md"), "w", encoding="utf-8") as f:
        f.write(f"""# {base}

CAD4Ai project saved {time.strftime('%Y-%m-%d %H:%M')}.

| Folder / file | What it is |
|---|---|
| `model/` | `{os.path.basename(model_rel)}` (exact B-rep){', the parametric script `' + os.path.basename(cur['script']) + '`' if cur.get('script') else ''}, variants and side files (`*.parts.json` part types, `*.motion.json` joints, `*.explode.json` disassembly) |
| `exports/` | the model as STL |
| `history/` | earlier versions kept by the viewer (`.step` / `.stl` + `index.json`) |
| `notes/` | notes sent to Claude from the viewer, with screenshots |
| `viewer/` | the CAD4Ai viewer{' with its libraries (works offline)' if offline else ' (loads its libraries from the internet)'} |
| `viewer-state.json` | dimensions, saved views, paint and markers; loaded the first time the project opens |
| `Open model.bat` | starts the viewer on this model at http://127.0.0.1:{PORT}/ |

## Open it

Double-click `Open model.bat`. It needs Python 3; changing parameters (Params tab) and exports also need CadQuery
(`pip install cadquery`). Without Claude everything works except sending notes, which are kept in `.viewer-data/inbox`.

## Continue with Claude

Open this folder in Claude Code and say what to change. The model is `{model_rel}`{', its source `model/' + os.path.basename(cur['script']) + '`: change parameters there and run it to re-export the STEP' if cur.get('script') else ''}.
Earlier requests and their screenshots are in `notes/`.
""")
    return root


if __name__ == "__main__":
    if "--ask" in sys.argv:
        print(ask_folder() or "")
    elif "--ask-model" in sys.argv:
        sys.stdout.reconfigure(encoding="utf-8")  # paths with diacritics
        print(ask_model(sys.argv[2] if len(sys.argv) > 2 else "") or "")
