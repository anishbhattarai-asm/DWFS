import sys
import json
import time
import numpy as np
from PIL import Image
from scipy.spatial import cKDTree

MAX_DIM = 400
GAMMA = 1.2
POINTS = 1500
RELAX = 30
KNN = 8
TWO_OPT_SECONDS = 8


def load_density(path):
    img = Image.open(path).convert("L")
    scale = min(1.0, MAX_DIM / max(img.size))
    w = max(1, round(img.size[0] * scale))
    h = max(1, round(img.size[1] * scale))
    img = img.resize((w, h))
    lum = np.asarray(img, dtype=float)
    density = ((255.0 - lum) / 255.0) ** GAMMA
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
    tree = cKDTree(pts)
    _, nb = tree.query(pts, k=knn + 1)
    nb = nb[:, 1:]
    pos = np.empty(n, dtype=int)
    for i in range(n):
        pos[order[i]] = i

    def d(a, b):
        return float(np.hypot(pts[a, 0] - pts[b, 0], pts[a, 1] - pts[b, 1]))

    t0 = time.time()
    improved = True
    while improved and time.time() - t0 < seconds:
        improved = False
        for i in range(n - 1):
            c1 = order[i]
            c2 = order[i + 1]
            d12 = d(c1, c2)
            for c3 in nb[c1]:
                j = pos[c3]
                if j <= i:
                    continue
                d13 = d(c1, c3)
                if d13 >= d12:
                    continue
                c4 = order[j + 1] if j + 1 < n else order[0]
                gain = d12 + d(c3, c4) - d13 - d(c2, c4)
                if gain > 1e-6:
                    order[i + 1:j + 1] = order[i + 1:j + 1][::-1]
                    pos[order[i + 1:j + 1]] = np.arange(i + 1, j + 1)
                    improved = True
                    c2 = order[i + 1]
                    d12 = d(c1, c2)
            if time.time() - t0 > seconds:
                break
    return order


def main():
    src = sys.argv[1] if len(sys.argv) > 1 else "input.png"
    out = sys.argv[2] if len(sys.argv) > 2 else "tsp.json"
    rng = np.random.default_rng()

    density, w, h = load_density(src)
    px, py = sample_points(density, w, h, POINTS, rng)
    px, py = relax(px, py, density, w, h, RELAX, rng)
    pts = np.column_stack([px, py])
    order = greedy_tour(pts)
    order = two_opt(order, pts, KNN, TWO_OPT_SECONDS)

    path = pts[order]
    length = float(np.sum(np.hypot(np.diff(path[:, 0]), np.diff(path[:, 1]))))
    data = {"width": w, "height": h, "closed": True,
            "path": [[round(float(x), 2), round(float(y), 2)] for x, y in path]}
    with open(out, "w") as f:
        json.dump(data, f)
    print("points", len(path), "tour", round(length, 1), "wrote", out)


if __name__ == "__main__":
    main()
