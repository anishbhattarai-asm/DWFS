const DWFS = (() => {
    const POINTS = 4096;
    const CANVAS = 800;
    const MARGIN = 24;

    function toGray(data, w, h) {
        const g = new Float32Array(w * h);
        for (let i = 0; i < w * h; i++) {
            const a = data[i * 4 + 3] / 255;
            const v = 0.299 * data[i * 4] + 0.587 * data[i * 4 + 1] + 0.114 * data[i * 4 + 2];
            g[i] = v * a + 255 * (1 - a);
        }
        return g;
    }

    function median(g) {
        const hist = new Uint32Array(256);
        for (let i = 0; i < g.length; i++) hist[Math.max(0, Math.min(255, g[i] | 0))]++;
        let acc = 0;
        for (let i = 0; i < 256; i++) {
            acc += hist[i];
            if (acc >= g.length / 2) return i;
        }
        return 255;
    }

    function morph(mask, w, h, r, keep) {
        const tmp = new Uint8Array(w * h);
        const out = new Uint8Array(w * h);
        for (let y = 0; y < h; y++) {
            for (let x = 0; x < w; x++) {
                let v = keep;
                for (let d = -r; d <= r; d++) {
                    const xx = x + d;
                    const s = xx >= 0 && xx < w ? mask[y * w + xx] : 0;
                    if (s !== keep) { v = s; break; }
                }
                tmp[y * w + x] = v;
            }
        }
        for (let y = 0; y < h; y++) {
            for (let x = 0; x < w; x++) {
                let v = keep;
                for (let d = -r; d <= r; d++) {
                    const yy = y + d;
                    const s = yy >= 0 && yy < h ? tmp[yy * w + x] : 0;
                    if (s !== keep) { v = s; break; }
                }
                out[y * w + x] = v;
            }
        }
        return out;
    }

    const erode = (mask, w, h, r) => morph(mask, w, h, r, 1);
    const dilate = (mask, w, h, r) => {
        const inv = new Uint8Array(w * h);
        for (let i = 0; i < w * h; i++) inv[i] = mask[i] ? 0 : 1;
        const e = morph(inv, w, h, r, 1);
        for (let i = 0; i < w * h; i++) e[i] = e[i] ? 0 : 1;
        return e;
    };

    function isLineArt(g, w, h) {
        const level = median(g);
        let flat = 0, dark = 0;
        const mask = new Uint8Array(w * h);
        for (let i = 0; i < w * h; i++) {
            if (Math.abs(g[i] - level) < 12) flat++;
            if (g[i] < level - 40) { mask[i] = 1; dark++; }
        }
        if (flat / (w * h) < 0.6 || dark / (w * h) < 0.002) return false;
        const core = erode(mask, w, h, 2);
        let kept = 0;
        for (let i = 0; i < w * h; i++) kept += core[i];
        return kept / dark < 0.6;
    }

    function boxMean(g, w, h, r) {
        const W = w + 1;
        const I = new Float64Array(W * (h + 1));
        for (let y = 0; y < h; y++) {
            let row = 0;
            for (let x = 0; x < w; x++) {
                row += g[y * w + x];
                I[(y + 1) * W + x + 1] = I[y * W + x + 1] + row;
            }
        }
        const out = new Float32Array(w * h);
        for (let y = 0; y < h; y++) {
            const y0 = Math.max(0, y - r), y1 = Math.min(h - 1, y + r);
            for (let x = 0; x < w; x++) {
                const x0 = Math.max(0, x - r), x1 = Math.min(w - 1, x + r);
                const sum = I[(y1 + 1) * W + x1 + 1] - I[y0 * W + x1 + 1] - I[(y1 + 1) * W + x0] + I[y0 * W + x0];
                out[y * w + x] = sum / ((x1 - x0 + 1) * (y1 - y0 + 1));
            }
        }
        return out;
    }

    function majority(mask, w, h) {
        const out = new Uint8Array(w * h);
        for (let y = 0; y < h; y++) {
            for (let x = 0; x < w; x++) {
                let c = 0;
                for (let dy = -1; dy <= 1; dy++) {
                    for (let dx = -1; dx <= 1; dx++) {
                        const xx = x + dx, yy = y + dy;
                        if (xx >= 0 && yy >= 0 && xx < w && yy < h) c += mask[yy * w + xx];
                    }
                }
                out[y * w + x] = c >= 5 ? 1 : 0;
            }
        }
        return out;
    }

    function blur(g, w, h, sigma) {
        const r = Math.ceil(sigma * 3);
        const k = [];
        let total = 0;
        for (let i = -r; i <= r; i++) {
            const v = Math.exp(-(i * i) / (2 * sigma * sigma));
            k.push(v);
            total += v;
        }
        for (let i = 0; i < k.length; i++) k[i] /= total;
        const tmp = new Float32Array(w * h);
        const out = new Float32Array(w * h);
        for (let y = 0; y < h; y++) {
            for (let x = 0; x < w; x++) {
                let s = 0;
                for (let i = -r; i <= r; i++) s += k[i + r] * g[y * w + Math.min(w - 1, Math.max(0, x + i))];
                tmp[y * w + x] = s;
            }
        }
        for (let y = 0; y < h; y++) {
            for (let x = 0; x < w; x++) {
                let s = 0;
                for (let i = -r; i <= r; i++) s += k[i + r] * tmp[Math.min(h - 1, Math.max(0, y + i)) * w + x];
                out[y * w + x] = s;
            }
        }
        return out;
    }

    function canny(g, w, h, low, high) {
        const mag = new Float32Array(w * h);
        const dir = new Uint8Array(w * h);
        for (let y = 1; y < h - 1; y++) {
            for (let x = 1; x < w - 1; x++) {
                const p = (yy, xx) => g[(y + yy) * w + x + xx];
                const gx = p(-1, 1) + 2 * p(0, 1) + p(1, 1) - p(-1, -1) - 2 * p(0, -1) - p(1, -1);
                const gy = p(1, -1) + 2 * p(1, 0) + p(1, 1) - p(-1, -1) - 2 * p(-1, 0) - p(-1, 1);
                mag[y * w + x] = Math.abs(gx) + Math.abs(gy);
                const a = (Math.atan2(gy, gx) * 180 / Math.PI + 180) % 180;
                dir[y * w + x] = a < 22.5 || a >= 157.5 ? 0 : a < 67.5 ? 1 : a < 112.5 ? 2 : 3;
            }
        }
        const steps = [[1, 0], [1, 1], [0, 1], [-1, 1]];
        const strong = new Uint8Array(w * h);
        for (let y = 1; y < h - 1; y++) {
            for (let x = 1; x < w - 1; x++) {
                const i = y * w + x;
                const m = mag[i];
                if (m < low) continue;
                const [dx, dy] = steps[dir[i]];
                if (m < mag[i + dy * w + dx] || m < mag[i - dy * w - dx]) continue;
                strong[i] = m >= high ? 2 : 1;
            }
        }
        const out = new Uint8Array(w * h);
        const stack = [];
        for (let i = 0; i < w * h; i++) if (strong[i] === 2) { out[i] = 1; stack.push(i); }
        while (stack.length) {
            const i = stack.pop();
            const x = i % w, y = (i / w) | 0;
            for (let dy = -1; dy <= 1; dy++) {
                for (let dx = -1; dx <= 1; dx++) {
                    const xx = x + dx, yy = y + dy;
                    if (xx < 0 || yy < 0 || xx >= w || yy >= h) continue;
                    const j = yy * w + xx;
                    if (strong[j] === 1 && !out[j]) { out[j] = 1; stack.push(j); }
                }
            }
        }
        return out;
    }

    function thin(mask, w, h) {
        const W = w + 2, H = h + 2;
        const img = new Uint8Array(W * H);
        for (let y = 0; y < h; y++) for (let x = 0; x < w; x++) img[(y + 1) * W + x + 1] = mask[y * w + x] ? 1 : 0;
        let live = [];
        for (let i = 0; i < W * H; i++) if (img[i]) live.push(i);
        let changed = true;
        while (changed) {
            changed = false;
            for (let pass = 0; pass < 2; pass++) {
                const kill = [];
                for (const i of live) {
                    if (!img[i]) continue;
                    const p2 = img[i - W], p3 = img[i - W + 1], p4 = img[i + 1], p5 = img[i + W + 1];
                    const p6 = img[i + W], p7 = img[i + W - 1], p8 = img[i - 1], p9 = img[i - W - 1];
                    const b = p2 + p3 + p4 + p5 + p6 + p7 + p8 + p9;
                    if (b < 2 || b > 6) continue;
                    const seq = [p2, p3, p4, p5, p6, p7, p8, p9, p2];
                    let a = 0;
                    for (let k = 0; k < 8; k++) if (!seq[k] && seq[k + 1]) a++;
                    if (a !== 1) continue;
                    if (pass === 0 ? (p2 * p4 * p6 || p4 * p6 * p8) : (p2 * p4 * p8 || p2 * p6 * p8)) continue;
                    kill.push(i);
                }
                for (const i of kill) img[i] = 0;
                if (kill.length) changed = true;
            }
            live = live.filter(i => img[i]);
        }
        const out = new Uint8Array(w * h);
        for (let y = 0; y < h; y++) for (let x = 0; x < w; x++) out[y * w + x] = img[(y + 1) * W + x + 1];
        return out;
    }

    function components(mask, w, h) {
        const labels = new Int32Array(w * h).fill(-1);
        const sizes = [];
        const boxes = [];
        const stack = [];
        for (let s = 0; s < w * h; s++) {
            if (!mask[s] || labels[s] >= 0) continue;
            const id = sizes.length;
            let size = 0, x0 = w, y0 = h, x1 = 0, y1 = 0, sx = 0, sy = 0;
            labels[s] = id;
            stack.push(s);
            while (stack.length) {
                const i = stack.pop();
                const x = i % w, y = (i / w) | 0;
                size++;
                sx += x;
                sy += y;
                if (x < x0) x0 = x;
                if (y < y0) y0 = y;
                if (x > x1) x1 = x;
                if (y > y1) y1 = y;
                for (let dy = -1; dy <= 1; dy++) {
                    for (let dx = -1; dx <= 1; dx++) {
                        const xx = x + dx, yy = y + dy;
                        if (xx < 0 || yy < 0 || xx >= w || yy >= h) continue;
                        const j = yy * w + xx;
                        if (mask[j] && labels[j] < 0) { labels[j] = id; stack.push(j); }
                    }
                }
            }
            sizes.push(size);
            boxes.push({ x0, y0, x1, y1, cx: sx / size, cy: sy / size });
        }
        return { labels, sizes, boxes };
    }

    function graphOf(mask, w, h) {
        const index = new Int32Array(w * h).fill(-1);
        const xs = [], ys = [];
        for (let y = 0; y < h; y++) {
            for (let x = 0; x < w; x++) {
                if (mask[y * w + x]) { index[y * w + x] = xs.length; xs.push(x); ys.push(y); }
            }
        }
        const at = (x, y) => (x < 0 || y < 0 || x >= w || y >= h) ? -1 : index[y * w + x];
        const ea = [], eb = [];
        for (let i = 0; i < xs.length; i++) {
            const x = xs[i], y = ys[i];
            for (const [dx, dy] of [[1, 0], [0, 1], [1, 1], [-1, 1]]) {
                const j = at(x + dx, y + dy);
                if (j < 0) continue;
                if (dx && dy && (at(x + dx, y) >= 0 || at(x, y + dy) >= 0)) continue;
                ea.push(i);
                eb.push(j);
            }
        }
        return { xs, ys, ea, eb };
    }

    function adjacency(n, ea, eb) {
        const deg = new Int32Array(n);
        for (let e = 0; e < ea.length; e++) { deg[ea[e]]++; deg[eb[e]]++; }
        const start = new Int32Array(n + 1);
        for (let i = 0; i < n; i++) start[i + 1] = start[i] + deg[i];
        const nb = new Int32Array(2 * ea.length), ne = new Int32Array(2 * ea.length);
        const fill = start.slice(0, n);
        for (let e = 0; e < ea.length; e++) {
            const a = ea[e], b = eb[e];
            nb[fill[a]] = b; ne[fill[a]++] = e;
            nb[fill[b]] = a; ne[fill[b]++] = e;
        }
        return { deg, start, nb, ne };
    }

    function clean(mask, w, h, minStroke) {
        const comp = components(mask, w, h);
        let kept = new Uint8Array(w * h);
        for (let i = 0; i < w * h; i++) if (mask[i] && comp.sizes[comp.labels[i]] >= minStroke) kept[i] = 1;
        const G = graphOf(kept, w, h);
        const A = adjacency(G.xs.length, G.ea, G.eb);
        const other = (cur, prev) => {
            for (let t = A.start[cur]; t < A.start[cur + 1]; t++) if (A.nb[t] !== prev) return A.nb[t];
            return -1;
        };
        for (let s = 0; s < G.xs.length; s++) {
            if (A.deg[s] !== 1) continue;
            const chain = [s];
            let prev = s, cur = A.nb[A.start[s]];
            while (A.deg[cur] === 2 && chain.length < minStroke) {
                chain.push(cur);
                const next = other(cur, prev);
                prev = cur;
                cur = next;
            }
            if (A.deg[cur] >= 3 && chain.length < minStroke) {
                for (const v of chain) kept[G.ys[v] * w + G.xs[v]] = 0;
            }
        }
        return kept;
    }

    function ring(gx, gy, r, visit) {
        if (r === 0) { visit(gx, gy); return; }
        for (let ix = gx - r; ix <= gx + r; ix++) { visit(ix, gy - r); visit(ix, gy + r); }
        for (let iy = gy - r + 1; iy <= gy + r - 1; iy++) { visit(gx - r, iy); visit(gx + r, iy); }
    }

    class Heap {
        constructor() { this.k = []; this.v = []; }
        get size() { return this.k.length; }
        push(key, value) {
            const k = this.k, v = this.v;
            let i = k.length;
            k.push(key); v.push(value);
            while (i > 0) {
                const p = (i - 1) >> 1;
                if (k[p] <= key) break;
                k[i] = k[p]; v[i] = v[p];
                i = p;
            }
            k[i] = key; v[i] = value;
        }
        pop() {
            const k = this.k, v = this.v;
            const key = k[0], value = v[0];
            const lk = k.pop(), lv = v.pop();
            if (k.length) {
                let i = 0;
                const n = k.length;
                while (true) {
                    let c = 2 * i + 1;
                    if (c >= n) break;
                    if (c + 1 < n && k[c + 1] < k[c]) c++;
                    if (k[c] >= lk) break;
                    k[i] = k[c]; v[i] = v[c];
                    i = c;
                }
                k[i] = lk; v[i] = lv;
            }
            return [key, value];
        }
    }

    function route(xs, ys, ea, eb, retrace) {
        const n = xs.length;
        const A = adjacency(n, ea, eb);
        let extent = 1;
        for (let i = 0; i < n; i++) extent = Math.max(extent, xs[i], ys[i]);
        const used = new Uint8Array(ea.length);
        const free = A.deg.slice();
        let left = ea.length;
        const links = new Map();
        const link = (p, q) => {
            if (!links.has(p)) links.set(p, []);
            if (!links.has(q)) links.set(q, []);
            links.get(p).push(q);
            links.get(q).push(p);
        };
        const edge = (u, v) => {
            for (let t = A.start[u]; t < A.start[u + 1]; t++) if (A.nb[t] === v) return A.ne[t];
            return -1;
        };
        const take = (u, v) => {
            const e = edge(u, v);
            if (e >= 0 && !used[e]) { used[e] = 1; free[u]--; free[v]--; left--; }
            return e;
        };
        const path = [], cuts = [];
        const pick = cur => {
            const back = path.length >= 4 ? path[path.length - 4] : path[0];
            const hx = xs[cur] - xs[back], hy = ys[cur] - ys[back];
            const norm = Math.hypot(hx, hy) || 1;
            let best = -1, score = -2;
            for (let t = A.start[cur]; t < A.start[cur + 1]; t++) {
                if (used[A.ne[t]]) continue;
                const v = A.nb[t], dx = xs[v] - xs[cur], dy = ys[v] - ys[cur];
                const s = (hx * dx + hy * dy) / (norm * Math.hypot(dx, dy));
                if (s > score) { score = s; best = v; }
            }
            return best;
        };
        const dist = new Float64Array(n).fill(Infinity);
        const prev = new Int32Array(n).fill(-1);
        let seen = [];
        const search = (src, stop) => {
            for (const v of seen) { dist[v] = Infinity; prev[v] = -1; }
            seen = [src];
            dist[src] = 0;
            const heap = new Heap();
            heap.push(0, src);
            const relax = (u, v, d) => {
                const nd = d + Math.hypot(xs[u] - xs[v], ys[u] - ys[v]);
                if (nd < dist[v]) {
                    if (dist[v] === Infinity) seen.push(v);
                    dist[v] = nd;
                    prev[v] = u;
                    heap.push(nd, v);
                }
            };
            while (heap.size) {
                const [d, u] = heap.pop();
                if (d > dist[u]) continue;
                if (stop && u !== src && free[u] > 0) return u;
                for (let t = A.start[u]; t < A.start[u + 1]; t++) relax(u, A.nb[t], d);
                const extra = links.get(u);
                if (extra) for (const v of extra) relax(u, v, d);
            }
            return -1;
        };
        const follow = (cur, target) => {
            const seq = [];
            for (let v = target; v !== cur; v = prev[v]) seq.push(v);
            for (let i = seq.length - 1; i >= 0; i--) {
                const v = seq[i];
                if (take(path[path.length - 1], v) < 0) cuts.push(path.length);
                path.push(v);
            }
        };
        const compOf = new Int32Array(n).fill(-1);
        let biggest = -1, biggestSize = 0;
        for (let s = 0, id = 0; s < n; s++) {
            if (compOf[s] >= 0) continue;
            const stack = [s];
            compOf[s] = id;
            let size = 0;
            while (stack.length) {
                const u = stack.pop();
                size++;
                for (let t = A.start[u]; t < A.start[u + 1]; t++) {
                    const v = A.nb[t];
                    if (compOf[v] < 0) { compOf[v] = id; stack.push(v); }
                }
            }
            if (size > biggestSize) { biggestSize = size; biggest = id; }
            id++;
        }
        let start = -1;
        for (let i = 0; i < n; i++) {
            if (compOf[i] !== biggest) continue;
            if (start < 0) start = i;
            if (A.deg[i] === 1) { start = i; break; }
        }
        let cur = start;
        path.push(cur);
        let gaps = 0;
        while (left > 0) {
            const nxt = pick(cur);
            if (nxt >= 0) { take(cur, nxt); path.push(nxt); cur = nxt; continue; }
            const target = search(cur, true);
            if (target >= 0) { follow(cur, target); cur = target; continue; }
            const cell = 8;
            const grid = new Map();
            for (let v = 0; v < n; v++) {
                if (free[v] <= 0) continue;
                const key = Math.floor(xs[v] / cell) * 100000 + Math.floor(ys[v] / cell);
                if (!grid.has(key)) grid.set(key, []);
                grid.get(key).push(v);
            }
            const reach = Math.ceil(extent / cell) + 2;
            const nearest = (x, y, bound) => {
                const gx = Math.floor(x / cell), gy = Math.floor(y / cell);
                let best = -1, bd = bound * bound;
                const visit = (ix, iy) => {
                    const list = grid.get(ix * 100000 + iy);
                    if (!list) return;
                    for (const v of list) {
                        const d = (xs[v] - x) ** 2 + (ys[v] - y) ** 2;
                        if (d < bd) { bd = d; best = v; }
                    }
                };
                for (let r = 0; r <= reach; r++) {
                    if ((r - 1) * cell > Math.sqrt(bd)) break;
                    ring(gx, gy, r, visit);
                }
                return [best, Math.sqrt(bd)];
            };
            const order = seen.filter(v => dist[v] < Infinity).sort((a, b) => dist[a] - dist[b]);
            let bestScore = Infinity, bp = -1, bq = -1;
            for (const p of order) {
                const base = retrace * dist[p];
                if (base >= bestScore) break;
                const [q, gap] = nearest(xs[p], ys[p], Math.min(1e9, bestScore - base));
                if (q >= 0 && base + gap < bestScore) { bestScore = base + gap; bp = p; bq = q; }
            }
            if (bp < 0) break;
            follow(cur, bp);
            link(bp, bq);
            gaps++;
            path.push(bq);
            cuts.push(path.length - 1);
            cur = bq;
        }
        if (cur !== start) {
            search(cur, false);
            const straight = Math.hypot(xs[cur] - xs[start], ys[cur] - ys[start]);
            if (dist[start] < Infinity && retrace * dist[start] <= straight) follow(cur, start);
        }
        if (path.length > 1 && path[path.length - 1] === path[0]) path.pop();
        return { walk: path.map(i => [xs[i], ys[i]]), cuts, gaps };
    }

    function lengths(walk) {
        const cum = [0];
        for (let i = 1; i < walk.length; i++) {
            cum.push(cum[i - 1] + Math.hypot(walk[i][0] - walk[i - 1][0], walk[i][1] - walk[i - 1][1]));
        }
        const last = walk[walk.length - 1];
        const total = cum[cum.length - 1] + Math.hypot(walk[0][0] - last[0], walk[0][1] - last[1]);
        return { cum, total };
    }

    function resample(walk, count) {
        const { cum, total } = lengths(walk);
        const loop = walk.concat([walk[0]]);
        const c = cum.concat([total]);
        const out = [];
        let k = 0;
        for (let i = 0; i < count; i++) {
            const t = total * i / count;
            while (k < c.length - 2 && c[k + 1] < t) k++;
            const span = c[k + 1] - c[k] || 1;
            const f = (t - c[k]) / span;
            out.push([loop[k][0] + f * (loop[k + 1][0] - loop[k][0]), loop[k][1] + f * (loop[k + 1][1] - loop[k][1])]);
        }
        return out;
    }

    function liftRanges(walk, cuts, count) {
        const { cum, total } = lengths(walk);
        const at = v => Math.ceil(v / total * count - 1e-9);
        const out = [];
        for (const i of cuts) {
            const a = Math.floor(cum[i - 1] / total * count) + 1;
            const b = at(cum[i]) - 1;
            if (b >= a) out.push([a, b]);
        }
        const last = walk[walk.length - 1];
        if (Math.hypot(walk[0][0] - last[0], walk[0][1] - last[1]) > 1.5) {
            const a = Math.floor(cum[cum.length - 1] / total * count) + 1;
            if (a < count) out.push([a, count - 1]);
        }
        return out;
    }

    function finish(walk, cuts, w, h, mode, title, stats) {
        if (walk.length < 3) throw new Error("There is not enough to draw here.");
        return {
            width: w, height: h, closed: true, mode, title: title || undefined,
            lift: liftRanges(walk, cuts, POINTS), path: resample(walk, POINTS), stats: stats || {},
        };
    }

    function maskOfImage(image, mode, detail) {
        const { width: w, height: h, data } = image;
        const g = toGray(data, w, h);
        const kind = mode === "auto" ? (isLineArt(g, w, h) ? "lines" : "photo") : mode;
        let mask = new Uint8Array(w * h);
        if (kind === "lines") {
            const mean = boxMean(g, w, h, 6);
            for (let i = 0; i < w * h; i++) mask[i] = g[i] < mean[i] - 7 ? 1 : 0;
            mask = majority(mask, w, h);
        } else {
            const high = 150 - 11 * detail, low = high * 0.45;
            mask = canny(blur(g, w, h, 1.6), w, h, low, high);
            mask = erode(dilate(mask, w, h, 1), w, h, 1);
        }
        return { mask, kind };
    }

    function traceImage(image, options) {
        const opts = Object.assign({ mode: "auto", detail: 5, minStroke: 5 }, options);
        const { width: w, height: h } = image;
        const { mask, kind } = maskOfImage(image, opts.mode, opts.detail);
        const skel = clean(thin(mask, w, h), w, h, opts.minStroke);
        const G = graphOf(skel, w, h);
        if (!G.ea.length) throw new Error("No lines were found in this picture. Try the other mode or more detail.");
        const r = route(G.xs, G.ys, G.ea, G.eb, 0.5);
        return finish(r.walk, r.cuts, w, h, kind, opts.title, { gaps: r.gaps });
    }

    function contours(field, w, h, level) {
        const val = (x, y) => (x < 0 || y < 0 || x >= w || y >= h) ? 0 : field[y * w + x];
        const key = (x, y, v) => ((y + 1) * (w + 3) + (x + 1)) * 2 + v;
        const points = new Map();
        const segs = [];
        const point = (k, x0, y0, x1, y1, a, b) => {
            if (!points.has(k)) {
                const t = (level - a) / (b - a);
                points.set(k, [x0 + t * (x1 - x0) + 0.5, y0 + t * (y1 - y0) + 0.5]);
            }
            return k;
        };
        for (let y = -1; y < h; y++) {
            for (let x = -1; x < w; x++) {
                const a = val(x, y), b = val(x + 1, y), c = val(x + 1, y + 1), d = val(x, y + 1);
                const idx = (a > level ? 8 : 0) | (b > level ? 4 : 0) | (c > level ? 2 : 0) | (d > level ? 1 : 0);
                if (idx === 0 || idx === 15) continue;
                const T = () => point(key(x, y, 0), x, y, x + 1, y, a, b);
                const B = () => point(key(x, y + 1, 0), x, y + 1, x + 1, y + 1, d, c);
                const L = () => point(key(x, y, 1), x, y, x, y + 1, a, d);
                const R = () => point(key(x + 1, y, 1), x + 1, y, x + 1, y + 1, b, c);
                const centre = (a + b + c + d) / 4 > level;
                switch (idx) {
                    case 1: case 14: segs.push([L(), B()]); break;
                    case 2: case 13: segs.push([B(), R()]); break;
                    case 3: case 12: segs.push([L(), R()]); break;
                    case 4: case 11: segs.push([T(), R()]); break;
                    case 6: case 9: segs.push([T(), B()]); break;
                    case 7: case 8: segs.push([L(), T()]); break;
                    case 5:
                        if (centre) { segs.push([L(), T()]); segs.push([B(), R()]); }
                        else { segs.push([T(), R()]); segs.push([L(), B()]); }
                        break;
                    case 10:
                        if (centre) { segs.push([T(), R()]); segs.push([L(), B()]); }
                        else { segs.push([L(), T()]); segs.push([B(), R()]); }
                        break;
                }
            }
        }
        const byPoint = new Map();
        segs.forEach((s, i) => {
            for (const k of s) {
                if (!byPoint.has(k)) byPoint.set(k, []);
                byPoint.get(k).push(i);
            }
        });
        const done = new Uint8Array(segs.length);
        const loops = [];
        for (let s = 0; s < segs.length; s++) {
            if (done[s]) continue;
            done[s] = 1;
            const first = segs[s][0];
            const ring = [first];
            let cur = segs[s][1];
            while (cur !== first) {
                ring.push(cur);
                const next = (byPoint.get(cur) || []).find(i => !done[i]);
                if (next === undefined) break;
                done[next] = 1;
                cur = segs[next][0] === cur ? segs[next][1] : segs[next][0];
            }
            if (ring.length >= 8) loops.push(ring.map(k => points.get(k)));
        }
        return loops;
    }

    function smoothRing(ring, width) {
        const n = ring.length, half = width >> 1;
        const out = [];
        for (let i = 0; i < n; i++) {
            let sx = 0, sy = 0;
            for (let d = -half; d <= half; d++) {
                const p = ring[(i + d + n) % n];
                sx += p[0];
                sy += p[1];
            }
            out.push([sx / width, sy / width]);
        }
        return out;
    }

    function chainStrokes(strokes) {
        const cx = [], cy = [], owner = [], which = [];
        let x0 = Infinity, y0 = Infinity, x1 = -Infinity, y1 = -Infinity;
        strokes.forEach((s, i) => {
            const picks = s.closed ? s.pts.map((_, k) => k) : [0, s.pts.length - 1];
            for (const k of picks) {
                const [x, y] = s.pts[k];
                cx.push(x); cy.push(y); owner.push(i); which.push(k);
                x0 = Math.min(x0, x); y0 = Math.min(y0, y); x1 = Math.max(x1, x); y1 = Math.max(y1, y);
            }
        });
        const cell = Math.max(1e-6, Math.max(x1 - x0, y1 - y0) / Math.max(4, Math.sqrt(cx.length)));
        const grid = new Map();
        const cellOf = (x, y) => [Math.floor((x - x0) / cell), Math.floor((y - y0) / cell)];
        cx.forEach((x, i) => {
            const [gx, gy] = cellOf(x, cy[i]);
            const k = gx * 1000003 + gy;
            if (!grid.has(k)) grid.set(k, []);
            grid.get(k).push(i);
        });
        const gw = Math.ceil((x1 - x0) / cell) + 2, gh = Math.ceil((y1 - y0) / cell) + 2;
        const remaining = new Uint8Array(strokes.length).fill(1);
        const size = s => {
            let t = 0;
            for (let i = 1; i < s.pts.length; i++) t += Math.hypot(s.pts[i][0] - s.pts[i - 1][0], s.pts[i][1] - s.pts[i - 1][1]);
            return t;
        };
        let first = 0, firstSize = -1;
        strokes.forEach((s, i) => { const v = size(s); if (v > firstSize) { firstSize = v; first = i; } });
        remaining[first] = 0;
        const pieces = [strokes[first].pts];
        let cur = strokes[first].pts[strokes[first].pts.length - 1];
        for (let left = strokes.length - 1; left > 0; left--) {
            const [gx, gy] = cellOf(cur[0], cur[1]);
            let best = -1, bd = Infinity;
            const visit = (ix, iy) => {
                const list = grid.get(ix * 1000003 + iy);
                if (!list) return;
                for (const i of list) {
                    if (!remaining[owner[i]]) continue;
                    const d = (cx[i] - cur[0]) ** 2 + (cy[i] - cur[1]) ** 2;
                    if (d < bd) { bd = d; best = i; }
                }
            };
            for (let r = 0; r <= Math.max(gw, gh) + 2; r++) {
                if (best >= 0 && (r - 1) * cell > Math.sqrt(bd)) break;
                ring(gx, gy, r, visit);
            }
            if (best < 0) break;
            const s = strokes[owner[best]];
            let piece;
            if (s.closed) {
                const body = s.pts.slice();
                const k = which[best];
                piece = body.slice(k).concat(body.slice(0, k));
                piece.push(piece[0]);
            } else {
                piece = which[best] === 0 ? s.pts : s.pts.slice().reverse();
            }
            pieces.push(piece);
            remaining[owner[best]] = 0;
            cur = piece[piece.length - 1];
        }
        const walk = [], cuts = [];
        for (const piece of pieces) {
            if (walk.length) cuts.push(walk.length);
            for (const p of piece) walk.push(p);
        }
        return { walk, cuts };
    }

    function fit(strokes) {
        let x0 = Infinity, y0 = Infinity, x1 = -Infinity, y1 = -Infinity;
        for (const s of strokes) for (const [x, y] of s.pts) {
            x0 = Math.min(x0, x); y0 = Math.min(y0, y); x1 = Math.max(x1, x); y1 = Math.max(y1, y);
        }
        const size = Math.max(x1 - x0, y1 - y0);
        if (!(size > 0)) throw new Error("The drawing has no size.");
        const scale = (CANVAS - 2 * MARGIN) / size;
        const moved = strokes.map(s => ({ closed: s.closed, pts: s.pts.map(([x, y]) => [(x - x0) * scale + MARGIN, (y - y0) * scale + MARGIN]) }));
        return { strokes: moved, w: (x1 - x0) * scale + 2 * MARGIN, h: (y1 - y0) * scale + 2 * MARGIN };
    }

    function traceStrokes(strokes, mode, title) {
        const usable = strokes.filter(s => s.pts.length > 1);
        if (!usable.length) throw new Error("No shapes were found.");
        const f = fit(usable);
        const { walk, cuts } = chainStrokes(f.strokes);
        return finish(walk, cuts, f.w, f.h, mode, title, { strokes: usable.length });
    }

    function traceTextField(alpha, w, h, stroke, words) {
        if (stroke === "outline") {
            const loops = contours(alpha, w, h, 0.5).map(r => ({ closed: true, pts: smoothRing(r, 5) }));
            if (!loops.length) throw new Error("No letters were found.");
            const { walk, cuts } = chainStrokes(loops);
            return finish(walk, cuts, w, h, "text", words, { strokes: loops.length });
        }
        const mask = new Uint8Array(w * h);
        for (let i = 0; i < w * h; i++) mask[i] = alpha[i] > 0.5 ? 1 : 0;
        const comp = components(mask, w, h);
        const reach = 2 * 5 + 4;
        const dots = new Set();
        comp.boxes.forEach((b, i) => {
            const bw = b.x1 - b.x0 + 1, bh = b.y1 - b.y0 + 1;
            if (Math.max(bw, bh) <= reach * 3 && Math.min(bw, bh) * 2 >= Math.max(bw, bh)) dots.add(i);
        });
        const body = new Uint8Array(w * h);
        for (let i = 0; i < w * h; i++) if (mask[i] && !dots.has(comp.labels[i])) body[i] = 1;
        let walk = [], cuts = [], gaps = 0;
        if (body.some(v => v)) {
            const skel = clean(thin(body, w, h), w, h, 6);
            const G = graphOf(skel, w, h);
            if (G.ea.length) {
                const r = route(G.xs, G.ys, G.ea, G.eb, 0.5);
                walk = r.walk; cuts = r.cuts; gaps = r.gaps;
            }
        }
        for (const i of dots) {
            const b = comp.boxes[i];
            const radius = Math.max(1.5, Math.sqrt(comp.sizes[i] / Math.PI) * 0.7);
            if (walk.length) cuts.push(walk.length);
            for (let k = 0; k <= 16; k++) {
                const a = 2 * Math.PI * k / 16;
                walk.push([b.cx + radius * Math.cos(a), b.cy + radius * Math.sin(a)]);
            }
        }
        if (!walk.length) throw new Error("No letters were found.");
        return finish(walk, cuts, w, h, "text", words, { gaps, dots: dots.size });
    }

    function fft(re, im, inverse) {
        const n = re.length;
        for (let i = 1, j = 0; i < n; i++) {
            let bit = n >> 1;
            for (; j & bit; bit >>= 1) j ^= bit;
            j ^= bit;
            if (i < j) {
                [re[i], re[j]] = [re[j], re[i]];
                [im[i], im[j]] = [im[j], im[i]];
            }
        }
        for (let len = 2; len <= n; len <<= 1) {
            const ang = 2 * Math.PI / len * (inverse ? 1 : -1);
            const wr = Math.cos(ang), wi = Math.sin(ang);
            for (let i = 0; i < n; i += len) {
                let cr = 1, ci = 0;
                for (let k = 0; k < len / 2; k++) {
                    const a = i + k, b = i + k + len / 2;
                    const tr = re[b] * cr - im[b] * ci, ti = re[b] * ci + im[b] * cr;
                    re[b] = re[a] - tr; im[b] = im[a] - ti;
                    re[a] += tr; im[a] += ti;
                    const nr = cr * wr - ci * wi;
                    ci = cr * wi + ci * wr;
                    cr = nr;
                }
            }
        }
    }

    function stagesOf(nmax) {
        const out = [];
        for (let i = 1; i <= Math.min(8, nmax); i++) out.push(i);
        let v = out[out.length - 1];
        while (out[out.length - 1] < nmax) {
            v *= 1.5;
            out.push(Math.min(nmax, Math.max(out[out.length - 1] + 1, Math.round(v))));
        }
        return out;
    }

    function synth(amps, ks, limit, n) {
        const re = new Float64Array(n), im = new Float64Array(n);
        for (let i = 0; i < ks.length; i++) {
            if (Math.abs(ks[i]) > limit) continue;
            const slot = ((ks[i] % n) + n) % n;
            re[slot] += amps[i][0];
            im[slot] += amps[i][1];
        }
        fft(re, im, true);
        return [re, im];
    }

    function percentile(values, q) {
        const s = Float64Array.from(values).sort();
        return s[Math.min(s.length - 1, Math.max(0, Math.round(q / 100 * (s.length - 1))))];
    }

    function analyze(data, style, drawCircles) {
        const n = data.path.length;
        const w = data.width, h = data.height;
        const zr = new Float64Array(n), zi = new Float64Array(n);
        data.path.forEach(([x, y], i) => { zr[i] = x - w / 2; zi[i] = -(y - h / 2); });
        const lift = new Uint8Array(n);
        for (const [a, b] of data.lift || []) for (let i = Math.max(0, a); i <= Math.min(n - 1, b); i++) lift[i] = 1;
        const cr = zr.slice(), ci = zi.slice();
        fft(cr, ci, false);
        for (let i = 0; i < n; i++) { cr[i] /= n; ci[i] /= n; }
        const freq = i => (i < n / 2 ? i : i - n);
        const levels = stagesOf(n / 2);
        let total = 0;
        for (let i = 1; i < n; i++) total += cr[i] * cr[i] + ci[i] * ci[i];
        const errors = levels.map(N => {
            let rest = 0;
            for (let i = 1; i < n; i++) if (Math.abs(freq(i)) > N) rest += cr[i] * cr[i] + ci[i] * ci[i];
            return total > 0 ? 100 * Math.sqrt(rest / total) : 0;
        });
        const curves = levels.map(N => {
            const re = new Float64Array(n), im = new Float64Array(n);
            for (let i = 0; i < n; i++) if (Math.abs(freq(i)) <= N) { re[i] = cr[i]; im[i] = ci[i]; }
            fft(re, im, true);
            return [re, im];
        });
        const chains = [];
        if (style === "classic") {
            const idx = [];
            for (let i = 1; i < n; i++) idx.push(i);
            idx.sort((a, b) => (cr[b] ** 2 + ci[b] ** 2) - (cr[a] ** 2 + ci[a] ** 2));
            chains.push({ base: [cr[0], ci[0]], amps: idx.map(i => [cr[i], ci[i]]), ks: idx.map(freq) });
        } else {
            for (const [part, rot] of [[zr, false], [zi, true]]) {
                const re = Float64Array.from(part), im = new Float64Array(n);
                fft(re, im, false);
                const amps = [], ks = [];
                for (let k = 1; k <= n / 2; k++) {
                    const scale = (k === n / 2 ? 1 : 2) / n;
                    const ar = re[k] * scale, ai = im[k] * scale;
                    amps.push(rot ? [-ai, ar] : [ar, ai]);
                    ks.push(k);
                }
                const order = amps.map((_, i) => i).sort((a, b) => Math.hypot(...amps[b]) - Math.hypot(...amps[a]));
                const base = re[0] / n;
                chains.push({ base: rot ? [0, base] : [base, 0], amps: order.map(i => amps[i]), ks: order.map(i => ks[i]) });
            }
        }
        const times = Array.from({ length: 48 }, (_, i) => 2 * Math.PI * i / 48);
        for (const ch of chains) {
            ch.draw = [];
            ch.tips = [];
            const lows = [[], []], highs = [[], []];
            for (const N of levels) {
                const pick = [];
                for (let i = 0; i < ch.ks.length && pick.length < drawCircles; i++) if (Math.abs(ch.ks[i]) <= N) pick.push(i);
                ch.draw.push(pick);
                const tips = synth(ch.amps, ch.ks, N, n);
                ch.tips.push(tips);
                for (const t of times) {
                    let x = 0, y = 0, lx = 0, hx = 0, ly = 0, hy = 0;
                    for (const i of pick) {
                        const r = Math.hypot(...ch.amps[i]);
                        lx = Math.min(lx, x - r); hx = Math.max(hx, x + r);
                        ly = Math.min(ly, y - r); hy = Math.max(hy, y + r);
                        const a = ch.ks[i] * t, [ar, ai] = ch.amps[i];
                        x += ar * Math.cos(a) - ai * Math.sin(a);
                        y += ar * Math.sin(a) + ai * Math.cos(a);
                    }
                    lows[0].push(lx); highs[0].push(hx); lows[1].push(ly); highs[1].push(hy);
                }
                for (let j = 0; j < n; j += 16) {
                    lows[0].push(tips[0][j]); highs[0].push(tips[0][j]);
                    lows[1].push(tips[1][j]); highs[1].push(tips[1][j]);
                }
            }
            ch.lo = [percentile(lows[0], 3), percentile(lows[1], 3)];
            ch.hi = [percentile(highs[0], 97), percentile(highs[1], 97)];
        }
        let x0 = Infinity, x1 = -Infinity, y0 = Infinity, y1 = -Infinity;
        for (let i = 0; i < n; i++) {
            x0 = Math.min(x0, zr[i]); x1 = Math.max(x1, zr[i]); y0 = Math.min(y0, zi[i]); y1 = Math.max(y1, zi[i]);
        }
        const size = Math.max(x1 - x0, y1 - y0) || 1;
        if (data.ghost) {
            x0 = Math.min(x0, -w / 2); x1 = Math.max(x1, w / 2); y0 = Math.min(y0, -h / 2); y1 = Math.max(y1, h / 2);
        }
        const gap = 0.08 * size;
        const boxes = [[x0, x1, y0, y1]];
        if (style === "classic") {
            chains[0].origin = chains[0].base;
        } else {
            chains[0].origin = [chains[0].base[0], y1 + gap - chains[0].lo[1]];
            chains[1].origin = [x0 - gap - chains[1].hi[0], chains[1].base[1]];
        }
        for (const ch of chains) {
            boxes.push([ch.origin[0] + ch.lo[0], ch.origin[0] + ch.hi[0], ch.origin[1] + ch.lo[1], ch.origin[1] + ch.hi[1]]);
        }
        const pad = 0.04 * size;
        const box = [
            Math.min(...boxes.map(b => b[0])) - pad, Math.max(...boxes.map(b => b[1])) + pad,
            Math.min(...boxes.map(b => b[2])) - pad, Math.max(...boxes.map(b => b[3])) + pad,
        ];
        return { n, levels, errors, curves, chains, lift, box, size, style, width: w, height: h };
    }

    return {
        POINTS, traceImage, traceStrokes, traceTextField, analyze, fft, resample, liftRanges, route, graphOf,
        thin, clean, contours, chainStrokes, isLineArt, toGray, stagesOf,
    };
})();

if (typeof module !== "undefined") module.exports = DWFS;
