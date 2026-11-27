"""Stable copy of the CAD4Ai helpers for model scripts: ~/.CAD4Ai/lib (cadtools package + related.py).

The plugin itself lives in a versioned folder (…/plugins/cache/CAD4Ai/CAD4Ai/<version>/) that changes with
every update, so a model script must never point there. Scripts use
    sys.path.insert(0, os.path.expanduser("~/.CAD4Ai/lib"))
and this module keeps that copy in sync with the running plugin (called by the CLI, the hooks and the
viewer server; a cheap size/mtime comparison when nothing changed).
"""
import os
import shutil

SRC = os.path.dirname(os.path.abspath(__file__))
VIEWER = os.path.dirname(SRC)
APP_HOME = os.environ.get("CAD4AI_HOME") or os.path.join(os.path.expanduser("~"), ".CAD4Ai")
LIB = os.path.join(APP_HOME, "lib")


def _files():
    out = [(os.path.join(SRC, f), os.path.join(LIB, "cadtools", f)) for f in os.listdir(SRC) if f.endswith(".py")]
    out.append((os.path.join(VIEWER, "related.py"), os.path.join(LIB, "related.py")))
    return out


def sync():
    """Copy changed files; returns the number copied. Never raises."""
    if os.path.abspath(SRC).lower().startswith(os.path.abspath(LIB).lower()):
        return 0  # running from the copy itself
    n = 0
    try:
        os.makedirs(os.path.join(LIB, "cadtools"), exist_ok=True)
        for src, dst in _files():
            try:
                a = os.stat(src)
                b = os.stat(dst) if os.path.exists(dst) else None
                if b is None or a.st_size != b.st_size or int(a.st_mtime) != int(b.st_mtime):
                    tmp = dst + ".tmp"
                    shutil.copy2(src, tmp)
                    os.replace(tmp, dst)
                    n += 1
            except OSError:
                continue
        readme = os.path.join(LIB, "README.txt")
        if not os.path.exists(readme):
            with open(readme, "w", encoding="utf-8") as f:
                f.write("Copy of the CAD4Ai helpers (cadtools) for model scripts; kept in sync by the plugin.\n"
                        "Do not edit here - changes are overwritten.\n")
    except OSError:
        pass
    return n


def import_lines():
    return 'import os, sys; sys.path.insert(0, os.path.expanduser("~/.CAD4Ai/lib"))'
