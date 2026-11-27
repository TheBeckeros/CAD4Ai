"""Realistic screws and nuts: real geometry 1:1 except the thread (building blocks for lib_screws / lib_nuts).

Frames: headed screws - head seat (underside) at Z=0, head +Z, shank -Z; countersunk - head top at Z=0, L includes
the head; set screws / studs - see their families; nuts - bottom face at Z=0, up to +Z.
Real details: underhead fillet, thread length b by the standard, tip chamfer / point, drives (hex socket with
118 deg drill point, slot, cross recess, hexalobular), head chamfers, washer faces, nut double chamfer and 120 deg
countersinks.

Thread: not a helix. The threaded surface (nominal diameter on screws, tap drill bore in nuts - the CAD4Ai
convention) is split into rings P/2 wide; apply_colors / thread_colors colours every other ring dark and the
body metal, like a cosmetic thread. Rings are found by radius + width, so placed / rotated copies work too.
"""
import math

METAL = (0.70, 0.69, 0.67)        # sRGB (as written to STEP): body colour of steel parts
THREAD_DARK = (0.40, 0.40, 0.41)  # every other thread ring

# underhead fillet r min (ISO 4762 / 4017 / 4014) and hex washer face dw min, c max (ISO 4017 / 4014)
UNDERHEAD_R = {"M2": 0.1, "M2.5": 0.1, "M3": 0.1, "M4": 0.2, "M5": 0.2, "M6": 0.25, "M8": 0.4, "M10": 0.4,
               "M12": 0.6, "M14": 0.6, "M16": 0.6, "M18": 0.6, "M20": 0.8, "M22": 0.8, "M24": 0.8, "M27": 1.0, "M30": 1.0}
HEX_WASHER = {"M2": (3.1, 0.25), "M2.5": (4.0, 0.25), "M3": (4.6, 0.4), "M4": (5.9, 0.4), "M5": (6.9, 0.5),
              "M6": (8.9, 0.5), "M8": (11.6, 0.6), "M10": (14.6, 0.6), "M12": (16.6, 0.6), "M14": (19.6, 0.6),
              "M16": (22.5, 0.8), "M18": (25.3, 0.8), "M20": (28.2, 0.8), "M22": (31.7, 0.8), "M24": (33.6, 0.8),
              "M27": (38.0, 0.8), "M30": (42.8, 0.8)}
CSK_T = {"M3": 1.1, "M4": 1.5, "M5": 1.9, "M6": 2.2, "M8": 3.0, "M10": 3.6, "M12": 4.3, "M16": 4.8, "M20": 5.6}
BUTTON_T = {"M3": 1.04, "M4": 1.3, "M5": 1.56, "M6": 2.08, "M8": 2.6, "M10": 3.12, "M12": 4.16, "M16": 5.2}
# self-tapping thread ST: pitch
ST_PITCH = {"ST2.2": 0.8, "ST2.9": 1.1, "ST3.5": 1.3, "ST3.9": 1.3, "ST4.2": 1.4, "ST4.8": 1.6, "ST5.5": 1.8, "ST6.3": 1.8}
# hexalobular (Torx) point-to-point A, and the cross recess (Phillips) size -> recess diameter m
TORX_A = {6: 1.75, 8: 2.4, 10: 2.8, 15: 3.35, 20: 3.95, 25: 4.5, 27: 5.1, 30: 5.6, 40: 6.75, 45: 7.93, 50: 8.95, 55: 11.35}
PH_M = {0: 1.9, 1: 3.0, 2: 4.4, 3: 6.3, 4: 8.7}
TAN30 = math.tan(math.radians(30))


def thread_length(std_name, d, L, head_k=0.0):
    """Threaded length from the tip [mm]: ISO 4762 / 10642 / 4014-type b = 2d+12 / 2d+6 (L<=125, 2d+12 <=200,
    2d+25 above); short screws (plain shank < 1 d) are fully threaded (None)."""
    if std_name in ("ISO 4762", "ISO 10642", "DIN 7984"):
        b = 2 * d + 12
    elif std_name in ("ISO 4014", "ISO 8765", "ISO 4162p"):
        b = 2 * d + (6 if L <= 125 else 12 if L <= 200 else 25)
    else:
        return None
    return b if L - head_k - b >= d else None


