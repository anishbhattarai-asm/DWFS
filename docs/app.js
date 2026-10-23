(() => {
    const $ = id => document.getElementById(id);
    const canvas = $("stage");
    const ctx = canvas.getContext("2d");
    const THEMES = {
        light: { bg: "#f4f5f5", ink: "#141414", circle: 0.34, chains: ["#2f6aa8", "#b5473a"], accent: "#2e8b72", text: "#3b4252", panel: "#fcfdfd" },
        dark: { bg: "#05070a", ink: "#5fe3f0", circle: 0.36, chains: ["#7fb0ff", "#ff8e7d"], accent: "#5ad1b0", text: "#d8dee9", panel: "#0d1117" },
    };
    const TARGETS = { axes: ["x", "y", "pen"], classic: ["pen"] };
    const NAMES = { x: "x chain", y: "y chain", pen: "pen" };
    const W = 1000, HEAD = 128, FOOT = 118, DRAW = 120;
    const STAGE = 1.6, FINAL = 10, HOLD = 1.5;
    const SERIF = "'Latin Modern Roman', 'CMU Serif', 'Cambria Math', Cambria, Georgia, serif";
    const formulas = {};
    for (const style of ["axes", "classic"]) {
        for (const theme of ["light", "dark"]) {
            const img = new Image();
            img.src = `assets/formula_${style}_${theme}.png`;
            formulas[style + theme] = img;
        }
    }
    const state = {
        data: null, label: "", source: null, ghosts: {}, models: {}, model: null, view: null,
        style: "axes", theme: "light", playing: true, speed: 1, time: 0,
        lens: true, follow: 0, zoom: 1, recording: null, scrub: false,
    };
    const status = text => { $("status").textContent = text; };
    const busy = (text, work) => {
        status(text);
        setTimeout(() => {
            try {
                work();
            } catch (err) {
                status(err && err.message ? err.message : String(err));
            }
        }, 30);
    };

    function hex(color, alpha) {
        const v = parseInt(color.slice(1), 16);
        return `rgba(${v >> 16}, ${(v >> 8) & 255}, ${v & 255}, ${alpha})`;
    }

    function duration() {
        return (state.model.levels.length - 1) * STAGE + FINAL + HOLD;
    }

    function frameAt(time) {
        const m = state.model, last = m.levels.length - 1;
        if (time < last * STAGE) {
            const s = Math.floor(time / STAGE);
            return [s, Math.min(m.n, Math.floor((time - s * STAGE) / STAGE * m.n) + 1)];
        }
        const rest = time - last * STAGE;
        if (rest < FINAL) return [last, Math.min(m.n, Math.floor(rest / FINAL * m.n) + 1)];
        return [last, m.n];
    }

    function modelFor(style) {
        if (!state.models[style]) state.models[style] = DWFS.analyze(state.data, style, DRAW);
        const m = state.models[style];
        for (const ch of m.chains) if (!ch.radius) ch.radius = ch.amps.map(([a, b]) => Math.hypot(a, b));
        return m;
    }

    function layout() {
        const m = state.model;
        const [x0, x1, y0, y1] = m.box;
        const s = Math.min((W - 80) / (x1 - x0), 920 / (y1 - y0));
        const mw = (x1 - x0) * s, mh = (y1 - y0) * s;
        canvas.width = W;
        canvas.height = Math.round(HEAD + mh + FOOT);
        state.view = { s, ox: (W - mw) / 2, oy: HEAD, x0, y1, mw, mh };
        fitCss();
    }

    function fitCss() {
        const room = $("stagebox").clientWidth;
        const tall = Math.max(320, window.innerHeight - 170);
        const width = Math.min(room, tall * canvas.width / canvas.height);
        canvas.style.width = width + "px";
        canvas.style.height = width * canvas.height / canvas.width + "px";
    }

    function use(data, label) {
        state.data = data;
        state.label = label || data.title || "";
        state.ghosts = {};
        state.models = {};
        state.model = modelFor(state.style);
        state.follow = 0;
        state.zoom = 1;
        state.time = 0;
        state.playing = true;
        layout();
        refresh();
        const lifts = data.lift.length;
        status(`Ready: one path of ${data.path.length} points${lifts ? ", the pen lifts " + lifts + " times" : ""}. N grows to ${state.model.levels[state.model.levels.length - 1]}.`);
    }

    function ghostCanvas(theme) {
        const source = state.source;
        if (!source || !source.image || !state.data.ghost) return null;
        if (state.ghosts[theme]) return state.ghosts[theme];
        const { width: w, height: h, data } = source.image;
        const c = document.createElement("canvas");
        c.width = w;
        c.height = h;
        const g = c.getContext("2d");
        const out = g.createImageData(w, h);
        const v = parseInt(THEMES[theme].accent.slice(1), 16);
        for (let i = 0; i < w * h; i++) {
            const a = data[i * 4 + 3] / 255;
            const lum = (0.299 * data[i * 4] + 0.587 * data[i * 4 + 1] + 0.114 * data[i * 4 + 2]) * a + 255 * (1 - a);
            const dark = 1 - lum / 255;
            out.data[i * 4] = v >> 16;
            out.data[i * 4 + 1] = (v >> 8) & 255;
            out.data[i * 4 + 2] = v & 255;
            out.data[i * 4 + 3] = Math.round(255 * Math.pow(dark, 0.8) * 0.3);
        }
        g.putImageData(out, 0, 0);
        state.ghosts[theme] = c;
        return c;
    }

    function chainPoints(ch, s, t) {
        const pick = ch.draw[s];
        const pts = [[ch.origin[0], ch.origin[1]]];
        let x = ch.origin[0], y = ch.origin[1];
        for (const i of pick) {
            const a = ch.ks[i] * t, [ar, ai] = ch.amps[i];
            x += ar * Math.cos(a) - ai * Math.sin(a);
            y += ar * Math.sin(a) + ai * Math.cos(a);
            pts.push([x, y]);
        }
        return pts;
    }

    function drawScene(v, frame, th, scale) {
        const m = state.model;
        const X = x => v.ox + (x - v.x0) * v.s;
        const Y = y => v.oy + (v.y1 - y) * v.s;
        const { s, j, centers, ends, pen } = frame;
        if (m.style === "axes") {
            ctx.setLineDash([5 * scale, 5 * scale]);
            ctx.lineWidth = 1 * scale;
            ends.forEach((e, ci) => {
                ctx.strokeStyle = hex(th.chains[ci], 0.5);
                ctx.beginPath();
                ctx.moveTo(X(e[0]), Y(e[1]));
                ctx.lineTo(X(pen[0]), Y(pen[1]));
                ctx.stroke();
            });
            ctx.setLineDash([]);
        }
        m.chains.forEach((ch, ci) => {
            const pts = centers[ci];
            const pick = ch.draw[s];
            const count = pick.length;
            for (let q = 0; q < count; q++) {
                const fade = 1 - 0.7 * q / Math.max(1, count - 1);
                const r = ch.radius[pick[q]] * v.s;
                if (r < 0.4) continue;
                ctx.strokeStyle = hex(th.chains[ci], th.circle * fade);
                ctx.lineWidth = (0.5 + 0.6 * fade) * scale;
                ctx.beginPath();
                ctx.arc(X(pts[q][0]), Y(pts[q][1]), r, 0, 2 * Math.PI);
                ctx.stroke();
            }
            ctx.strokeStyle = hex(th.chains[ci], 0.9);
            ctx.fillStyle = hex(th.chains[ci], 0.9);
            ctx.lineWidth = 1.1 * scale;
            ctx.beginPath();
            ctx.moveTo(X(pts[0][0]), Y(pts[0][1]));
            for (let q = 1; q < pts.length; q++) ctx.lineTo(X(pts[q][0]), Y(pts[q][1]));
            ctx.lineTo(X(ends[ci][0]), Y(ends[ci][1]));
            ctx.stroke();
            const cap = 0.016 * m.size;
            ctx.beginPath();
            for (let q = 1; q < pts.length; q++) {
                const dx = pts[q][0] - pts[q - 1][0], dy = pts[q][1] - pts[q - 1][1];
                const len = Math.hypot(dx, dy);
                if (len * v.s < 2) continue;
                const ux = dx / len, uy = dy / len, hl = Math.min(0.3 * len, cap), hw = 0.32 * hl;
                const bx = pts[q][0] - ux * hl, by = pts[q][1] - uy * hl;
                ctx.moveTo(X(pts[q][0]), Y(pts[q][1]));
                ctx.lineTo(X(bx - uy * hw), Y(by + ux * hw));
                ctx.lineTo(X(bx + uy * hw), Y(by - ux * hw));
                ctx.closePath();
            }
            ctx.fill();
            ctx.beginPath();
            ctx.arc(X(ends[ci][0]), Y(ends[ci][1]), 2.4 * scale, 0, 2 * Math.PI);
            ctx.fill();
        });
        const [cr, ci2] = m.curves[s];
        ctx.strokeStyle = th.ink;
        ctx.lineWidth = 1.5 * scale;
        ctx.lineJoin = "round";
        ctx.lineCap = "round";
        ctx.beginPath();
        let down = false;
        for (let i = 0; i <= j; i++) {
            const k = i % m.n;
            if (m.lift[k]) { down = false; continue; }
            const px = X(cr[k]), py = Y(ci2[k]);
            if (down) ctx.lineTo(px, py); else ctx.moveTo(px, py);
            down = true;
        }
        ctx.stroke();
        ctx.beginPath();
        ctx.arc(X(pen[0]), Y(pen[1]), 3.4 * scale, 0, 2 * Math.PI);
        if (m.lift[j % m.n]) {
            ctx.lineWidth = 1.4 * scale;
            ctx.stroke();
        } else {
            ctx.fillStyle = th.ink;
            ctx.fill();
        }
    }

    function render() {
        const m = state.model, th = THEMES[state.theme], v = state.view;
        ctx.fillStyle = th.bg;
        ctx.fillRect(0, 0, canvas.width, canvas.height);
        const img = formulas[m.style + state.theme];
        if (img.complete && img.naturalWidth) {
            const hh = m.style === "axes" ? 100 : 46;
            ctx.drawImage(img, 34, (HEAD - hh) / 2, img.naturalWidth * hh / img.naturalHeight, hh);
        }
        const [s, j] = frameAt(state.time);
        const t = 2 * Math.PI * j / m.n;
        const [cr, ci] = m.curves[s];
        const pen = [cr[j % m.n], ci[j % m.n]];
        const centers = m.chains.map(ch => chainPoints(ch, s, t));
        const ends = m.chains.map(ch => {
            const [tx, ty] = ch.tips[s];
            return [ch.origin[0] + tx[j % m.n], ch.origin[1] + ty[j % m.n]];
        });
        const frame = { s, j, centers, ends, pen };
        const X = x => v.ox + (x - v.x0) * v.s;
        const Y = y => v.oy + (v.y1 - y) * v.s;
        const ghost = ghostCanvas(state.theme);
        if (ghost) {
            const w = state.data.width, h = state.data.height;
            ctx.drawImage(ghost, X(-w / 2), Y(h / 2), w * v.s, h * v.s);
            ctx.strokeStyle = hex(th.accent, 0.6);
            ctx.lineWidth = 1;
            ctx.strokeRect(X(-w / 2), Y(h / 2), w * v.s, h * v.s);
        }
        drawScene(v, frame, th, 1);
        if (state.lens) {
            const targets = TARGETS[m.style];
            const name = targets[state.follow % targets.length];
            const c = name === "pen" ? pen : ends[name === "x" ? 0 : 1];
            const half = m.size / 12 / state.zoom;
            const side = Math.min(230, 0.42 * v.mw, 0.42 * v.mh);
            const lx = v.ox + 12, ly = v.oy + 12;
            state.lensRect = [lx, ly, side];
            ctx.setLineDash([4, 4]);
            ctx.strokeStyle = hex(th.accent, 0.9);
            ctx.lineWidth = 1;
            ctx.strokeRect(X(c[0] - half), Y(c[1] + half), 2 * half * v.s, 2 * half * v.s);
            ctx.setLineDash([]);
            ctx.save();
            ctx.beginPath();
            ctx.rect(lx, ly, side, side);
            ctx.clip();
            ctx.fillStyle = th.panel;
            ctx.fillRect(lx, ly, side, side);
            drawScene({ s: side / (2 * half), ox: lx, oy: ly, x0: c[0] - half, y1: c[1] + half }, frame, th, 1);
            ctx.fillStyle = th.text;
            ctx.font = "12px system-ui, sans-serif";
            ctx.fillText(`${NAMES[name]}   ×${(m.size / (2 * half)).toFixed(1)}`, lx + 8, ly + 18);
            ctx.restore();
            ctx.strokeStyle = th.accent;
            ctx.lineWidth = 1.4;
            ctx.strokeRect(lx, ly, side, side);
        }
        const base = HEAD + v.mh;
        ctx.textBaseline = "middle";
        if (state.label) {
            let size = 26;
            ctx.font = `${size}px ${SERIF}`;
            while (ctx.measureText(state.label).width > W / 2 - 130 && size > 10) ctx.font = `${--size}px ${SERIF}`;
            ctx.fillStyle = th.text;
            ctx.textAlign = "left";
            ctx.fillText(state.label, 40, base + FOOT * 0.45);
        }
        ctx.font = `italic 50px ${SERIF}`;
        ctx.textAlign = "right";
        ctx.fillStyle = th.ink;
        ctx.fillText("N =", W / 2 + 6, base + FOOT * 0.42);
        ctx.font = `50px ${SERIF}`;
        ctx.textAlign = "left";
        ctx.fillStyle = th.accent;
        ctx.fillText(String(m.levels[s]), W / 2 + 18, base + FOOT * 0.42);
        ctx.font = `21px ${SERIF}`;
        ctx.textAlign = "center";
        ctx.fillStyle = th.text;
        ctx.fillText(`approximation error = ${m.errors[s].toFixed(2)}%`, W / 2, base + FOOT * 0.8);
        ctx.textAlign = "left";
        ctx.textBaseline = "alphabetic";
    }

    function refresh() {
        $("play").textContent = state.playing ? "Pause" : "Play";
        $("speed").textContent = `${state.speed}×`;
        $("lens").textContent = state.lens ? "Hide lens" : "Show lens";
        $("record").textContent = state.recording ? "Stop recording" : "Record video";
        const none = !state.model, rec = !!state.recording;
        for (const id of ["play", "prev", "next", "theme", "style", "timeline"]) $(id).disabled = none || rec;
        for (const id of ["lens", "follow", "png", "json", "record"]) $(id).disabled = none;
    }

    function jump(direction) {
        const m = state.model;
        const [s] = frameAt(state.time);
        const last = m.levels.length - 1;
        const target = Math.max(0, Math.min(last, s + direction));
        state.time = target * STAGE + 0.001;
    }

    function restyle(style) {
        if (!state.model) return;
        const share = state.time / duration();
        state.style = style;
        state.model = modelFor(style);
        state.follow = 0;
        layout();
        state.time = share * duration();
        refresh();
    }

    function download(blob, name) {
        const url = URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = url;
        a.download = name;
        document.body.appendChild(a);
        a.click();
        a.remove();
        setTimeout(() => URL.revokeObjectURL(url), 2000);
    }

    function fileStem() {
        return (state.label || "dwfs").toLowerCase().replace(/[^\p{L}\p{N}]+/gu, "_").replace(/^_+|_+$/g, "") || "dwfs";
    }

    function record() {
        if (state.recording) {
            state.recording.stop();
            return;
        }
        const types = ["video/mp4;codecs=avc1", "video/mp4", "video/webm;codecs=vp9", "video/webm"];
        const type = window.MediaRecorder && types.find(t => MediaRecorder.isTypeSupported(t));
        if (!type || !canvas.captureStream) {
            status("This browser cannot record video. Try Chrome, Edge or Firefox, or install dwfs for MP4 export.");
            return;
        }
        const rec = new MediaRecorder(canvas.captureStream(60), { mimeType: type, videoBitsPerSecond: 8000000 });
        const chunks = [];
        rec.ondataavailable = e => { if (e.data.size) chunks.push(e.data); };
        rec.onstop = () => {
            state.recording = null;
            download(new Blob(chunks, { type }), fileStem() + (type.startsWith("video/mp4") ? ".mp4" : ".webm"));
            status("Video saved.");
            refresh();
        };
        state.time = 0;
        state.playing = true;
        state.recording = rec;
        rec.start(500);
        refresh();
    }

    function renderText(words, stroke) {
        const lines = words.replace(/\\n/g, "\n").split("\n").map(l => l.trim()).filter(Boolean);
        if (!lines.length) throw new Error("Type some text first.");
        const size = 150;
        const font = `${size}px system-ui, "Segoe UI", Roboto, "Noto Sans", "Nirmala UI", "Noto Sans Devanagari", sans-serif`;
        const probe = document.createElement("canvas").getContext("2d");
        probe.font = font;
        const widths = lines.map(l => probe.measureText(l).width);
        const pad = size * 0.5, step = size * 1.25;
        const c = document.createElement("canvas");
        c.width = Math.ceil(Math.max(...widths) + 2 * pad);
        c.height = Math.ceil(step * lines.length + 2 * pad);
        const g = c.getContext("2d");
        g.font = font;
        g.fillStyle = "#000";
        g.textBaseline = "middle";
        lines.forEach((l, i) => g.fillText(l, pad, pad + step * (i + 0.5)));
        const data = g.getImageData(0, 0, c.width, c.height).data;
        const alpha = new Float32Array(c.width * c.height);
        for (let i = 0; i < alpha.length; i++) alpha[i] = data[i * 4 + 3] / 255;
        return DWFS.traceTextField(alpha, c.width, c.height, stroke, lines.join(" "));
    }

    function svgStrokes(text) {
        if (/<!doctype|<!entity/i.test(text)) throw new Error("SVG files with a DOCTYPE or entity declarations are not supported.");
        const doc = new DOMParser().parseFromString(text, "image/svg+xml");
        const root = doc.documentElement;
        if (doc.querySelector("parsererror") || !root || root.nodeName.toLowerCase() !== "svg") throw new Error("This SVG file could not be read.");
        root.querySelectorAll("script, foreignObject, iframe, image, a").forEach(e => e.replaceWith(...e.childNodes));
        for (const el of [root, ...root.querySelectorAll("*")]) {
            for (const a of [...el.attributes]) {
                if (/^on/i.test(a.name) || /^\s*javascript:/i.test(a.value)) el.removeAttribute(a.name);
            }
        }
        const NS = "http://www.w3.org/2000/svg";
        for (const u of [...root.querySelectorAll("use")]) {
            const ref = (u.getAttribute("href") || u.getAttributeNS("http://www.w3.org/1999/xlink", "href") || "").replace(/^#/, "");
            const target = ref && doc.getElementById(ref);
            const g = doc.createElementNS(NS, "g");
            g.setAttribute("transform", `${u.getAttribute("transform") || ""} translate(${parseFloat(u.getAttribute("x")) || 0} ${parseFloat(u.getAttribute("y")) || 0})`);
            if (target) {
                const copy = target.cloneNode(true);
                copy.removeAttribute("id");
                if (copy.nodeName.toLowerCase() === "symbol") g.append(...copy.childNodes); else g.appendChild(copy);
            }
            u.replaceWith(g);
        }
        const host = document.createElement("div");
        host.style.cssText = "position:absolute;left:-100000px;top:0;width:800px;height:800px;overflow:hidden;opacity:0;pointer-events:none";
        const node = document.importNode(root, true);
        host.appendChild(node);
        document.body.appendChild(host);
        try {
            const inverse = node.getScreenCTM().inverse();
            const shapes = [...node.querySelectorAll("path, rect, circle, ellipse, line, polyline, polygon")]
                .filter(el => !el.closest("defs, clipPath, mask, symbol, marker, pattern"));
            const strokes = [];
            for (const el of shapes) {
                const cs = getComputedStyle(el);
                if (cs.display === "none" || cs.visibility === "hidden") continue;
                let len = 0;
                try { len = el.getTotalLength(); } catch (err) { len = 0; }
                if (!(len > 0)) continue;
                const m = inverse.multiply(el.getScreenCTM());
                const count = Math.max(24, Math.min(5000, Math.ceil(len)));
                const gapLimit = 3 * len / count;
                let cur = [], prev = null;
                for (let k = 0; k <= count; k++) {
                    const p = el.getPointAtLength(len * k / count);
                    if (prev && Math.hypot(p.x - prev.x, p.y - prev.y) > gapLimit && cur.length > 1) {
                        strokes.push(cur);
                        cur = [];
                    }
                    const q = new DOMPoint(p.x, p.y).matrixTransform(m);
                    cur.push([q.x, q.y]);
                    prev = p;
                }
                if (cur.length > 1) strokes.push(cur);
            }
            return strokes.map(pts => {
                const a = pts[0], b = pts[pts.length - 1];
                const span = Math.hypot(b[0] - a[0], b[1] - a[1]);
                return { pts, closed: span < 1e-6 * (1 + Math.abs(a[0]) + Math.abs(a[1])) || span < 0.5 };
            });
        } finally {
            host.remove();
        }
    }

    function fromImage(image, label) {
        state.source = { kind: "image", image, label };
        retrace();
    }

    function retrace() {
        const src = state.source;
        if (!src || src.kind !== "image") return;
        busy("Tracing the picture…", () => {
            const data = DWFS.traceImage(src.image, { mode: $("mode").value, detail: Number($("detail").value), title: src.label });
            data.ghost = true;
            use(data, src.label);
        });
    }

    function fromBitmap(bitmap, label) {
        const scale = Math.min(1, 520 / Math.max(bitmap.width, bitmap.height));
        const w = Math.max(1, Math.round(bitmap.width * scale)), h = Math.max(1, Math.round(bitmap.height * scale));
        const c = document.createElement("canvas");
        c.width = w;
        c.height = h;
        const g = c.getContext("2d");
        g.fillStyle = "#fff";
        g.fillRect(0, 0, w, h);
        g.drawImage(bitmap, 0, 0, w, h);
        fromImage(g.getImageData(0, 0, w, h), label);
    }

    function niceName(name) {
        const stem = name.replace(/\.[^.]+$/, "").replace(/[_\s]+/g, " ").replace(/[^\p{L}\p{N}\p{M} ]+/gu, " ").trim();
        return stem.replace(/\b\w/g, c => c.toUpperCase());
    }

    async function fromFile(file) {
        if (!file) return;
        const label = niceName(file.name);
        if (file.size > 30 * 1024 * 1024) { status("That file is too large. Please use one under 30 MB."); return; }
        if (file.type === "image/svg+xml" || /\.svg$/i.test(file.name)) {
            const text = await file.text();
            state.source = { kind: "svg" };
            busy("Reading the SVG…", () => use(DWFS.traceStrokes(svgStrokes(text), "svg", label), label));
            return;
        }
        try {
            const bitmap = await createImageBitmap(file);
            fromBitmap(bitmap, label);
        } catch (err) {
            status("This file could not be opened as a picture.");
        }
    }

    function sample(name) {
        if (name === "horse" || name === "astronaut") {
            const img = new Image();
            img.onload = () => fromBitmap(img, name === "horse" ? "Horse" : "Astronaut");
            img.onerror = () => status("The sample could not be loaded.");
            img.src = `assets/${name === "horse" ? "horse.png" : "astronaut.jpg"}`;
            return;
        }
        if (name === "text") {
            $("words").value = "Hello\nWorld";
            writeText();
            return;
        }
        if (name === "heart") {
            state.source = { kind: "heart" };
            const pts = [];
            for (let i = 0; i < 2000; i++) {
                const t = 2 * Math.PI * i / 2000;
                pts.push([20 + 16 * Math.sin(t) ** 3, 20 - (13 * Math.cos(t) - 5 * Math.cos(2 * t) - 2 * Math.cos(3 * t) - Math.cos(4 * t))]);
            }
            busy("Drawing…", () => use(DWFS.traceStrokes([{ pts, closed: true }], "path", "Heart"), "Heart"));
            return;
        }
        if (name === "star") {
            const points = [];
            for (let i = 0; i < 10; i++) {
                const a = Math.PI / 2 + Math.PI * i / 5, r = i % 2 ? 38 : 90;
                points.push(`${(100 + r * Math.cos(a)).toFixed(2)},${(100 - r * Math.sin(a)).toFixed(2)}`);
            }
            const svg = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 200 200"><polygon points="${points.join(" ")}"/><circle cx="100" cy="100" r="96"/><circle cx="100" cy="100" r="20"/></svg>`;
            state.source = { kind: "svg" };
            busy("Reading the SVG…", () => use(DWFS.traceStrokes(svgStrokes(svg), "svg", "Star"), "Star"));
        }
    }

    function writeText() {
        const words = $("words").value;
        const stroke = $("stroke").value;
        state.source = { kind: "text" };
        busy("Writing…", () => {
            const data = renderText(words, stroke);
            use(data, data.title);
        });
    }

    function pathJson() {
        const d = state.data;
        const out = {
            width: Math.round(d.width * 100) / 100, height: Math.round(d.height * 100) / 100, closed: true,
            mode: d.mode, title: d.title, lift: d.lift,
            path: d.path.map(([x, y]) => [Math.round(x * 100) / 100, Math.round(y * 100) / 100]),
        };
        download(new Blob([JSON.stringify(out)], { type: "application/json" }), fileStem() + ".json");
    }

    let last = performance.now();
    function tick(now) {
        const dt = Math.min(0.1, (now - last) / 1000);
        last = now;
        if (state.model) {
            if (state.playing && !state.scrub) {
                state.time += dt * state.speed;
                const total = duration();
                if (state.time >= total) {
                    if (state.recording) {
                        state.time = total;
                        state.recording.stop();
                    } else {
                        state.time %= total;
                    }
                }
            }
            render();
            if (!state.scrub) $("timeline").value = Math.round(1000 * state.time / duration());
            if (state.recording) status(`Recording… ${Math.round(100 * state.time / duration())}%`);
        }
        requestAnimationFrame(tick);
    }

    $("file").addEventListener("change", e => fromFile(e.target.files[0]));
    const drop = $("drop");
    drop.addEventListener("dragover", e => { e.preventDefault(); drop.classList.add("over"); });
    drop.addEventListener("dragleave", () => drop.classList.remove("over"));
    drop.addEventListener("drop", e => {
        e.preventDefault();
        drop.classList.remove("over");
        fromFile(e.dataTransfer.files[0]);
    });
    $("mode").addEventListener("change", retrace);
    $("detail").addEventListener("change", retrace);
    $("write").addEventListener("click", writeText);
    $("samples").addEventListener("click", e => { if (e.target.dataset.sample) sample(e.target.dataset.sample); });
    $("play").addEventListener("click", () => { state.playing = !state.playing; refresh(); });
    $("prev").addEventListener("click", () => jump(-1));
    $("next").addEventListener("click", () => jump(1));
    $("slower").addEventListener("click", () => { state.speed = Math.max(0.125, state.speed / 2); refresh(); });
    $("faster").addEventListener("click", () => { state.speed = Math.min(16, state.speed * 2); refresh(); });
    $("lens").addEventListener("click", () => { state.lens = !state.lens; refresh(); });
    $("follow").addEventListener("click", () => { state.lens = true; state.follow++; refresh(); });
    $("theme").addEventListener("click", () => { state.theme = state.theme === "light" ? "dark" : "light"; refresh(); });
    $("style").addEventListener("click", () => restyle(state.style === "axes" ? "classic" : "axes"));
    $("png").addEventListener("click", () => canvas.toBlob(b => download(b, fileStem() + ".png")));
    $("record").addEventListener("click", record);
    $("json").addEventListener("click", pathJson);
    const timeline = $("timeline");
    timeline.addEventListener("input", () => {
        if (!state.model) return;
        state.scrub = true;
        state.time = Number(timeline.value) / 1000 * duration();
    });
    timeline.addEventListener("change", () => { state.scrub = false; });
    window.addEventListener("resize", () => { if (state.model) fitCss(); });
    document.addEventListener("keydown", e => {
        if (!state.model || /^(INPUT|TEXTAREA|SELECT)$/.test(document.activeElement.tagName)) return;
        const keys = {
            " ": () => { state.playing = !state.playing; },
            ArrowRight: () => { state.playing = false; state.time = Math.min(duration(), state.time + STAGE / state.model.n * 8); },
            ArrowLeft: () => { state.playing = false; state.time = Math.max(0, state.time - STAGE / state.model.n * 8); },
            ArrowUp: () => { state.speed = Math.min(16, state.speed * 2); },
            ArrowDown: () => { state.speed = Math.max(0.125, state.speed / 2); },
            ".": () => jump(1),
            ",": () => jump(-1),
            "0": () => { state.time = 0; state.playing = true; },
            m: () => { state.lens = !state.lens; },
            f: () => { state.lens = true; state.follow++; },
            "]": () => { state.zoom = Math.min(200, state.zoom * 1.5); },
            "[": () => { state.zoom = Math.max(0.05, state.zoom / 1.5); },
            t: () => { state.theme = state.theme === "light" ? "dark" : "light"; },
            s: () => restyle(state.style === "axes" ? "classic" : "axes"),
        };
        const act = keys[e.key];
        if (!act || state.recording) return;
        e.preventDefault();
        act();
        refresh();
    });
    canvas.addEventListener("wheel", e => {
        if (!state.model || !state.lens || !state.lensRect) return;
        const x = e.offsetX * canvas.width / canvas.clientWidth, y = e.offsetY * canvas.height / canvas.clientHeight;
        const [lx, ly, side] = state.lensRect;
        if (x < lx || y < ly || x > lx + side || y > ly + side) return;
        e.preventDefault();
        state.zoom = Math.min(200, Math.max(0.05, state.zoom * (e.deltaY < 0 ? 1.25 : 0.8)));
    }, { passive: false });

    refresh();
    requestAnimationFrame(tick);
    const params = new URLSearchParams(location.search);
    if (params.get("text")) {
        $("words").value = params.get("text");
        if (params.get("stroke") === "outline") $("stroke").value = "outline";
        writeText();
    } else {
        sample("horse");
    }
})();
