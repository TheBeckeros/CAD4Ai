"""Export the current model to another 3D format (CAD4Ai Export menu).

Run:  python export.py <source .step|.stl> <format> [--quality coarse|normal|fine] [--out <path>]
Without --out a native "Save as" dialog asks where to save. Prints one JSON line:
{"ok": true, "path": ...} | {"cancelled": true} | {"ok": false, "error": ...}
Conversion from STEP needs CadQuery; an STL source can only be saved as STL.
"""
import argparse
import json
import os
import shutil
import sys

# format -> (extension, description, needs CadQuery)
FORMATS = {
    "step": (".step", "AP214 · exact B-rep, keeps names and colours", False),
    "step-merged": (".step", "AP214 · cylinders and planes merged into whole faces (no split half-faces)", True),
    "iges": (".igs", "exact B-rep, older CAD systems", True),
    "brep": (".brep", "OpenCascade native, exact", True),
    "stl": (".stl", "mesh · 3D printing", True),
    "3mf": (".3mf", "mesh · modern 3D printing", True),
    "obj": (".obj", "mesh · rendering, Blender", True),
    "glb": (".glb", "binary glTF · web, AR", True),
    "gltf": (".gltf", "glTF JSON + .bin", True),
    "amf": (".amf", "mesh · older 3D printing", True),
    "wrl": (".wrl", "mesh · VRML", True),
}
QUALITY = {"coarse": (0.1, 0.5), "normal": (0.02, 0.2), "fine": (0.005, 0.1)}  # (mm, rad)


def have_cadquery():
    try:
        import cadquery  # noqa: F401
        return True
    except Exception:  # noqa: BLE001
        return False


def ask_path(src, fmt):
    import tkinter
    from tkinter import filedialog
    ext, desc, _ = FORMATS[fmt]
    root = tkinter.Tk()
    root.withdraw()
    root.attributes("-topmost", True)  # otherwise the dialog opens behind the Claude window
    stem = os.path.splitext(os.path.basename(src))[0]
    path = filedialog.asksaveasfilename(
        parent=root, title=f"Export as {fmt.upper()}", initialdir=os.path.dirname(src),
        initialfile=stem + ext, defaultextension=ext, filetypes=[(f"{fmt.upper()} {desc}", "*" + ext), ("All files", "*.*")])
    root.destroy()
    return path


def write_obj(shape, path, tol, ang):
    lines, base = [f"# exported by CAD4Ai from {os.path.basename(path)}"], 1
    for i, solid in enumerate(shape.Solids() or [shape], 1):
        verts, tris = solid.tessellate(tol, ang)
        lines.append(f"o part_{i}")
        lines += [f"v {v.x:.6g} {v.y:.6g} {v.z:.6g}" for v in verts]
        lines += [f"f {a + base} {b + base} {c + base}" for a, b, c in tris]
        base += len(verts)
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