# ---------------------------------------------------------------- profile helpers

def _revolve(cq, segs, clean=False):
    """Solid of revolution about Z from a profile in the XZ half plane: segs = [(x, z) | ("arc", mid, end)]."""
    wp = cq.Workplane("XZ").moveTo(*segs[0])
    for s in segs[1:]:
        wp = wp.threePointArc(s[1], s[2]) if s[0] == "arc" else wp.lineTo(*s)
    return wp.close().revolve(360, (0, 0, 0), (0, 1, 0), clean=clean)


MAX_RINGS = 300


def _bands(x, z0, z1, w):
    """Profile points on radius x from z0 to z1 (either direction) splitting it every w (P/2). Long threads use a
    multiple of w so a part never gets more than MAX_RINGS rings (thread_faces finds the rings by their common width)."""
    n = int(abs(z1 - z0) / w + 1e-9)
    if n > MAX_RINGS:
        w *= math.ceil(n / MAX_RINGS)
        n = int(abs(z1 - z0) / w + 1e-9)
    step = w if z1 > z0 else -w
    pts = [(x, z0 + i * step) for i in range(1, n + 1) if abs(z0 + i * step - z1) > 1e-6]
    return pts + [(x, z1)]


def tip_profile(d, P, L, tip="chamfer", dp=None, z_len=None):
    """Profile from the axis at the tip (z=-L) to the start of the cylindrical thread -> (segs, z_thread_start).
    tip: chamfer | point (self-tapping, form C) | cone (ISO 4027 90 deg) | dog (ISO 4028, dp x z_len) |
    cup (ISO 4029, chamfer here, cup cut later) | flat (ISO 4026) | none."""
    r = d / 2
    if tip == "none":
        return [(0, -L), (r, -L)], -L
    if tip == "point":
        lp = min(1.8 * d, 0.45 * L)
        return [(0, -L), (0.12 * d, -L), (r, -L + lp)], -L + lp
    if tip == "cone":
        h = r - 0.1 * d
        return [(0, -L), (0.1 * d, -L), (r, -L + h)], -L + h
    if tip == "dog":
        dp = dp or 0.6 * d
        z_len = z_len or 0.5 * d
        c = 0.08 * d
        segs = [(0, -L), (dp / 2 - c, -L), (dp / 2, -L + c), (dp / 2, -L + z_len), (r - 0.6 * P, -L + z_len),
                (r, -L + z_len + 0.6 * P)]
        return segs, -L + z_len + 0.6 * P
    ch = min(0.7 * P, r * 0.3)
    return [(0, -L), (r - ch, -L), (r, -L + ch)], -L + ch


def shank(d, P, L, z_top, thread_top, tip="chamfer", **tipkw):
    """Profile from the tip up the shank to (d/2, z_top): tip, P/2 thread rings up to thread_top, plain above."""
    r = d / 2
    segs, z0 = tip_profile(d, P, L, tip, **tipkw)
    top = min(thread_top, z_top)
    if top > z0 + 1e-6:
        segs += _bands(r, z0, top, P / 2)
    if z_top > max(top, z0) + 1e-6:
        segs.append((r, z_top))
    return segs


def _fillet_to_seat(r_shank, rf):
    """Concave underhead fillet from the shank (r_shank, -rf) to the seat (r_shank + rf, 0)."""
    if rf <= 0:
        return [(r_shank, 0)]
    c = math.sqrt(0.5)
    return [("arc", (r_shank + rf - rf * c, -rf + rf * c), (r_shank + rf, 0))]


def _hex_prism(cq, s, z0, z1):
    return cq.Workplane("XY").workplane(offset=z0).polygon(6, s / math.cos(math.pi / 6)).extrude(z1 - z0)


def _sq_prism(cq, s, z0, z1):
    return cq.Workplane("XY").workplane(offset=z0).rect(s, s).extrude(z1 - z0)


