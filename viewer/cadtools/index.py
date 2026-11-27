"""Search index of your own CadQuery scripts: "have I built something like this before?"

`cad4ai index [folders...]` scans for .py files that use CadQuery (default: Documents, Desktop) and splits
them into functions/classes and parameter blocks; `cad4ai find "ložisko 6204 domek"` returns the best
matching pieces as file:line-range + name + parameters, so Claude reads 30 lines instead of searching
and opening whole projects. TF-IDF on identifiers, comments, strings (accents removed, snake/camel split)
plus character n-grams for Czech word forms. Index: ~/.CAD4Ai/cache/index/index.pkl.
"""
import ast
import os
import pickle
import re
import time
import unicodedata

import numpy as np

from . import core

SKIP = re.compile(r"(^|[\\/])(\.|node_modules|__pycache__|venv|\.venv|site-packages|AppData|\$Recycle)", re.I)
IDX = os.path.join(core.CACHE, "index", "index.pkl")


def norm(text):
    t = unicodedata.normalize("NFKD", text)
    t = "".join(c for c in t if not unicodedata.combining(c))
    t = re.sub(r"([a-z])([A-Z])", r"\1 \2", t)
    return re.sub(r"[_\W]+", " ", t).lower()


def _chunks(path):
    with open(path, encoding="utf-8", errors="replace") as f:
        src = f.read()
    if "cadquery" not in src and "import cq" not in src and "build123d" not in src:
        return []
    try:
        tree = ast.parse(src)
    except SyntaxError:
        return []
    lines = src.split("\n")
    out = []
    params = [n for n in tree.body if isinstance(n, ast.Assign) and len(n.targets) == 1 and
              isinstance(n.targets[0], ast.Name) and re.match(r"^[A-Z][A-Z0-9_]*$", n.targets[0].id)]
    doc = ast.get_docstring(tree) or ""
    if params or doc:
        a = min([p.lineno for p in params] or [1])
        b = max([p.end_lineno for p in params] or [min(len(lines), 30)])
        text = doc + "\n" + "\n".join(lines[a - 1:b])
        out.append({"file": path, "from": a, "to": b, "name": "(module parameters)",
                    "params": [p.targets[0].id for p in params][:40], "text": text, "doc": doc[:160]})
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.ClassDef)):
            a, b = node.lineno, node.end_lineno
            body = "\n".join(lines[a - 1:b])
            if b - a < 3 or len(body) < 80:  # one-liners and tiny helpers drown the real builders
                continue
            out.append({"file": path, "from": a, "to": b, "name": node.name, "params": [],
                        "doc": (ast.get_docstring(node) or "")[:160], "text": body[:6000]})
    return out


def build(folders=None):
    t0 = time.time()
    home = os.path.expanduser("~")
    folders = folders or [os.path.join(home, "Documents"), os.path.join(home, "Desktop")]
    chunks, files = [], 0
    for root_dir in folders:
        for root, dirs, fs in os.walk(root_dir):
            dirs[:] = [d for d in dirs if not SKIP.search(os.sep + d)]
            for f in fs:
                if f.endswith(".py") and not f.startswith(".cad4ai_"):
                    p = os.path.join(root, f)
                    try:
                        if os.path.getsize(p) > 2_000_000:
                            continue
                        c = _chunks(p)
                    except OSError:
                        continue
                    if c:
                        files += 1
                        for x in c:
                            x["folder"] = os.path.basename(os.path.dirname(p))
                        chunks += c
    from sklearn.feature_extraction.text import TfidfVectorizer
    docs = [norm(f"{c['folder']} {os.path.basename(c['file'])} {c['name']} {c['doc']} {c['text']}") for c in chunks]
    wv = TfidfVectorizer(sublinear_tf=True, min_df=1, token_pattern=r"[a-z0-9]{2,}")
    cv = TfidfVectorizer(analyzer="char_wb", ngram_range=(3, 5), sublinear_tf=True, min_df=1, max_features=300000)
    W = wv.fit_transform(docs) if docs else None
    C = cv.fit_transform(docs) if docs else None
    for c in chunks:
        c.pop("text", None)
    os.makedirs(os.path.dirname(IDX), exist_ok=True)
    with open(IDX, "wb") as f:
        pickle.dump({"chunks": chunks, "wv": wv, "cv": cv, "W": W, "C": C, "folders": folders, "built": time.time()}, f)
    return {"ok": True, "files": files, "chunks": len(chunks), "folders": folders, "seconds": round(time.time() - t0, 1),
            "index": IDX}


def find(query, k=6):
    if not os.path.isfile(IDX):
        build()
    with open(IDX, "rb") as f:
        d = pickle.load(f)
    if not d["chunks"]:
        return {"ok": True, "hits": [], "note": "no CadQuery scripts indexed"}
    q = norm(query)
    s = 0.6 * (d["W"] @ d["wv"].transform([q]).T).toarray().ravel() + 0.4 * (d["C"] @ d["cv"].transform([q]).T).toarray().ravel()
    size = np.array([min(1.0, (c["to"] - c["from"] + 1) / 15) ** 0.3 for c in d["chunks"]])
    s = s * size
    order = s.argsort()[::-1][:k]
    hits = []
    for i in order:
        if s[i] <= 0.02:
            break
        c = d["chunks"][i]
        hits.append({"score": round(float(s[i]), 3), "where": f"{c['file']}:{c['from']}-{c['to']}", "name": c["name"],
                     "doc": c["doc"], "params": c["params"][:15]})
    age_h = (time.time() - d["built"]) / 3600
    return {"ok": True, "query": query, "hits": hits, "index_age_h": round(age_h, 1)}
