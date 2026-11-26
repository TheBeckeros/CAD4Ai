"""Local checks of a STEP model after a rebuild (no Claude): B-rep validity and volume of every part.

Usage: python checks.py <file.step>  ->  one JSON line
{"ok": true, "parts": n, "invalid": ["name", ...], "volume": mm3, "vols": {"name": mm3}, "seconds": s}
"""
import json
import sys
import time


def main(path):
    t0 = time.time()
    from OCP.STEPCAFControl import STEPCAFControl_Reader
    from OCP.TDocStd import TDocStd_Document
    from OCP.TCollection import TCollection_ExtendedString
    from OCP.XCAFDoc import XCAFDoc_DocumentTool
    from OCP.TDF import TDF_Label, TDF_LabelSequence
    from OCP.TDataStd import TDataStd_Name
    from OCP.IFSelect import IFSelect_RetDone
    from OCP.BRepCheck import BRepCheck_Analyzer
    from OCP.GProp import GProp_GProps
    from OCP.BRepGProp import BRepGProp

    doc = TDocStd_Document(TCollection_ExtendedString("XmlOcaf"))
    rd = STEPCAFControl_Reader()
    rd.SetNameMode(True)
    if rd.ReadFile(path) != IFSelect_RetDone or not rd.Transfer(doc):
        raise RuntimeError("cannot read STEP")
    st = XCAFDoc_DocumentTool.ShapeTool_s(doc.Main())

    def name(lab):
        a = TDataStd_Name()
        return a.Get().ToExtString() if lab.FindAttribute(TDataStd_Name.GetID_s(), a) else ""

    # every distinct part shape once (instances share it), named by its first instance
    shapes = {}

    def walk(lab):
        ref = lab
        if st.IsReference_s(lab):
            ref = TDF_Label()
            st.GetReferredShape_s(lab, ref)
        if st.IsAssembly_s(ref):
            seq = TDF_LabelSequence()
            st.GetComponents_s(ref, seq)
            for i in range(1, seq.Length() + 1):
                walk(seq.Value(i))
            return
        key = ref.Tag()
        if key not in shapes:
            shapes[key] = (name(lab) or name(ref) or f"part{len(shapes) + 1}", st.GetShape_s(ref))
    roots = TDF_LabelSequence()
    st.GetFreeShapes(roots)
    for i in range(1, roots.Length() + 1):
        walk(roots.Value(i))

    invalid, vols, total = [], {}, 0.0
    for nm, shp in shapes.values():
        if not BRepCheck_Analyzer(shp).IsValid():
            invalid.append(nm)
        g = GProp_GProps()
        BRepGProp.VolumeProperties_s(shp, g)
        v = abs(g.Mass())
        vols[nm] = round(v, 1)
        total += v
    return {"ok": True, "parts": len(shapes), "invalid": invalid, "volume": round(total, 1), "vols": vols,
            "seconds": round(time.time() - t0, 1)}


if __name__ == "__main__":
    try:
        print(json.dumps(main(sys.argv[1]), ensure_ascii=False))
    except Exception as exc:  # noqa: BLE001
        print(json.dumps({"ok": False, "error": f"{type(exc).__name__}: {exc}"}))