def chamfered_prism(cq, s, z0, z1, top=True, bottom=False, sides=6, r0f=0.95):
    """Hexagon (or square) across flats s from z0 to z1 with the 30 deg chamfer circle (~0.95 s) on top / bottom."""
    e2 = (s / math.cos(math.pi / 6) if sides == 6 else s * math.sqrt(2)) / 2
    R, r0 = e2 + 1.0, r0f * s / 2
    dz = (R - r0) * TAN30
    prof = [(0, z0)]
    prof += [(r0, z0), (R, z0 + dz)] if bottom else [(R, z0)]
    prof += [(R, z1 - dz), (r0, z1)] if top else [(R, z1)]
    prof += [(0, z1)]
    prism = _hex_prism(cq, s, z0, z1) if sides == 6 else _sq_prism(cq, s, z0, z1)
    return prism.intersect(_revolve(cq, prof, clean=True))


_chamfered_hex = chamfered_prism


# ---------------------------------------------------------------- drives (tools to cut from the head top at z_top)

def socket_tool(cq, s, depth, z_top):
    """Hex socket: across flats s, flat depth below z_top, 118 deg drill-point bottom, small 90 deg entry chamfer."""
    r = s / 2
    tip = r / math.tan(math.radians(59))
    e = s / math.cos(math.pi / 6) / 2
    cone = _revolve(cq, [(0, z_top - depth - tip), (r, z_top - depth), (r, z_top - depth + 1e-3),
                         (0, z_top - depth + 1e-3)], clean=True)
    entry = _revolve(cq, [(0, z_top - 0.1 * s), (e, z_top - 0.1 * s), (e + 0.1 * s + 1, z_top + 1), (0, z_top + 1)], clean=True)
    return _hex_prism(cq, s, z_top - depth, z_top + 1.0).union(cone).union(entry)


def slot_tool(cq, n, t, z_top, width):
    return cq.Workplane("XY").workplane(offset=z_top - t).rect(width + 2, n).extrude(t + 1)


def cross_tool(cq, ph, z_top, depth=None):
    """Phillips recess approximated: two crossing tapered wings + a 26.5 deg cone, recess diameter m by PH size."""
    m = PH_M.get(ph, 4.4)
    depth = depth or 0.62 * m
    w = {0: 0.35, 1: 0.6, 2: 0.85, 3: 1.25, 4: 1.7}.get(ph, 0.85)
    cone = _revolve(cq, [(0, z_top - depth), (m * 0.28, z_top - depth * 0.8), (m / 2 * 0.62, z_top), (m / 2 * 0.62, z_top + 1), (0, z_top + 1)], clean=True)
    wing = (cq.Workplane("XZ").polyline([(-m / 2, z_top + 1), (m / 2, z_top + 1), (m / 2, z_top), (w, z_top - depth),
                                          (-w, z_top - depth), (-m / 2, z_top)]).close().extrude(w, both=True))
    return cone.union(wing).union(wing.rotate((0, 0, 0), (0, 0, 1), 90))


def torx_tool(cq, size, depth, z_top):
    """Hexalobular socket (Torx): six lobes, point-to-point A by size."""
    A = TORX_A.get(size, 0.25 * size)
    R = A / 2
    ri = 0.72 * R
    pts = []
    for i in range(12):
        a = math.radians(i * 30)
        rr = R if i % 2 == 0 else ri
        pts.append((rr * math.cos(a), rr * math.sin(a)))
    wp = cq.Workplane("XY").workplane(offset=z_top - depth).moveTo(*pts[0])
    for i in range(12):
        p1 = pts[(i + 1) % 12]
        a_mid = math.radians(i * 30 + 15)
        rm = (R + ri) / 2 * (1.06 if i % 2 == 0 else 0.94)
        wp = wp.threePointArc((rm * math.cos(a_mid), rm * math.sin(a_mid)), p1)
    return wp.close().extrude(depth + 1)


