import os
import sys
import json
import numpy as np
import cv2
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import dijkstra, connected_components
from scipy.spatial import cKDTree
from skimage.morphology import skeletonize

MAXDIM = 820
MODE = "auto"
BLOCK = 21
C = 7
CANNY_LOW = 40
CANNY_HIGH = 100
LINE_ART = 0.6
BACKGROUND = 0.6
MIN_STROKE = 6
RESAMPLE = 6000
RETRACE_COST = 0.5
NEAR = 48.0

OFFSETS = ((1, 0), (0, 1), (1, 1), (-1, 1))


def binarize(gray):
    bw = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                               cv2.THRESH_BINARY_INV, BLOCK, C)
    return cv2.medianBlur(bw, 3)


def is_line_art(gray):
    level = np.median(gray)
    if np.mean(np.abs(gray.astype(float) - level) < 12) < BACKGROUND:
        return False
    dark = (gray < level - 40).astype(np.uint8)
    if dark.mean() < 0.002:
        return False
    core = cv2.erode(dark, np.ones((5, 5), np.uint8))
    return core.sum() / dark.sum() < LINE_ART


def edges(img):
    smooth = img
    for _ in range(4):
        smooth = cv2.bilateralFilter(smooth, 9, 40, 7)
    bw = cv2.Canny(smooth, CANNY_LOW, CANNY_HIGH)
    return cv2.morphologyEx(bw, cv2.MORPH_CLOSE, np.ones((3, 3), np.uint8))


