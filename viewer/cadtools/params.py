"""The one parser of a model script's parameter block (viewer Parameters tab, sandbox runs, change guard).

A parameter is a top-level `NAME = <number|bool>` on one line; its comment gives description, [unit] and an
optional lo..hi range; "# --- Group ---" lines group them. Values are rewritten in place (byte offsets), so
the rest of the line and the file stay untouched.
"""
import ast
import io
import re
import tokenize

PARAM_NAME = re.compile(r"^[A-Z][A-Z0-9_]*$")
# a comment line that starts a parameter group: "# --- Lid ---", "# === Lid ===", "## Lid"
SECTION = re.compile(r"^#+\s*[-=*~]{3,}\s*(.+?)\s*[-=*~]*\s*$|^##+\s+(.+?)\s*$")
# a range in the parameter comment: "[mm] 10..80" or "10…80"
RANGE = re.compile(r"(-?\d+(?:\.\d+)?)\s*(?:\.\.|…)\s*(-?\d+(?:\.\d+)?)")


def _literal(node):
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float, bool)):
        return node.value
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.USub, ast.UAdd)) and \
            isinstance(node.operand, ast.Constant) and isinstance(node.operand.value, (int, float)) and \
            not isinstance(node.operand.value, bool):
        return -node.operand.value if isinstance(node.op, ast.USub) else node.operand.value
    raise ValueError


def parse_params(script):
    with open(script, encoding="utf-8") as f:
        src = f.read()
    tree = ast.parse(src)
    comments, sections = {}, []
    try:
        for tok in tokenize.generate_tokens(io.StringIO(src).readline):
            if tok.type == tokenize.COMMENT:
                comments[tok.start[0]] = tok.string.lstrip("#").strip()
                m = SECTION.match(tok.string.strip()) if tok.line.strip().startswith("#") else None
                if m:
                    sections.append((tok.start[0], (m.group(1) or m.group(2)).strip()))
    except tokenize.TokenError:
        pass
    out = []
    for node in tree.body:
        if not isinstance(node, ast.Assign) or len(node.targets) != 1:
            continue
        t = node.targets[0]
        if not isinstance(t, ast.Name) or not PARAM_NAME.match(t.id):
            continue
        try:
            val = _literal(node.value)
        except ValueError:
            continue
        if node.value.lineno != node.value.end_lineno:
            continue
        comment = comments.get(node.lineno, "")
        unit = ""
        m = re.search(r"\[([^\]]+)\]", comment)
        if m:
            unit = m.group(1)
        kind = "bool" if isinstance(val, bool) else ("int" if isinstance(val, int) else "float")
        group = next((name for line, name in reversed(sections) if line < node.lineno), "")
        item = {
            "name": t.id, "value": val, "type": kind, "comment": comment, "unit": unit, "group": group,
            "line": node.value.lineno, "col": node.value.col_offset, "endCol": node.value.end_col_offset,
        }
        r = RANGE.search(comment)
        if r and kind != "bool":
            lo, hi = sorted((float(r.group(1)), float(r.group(2))))
            item["min"], item["max"] = lo, hi
        out.append(item)
    return out


def fmt_value(val, kind):
    if kind == "bool":
        return "True" if val else "False"
    if kind == "int":
        return str(int(round(float(val))))
    v = float(val)
    s = f"{v:.6f}".rstrip("0")
    return s + "0" if s.endswith(".") else s


def write_params(script, values):
    params = {p["name"]: p for p in parse_params(script)}
    with open(script, encoding="utf-8") as f:
        lines = f.read().split("\n")
    changes = []
    # back to front by position so offsets do not shift
    for name, val in sorted(values.items(), key=lambda kv: (-params[kv[0]]["line"], -params[kv[0]]["col"])
                            if kv[0] in params else (0, 0)):
        p = params.get(name)
        if not p:
            continue
        i = p["line"] - 1
        line = lines[i]
        # col_offset is in UTF-8 bytes
        b = line.encode("utf-8")
        new = fmt_value(val, p["type"])
        old = b[p["col"]:p["endCol"]].decode("utf-8")
        if old == new:
            continue
        lines[i] = (b[:p["col"]] + new.encode("utf-8") + b[p["endCol"]:]).decode("utf-8")
        changes.append(f"{name} {old}→{new}")
    with open(script, "w", encoding="utf-8", newline="") as f:
        f.write("\n".join(lines))
    return changes


def set_in_source(src, values):
    """Same rewrite as write_params, on a source string (for sandbox copies)."""
    import os
    import tempfile
    fd, tmp = tempfile.mkstemp(suffix=".py")
    os.close(fd)
    try:
        with open(tmp, "w", encoding="utf-8", newline="") as f:
            f.write(src)
        known = {p["name"] for p in parse_params(tmp)}
        missing = [k for k in values if k not in known]
        if missing:
            raise ValueError(f"parameter(s) {', '.join(missing)} not found as plain numbers at the top of the script")
        write_params(tmp, values)
        with open(tmp, encoding="utf-8") as f:
            return f.read()
    finally:
        os.remove(tmp)
