"""Quick linear static FEM of one part on a voxel grid (no mesher needed; all numpy, heavy on CPU/RAM).

The solid is voxelised (ray parity on its triangulation), each voxel is an 8-node hexahedron, the system
is solved matrix-free with Jacobi-preconditioned CG. Units: mm, N, MPa.
Regions (fix / load):  xmin xmax ymin ymax zmin zmax | plane:Z=20 | box:x0,y0,z0,x1,y1,z1 | hole:6.6 (all
holes of that diameter, ±0.3) | hole:6.6@x,y,z (the one nearest the point).
Accuracy: a comparison tool (±10-30 %); stresses at sharp voxel steps are overestimated, so the 99.5th
percentile is reported next to the maximum. Use finer --elements for a better answer (more CPU and RAM).
"""
import math
import os
import re

import numpy as np

from . import core


# ---------------------------------------------------------------- voxelise

def voxelise(shape, h):
    """-> occupancy (nx,ny,nz), grid origin, voxel size per axis (the grid spans the bounding box exactly,
    so a prismatic part keeps its true section)."""
    V, T = core.mesh(shape, tol=min(h / 4, 0.05))
    bb = core.bbox(shape)
    lo, hi = np.array(bb[:3]), np.array(bb[3:])
    n = np.maximum(1, np.round((hi - lo) / h)).astype(int)
    hv = (hi - lo) / n
    nx, ny, nz = n
    x0 = lo
    jit = hv * 1e-4 * np.array([math.pi, math.e, 0])
    xs = x0[0] + (np.arange(nx) + 0.5) * hv[0] + jit[0]
    ys = x0[1] + (np.arange(ny) + 0.5) * hv[1] + jit[1]
    hits = [[] for _ in range(nx * ny)]
    P = V[T]  # (m,3,3)
    for t in range(len(P)):
        a, b, c = P[t]
        mnx, mxx = min(a[0], b[0], c[0]), max(a[0], b[0], c[0])
        mny, mxy = min(a[1], b[1], c[1]), max(a[1], b[1], c[1])
        i0, i1 = np.searchsorted(xs, mnx), np.searchsorted(xs, mxx)
        j0, j1 = np.searchsorted(ys, mny), np.searchsorted(ys, mxy)
        if i0 >= i1 or j0 >= j1:
            continue
        X, Y = np.meshgrid(xs[i0:i1], ys[j0:j1], indexing="ij")
        d = (b[1] - c[1]) * (a[0] - c[0]) + (c[0] - b[0]) * (a[1] - c[1])
        if abs(d) < 1e-14:
            continue
        l1 = ((b[1] - c[1]) * (X - c[0]) + (c[0] - b[0]) * (Y - c[1])) / d
        l2 = ((c[1] - a[1]) * (X - c[0]) + (a[0] - c[0]) * (Y - c[1])) / d
        l3 = 1 - l1 - l2
        inside = (l1 >= 0) & (l2 >= 0) & (l3 >= 0)
        if not inside.any():
            continue
        Z = l1 * a[2] + l2 * b[2] + l3 * c[2]
        ii, jj = np.nonzero(inside)
        for p, q, z in zip(ii + i0, jj + j0, Z[inside]):
            hits[p * ny + q].append(z)
    zc = x0[2] + (np.arange(nz) + 0.5) * hv[2]
    occ = np.zeros((nx, ny, nz), bool)
    for k, zs in enumerate(hits):
        if len(zs) < 2:
            continue
        zs = np.unique(np.round(np.sort(zs), 9))
        if len(zs) % 2:
            zs = zs[:-1]
        for z_a, z_b in zs.reshape(-1, 2):
            occ[k // ny, k % ny, (zc > z_a) & (zc < z_b)] = True
    return occ, x0, hv


# ---------------------------------------------------------------- element

def hex8(E, nu, hv=(1.0, 1.0, 1.0)):
    """24x24 stiffness of a brick hex8 with edge lengths hv, its centre B matrix and D."""
    hv = np.asarray(hv, float)
    lam = E * nu / ((1 + nu) * (1 - 2 * nu))
    mu = E / (2 * (1 + nu))
    D = np.zeros((6, 6))
    D[:3, :3] = lam
    D[np.arange(3), np.arange(3)] += 2 * mu
    D[3:, 3:] = np.eye(3) * mu
    nodes = np.array([[-1, -1, -1], [1, -1, -1], [1, 1, -1], [-1, 1, -1], [-1, -1, 1], [1, -1, 1], [1, 1, 1], [-1, 1, 1]], float)

    def Bmat(xi):
        dN = nodes * 0.125 * np.prod(1 + nodes * xi, axis=1)[:, None] / (1 + nodes * xi)
        dN = dN * (2 / hv)  # d/dx = d/dxi * 2/h
        B = np.zeros((6, 24))
        for n in range(8):
            dx, dy, dz = dN[n]
            B[0, 3 * n], B[1, 3 * n + 1], B[2, 3 * n + 2] = dx, dy, dz
            B[3, 3 * n], B[3, 3 * n + 1] = dy, dx
            B[4, 3 * n + 1], B[4, 3 * n + 2] = dz, dy
            B[5, 3 * n], B[5, 3 * n + 2] = dz, dx
        return B
    g = 1 / math.sqrt(3)
    K = np.zeros((24, 24))
    for xi in nodes * g:
        B = Bmat(xi)
        K += B.T @ D @ B * (np.prod(hv) / 8)  # det J
    return K, Bmat(np.zeros(3)), D


# ---------------------------------------------------------------- regions

def _holes(shape):
    from . import digest
    return [f for f in digest._cyl_features(shape) if f["concave"] and f["ang"] > 1.9 * math.pi]


def select_nodes(spec, X, shape, h):
    s = spec.strip()
    lo, hi = X.min(0), X.max(0)
    ax = {"x": 0, "y": 1, "z": 2}
    m = re.fullmatch(r"([xyz])(min|max)", s, re.I)
    if m:
        a = ax[m.group(1).lower()]
        return X[:, a] <= lo[a] + 0.51 * h if m.group(2).lower() == "min" else X[:, a] >= hi[a] - 0.51 * h
    m = re.fullmatch(r"plane:([xyz])=(-?[\d.]+)", s, re.I)
    if m:
        a = ax[m.group(1).lower()]
        return np.abs(X[:, a] - float(m.group(2))) <= 0.51 * h
    m = re.fullmatch(r"box:(.+)", s, re.I)
    if m:
        v = list(map(float, m.group(1).split(",")))
        return np.all((X >= np.array(v[:3]) - 1e-9) & (X <= np.array(v[3:]) + 1e-9), axis=1)
    m = re.fullmatch(r"hole:([\d.]+)(?:@(.+))?", s, re.I)
    if m:
        D = float(m.group(1))
        hs = [f for f in _holes(shape) if abs(2 * f["r"] - D) <= 0.3]
        if m.group(2):
            p = np.array(list(map(float, m.group(2).split(","))))
            hs = sorted(hs, key=lambda f: _axis_dist(p[None], f)[0])[:1]
        if not hs:
            raise ValueError(f"no hole of Ø{D}")
        sel = np.zeros(len(X), bool)
        for f in hs:
            d = _axis_dist(X, f)
            t = X @ np.array(f["dir"])
            sel |= (d <= f["r"] + 1.5 * h) & (t >= f["t0"] - h) & (t <= f["t1"] + h)
        return sel
    raise ValueError(f"bad region '{spec}'")


def _axis_dist(P, f):
    d = np.array(f["dir"])
    w = P - np.array(f["foot"])
    return np.linalg.norm(w - np.outer(w @ d, d), axis=1)


# ---------------------------------------------------------------- solve

def solve(step, part, fix, loads, material=None, elements=60000, gravity=False, tol=1e-6, maxiter=30000):
    import time
    t0 = time.time()
    model = core.load(step)
    inst = core.find(model, [part])[0]
    mat = material or inst.material or "steel"
    E, nu, fy = core.mech_of(mat)
    vol = core.props(inst.shape)[0]
    h = (vol / elements) ** (1 / 3)
    occ, x0, hv = voxelise(inst.shape, h)
    nx, ny, nz = occ.shape
    el = np.argwhere(occ)
    if len(el) < 8:
        raise ValueError("part too thin for this resolution; raise --elements")
    # nodes
    offs = np.array([[0, 0, 0], [1, 0, 0], [1, 1, 0], [0, 1, 0], [0, 0, 1], [1, 0, 1], [1, 1, 1], [0, 1, 1]])
    gid = lambda ijk: (ijk[..., 0] * (ny + 1) + ijk[..., 1]) * (nz + 1) + ijk[..., 2]  # noqa: E731
    en_g = gid(el[:, None, :] + offs[None])
    used, en = np.unique(en_g, return_inverse=True)
    en = en.reshape(-1, 8)
    nn = len(used)
    ijk = np.stack([used // ((ny + 1) * (nz + 1)), (used // (nz + 1)) % (ny + 1), used % (nz + 1)], 1)
    X = x0 + ijk * hv
    h = float(hv.max())
    edof = (en[:, :, None] * 3 + np.arange(3)).reshape(-1, 24)
    Ke, B0, D = hex8(E, nu, hv)
    ndof = 3 * nn

    # boundary conditions
    fixed = np.zeros(ndof, bool)
    for spec in fix:
        sel = select_nodes(spec, X, inst.shape, h)
        if not sel.any():
            raise ValueError(f"fix region '{spec}' selects no nodes")
        fixed[(np.nonzero(sel)[0][:, None] * 3 + np.arange(3)).ravel()] = True
    F = np.zeros(ndof)
    load_info = []
    for spec in loads:
        reg, vec = spec.rsplit("=", 1)
        fv = np.array(list(map(float, vec.split(","))))
        sel = np.nonzero(select_nodes(reg, X, inst.shape, h))[0]
        if not len(sel):
            raise ValueError(f"load region '{reg}' selects no nodes")
        for a in range(3):
            F[sel * 3 + a] += fv[a] / len(sel)
        load_info.append({"region": reg, "N": fv.tolist(), "nodes": int(len(sel))})
    if gravity:
        w = core.density_of(mat) * 1e-6 * 9.81 * float(np.prod(hv))  # N per voxel (g/cm3 -> kg/mm3 is 1e-6)
        np.add.at(F, edof[:, 2::3].ravel(), -w / 8)
        load_info.append({"region": "gravity -Z", "N": [0, 0, -w * len(el)]})
    free = ~fixed
    if not fixed.any():
        raise ValueError("no fixed region: the part would fly away")

    def Kmul(u):
        ue = u[edof]
        return np.bincount(edof.ravel(), weights=(ue @ Ke).ravel(), minlength=ndof)
    diag = np.bincount(edof.ravel(), weights=np.tile(np.diag(Ke), len(edof)), minlength=ndof)
    Minv = np.where(free, 1 / np.maximum(diag, 1e-30), 0)
    # PCG on free dofs
    u = np.zeros(ndof)
    r = np.where(free, F, 0)
    z = Minv * r
    p = z.copy()
    rz = r @ z
    nb = math.sqrt(r @ r) or 1
    it = 0
    for it in range(1, maxiter + 1):
        Ap = np.where(free, Kmul(p), 0)
        alpha = rz / (p @ Ap)
        u += alpha * p
        r -= alpha * Ap
        if math.sqrt(r @ r) / nb < tol:
            break
        z = Minv * r
        rz_new = r @ z
        p = z + (rz_new / rz) * p
        rz = rz_new
    U = u.reshape(-1, 3)
    disp = np.linalg.norm(U, axis=1)
    # stresses at element centres
    sig = (u[edof] @ B0.T) @ D.T
    sx, sy, sz, txy, tyz, txz = sig.T
    vm = np.sqrt(0.5 * ((sx - sy) ** 2 + (sy - sz) ** 2 + (sz - sx) ** 2) + 3 * (txy ** 2 + tyz ** 2 + txz ** 2))
    imax = int(np.argmax(vm))
    cmax = x0 + (el[imax] + 0.5) * hv
    p995 = float(np.percentile(vm, 99.5))
    imgs = _images(step, inst.name, occ, el, vm, x0, h)
    pts_file = _points(step, inst.name, x0 + (el + 0.5) * hv, vm, disp_el=None)
    vox_vol = len(el) * float(np.prod(hv))
    res = {"ok": True, "part": inst.name, "material": mat, "E": E, "nu": nu, "yield": fy,
           "voxel_mm": core.r(hv.tolist(), 3), "voxel_volume_ratio": core.r(vox_vol / vol, 3), "elements": int(len(el)), "dof": int(ndof), "cg_iters": it,
           "converged": it < maxiter, "loads": load_info, "fix": fix,
           "max_disp_mm": core.r(float(disp.max()), 4), "max_disp_at": core.r((X[int(np.argmax(disp))]).tolist()),
           "vm_max_MPa": core.r(float(vm.max()), 1), "vm_max_at": core.r(cmax.tolist()),
           "vm_p99_5_MPa": core.r(p995, 1), "vm_mean_MPa": core.r(float(vm.mean()), 2),
           "safety_vs_yield_p99_5": core.r(fy / p995, 2) if p995 > 0 else None,
           "image": imgs, "points": pts_file, "seconds": round(time.time() - t0, 1),
           "note": "voxel FEM: compare variants, do not certify; vm_max at voxel steps is overestimated"}
    return res


def _points(step, name, centres, vm, disp_el=None, limit=30000):
    """Element centres + von Mises for the viewer's 3D overlay (all high-stress ones, the rest thinned)."""
    import json
    n = len(vm)
    idx = np.arange(n)
    if n > limit:
        top = np.argsort(vm)[-limit // 4:]
        rest = np.setdiff1d(idx, top)
        rest = rest[:: max(1, len(rest) // (limit - len(top)))]
        idx = np.concatenate([rest, top])
    p = os.path.join(core.out_dir(step, "fem"), re.sub(r"[^\w.-]+", "_", name) + ".points.json")
    with open(p, "w", encoding="utf-8") as f:
        json.dump({"p": np.round(centres[idx], 3).ravel().tolist(), "v": np.round(vm[idx], 2).tolist(),
                   "vmax": float(np.percentile(vm, 99.5)) if n else 0.0}, f)
    return p


def _images(step, name, occ, el, vm, x0, h):
    """Max von Mises projected along X, Y and Z (one PNG)."""
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except Exception:  # noqa: BLE001
        return None
    grid = np.zeros(occ.shape)
    grid[tuple(el.T)] = vm
    vmax = np.percentile(vm, 99.5)
    fig, axs = plt.subplots(1, 3, figsize=(12, 4.2))
    for a, (axis, lbl) in enumerate(((2, "top (along Z)"), (1, "front (along Y)"), (0, "side (along X)"))):
        img = grid.max(axis=axis)
        mask = occ.any(axis=axis)
        img = np.where(mask, img, np.nan)
        im = axs[a].imshow(img.T, origin="lower", cmap="turbo", vmin=0, vmax=vmax, interpolation="nearest")
        axs[a].set_title(lbl, fontsize=9)
        axs[a].set_xticks([])
        axs[a].set_yticks([])
    fig.colorbar(im, ax=axs, shrink=0.8, label="von Mises [MPa] (max through depth)")
    fig.suptitle(f"{name}: voxel {h:.2f} mm", fontsize=10)
    p = os.path.join(core.out_dir(step, "fem"), re.sub(r"[^\w.-]+", "_", name) + ".png")
    fig.savefig(p, dpi=80)
    plt.close(fig)
    return p
