"""Run a model script as a throw-away copy: other parameter values, exports caught in a temp folder.

The copy lives next to the original (so its local imports work) as .cad4ai_<id>.py and is deleted after
the run. A header patches every CadQuery export (cq.exporters.export, Assembly.save/export,
Shape.exportStep/exportStl, Workplane.export) to write into CAD4AI_OUT instead of the real path, so a
sandbox run never overwrites the model. Several runs can go in parallel.
"""
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import uuid

HEADER = r'''
# --- CAD4Ai sandbox header (temporary copy) ---
import os as _c4_os, sys as _c4_sys
_C4_OUT = _c4_os.environ.get("CAD4AI_OUT")
_C4_K = float(_c4_os.environ.get("CAD4AI_K", "1"))
def _c4_r(v):
    print("\x1eC4R", v, flush=True)
    return v * _C4_K
def _c4_target(p):
    p = str(p)
    return _c4_os.path.join(_C4_OUT, _c4_os.path.basename(p)) if _C4_OUT else p
try:
    import cadquery as _c4_cq
    from cadquery import exporters as _c4_ex
    _c4_orig = _c4_ex.export
    def _c4_export(w, fname, *a, **k):
        return _c4_orig(w, _c4_target(fname), *a, **k)
    _c4_ex.export = _c4_export
    try:
        import cadquery.occ_impl.exporters as _c4_ex2
        _c4_ex2.export = _c4_export
    except Exception:
        pass
    for _c4_cls, _c4_names in ((_c4_cq.Assembly, ("save", "export")), (_c4_cq.Shape, ("exportStep", "exportStl", "exportBrep")),
                               (_c4_cq.Workplane, ("export",))):
        for _c4_n in _c4_names:
            _c4_f = getattr(_c4_cls, _c4_n, None)
            if _c4_f is None:
                continue
            def _c4_wrap(f):
                def g(self, path, *a, **k):
                    return f(self, _c4_target(path), *a, **k)
                return g
            setattr(_c4_cls, _c4_n, _c4_wrap(_c4_f))
except Exception as _c4_e:
    print("CAD4Ai sandbox: cadquery not patched:", _c4_e, file=_c4_sys.stderr)
_c4_open = open
def open(file, mode="r", *a, **k):  # noqa: A001 - side files (parts.json...) go to the sandbox too
    if _C4_OUT and isinstance(file, (str, bytes, _c4_os.PathLike)) and any(c in mode for c in "wax"):
        file = _c4_target(_c4_os.fsdecode(file))
    return _c4_open(file, mode, *a, **k)
# --- end of CAD4Ai header ---
'''


def _insert_header(src):
    """After a leading docstring / __future__ imports, keep line numbers mappable (returns offset)."""
    lines = src.split("\n")
    i = 0
    # skip shebang/encoding/docstring/future imports
    import ast
    try:
        tree = ast.parse(src)
        body = tree.body
        k = 0
        if body and isinstance(body[0], ast.Expr) and isinstance(getattr(body[0], "value", None), ast.Constant) \
                and isinstance(body[0].value.value, str):
            i = body[0].end_lineno
            k = 1
        while k < len(body) and isinstance(body[k], ast.ImportFrom) and body[k].module == "__future__":
            i = body[k].end_lineno
            k += 1
    except SyntaxError:
        pass
    hdr = HEADER.strip("\n").split("\n")
    return "\n".join(lines[:i] + hdr + lines[i:]), i, len(hdr)


def make_copy(script, values=None, transform=None):
    """Write the sandbox copy; returns (path, header_line, header_len)."""
    with open(script, encoding="utf-8") as f:
        src = f.read()
    if values:
        src = set_params(src, values)
    if transform:
        src = transform(src)
    src, at, n = _insert_header(src)
    p = os.path.join(os.path.dirname(os.path.abspath(script)), f".cad4ai_{uuid.uuid4().hex[:8]}.py")
    with open(p, "w", encoding="utf-8") as f:
        f.write(src)
    return p, at, n


def set_params(src, values):
    """New values of top-level parameters - the same parser and rewrite as the viewer's Parameters tab."""
    from .params import set_in_source
    return set_in_source(src, values)


def run(script, values=None, transform=None, env=None, timeout=900, keep=False):
    """-> {ok, code, stderr, stdout, ms, out_dir, files:[...], radii:[...]}; out_dir is deleted unless keep."""
    cp, at, n = make_copy(script, values, transform)
    out = tempfile.mkdtemp(prefix="cad4ai_sb_")
    e = dict(os.environ, CAD4AI_OUT=out, PYTHONIOENCODING="utf-8", **(env or {}))
    t0 = time.time()
    try:
        r = subprocess.run([sys.executable, "-B", cp], cwd=os.path.dirname(cp), capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=timeout, env=e,
                           creationflags=0x08000000 if os.name == "nt" else 0)
        code, so, se = r.returncode, r.stdout, r.stderr
    except subprocess.TimeoutExpired:
        code, so, se = -9, "", f"timeout after {timeout}s"
    finally:
        try:
            os.remove(cp)
        except OSError:
            pass
    radii = [float(x) for x in re.findall(r"\x1eC4R (\S+)", so) if _isnum(x)]
    se = remap_lines(se, cp, script, at, n)
    res = {"ok": code == 0, "code": code, "stderr": se[-6000:], "stdout": re.sub(r"\x1eC4R \S+\n?", "", so)[-2000:],
           "ms": int((time.time() - t0) * 1000), "out_dir": out, "files": sorted(os.listdir(out)), "radii": radii}
    if not keep:
        shutil.rmtree(out, ignore_errors=True)
    return res


def _isnum(x):
    try:
        float(x)
        return True
    except ValueError:
        return False


def remap_lines(text, copy_path, script, at, n):
    """Traceback lines of the copy -> lines of the real script."""
    cb = os.path.basename(copy_path)

    def fix(m):
        ln = int(m.group(2))
        real = ln - n if ln > at + n else (ln if ln <= at else 0)
        return f'File "{script}", line {real}' if real else f'File "<CAD4Ai header>", line {ln}'
    return re.sub(r'File "([^"]*' + re.escape(cb) + r')", line (\d+)', fix, text)


def main_step(files, script):
    """Which exported file is the model: same base name as the script, else the biggest STEP."""
    steps = [f for f in files if f.lower().endswith((".step", ".stp"))]
    base = os.path.splitext(os.path.basename(script))[0].lower()
    for f in steps:
        if os.path.splitext(f)[0].lower() == base:
            return f
    return steps[0] if len(steps) == 1 else (max(steps, key=len) if steps else None)


if __name__ == "__main__":
    print(json.dumps(run(sys.argv[1]), ensure_ascii=False)[:3000])