def drive(cq, body, kind, z_top, head_w, **k):
    if kind == "socket":
        return body.cut(socket_tool(cq, k["s"], k["t"], z_top), clean=False)
    if kind == "slot":
        return body.cut(slot_tool(cq, k["n"], k["t"], z_top, head_w), clean=False)
    if kind == "cross":
        return body.cut(cross_tool(cq, k["ph"], z_top), clean=False)
    if kind == "torx":
        return body.cut(torx_tool(cq, k["tx"], k.get("t", 0.4 * head_w), z_top), clean=False)
    return body


# ---------------------------------------------------------------- headed screw

def headed(d, P, L, head, b=None, tip="chamfer", rf=None, **h):
    """Generic screw. head: hex | flange | socket | button | cheese | pan | csk | raised_csk | square | wing |
    eye | none (stud: shank only). b = thread length from the tip (None = full thread up to ~2P under the head).
    h: head dimensions + drive (drive='socket' s,t | 'slot' n,t | 'cross' ph | 'torx' tx,t)."""
    import cadquery as cq
    r = d / 2
    rf = 0.1 * d if rf is None else rf
    if head in ("csk", "raised_csk"):
        dk, k = h["dk"], h["k"]
        land = max(0.1, 0.03 * dk)
        thread_top = -L + b if b else -k - max(P, 0.5)
        segs = shank(d, P, L, -k, thread_top, tip)
        segs += [(dk / 2 - land, -land), (dk / 2 - land, 0)]
        f = h.get("f", 0)
        if head == "raised_csk" and f:
            Rs = ((dk / 2 - land) ** 2 + f ** 2) / (2 * f)
            zc = f - Rs
            am = math.atan2(-zc, dk / 2 - land) / 2 + math.pi / 4
            segs += [("arc", (Rs * math.cos(am), zc + Rs * math.sin(am)), (0, f))]
            top = f
        else:
            segs += [(0, 0)]
            top = 0
        body = _revolve(cq, segs)
        return drive(cq, body, h.get("drive"), top, dk, **h)

    thread_top = -L + b if b else -max(2 * P, rf + P / 2)
    segs = shank(d, P, L, -rf, thread_top, tip, **{k: h[k] for k in ("dp", "z_len") if k in h}) + _fillet_to_seat(r, rf)

    if head == "hex":
        s, k = h["s"], h["k"]
        dw, c = h.get("dw", 0.9 * s), h.get("c", 0.0)
        if c > 0:
            segs += [(dw / 2, 0), (dw / 2, c), (0, c)]
            return _revolve(cq, segs).union(chamfered_prism(cq, s, c, k), clean=False)
        segs += [(0, 0)]
        return _revolve(cq, segs).union(chamfered_prism(cq, s, 0, k), clean=False)
    if head == "flange":  # hex with a round flange at the seat (ISO 4162)
        s, k, dc, c = h["s"], h["k"], h["dc"], h["c"]
        segs += [(dc / 2, 0), (dc / 2, c * 0.6), (dc / 2 - c, c), (0, c)]
        return _revolve(cq, segs).union(chamfered_prism(cq, s, c, k), clean=False)
    if head == "square":
        s, k = h["s"], h["k"]
        dk_c, c = h.get("dc"), h.get("c", 0.0)
        if dk_c:
            segs += [(dk_c / 2, 0), (dk_c / 2, c), (0, c)]
            return _revolve(cq, segs).union(chamfered_prism(cq, s, c, k, sides=4), clean=False)
        segs += [(0, 0)]
        return _revolve(cq, segs).union(chamfered_prism(cq, s, 0, k, sides=4), clean=False)
    if head == "socket":
        dk, k = h["dk"], h["k"]
        ch = max(0.2, 0.1 * d)
        segs += [(dk / 2 - 0.1 * ch, 0), (dk / 2, 0.1 * ch), (dk / 2, k - ch), (dk / 2 - ch, k), (0, k)]
        return drive(cq, _revolve(cq, segs), h.get("drive", "socket"), k, dk, **h)
    if head == "cheese":
        dk, k = h["dk"], h["k"]
        ch = 0.08 * dk
        segs += [(dk / 2, 0), (dk / 2, k - ch), (dk / 2 - ch, k), (0, k)]
        return drive(cq, _revolve(cq, segs), h.get("drive", "slot"), k, dk, **h)
    if head in ("pan", "button"):
        dk, k = h["dk"], h["k"]
        R = dk / 2
        z_e = (0.12 if head == "button" else 0.3) * k
        rt = 0.0 if head == "button" else 0.32 * dk       # pan: flat top of radius rt with a rounded edge
        if rt:
            c45 = math.sqrt(0.5)
            segs += [(R, 0), (R, z_e), ("arc", (rt + (R - rt) * c45, z_e + (k - z_e) * c45), (rt, k)), (0, k)]
        else:
            zc = ((R ** 2 + z_e ** 2) - k ** 2) / (2 * (z_e - k))
            rs = k - zc
            a0 = math.atan2(z_e - zc, R)
            am = (a0 + math.pi / 2) / 2
            segs += [(R, 0), (R, z_e), ("arc", (rs * math.cos(am), zc + rs * math.sin(am)), (0, k))]
        return drive(cq, _revolve(cq, segs), h.get("drive", "socket"), k, dk, **h)
    if head == "wing":  # DIN 316: round boss + two flat wings
        e, hh = h["e"], h["h"]
        db = h.get("db", 1.6 * d + 2)
        hb = 0.55 * hh
        segs += [(db / 2, 0), (db / 2 * 0.85, hb), (0, hb)]
        body = _revolve(cq, segs)
        t = h.get("t", 0.12 * e)
        wing = (cq.Workplane("XZ").polyline([(-db / 2 * 0.6, 0), (-e / 2, hh * 0.7), (-e / 2 + 0.06 * e, hh), (-db / 2 * 0.5, hh),
                                              (db / 2 * 0.5, hh), (e / 2 - 0.06 * e, hh), (e / 2, hh * 0.7), (db / 2 * 0.6, 0)])
                .close().extrude(t / 2, both=True))
        return body.union(wing, clean=False)
    if head == "eye":  # DIN 580 eye bolt: collar + neck + ring (torus)
        d1, d2, d4, hh, k = h["d1"], h["d2"], h["d4"], h["h"], h["k"]
        segs += [(d4 / 2, 0), (d4 / 2, k * 0.7), (d4 / 2 - 0.3 * k, k), (0, k)]
        body = _revolve(cq, segs)
        rc = (d1 - d2) / 2                         # ring: centre-line radius
        zc = hh - d1 / 2                           # ring centre height above the seat
        torus = cq.Workplane("XY").add(cq.Solid.makeTorus(rc, d2 / 2, pnt=cq.Vector(0, 0, zc), dir=cq.Vector(0, 1, 0)))
        z_ring = zc - rc + d2 * 0.25
        neck = _revolve(cq, [(0, k * 0.5), (0.42 * d4, k * 0.5), (0.32 * d4, z_ring), (0, z_ring)], clean=True)
        return body.union(neck, clean=False).union(torus, clean=False)
    if head == "shoulder":  # ISO 7379: socket head, ground shoulder ds x ls, thread d x l2 below it
        dk, k, ds, ls, l2 = h["dk"], h["k"], h["ds"], h["ls"], h["l2"]
        # rebuild: thread from -ls-l2 to -ls, neck, shoulder -ls..0, head 0..k
        segs = shank(d, P, ls + l2, -ls - 0.5 * P, -ls - 0.5 * P, "chamfer")
        segs += [(0.85 * d / 2, -ls - 0.5 * P), (0.85 * d / 2, -ls), (ds / 2 - 0.3, -ls), (ds / 2, -ls + 0.3),
                 (ds / 2, -rf)] + _fillet_to_seat(ds / 2, rf)
        ch = 0.08 * dk
        segs += [(dk / 2, 0), (dk / 2, k - ch), (dk / 2 - ch, k), (0, k)]
        return drive(cq, _revolve(cq, segs), "socket", k, dk, s=h["s"], t=h.get("t", 0.6 * k))
    raise ValueError(f"unknown head {head}")


