"""One labelled 2x2 picture (front, top, right, iso) of a model, rendered offline with matplotlib.

Replaces several viewer screenshots: one small PNG with every part's name at its centre, flat shading
and dimensions of the envelope. Optional: --highlight parts drawn in red, others greyed.
"""
import os
import re

import numpy as np

from . import core

VIEWS = {  # name: (view direction towards the viewer, up)
    "front (-Y)": ((0, -1, 0), (0, 0, 1)),
    "top (+Z)": ((0, 0, 1), (0, 1, 0)),
    "right (+X)": ((1, 0, 0), (0, 0, 1)),
    "iso": ((1, -1, 1), (0, 0, 1)),
}
PAL = ["#5b8cc9", "#e0a040", "#6bb36b", "#c96b6b", "#9a7fc4", "#4fb0b0", "#c9a35b", "#8c8c8c", "#d47fb0", "#7fa0d4"]


def _frame(d, up):
    d = np.asarray(d, float)
    d /= np.linalg.norm(d)
    r = np.cross(up, d)
    r /= np.linalg.norm(r)
    u = np.cross(d, r)
    return r, u, d


def render(step, size=900, highlight=None, labels=40, out=None):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.collections import PolyCollection
    model = core.load(step)
    hl = set(i.name for i in core.find(model, highlight)) if highlight else None
    meshes = []
    for k, inst in enumerate(model):
        V, T = core.mesh(inst.shape)
        if len(T) > 40000:
            V, T = core.mesh(inst.shape, tol=0.01 * float(np.ptp(V, 0).max()))
        meshes.append((inst.name, V, T, PAL[k % len(PAL)]))
    allV = np.vstack([m[1] for m in meshes])
    lo, hi = allV.min(0), allV.max(0)
    light = np.array([0.4, -0.5, 0.75])
    light /= np.linalg.norm(light)
    fig, axs = plt.subplots(2, 2, figsize=(size / 100, size / 100), dpi=100)
    order = sorted(model, key=lambda i: -core.props(i.shape)[0])[:labels]
    lab = {i.name for i in order}
    for ax, (title, (d, up)) in zip(axs.ravel(), VIEWS.items()):
        r, u, dd = _frame(d, up)
        polys, cols, depth = [], [], []
        texts = []
        for name, V, T, col in meshes:
            tri = V[T]
            n = np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0])
            ln = np.linalg.norm(n, axis=1)
            ok = ln > 1e-12
            tri, n = tri[ok], n[ok] / ln[ok, None]
            vis = n @ dd > 0
            tri, n = tri[vis], n[vis]
            if not len(tri):
                continue
            P2 = np.stack([tri @ r, tri @ u], -1)
            shade = 0.35 + 0.65 * np.clip(np.abs(n @ light), 0, 1)
            base = np.array(matplotlib.colors.to_rgb("#d04040" if hl and name in hl else ("#c8c8c8" if hl else col)))
            polys.extend(P2)
            cols.extend(np.clip(base[None] * shade[:, None], 0, 1))
            depth.extend((tri @ dd).mean(1))
            if name in lab:
                c = V.mean(0)
                texts.append((c @ r, c @ u, c @ dd, name))
        o = np.argsort(depth)
        pc = PolyCollection([polys[i] for i in o], facecolors=[cols[i] for i in o], edgecolors="none", antialiased=False)
        ax.add_collection(pc)
        ax.autoscale_view()
        ax.set_aspect("equal")
        ax.axis("off")
        ax.set_title(title, fontsize=8)
        if title != "iso":
            for x, y, _, name in sorted(texts, key=lambda t: t[2])[-labels:]:
                ax.text(x, y, re.sub(r"\s+", " ", name)[:24], fontsize=6, ha="center", va="center",
                        bbox=dict(boxstyle="round,pad=0.1", fc="white", ec="none", alpha=0.75))
    sz = hi - lo
    fig.suptitle(f"{os.path.basename(step)}  {sz[0]:.1f} x {sz[1]:.1f} x {sz[2]:.1f} mm, {len(model)} parts", fontsize=8)
    fig.tight_layout(rect=(0, 0, 1, 0.97))
    p = out or os.path.join(core.out_dir(step, "views"), "views.png")
    fig.savefig(p, dpi=100)
    plt.close(fig)
    return {"ok": True, "image": p, "px": size, "labels": len(lab)}
