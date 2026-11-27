"""Part colours of a STEP file, read with OCCT's XCAF (the browser loader misses colours set on instances).

Usage: python stepcolors.py <file.step>  ->  {"colors": {"<part name>": [r, g, b]}}  (linear RGB, like occt-import-js)

CadQuery assemblies and most CAD systems put the colour on the instance (or on the
assembly above it) when one shape is used several times; occt-import-js only reads
colours stored on the shape itself, so those parts lost their colour in the viewer.
"""
import json
import sys

sys.dont_write_bytecode = True  # no __pycache__ inside the app folder


def read_colors(path):
    from OCP.STEPCAFControl import STEPCAFControl_Reader
    from OCP.TDocStd import TDocStd_Document
    from OCP.TCollection import TCollection_ExtendedString
    from OCP.XCAFDoc import XCAFDoc_DocumentTool, XCAFDoc_ColorType
    from OCP.TDF import TDF_Label, TDF_LabelSequence
    from OCP.TDataStd import TDataStd_Name
    from OCP.Quantity import Quantity_Color
    from OCP.IFSelect import IFSelect_RetDone

    doc = TDocStd_Document(TCollection_ExtendedString("XmlOcaf"))
    rd = STEPCAFControl_Reader()
    rd.SetColorMode(True)
    rd.SetNameMode(True)
    if rd.ReadFile(path) != IFSelect_RetDone or not rd.Transfer(doc):
        raise RuntimeError("cannot read STEP")
    st = XCAFDoc_DocumentTool.ShapeTool_s(doc.Main())
    ct = XCAFDoc_DocumentTool.ColorTool_s(doc.Main())

    def name(lab):
        a = TDataStd_Name()
        return a.Get().ToExtString() if lab.FindAttribute(TDataStd_Name.GetID_s(), a) else ""

    types = (XCAFDoc_ColorType.XCAFDoc_ColorSurf, XCAFDoc_ColorType.XCAFDoc_ColorGen)

    def rgb(c):
        return [round(c.Red(), 6), round(c.Green(), 6), round(c.Blue(), 6)]

    def own(lab):
        c = Quantity_Color()
        for t in types:
            if ct.GetColor_s(lab, t, c):
                return rgb(c)
        # colour bound to the located shape (also how instance colours are stored)
        shp = st.GetShape_s(lab)
        if not shp.IsNull():
            for t in types:
                if ct.GetColor(shp, t, c):
                    return rgb(c)
        return None

    def sub(lab):
        # a part made of several solids keeps the colour on each solid (a sub-shape label)
        seq = TDF_LabelSequence()
        st.GetSubShapes_s(lab, seq)
        for i in range(1, seq.Length() + 1):
            c = own(seq.Value(i))
            if c:
                return c
        return None

    colors = {}

    def walk(lab, inherited):
        ref = lab
        if st.IsReference_s(lab):
            ref = TDF_Label()
            st.GetReferredShape_s(lab, ref)
        col = own(lab) or own(ref) or sub(ref) or inherited
        if st.IsAssembly_s(ref):
            seq = TDF_LabelSequence()
            st.GetComponents_s(ref, seq)
            for i in range(1, seq.Length() + 1):
                walk(seq.Value(i), col)
            return
        if col:
            for nm in {name(lab), name(ref)} - {""}:
                colors.setdefault(nm, col)

    roots = TDF_LabelSequence()
    st.GetFreeShapes(roots)
    for i in range(1, roots.Length() + 1):
        walk(roots.Value(i), None)
    return colors


if __name__ == "__main__":
    try:
        print(json.dumps({"colors": read_colors(sys.argv[1])}))
    except Exception as exc:  # noqa: BLE001
        print(json.dumps({"colors": {}, "error": f"{type(exc).__name__}: {exc}"}))