def set_screw(d, P, L, point, drive_kind, **h):
    """Headless set screw: drive end at Z=0, body to -Z; point flat | cone | dog | cup."""
    import cadquery as cq
    ch = min(0.7 * P, d * 0.15)
    tip = {"flat": "chamfer", "cup": "chamfer"}.get(point, point)
    segs = shank(d, P, L, -ch, -ch, tip, **{k: h[k] for k in ("dp", "z_len") if k in h})
    segs += [(d / 2 - ch, 0), (0, 0)]
    body = _revolve(cq, segs)
    if point == "cup":
        rz = 0.25 * d
        body = body.cut(_revolve(cq, [(0, -L - 0.01), (rz, -L - 0.01), (0, -L + rz * 0.8)], clean=True), clean=False)
    if drive_kind == "socket":
        return body.cut(socket_tool(cq, h["s"], h.get("t", max(0.5 * d, 1.2 * h["s"])), 0), clean=False)
    return body.cut(slot_tool(cq, h["n"], h["t"], 0, d), clean=False)


def stud(d, P, L, bm, b=None):
    """Stud (DIN 938/939/835/940): metal end bm to -Z from Z=0, nut end L to +Z; DIN 976 rod: bm = 0, full."""
    import cadquery as cq
    r = d / 2
    ch = min(0.7 * P, r * 0.3)
    top = L
    b = b if b is not None else L
    segs = [(0, -bm), (r - ch, -bm), (r, -bm + ch)]
    if bm > 0:
        segs += _bands(r, -bm + ch, -0.5 * P, P / 2)
        segs += [(r, top - b)] if top - b > 0 else []
        z0 = max(top - b, 0)
    else:
        z0 = -bm + ch
    segs += _bands(r, z0 if bm > 0 else -bm + ch, top - ch, P / 2)
    segs += [(r - ch, top), (0, top)]
    return _revolve(cq, segs)


