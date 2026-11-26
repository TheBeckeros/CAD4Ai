"""Warm script runner for the Parameters tab.

The viewer server keeps one of these processes alive: CadQuery (and OCP) are imported once, so a
parameter change only runs the model script itself instead of paying the 2-10 s import every time.

Protocol: one JSON request per stdin line {"script": "<abs path>"}; the reply is one line on stdout
starting with RESULT followed by JSON {ok, code, stdout, stderr, ms}. Anything else the script or
OpenCascade writes straight to the file descriptor arrives as other lines and is ignored by the server.
"""
import contextlib
import io
import json
import os
import runpy
import sys
import time
import traceback

RESULT = "\x1eCAD4AI-RESULT "

try:  # warm up: the expensive part of every run
    import cadquery  # noqa: F401
except Exception:  # noqa: BLE001 - a script without CadQuery still runs
    pass

_out = sys.stdout


def run(script):
    folder = os.path.dirname(os.path.abspath(script))
    out, err = io.StringIO(), io.StringIO()
    code, t0 = 0, time.time()
    cwd, argv = os.getcwd(), sys.argv
    sys.path.insert(0, folder)
    os.chdir(folder)
    sys.argv = [script]
    try:
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            runpy.run_path(script, run_name="__main__")
    except SystemExit as e:
        code = e.code if isinstance(e.code, int) else (0 if e.code is None else 1)
        if e.code not in (None, 0) and not isinstance(e.code, int):
            err.write(str(e.code) + "\n")
    except BaseException:  # noqa: BLE001 - report every failure of the user's script
        traceback.print_exc(file=err)
        code = 1
    finally:
        os.chdir(cwd)
        sys.argv = argv
        with contextlib.suppress(ValueError):
            sys.path.remove(folder)
        # helper modules next to the script are imported fresh next time, so edits to them count
        for name, mod in list(sys.modules.items()):
            f = getattr(mod, "__file__", None)
            if f and os.path.dirname(os.path.abspath(f)) == folder:
                del sys.modules[name]
    return {"ok": code == 0, "code": code, "stdout": out.getvalue()[-4000:], "stderr": err.getvalue()[-4000:],
            "ms": int((time.time() - t0) * 1000), "warm": True}


def main():
    _out.write(RESULT + json.dumps({"ready": True}) + "\n")
    _out.flush()
    for line in sys.stdin:
        try:
            req = json.loads(line)
            res = run(req["script"])
        except Exception as e:  # noqa: BLE001
            res = {"ok": False, "code": 1, "stdout": "", "stderr": f"runner: {e}", "ms": 0, "warm": True}
        _out.write(RESULT + json.dumps(res) + "\n")
        _out.flush()


if __name__ == "__main__":
    main()
