import sys
import json
import numpy as np
import cv2
from skimage.morphology import skeletonize

MAXDIM = 820
BLOCK = 21
C = 7
MIN_STROKE = 4
RESAMPLE = 4000


def binarize(gray):
    bw = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                               cv2.THRESH_BINARY_INV, BLOCK, C)
    return cv2.medianBlur(bw, 3)


def trace_strokes(skel, min_stroke):
    h, w = skel.shape
    idx = np.nonzero(skel.ravel())[0]
    present = np.zeros(h * w, dtype=bool)
    present[idx] = True

    def neighbors(p):
        x = p % w
        out = []
        u = p - w
        d = p + w
        if u >= 0:
            if x > 0 and present[u - 1]:
                out.append(u - 1)
            if present[u]:
                out.append(u)
            if x < w - 1 and present[u + 1]:
                out.append(u + 1)
        if x > 0 and present[p - 1]:
            out.append(p - 1)
        if x < w - 1 and present[p + 1]:
            out.append(p + 1)
        if d < h * w:
            if x > 0 and present[d - 1]:
                out.append(d - 1)
            if present[d]:
                out.append(d)
            if x < w - 1 and present[d + 1]:
                out.append(d + 1)
        return out

    deg = {p: len(neighbors(p)) for p in idx}
    used = set()
    strokes = []

    def ek(a, b):
        return (a, b) if a < b else (b, a)

    for s in (p for p in idx if deg[p] != 2):
        for nb in neighbors(s):
            if ek(s, nb) in used:
                continue
            chain = [s, nb]
            used.add(ek(s, nb))
            prev, cur = s, nb
            while deg.get(cur, 0) == 2:
                nxts = [q for q in neighbors(cur) if q != prev]
                if not nxts or ek(cur, nxts[0]) in used:
                    break
                used.add(ek(cur, nxts[0]))
                chain.append(nxts[0])
                prev, cur = cur, nxts[0]
            strokes.append(chain)

    for p in idx:
        if deg[p] == 2:
            cur, prev, start = p, -1, p
            loop = [p]
            while True:
                nxts = [q for q in neighbors(cur) if q != prev and ek(cur, q) not in used]
                if not nxts:
                    break
                used.add(ek(cur, nxts[0]))
                loop.append(nxts[0])
                prev, cur = cur, nxts[0]
                if cur == start:
                    break
            if len(loop) > 3:
                strokes.append(loop)

    polys = [np.column_stack([np.array(s) % w, np.array(s) // w]).astype(float)
             for s in strokes if len(s) >= min_stroke]
    return polys


def connect(polys):
    polys = sorted(polys, key=lambda a: -len(a))
    order = [polys[0]]
    tip = polys[0][-1]
    rem = polys[1:]
    while rem:
        best, bestd, flip = -1, 1e18, False
        for i, pl in enumerate(rem):
            d0 = (pl[0][0] - tip[0]) ** 2 + (pl[0][1] - tip[1]) ** 2
            d1 = (pl[-1][0] - tip[0]) ** 2 + (pl[-1][1] - tip[1]) ** 2
            if d0 < bestd:
                bestd, best, flip = d0, i, False
            if d1 < bestd:
                bestd, best, flip = d1, i, True
        pl = rem.pop(best)
        if flip:
            pl = pl[::-1]
        order.append(pl)
        tip = pl[-1]
    return np.vstack(order)


def resample_closed(path, n):
    if len(path) < 2:
        return path
    seg = np.hypot(np.diff(path[:, 0]), np.diff(path[:, 1]))
    close = np.hypot(path[0, 0] - path[-1, 0], path[0, 1] - path[-1, 1])
    cum = np.concatenate([[0], np.cumsum(seg)])
    total = cum[-1] + close
    if total <= 0:
        return path
    targets = np.linspace(0, total, n, endpoint=False)
    loop = np.vstack([path, path[0]])
    cloop = np.concatenate([cum, [total]])
    x = np.interp(targets, cloop, loop[:, 0])
    y = np.interp(targets, cloop, loop[:, 1])
    return np.column_stack([x, y])


def main():
    src = sys.argv[1] if len(sys.argv) > 1 else "input.png"
    out = sys.argv[2] if len(sys.argv) > 2 else "tsp.json"

    g = cv2.imread(src, cv2.IMREAD_GRAYSCALE)
    if g is None:
        print("could not read", src)
        return
    scale = min(1.0, MAXDIM / max(g.shape))
    g = cv2.resize(g, (int(g.shape[1] * scale), int(g.shape[0] * scale)))
    h, w = g.shape

    bw = binarize(g)
    skel = skeletonize(bw > 0)
    polys = trace_strokes(skel, MIN_STROKE)
    if not polys:
        print("no strokes found")
        return

    path = connect(polys)
    path = resample_closed(path, min(RESAMPLE, len(path)))
    length = float(np.sum(np.hypot(np.diff(path[:, 0]), np.diff(path[:, 1]))))

    data = {"width": w, "height": h, "closed": True,
            "path": [[round(float(x), 2), round(float(y), 2)] for x, y in path]}
    with open(out, "w") as f:
        json.dump(data, f)
    print("strokes", len(polys), "points", len(path), "length", round(length, 1), "wrote", out)


if __name__ == "__main__":
    main()