# legacy entry used by std.part for the first families (dims dicts from std.dims)
def screw(d_):
    from .std import THREAD
    std_name, size, L = d_["std"], d_["size"], float(d_["L"])
    d, P = float(size[1:]), THREAD[size][0]
    form = d_.get("form", std_name)
    if std_name == "ISO 10642":
        b = thread_length("ISO 10642", d, L, d_["head_h"])
        return headed(d, P, L, "csk", b, dk=d_["head_d"], k=d_["head_h"], drive="socket", s=d_["socket"],
                      t=CSK_T.get(size, 0.6 * d_["head_h"]))
    if std_name == "ISO 4029":
        return set_screw(d, P, L, d_.get("point", "cup"), "socket", s=d_["socket"])
    rf = UNDERHEAD_R.get(size, 0.1 * d)
    b = thread_length(form, d, L)
    if std_name == "ISO 4017":
        dw, c = HEX_WASHER.get(size, (0.87 * d_["s"], 0.1 * d))
        return headed(d, P, L, "hex", b, rf=rf, s=d_["s"], k=d_["head_h"], dw=dw, c=c)
    if std_name == "ISO 4762":
        return headed(d, P, L, "socket", b, rf=rf, dk=d_["head_d"], k=d_["head_h"], s=d_["socket"], t=d_["socket_depth"])
    if std_name == "ISO 7380":
        return headed(d, P, L, "button", None, rf=rf, dk=d_["head_d"], k=d_["head_h"], s=d_["socket"],
                      t=BUTTON_T.get(size, 0.55 * d_["head_h"]))
    raise ValueError(f"no realistic screw model for {std_name}")


# ---------------------------------------------------------------- nuts

def nut_bore(cq, body, d, P, tap, z0, z1, csk=True):
    """Cut the threaded bore (tap drill, P/2 rings) with 120 deg countersinks to ~1.08 d at both open ends."""
    da = 1.08 * d
    k60 = math.tan(math.radians(60))
    zc = (da / 2 - tap / 2) / k60 if csk else 0.0
    out = 0.5
    tool = [(0, z0 - out), (da / 2 + out * k60 if csk else tap / 2, z0 - out)]
    tool += [(tap / 2, z0 + zc)]
    tool += _bands(tap / 2, z0 + zc, z1 - (zc if csk else 0), P / 2)
    tool += [(da / 2 + out * k60 if csk else tap / 2, z1 + out), (0, z1 + out)]
    return body.cut(_revolve(cq, tool), clean=False)