def write_step_merged(src, out):
    """STEP with split faces merged (ShapeUpgrade_UnifySameDomain) while keeping names, colours and the assembly.

    CadQuery and many kernels build a full cylinder from two half-faces; merging leaves one face per
    cylinder (a closed periodic face still has its seam edge, which every B-rep needs)."""
    from OCP.STEPCAFControl import STEPCAFControl_Reader, STEPCAFControl_Writer
    from OCP.TDocStd import TDocStd_Document
    from OCP.TCollection import TCollection_ExtendedString
    from OCP.XCAFDoc import XCAFDoc_DocumentTool
    from OCP.TDF import TDF_LabelSequence
    from OCP.ShapeUpgrade import ShapeUpgrade_UnifySameDomain
    from OCP.IFSelect import IFSelect_RetDone
    from OCP.STEPControl import STEPControl_AsIs

    doc = TDocStd_Document(TCollection_ExtendedString("XmlOcaf"))
    rd = STEPCAFControl_Reader()
    rd.SetColorMode(True)
    rd.SetNameMode(True)
    rd.SetLayerMode(True)
    if rd.ReadFile(src) != IFSelect_RetDone or not rd.Transfer(doc):
        raise RuntimeError("cannot read the STEP file")
    st = XCAFDoc_DocumentTool.ShapeTool_s(doc.Main())
    labels = TDF_LabelSequence()
    st.GetShapes(labels)
    for i in range(1, labels.Length() + 1):
        lab = labels.Value(i)
        if st.IsAssembly_s(lab) or st.IsReference_s(lab):
            continue
        shp = st.GetShape_s(lab)
        if shp.IsNull():
            continue
        usd = ShapeUpgrade_UnifySameDomain(shp, True, True, True)
        usd.Build()
        new = usd.Shape()
        if new.IsNull():
            continue
        hist = usd.History()
        # sub-shape labels (coloured solids or faces) follow their merged shape
        subs = TDF_LabelSequence()
        st.GetSubShapes_s(lab, subs)
        for k in range(1, subs.Length() + 1):
            sl = subs.Value(k)
            old = st.GetShape_s(sl)
            if hist.IsRemoved(old):
                continue
            mod = hist.Modified(old)
            if mod.Size() == 1:
                st.SetShape(sl, mod.First())
        st.SetShape(lab, new)
    st.UpdateAssemblies()
    w = STEPCAFControl_Writer()
    w.SetColorMode(True)
    w.SetNameMode(True)
    w.SetLayerMode(True)
    if not w.Transfer(doc, STEPControl_AsIs) or w.Write(out) != IFSelect_RetDone:
        raise RuntimeError("STEP writer failed")


def export(src, fmt, out, quality="normal"):
    is_step = src.lower().endswith((".step", ".stp"))
    if (fmt == "step" and is_step) or (fmt == "stl" and not is_step):
        shutil.copy2(src, out)  # same format: keep the original bytes (names, colours, assembly)
        return
    if not is_step:
        raise ValueError("an STL model can only be saved as STL")
    if fmt == "step-merged":
        write_step_merged(src, out)
        if not os.path.isfile(out) or os.path.getsize(out) == 0:
            raise RuntimeError("the exporter wrote nothing")
        return
    import cadquery as cq
    tol, ang = QUALITY[quality]
    vals = cq.importers.importStep(src).vals()
    shape = vals[0] if len(vals) == 1 else cq.Compound.makeCompound(vals)
    if fmt == "iges":
        from OCP.IGESControl import IGESControl_Writer
        w = IGESControl_Writer("MM", 1)  # 1 = B-rep solids, not trimmed surfaces only
        w.AddShape(shape.wrapped)
        w.ComputeModel()
        if not w.Write(out):
            raise RuntimeError("IGES writer failed")
    elif fmt == "obj":
        write_obj(shape, out, tol, ang)
    elif fmt in ("glb", "gltf"):
        cq.Assembly(shape, name=os.path.splitext(os.path.basename(src))[0]).export(
            out, "GLTF", tolerance=tol, angularTolerance=ang)
    else:
        kind = {"brep": "BREP", "stl": "STL", "3mf": "3MF", "amf": "AMF", "wrl": "VRML", "step": "STEP"}[fmt]
        cq.exporters.export(shape, out, kind, tolerance=tol, angularTolerance=ang)
    if not os.path.isfile(out) or os.path.getsize(out) == 0:
        raise RuntimeError("the exporter wrote nothing")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("src")
    ap.add_argument("format", choices=sorted(FORMATS))
    ap.add_argument("--quality", default="normal", choices=sorted(QUALITY))
    ap.add_argument("--out")
    a = ap.parse_args()
    try:
        out = a.out or ask_path(a.src, a.format)
        if not out:
            print(json.dumps({"cancelled": True}))
            return
        export(a.src, a.format, out, a.quality)
        print(json.dumps({"ok": True, "path": os.path.abspath(out), "size": os.path.getsize(out)}))
    except Exception as exc:  # noqa: BLE001
        print(json.dumps({"ok": False, "error": f"{type(exc).__name__}: {exc}"}))
        sys.exit(1)


if __name__ == "__main__":
    main()
