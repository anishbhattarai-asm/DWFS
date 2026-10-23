import os
import time
import numpy as np
from PIL import Image
from scipy.spatial import cKDTree

from .options import settings
from .tracing import save_json

DEFAULTS = {
    "maxdim": 400,
    "gamma": 1.6,
    "white_cutoff": 230.0,
    "points": 8000,
    "relax": 30,
    "knn": 10,
    "seconds": 15.0,
    "seed": None,
}


LIMITS = {
    "maxdim": (16, 20000),
    "gamma": (0.05, 20),
    "white_cutoff": (1, 255),
    "points": (16, 200000),
    "relax": (0, 1000),
    "knn": (1, 100),
    "seconds": (0, 3600),
}


def load_density(image, cfg):
    if isinstance(image, (str, os.PathLike)):
        img = Image.open(image)
    elif hasattr(image, "convert"):
        img = image
    else:
        arr = np.asarray(image)
        if arr.dtype != np.uint8:
            arr = np.clip(arr * 255.0 if arr.max() <= 1.0 else arr, 0, 255).astype(np.uint8)
        img = Image.fromarray(arr)
    img = img.convert("L")
    scale = min(1.0, cfg.maxdim / max(img.size))
    w = max(1, round(img.size[0] * scale))
    h = max(1, round(img.size[1] * scale))
    img = img.resize((w, h))
    lum = np.asarray(img, dtype=float)
    base = np.clip((cfg.white_cutoff - lum) / cfg.white_cutoff, 0.0, 1.0)
    density = base ** cfg.gamma
    return density, w, h


def sample_points(density, w, h, n, rng):
    ys, xs = np.nonzero(density > 1e-6)
    if len(xs) == 0:
        return rng.random(n) * w, rng.random(n) * h
    p = density[ys, xs]
    p = p / p.sum()
    pick = rng.choice(len(xs), size=n, replace=True, p=p)
    px = xs[pick].astype(float) + rng.random(n)
    py = ys[pick].astype(float) + rng.random(n)
    return px, py


def relax(px, py, density, w, h, iters, rng):
    n = len(px)
    gy, gx = np.mgrid[0:h, 0:w]
    pix = np.column_stack([gx.ravel(), gy.ravel()]).astype(float)
    wgt = density.ravel()
    keep = wgt > 1e-6
    pix = pix[keep]
    wgt = wgt[keep]
    ys, xs = np.nonzero(density > 1e-6)
    if not len(xs):
        return px, py
    prob = density[ys, xs]
    prob = prob / prob.sum()
    for _ in range(iters):
        tree = cKDTree(np.column_stack([px, py]))
        _, idx = tree.query(pix, workers=-1)
        sw = np.bincount(idx, weights=wgt, minlength=n)
        sx = np.bincount(idx, weights=wgt * pix[:, 0], minlength=n)
        sy = np.bincount(idx, weights=wgt * pix[:, 1], minlength=n)
        good = sw > 1e-6
        px[good] = sx[good] / sw[good]
        py[good] = sy[good] / sw[good]
        bad = ~good
        if bad.any():
            r = rng.choice(len(xs), size=int(bad.sum()), p=prob)
            px[bad] = xs[r] + rng.random(int(bad.sum()))
            py[bad] = ys[r] + rng.random(int(bad.sum()))
    return px, py


def greedy_tour(pts):
    n = len(pts)
    tree = cKDTree(pts)
    visited = np.zeros(n, dtype=bool)
    order = np.empty(n, dtype=int)
    cur = 0
    visited[0] = True
    order[0] = 0
    for i in range(1, n):
        k = 2
        nxt = -1
        while nxt < 0:
            _, ii = tree.query(pts[cur], k=min(k, n))
            for cand in np.atleast_1d(ii):
                if not visited[cand]:
                    nxt = cand
                    break
            k *= 2
            if k > 2 * n:
                nxt = int(np.where(~visited)[0][0])
                break
        visited[nxt] = True
        order[i] = nxt
        cur = nxt
    return order


def two_opt(order, pts, knn, seconds):
    n = len(order)
    order = order.copy()
    tree = cKDTree(pts)
    _, nb = tree.query(pts, k=min(knn + 1, n))
    nb = nb[:, 1:]
    pos = np.empty(n, dtype=int)
    pos[order] = np.arange(n)

    def d(a, b):
        return float(np.hypot(pts[a, 0] - pts[b, 0], pts[a, 1] - pts[b, 1]))

    dontlook = np.zeros(n, dtype=bool)
    t0 = time.time()
    remaining = n
    while remaining > 0 and time.time() - t0 < seconds:
        remaining = 0
        for c1 in range(n):
            if dontlook[c1]:
                continue
            improved = False
            a = pos[c1]
            for s in (1, -1):
                if improved:
                    break
                c2 = order[(a + s) % n]
                d12 = d(c1, c2)
                for c3 in nb[c1]:
                    c3 = int(c3)
                    if c3 == c1 or c3 == c2:
                        continue
                    d13 = d(c1, c3)
                    if d13 >= d12:
                        break
                    cp = pos[c3]
                    c4 = order[(cp + s) % n]
                    if c4 == c1:
                        continue
                    gain = d12 + d(c3, c4) - d13 - d(c2, c4)
                    if gain > 1e-7:
                        left_a = a if s == 1 else (a - 1) % n
                        left_b = cp if s == 1 else (cp - 1) % n
                        if left_a == left_b:
                            continue
                        lo = min(left_a, left_b)
                        hi = max(left_a, left_b)
                        order[lo + 1:hi + 1] = order[lo + 1:hi + 1][::-1]
                        pos[order[lo + 1:hi + 1]] = np.arange(lo + 1, hi + 1)
                        dontlook[c1] = dontlook[c2] = dontlook[c3] = dontlook[c4] = False
                        improved = True
                        break
            if improved:
                remaining += 1
            else:
                dontlook[c1] = True
            if time.time() - t0 > seconds:
                break
    return order


def stipple(image, out=None, **options):
    cfg = settings(DEFAULTS, options, LIMITS)
    rng = np.random.default_rng(cfg.seed)
    density, w, h = load_density(image, cfg)
    px, py = sample_points(density, w, h, cfg.points, rng)
    px, py = relax(px, py, density, w, h, cfg.relax, rng)
    pts = np.column_stack([px, py])
    order = greedy_tour(pts)
    order = two_opt(order, pts, cfg.knn, cfg.seconds)

    path = pts[order]
    length = float(np.sum(np.hypot(np.diff(path[:, 0]), np.diff(path[:, 1]))))
    source = os.path.abspath(os.fspath(image)) if isinstance(image, (str, os.PathLike)) else None
    data = {"width": w, "height": h, "closed": True, "mode": "stipple", "source": source,
            "stats": {"points": len(path), "route": round(length, 1)},
            "path": [[round(float(x), 2), round(float(y), 2)] for x, y in path]}
    if out:
        save_json(data, out)
    return data