def hex_nut(d, P, tap, s, m, sides=6, csk=True, chamfer=(True, True)):
    import cadquery as cq
    body = chamfered_prism(cq, s, 0, m, top=chamfer[1], bottom=chamfer[0], sides=sides)
    return nut_bore(cq, body, d, P, tap, 0, m, csk)


def nut(d_):
    """legacy: ISO 4032 / 4035 from std.dims"""
    from .std import THREAD
    size = d_["size"]
    d, (P, tp) = float(size[1:]), THREAD[size][:2]
    return hex_nut(d, P, tp, d_["s"], d_["m"])


# ---------------------------------------------------------------- thread colouring

def _thread_pitches(r):
    """Pitches of threads whose nominal (screw) or tap drill (nut) radius is r."""
    from .std import THREAD, FINE
    out = []
    for size, v in THREAD.items():
        if abs(float(size[1:]) / 2 - r) < 1e-4 or abs(v[1] / 2 - r) < 1e-4:
            out.append(v[0])
    for code, tp in FINE.items():
        nom, p = code[1:].split("x")
        if abs(float(nom) / 2 - r) < 1e-4 or abs(tp / 2 - r) < 1e-4:
            out.append(float(p))
    for st, p in ST_PITCH.items():
        if abs(float(st[2:]) / 2 - r) < 1e-4:
            out.append(p)
    from . import lib_nuts
    for (nom, p) in lib_nuts.KM_THREADS:
        if abs(nom / 2 - r) < 1e-4 or abs((nom - p) / 2 - r) < 1e-4:
            out.append(p)
    return out


def thread_faces(shape):
    """Faces of a shape to colour dark: every other P/2 ring of each thread (found by radius + width)."""
    from OCP.BRepAdaptor import BRepAdaptor_Surface
    from OCP.GeomAbs import GeomAbs_Cylinder
    groups = {}
    for f in shape.Faces():
        ad = BRepAdaptor_Surface(f.wrapped)
        if ad.GetType() != GeomAbs_Cylinder:
            continue
        cyl = ad.Cylinder()
        r = cyl.Radius()
        Ps = _thread_pitches(r)
        if not Ps:
            continue
        h = f.Area() / (2 * math.pi * r)
        if not any(abs(h / (P / 2) - round(h / (P / 2))) * (P / 2) <= 2e-3 and 1 <= round(h / (P / 2)) <= 12 for P in Ps):
            continue
        ax = cyl.Axis()
        dv, lp = ax.Direction(), ax.Location()
        dvec = (dv.X(), dv.Y(), dv.Z())
        if next(c for c in dvec if abs(c) > 1e-9) < 0:
            dvec = tuple(-c for c in dvec)
        o = (lp.X(), lp.Y(), lp.Z())
        t0 = sum(o[i] * dvec[i] for i in range(3))
        foot = tuple(round(o[i] - t0 * dvec[i], 3) for i in range(3))
        key = (tuple(round(c, 4) for c in dvec), foot, round(r, 4))
        c = f.Center()
        groups.setdefault(key, []).append((c.x * dvec[0] + c.y * dvec[1] + c.z * dvec[2], f, round(h, 3)))
    out = []
    for rings in groups.values():
        hs = [h for _, _, h in rings]
        mode = max(set(hs), key=hs.count)          # the ring width; a plain shank face of another height drops out
        rings = sorted([r for r in rings if r[2] == mode], key=lambda x: x[0])
        if len(rings) < 2:
            continue
        out += [f for i, (_, f, _) in enumerate(rings) if i % 2 == 0]
    return out


def thread_colors(assy, metal=METAL, dark=THREAD_DARK):
    """Colour a cq.Assembly before export: library part colours, painted faces and every other thread ring dark."""
    from .famreg import apply_colors
    return apply_colors(assy)