def read_image(src):
    img = cv2.imread(src, cv2.IMREAD_UNCHANGED)
    if img is None:
        return None
    if img.dtype == np.uint16:
        img = (img // 257).astype(np.uint8)
    elif img.dtype != np.uint8:
        img = cv2.normalize(img, None, 0, 255, cv2.NORM_MINMAX).astype(np.uint8)
    if img.ndim == 2:
        img = cv2.cvtColor(img, cv2.COLOR_GRAY2BGR)
    elif img.shape[2] == 4:
        alpha = img[..., 3:].astype(float) / 255.0
        img = (img[..., :3] * alpha + 255.0 * (1.0 - alpha)).astype(np.uint8)
    return img


def pixel_graph(skel):
    h, w = skel.shape
    ys, xs = np.nonzero(skel)
    ids = np.arange(len(xs))
    index = np.full((h + 2, w + 2), -1, dtype=np.int64)
    index[ys + 1, xs + 1] = ids
    a, b = [], []
    for dx, dy in OFFSETS:
        j = index[ys + 1 + dy, xs + 1 + dx]
        ok = j >= 0
        if dx and dy:
            ok &= (index[ys + 1, xs + 1 + dx] < 0) & (index[ys + 1 + dy, xs + 1] < 0)
        a.append(ids[ok])
        b.append(j[ok])
    xy = np.column_stack([xs, ys]).astype(float)
    return xy, np.concatenate(a), np.concatenate(b)


def neighbors(n, a, b):
    adj = [[] for _ in range(n)]
    for e, (u, v) in enumerate(zip(a.tolist(), b.tolist())):
        adj[u].append((v, e))
        adj[v].append((u, e))
    return adj


def clean(skel, min_stroke):
    _, labels, stats, _ = cv2.connectedComponentsWithStats(skel.astype(np.uint8), connectivity=8)
    small = np.nonzero(stats[:, cv2.CC_STAT_AREA] < min_stroke)[0]
    skel = skel & ~np.isin(labels, small[small > 0])

    xy, a, b = pixel_graph(skel)
    adj = neighbors(len(xy), a, b)
    drop = []
    for s in range(len(xy)):
        if len(adj[s]) != 1:
            continue
        chain = [s]
        prev, cur = s, adj[s][0][0]
        while len(adj[cur]) == 2 and len(chain) < min_stroke:
            chain.append(cur)
            step = adj[cur][0][0] if adj[cur][0][0] != prev else adj[cur][1][0]
            prev, cur = cur, step
        if len(adj[cur]) >= 3 and len(chain) < min_stroke:
            drop.extend(chain)
    if drop:
        pts = xy[drop].astype(int)
        skel = skel.copy()
        skel[pts[:, 1], pts[:, 0]] = False
    return skel


def route(xy, a, b, retrace_cost):
    n = len(xy)
    adj = neighbors(n, a, b)
    edge_of = {}
    for e, (u, v) in enumerate(zip(a.tolist(), b.tolist())):
        edge_of[(u, v)] = e
        edge_of[(v, u)] = e
    used = np.zeros(len(a), dtype=bool)
    free = np.array([len(x) for x in adj])
    weight = np.hypot(*(xy[a] - xy[b]).T)
    links = []
    cuts = []
    stats = {"left": len(a), "jumps": 0, "jump_length": 0.0}

    def graph():
        ja = np.array([p for p, _ in links], dtype=np.int64)
        jb = np.array([q for _, q in links], dtype=np.int64)
        jw = np.hypot(*(xy[ja] - xy[jb]).T) if links else np.zeros(0)
        return coo_matrix((np.concatenate([weight, jw]),
                           (np.concatenate([a, ja]), np.concatenate([b, jb]))), shape=(n, n)).tocsr()

    def take(u, v):
        e = edge_of.get((u, v))
        if e is not None and not used[e]:
            used[e] = True
            free[u] -= 1
            free[v] -= 1
            stats["left"] -= 1

    def pick(cur, path):
        best, score = None, -2.0
        back = path[-4] if len(path) >= 4 else path[0]
        hx, hy = xy[cur] - xy[back]
        norm = np.hypot(hx, hy) or 1.0
        for v, e in adj[cur]:
            if used[e]:
                continue
            dx, dy = xy[v] - xy[cur]
            s = (hx * dx + hy * dy) / (norm * np.hypot(dx, dy))
            if s > score:
                best, score = v, s
        return best

    def follow(cur, target, pred, path):
        seq = []
        v = target
        while v != cur:
            seq.append(v)
            v = pred[v]
        for v in reversed(seq):
            if (path[-1], v) not in edge_of:
                cuts.append(len(path))
            take(path[-1], v)
            path.append(v)

    g = graph()
    _, comp = connected_components(g, directed=False)
    biggest = np.argmax(np.bincount(comp))
    ends = np.nonzero((comp == biggest) & (free == 1))[0]
    start = int(ends[0]) if len(ends) else int(np.nonzero(comp == biggest)[0][0])

    cur = start
    path = [cur]
    while stats["left"]:
        nxt = pick(cur, path)
        if nxt is not None:
            take(cur, nxt)
            path.append(nxt)
            cur = nxt
            continue
        dist, pred = dijkstra(g, directed=False, indices=cur, return_predecessors=True, limit=NEAR)
        cand = np.nonzero((free > 0) & np.isfinite(dist))[0]
        if not len(cand):
            dist, pred = dijkstra(g, directed=False, indices=cur, return_predecessors=True)
            cand = np.nonzero((free > 0) & np.isfinite(dist))[0]
        if len(cand):
            target = int(cand[np.argmin(dist[cand])])
            follow(cur, target, pred, path)
            cur = target
            continue
        reach = np.nonzero(np.isfinite(dist))[0]
        todo = np.nonzero(free > 0)[0]
        gap, k = cKDTree(xy[todo]).query(xy[reach])
        best = np.argmin(retrace_cost * dist[reach] + gap)
        p, q = int(reach[best]), int(todo[k[best]])
        follow(cur, p, pred, path)
        links.append((p, q))
        stats["jumps"] += 1
        stats["jump_length"] += float(gap[best])
        g = graph()
        path.append(q)
        cuts.append(len(path) - 1)
        cur = q

    if cur != start:
        dist, pred = dijkstra(g, directed=False, indices=cur, return_predecessors=True)
        if retrace_cost * dist[start] <= np.hypot(*(xy[cur] - xy[start])):
            follow(cur, start, pred, path)
    stats["ink"] = float(weight.sum())
    if len(path) > 1 and path[-1] == path[0]:
        path = path[:-1]
    return xy[path], cuts, stats


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


def lift_ranges(walk, cuts, n):
    seg = np.hypot(np.diff(walk[:, 0]), np.diff(walk[:, 1]))
    cum = np.concatenate([[0], np.cumsum(seg)])
    total = cum[-1] + np.hypot(*(walk[0] - walk[-1]))
    targets = np.linspace(0, total, n, endpoint=False)
    out = []
    for i in cuts:
        a = int(np.searchsorted(targets, cum[i - 1], side="right"))
        b = int(np.searchsorted(targets, cum[i], side="left")) - 1
        if b >= a:
            out.append([a, b])
    if np.hypot(*(walk[0] - walk[-1])) > 1.5:
        a = int(np.searchsorted(targets, cum[-1], side="right"))
        if a < n:
            out.append([a, n - 1])
    return out


def main():
    src = sys.argv[1] if len(sys.argv) > 1 else "input.png"
    out = sys.argv[2] if len(sys.argv) > 2 else "tsp.json"

    img = read_image(src)
    if img is None:
        print("could not read", src)
        return
    scale = min(1.0, MAXDIM / max(img.shape[:2]))
    img = cv2.resize(img, (int(img.shape[1] * scale), int(img.shape[0] * scale)), interpolation=cv2.INTER_AREA)
    h, w = img.shape[:2]
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

    mode = MODE if MODE != "auto" else ("lines" if is_line_art(gray) else "photo")
    bw = binarize(gray) if mode == "lines" else edges(img)
    skel = clean(skeletonize(bw > 0), MIN_STROKE)
    xy, a, b = pixel_graph(skel)
    if not len(a):
        print("no strokes found")
        return

    walk, cuts, stats = route(xy, a, b, RETRACE_COST)
    seg = np.hypot(*np.diff(np.vstack([walk, walk[:1]]), axis=0).T)
    count = min(RESAMPLE, len(walk))
    path = resample_closed(walk, count)

    data = {"width": w, "height": h, "closed": True, "source": os.path.abspath(src),
            "lift": lift_ranges(walk, cuts, count),
            "path": [[round(float(x), 2), round(float(y), 2)] for x, y in path]}
    with open(out, "w") as f:
        json.dump(data, f)
    print("mode", mode, "pixels", len(xy), "ink", round(stats["ink"], 1), "route", round(float(seg.sum()), 1),
          "jumps", stats["jumps"], "jump length", round(stats["jump_length"], 1),
          "points", len(path), "wrote", out)


if __name__ == "__main__":
    main()
