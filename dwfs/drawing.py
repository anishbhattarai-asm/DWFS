import os
import re
import json
import shutil
import tempfile
import subprocess
from types import SimpleNamespace
import numpy as np
import matplotlib.pyplot as plt
from matplotlib.animation import FuncAnimation
from matplotlib.collections import LineCollection, PolyCollection
from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.colors import to_rgb
from matplotlib.figure import Figure
from matplotlib.patches import Rectangle
from PIL import Image

from .options import settings

DEFAULTS = {
    "style": "axes",
    "theme": "light",
    "grow": True,
    "linear": 8,
    "growth": 1.5,
    "stage_frames": 90,
    "frames": 600,
    "hold": 60,
    "draw_circles": 140,
    "ghost": True,
    "ghost_alpha": 0.3,
    "image": None,
    "label": None,
    "lift": True,
    "lens": True,
    "follow": "auto",
    "zoom": 1.0,
    "latex": True,
    "fps": 30,
    "dpi": 120,
}
THEMES = {
    "light": {"bg": "#f4f5f5", "ink": "#141414", "circle": 0.34, "chains": ("#2f6aa8", "#b5473a"),
              "accent": "#2e8b72", "text": "#3b4252", "width": 1.1, "panel": "#fcfdfd",
              "button": "#e4e9e9", "hover": "#d0dad9"},
    "dark": {"bg": "#05070a", "ink": "#5fe3f0", "circle": 0.36, "chains": ("#7fb0ff", "#ff8e7d"),
             "accent": "#5ad1b0", "text": "#d8dee9", "width": 1.3, "panel": "#0d1117",
             "button": "#1b2129", "hover": "#2b3440"},
}
UNIT = np.exp(1j * np.linspace(0, 2 * np.pi, 49))
FORMULAS = {
    "axes": [r"x_N(t) = a_0 + \sum_{k=1}^{N} \left(a_k \cos kt + b_k \sin kt\right)",
             r"y_N(t) = c_0 + \sum_{k=1}^{N} \left(c_k \cos kt + d_k \sin kt\right)"],
    "classic": [r"z_N(t) = \sum_{k=-N}^{N} c_k\, e^{ikt}"],
}
TARGETS = {"axes": ["x", "y", "pen"], "classic": ["pen"]}
TARGET_NAMES = {"x": "x chain", "y": "y chain", "pen": "pen"}


def load(data):
    if not isinstance(data, dict):
        with open(data) as f:
            data = json.load(f)
    path = np.array(data["path"], dtype=float)
    w = float(data.get("width", path[:, 0].max()))
    h = float(data.get("height", path[:, 1].max()))
    z = (path[:, 0] - w / 2.0) - 1j * (path[:, 1] - h / 2.0)
    lift = np.zeros(len(z), dtype=bool)
    for a, b in data.get("lift", []):
        lift[a:b + 1] = True
    return z, w, h, data.get("source"), lift


def latex_ready():
    if not shutil.which("latex"):
        return False
    try:
        found = subprocess.run(["kpsewhich", "type1ec.sty"], capture_output=True, text=True, timeout=15).stdout
    except (OSError, subprocess.TimeoutExpired):
        return False
    return bool(found.strip())


def stages(nmax, cfg):
    if not cfg.grow:
        return [nmax]
    out = list(range(1, min(cfg.linear, nmax) + 1))
    v = float(out[-1])
    while out[-1] < nmax:
        v *= cfg.growth
        out.append(min(nmax, max(out[-1] + 1, int(round(v)))))
    return out


def spectrum(z):
    n = len(z)
    c = np.fft.fft(z) / n
    k = np.fft.fftfreq(n, d=1.0 / n).round().astype(int)
    return c, k


def error(c, k, N):
    p = np.abs(c) ** 2
    total = p[k != 0].sum()
    return 100.0 * np.sqrt(p[np.abs(k) > N].sum() / total) if total > 0 else 0.0


def synth(amps, ks, N, n):
    sel = np.abs(ks) <= N
    spec = np.zeros(n, dtype=complex)
    np.add.at(spec, ks[sel] % n, amps[sel])
    return np.fft.ifft(spec) * n


def chains(z, style):
    n = len(z)
    if style == "classic":
        c, k = spectrum(z)
        keep = k != 0
        amps, ks = c[keep], k[keep]
        o = np.argsort(-np.abs(amps), kind="stable")
        return [{"base": c[0], "amps": amps[o], "ks": ks[o]}]
    out = []
    ks = np.arange(1, n // 2 + 1)
    for part, rot in ((z.real, 1.0), (z.imag, 1j)):
        X = np.fft.fft(part) / n
        amps = 2.0 * X[ks] * rot
        if n % 2 == 0:
            amps[-1] /= 2.0
        o = np.argsort(-np.abs(amps), kind="stable")
        out.append({"base": X[0].real * rot, "amps": amps[o], "ks": ks[o]})
    return out


def prepare(chain, levels, n, limit):
    t = 2 * np.pi * np.arange(96) / 96
    chain["draw"], chain["tips"] = [], []
    lows, highs = [], []
    for N in levels:
        sel = np.abs(chain["ks"]) <= N
        amps, ks = chain["amps"][sel][:limit], chain["ks"][sel][:limit]
        tips = synth(chain["amps"], chain["ks"], N, n)
        chain["draw"].append((amps, ks))
        chain["tips"].append(tips)
        cum = np.vstack([np.zeros(len(t)), np.cumsum(amps[:, None] * np.exp(1j * ks[:, None] * t), axis=0)])
        r = np.abs(amps)[:, None]
        for part in (np.real, np.imag):
            lows.append(np.concatenate([(part(cum[:-1]) - r).min(axis=0, initial=0), part(tips)]))
            highs.append(np.concatenate([(part(cum[:-1]) + r).max(axis=0, initial=0), part(tips)]))
    chain["lo"] = np.array([np.percentile(np.concatenate(lows[i::2]), 3) for i in (0, 1)])
    chain["hi"] = np.array([np.percentile(np.concatenate(highs[i::2]), 97) for i in (0, 1)])


def place(chain_list, curve, w, h, ghost, style):
    x0, x1 = curve.real.min(), curve.real.max()
    y0, y1 = curve.imag.min(), curve.imag.max()
    if ghost:
        x0, x1, y0, y1 = min(x0, -w / 2), max(x1, w / 2), min(y0, -h / 2), max(y1, h / 2)
    size = max(x1 - x0, y1 - y0)
    gap = 0.08 * size
    boxes = [(x0, x1, y0, y1)]
    if style == "classic":
        ch = chain_list[0]
        ch["origin"] = ch["base"]
    else:
        cx, cy = chain_list
        cx["origin"] = cx["base"] + 1j * (y1 + gap - cx["lo"][1])
        cy["origin"] = cy["base"] + (x0 - gap - cy["hi"][0])
    for ch in chain_list:
        o = ch["origin"]
        boxes.append((o.real + ch["lo"][0], o.real + ch["hi"][0], o.imag + ch["lo"][1], o.imag + ch["hi"][1]))
    b = np.array(boxes)
    pad = 0.04 * size
    return b[:, 0].min() - pad, b[:, 1].max() + pad, b[:, 2].min() - pad, b[:, 3].max() + pad


def rings(centers, radii):
    pts = centers[:, None] + radii[:, None] * UNIT[None, :]
    return np.stack([pts.real, pts.imag], axis=-1)


def heads(centers, size):
    d = np.diff(centers)
    length = np.abs(d)
    keep = length > 0
    if not keep.any():
        return np.zeros((0, 3, 2))
    d, tip, length = d[keep], centers[1:][keep], length[keep]
    u = d / length
    h = np.minimum(0.3 * length, size)
    base = tip - h * u
    side = 0.32 * h * 1j * u
    tri = np.stack([tip, base + side, base - side], axis=1)
    return np.stack([tri.real, tri.imag], axis=-1)


def tinted(source, w, h, color, alpha):
    img = Image.open(source).convert("L").resize((max(1, int(round(w))), max(1, int(round(h)))))
    dark = 1.0 - np.asarray(img, dtype=float) / 255.0
    rgba = np.zeros(dark.shape + (4,))
    rgba[..., :3] = to_rgb(color)
    rgba[..., 3] = dark ** 0.8 * alpha
    return rgba


def even_inches(inches, dpi):
    return (2 * np.ceil(inches * dpi / 2) + 0.01) / dpi


def model(data, cfg):
    if cfg.style not in FORMULAS:
        raise ValueError("style must be axes or classic")
    if cfg.theme not in THEMES:
        raise ValueError("theme must be light or dark")
    if cfg.follow not in ("auto", "x", "y", "pen"):
        raise ValueError("follow must be auto, x, y or pen")
    z, w, h, source, lift = load(data)
    n = len(z)
    c, k = spectrum(z)
    levels = stages(n // 2, cfg)
    curves = [np.append(cv, cv[:1]) for cv in (synth(c, k, N, n) for N in levels)]
    if not cfg.lift:
        lift = np.zeros(n, dtype=bool)
    inked = []
    for cv in curves:
        ink = cv.copy()
        ink[:-1][lift] = np.nan
        inked.append(ink)
    chain_list = chains(z, cfg.style)
    for ch in chain_list:
        prepare(ch, levels, n, cfg.draw_circles)
    image = cfg.image or source
    ghost = bool(cfg.ghost and image and os.path.exists(image))
    box = place(chain_list, z, w, h, ghost, cfg.style)

    frames = []
    for s in range(len(levels)):
        count = cfg.frames if s == len(levels) - 1 else cfg.stage_frames
        frames += [(s, int(round((q + 1) * n / count))) for q in range(count)]
    frames += [(len(levels) - 1, n)] * (cfg.hold if cfg.grow else 0)

    return SimpleNamespace(z=z, w=w, h=h, source=source, lift=lift, n=n, levels=levels, curves=curves,
                           inked=inked, errors=[error(c, k, N) for N in levels], chains=chain_list,
                           image=image, ghost=ghost, box=box, frames=frames,
                           size=max(np.ptp(z.real), np.ptp(z.imag), 1e-9))


def layout(m, cfg, controls=0.0):
    x0, x1, y0, y1 = m.box
    scale = min(7.5 / (x1 - x0), 8.0 / (y1 - y0))
    main_w, main_h = (x1 - x0) * scale, (y1 - y0) * scale
    top, bottom = 1.7, 1.4 + controls
    fig_w = even_inches(max(main_w + 0.6, 6.4), cfg.dpi)
    fig_h = even_inches(main_h + top + bottom, cfg.dpi)
    return SimpleNamespace(main_w=main_w, main_h=main_h, top=top, bottom=bottom, fig_w=fig_w, fig_h=fig_h,
                           controls=controls)


def make_layer(ax, m, theme, guides):
    trace, = ax.plot([], [], color=theme["ink"], lw=theme["width"], zorder=3, solid_capstyle="round")
    pen, = ax.plot([], [], "o", color=theme["ink"], ms=4.5, mew=1.2, zorder=6)
    parts = []
    for ci, ch in enumerate(m.chains):
        color = to_rgb(theme["chains"][ci])
        count = max(1, max(len(a) for a, _ in ch["draw"]))
        fade = np.linspace(1.0, 0.3, count)
        rgba = np.zeros((count, 4))
        rgba[:, :3] = color
        rgba[:, 3] = theme["circle"] * fade
        circ = LineCollection([], colors=rgba, linewidths=0.45 + 0.55 * fade, zorder=2)
        ax.add_collection(circ, autolim=False)
        arm, = ax.plot([], [], color=color, lw=0.9, alpha=0.9, zorder=4, solid_capstyle="round")
        head = PolyCollection([], facecolors=[color], edgecolors="none", alpha=0.9, zorder=4)
        ax.add_collection(head, autolim=False)
        tip, = ax.plot([], [], "o", color=color, ms=3.2, zorder=5)
        guide = None
        if guides:
            guide, = ax.plot([], [], color=color, alpha=0.5, lw=0.9, ls=(0, (4, 4)), zorder=1)
        parts.append({"circ": circ, "arm": arm, "head": head, "tip": tip, "guide": guide})
    artists = [trace, pen] + [a for p in parts for a in (p["circ"], p["arm"], p["head"], p["tip"], p["guide"]) if a]
    return {"trace": trace, "pen": pen, "parts": parts, "artists": artists}


def build(m, cfg, dpi=None, controls=0.0, offscreen=False):
    theme = THEMES[cfg.theme]
    g = layout(m, cfg, controls)
    x0, x1, y0, y1 = m.box
    if offscreen:
        fig = Figure(figsize=(g.fig_w, g.fig_h), facecolor=theme["bg"], dpi=cfg.dpi)
        FigureCanvasAgg(fig)
    else:
        fig = plt.figure(figsize=(g.fig_w, g.fig_h), facecolor=theme["bg"], dpi=dpi)
    ax = fig.add_axes([(g.fig_w - g.main_w) / 2 / g.fig_w, g.bottom / g.fig_h, g.main_w / g.fig_w, g.main_h / g.fig_h])
    head = fig.add_axes([0, (g.bottom + g.main_h) / g.fig_h, 1, g.top / g.fig_h])
    foot = fig.add_axes([0, controls / g.fig_h, 1, 1.4 / g.fig_h])
    for a in (ax, head, foot):
        a.set_facecolor(theme["bg"])
        a.axis("off")
    ax.set_xlim(x0, x1)
    ax.set_ylim(y0, y1)
    ax.set_aspect("equal")

    if m.ghost:
        ax.imshow(tinted(m.image, m.w, m.h, theme["accent"], cfg.ghost_alpha),
                  extent=(-m.w / 2, m.w / 2, -m.h / 2, m.h / 2), zorder=0, interpolation="bilinear")
        ax.add_patch(Rectangle((-m.w / 2, -m.h / 2), m.w, m.h, fill=False, ec=theme["accent"], lw=0.8,
                               alpha=0.6, zorder=0))

    tex = bool(cfg.latex) and latex_ready()
    for i, text in enumerate(FORMULAS[cfg.style]):
        head.text(0.04, 0.72 - 0.44 * i, (r"$\displaystyle %s$" if tex else "$%s$") % text, usetex=tex,
                  math_fontfamily="cm", color=theme["text"], fontsize=14, va="center")

    label = cfg.label if cfg.label is not None else m.source and os.path.splitext(os.path.basename(m.source))[0]
    label = re.sub(r"[\W_]+", " ", label or "").strip().title()
    n_label = foot.text(0.5, 0.6, r"$N \;=$", math_fontfamily="cm", color=theme["ink"], fontsize=32,
                        ha="right", va="center")
    n_text = foot.text(0.515, 0.6, "", math_fontfamily="cm", color=theme["accent"], fontsize=32,
                       ha="left", va="center")
    e_text = foot.text(0.5, 0.2, "", math_fontfamily="cm", color=theme["text"], fontsize=13,
                       ha="center", va="center")
    status = foot.text(0.97, 0.2, "", color=theme["text"], fontsize=9, ha="right", va="center", alpha=0.85)
    if label:
        caption = foot.text(0.04, 0.55, r"$\mathrm{%s}$" % label.replace(" ", r"\ "), math_fontfamily="cm",
                            color=theme["text"], fontsize=17, va="center")
        renderer = fig.canvas.get_renderer()
        limit = n_label.get_window_extent(renderer).x0 - 14 * fig.dpi / 72
        while caption.get_window_extent(renderer).x1 > limit and caption.get_fontsize() > 7:
            caption.set_fontsize(caption.get_fontsize() * 0.9)

    main = make_layer(ax, m, theme, cfg.style == "axes")
    frame_line, = ax.plot([], [], color=theme["accent"], lw=1.0, ls=(0, (3, 3)), zorder=7)

    side = min(2.4, 0.42 * g.main_w, 0.42 * g.main_h)
    left = (g.fig_w - g.main_w) / 2 + 0.12
    lens_ax = fig.add_axes([left / g.fig_w, (g.bottom + g.main_h - 0.12 - side) / g.fig_h,
                            side / g.fig_w, side / g.fig_h])
    lens_ax.set_zorder(5)
    lens_ax.set_facecolor(theme["panel"])
    lens_ax.set_xticks([])
    lens_ax.set_yticks([])
    for spine in lens_ax.spines.values():
        spine.set_color(theme["accent"])
        spine.set_linewidth(1.2)
    lens = make_layer(lens_ax, m, theme, cfg.style == "axes")
    lens_text = lens_ax.text(0.04, 0.95, "", transform=lens_ax.transAxes, color=theme["text"], fontsize=8,
                             ha="left", va="top", alpha=0.9)

    targets = TARGETS[cfg.style]
    follow = targets[0] if cfg.follow == "auto" or cfg.follow not in targets else cfg.follow
    state = {"on": bool(cfg.lens), "target": targets.index(follow), "zoom": float(cfg.zoom)}
    panel = [lens_ax.patch] + list(lens_ax.spines.values())
    lens_artists = panel + lens["artists"] + [lens_text, frame_line]
    head_size = 0.016 * m.size

    def set_lens(on):
        state["on"] = bool(on)
        lens_ax.set_visible(state["on"])
        for a in lens_artists:
            a.set_visible(state["on"])

    def lens_half():
        return m.size / 12.0 / state["zoom"]

    def step(i):
        s, j = m.frames[i]
        t = 2 * np.pi * j / m.n
        point = m.curves[s][j]
        ink = m.inked[s]
        layers = [main, lens] if state["on"] else [main]
        ends = []
        for ci, ch in enumerate(m.chains):
            amps, ks = ch["draw"][s]
            o = ch["origin"]
            centers = o + np.concatenate([[0], np.cumsum(amps * np.exp(1j * ks * t))])
            end = o + ch["tips"][s][j % m.n]
            ends.append(end)
            segs = rings(centers[:-1], np.abs(amps))
            tri = heads(centers, head_size)
            arm = np.append(centers, end)
            for layer in layers:
                part = layer["parts"][ci]
                part["circ"].set_segments(segs)
                part["head"].set_verts(tri)
                part["arm"].set_data(arm.real, arm.imag)
                part["tip"].set_data([end.real], [end.imag])
                if part["guide"] is not None:
                    part["guide"].set_data([end.real, point.real], [end.imag, point.imag])
        for layer in layers:
            layer["trace"].set_data(ink.real[:j + 1], ink.imag[:j + 1])
            layer["pen"].set_data([point.real], [point.imag])
            layer["pen"].set_markerfacecolor("none" if m.lift[j % m.n] else theme["ink"])
        if state["on"]:
            name = targets[state["target"]]
            center = point if name == "pen" else ends[0 if name == "x" else 1]
            half = lens_half()
            lens_ax.set_xlim(center.real - half, center.real + half)
            lens_ax.set_ylim(center.imag - half, center.imag + half)
            box = center + half * np.array([-1 - 1j, 1 - 1j, 1 + 1j, -1 + 1j, -1 - 1j])
            frame_line.set_data(box.real, box.imag)
            lens_text.set_text("%s   ×%.1f" % (TARGET_NAMES[name], m.size / (2 * half)))
        n_text.set_text(r"$%d$" % m.levels[s])
        e_text.set_text(r"$\mathrm{approximation\ error} = %.2f\%%$" % m.errors[s])
        return animated

    animated = main["artists"] + [frame_line, n_text, e_text, status] + panel + lens["artists"] + [lens_text]
    set_lens(state["on"])
    return SimpleNamespace(fig=fig, ax=ax, foot=foot, lens_ax=lens_ax, step=step, frames=m.frames,
                           animated=animated, lens=state, targets=targets, set_lens=set_lens,
                           home=(x0, x1, y0, y1), theme=theme, status=status, layout=g, model=m, label=label)


def animate(data, **options):
    cfg = settings(DEFAULTS, options)
    scene = build(model(data, cfg), cfg)
    return FuncAnimation(scene.fig, scene.step, frames=len(scene.frames), init_func=lambda: scene.step(0),
                         interval=1000 / cfg.fps, blit=False)


def frames_of(scene, report=None):
    fig = scene.fig
    canvas = fig.canvas
    for a in scene.animated:
        a.set_animated(True)
    canvas.draw()
    background = canvas.copy_from_bbox(fig.bbox)
    total = len(scene.frames)
    for i in range(total):
        scene.step(i)
        canvas.restore_region(background)
        for a in scene.animated:
            if a.get_visible():
                fig.draw_artist(a)
        if report:
            report(i, total)
        yield np.asarray(canvas.buffer_rgba())


def temp_path(suffix):
    handle, path = tempfile.mkstemp(prefix="dwfs_", suffix=suffix)
    os.close(handle)
    return path


def encode(scene, cfg, out, ffmpeg, report):
    gif = out.lower().endswith(".gif")
    target = temp_path(".mp4") if gif else out
    proc = None
    try:
        for frame in frames_of(scene, report):
            if proc is None:
                h, w = frame.shape[:2]
                proc = subprocess.Popen(
                    [ffmpeg, "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgba",
                     "-s", "%dx%d" % (w, h), "-r", str(cfg.fps), "-i", "-",
                     "-vf", "pad=ceil(iw/2)*2:ceil(ih/2)*2", "-c:v", "libx264", "-preset", "fast",
                     "-crf", "12" if gif else "18", "-pix_fmt", "yuv420p", "-movflags", "+faststart", target],
                    stdin=subprocess.PIPE)
            proc.stdin.write(frame.tobytes())
        proc.stdin.close()
        if proc.wait() != 0:
            raise RuntimeError("ffmpeg could not encode the video")
        if gif:
            rate = min(cfg.fps, 20)
            palette = temp_path(".png")
            try:
                subprocess.run([ffmpeg, "-y", "-loglevel", "error", "-i", target, "-vf",
                                "fps=%d,palettegen=max_colors=200:stats_mode=full" % rate, palette], check=True)
                subprocess.run([ffmpeg, "-y", "-loglevel", "error", "-i", target, "-i", palette, "-lavfi",
                                "fps=%d[x];[x][1:v]paletteuse=dither=none:diff_mode=rectangle" % rate, out],
                               check=True)
            finally:
                os.remove(palette)
    finally:
        if proc is not None and proc.poll() is None:
            proc.kill()
        if gif and os.path.exists(target):
            os.remove(target)
    return out


def draw(data, save=None, progress=False, **options):
    cfg = settings(DEFAULTS, options)
    m = model(data, cfg)
    if not save:
        from .player import play
        play(data, m, cfg)
        return None

    save = os.fspath(save)
    scene = build(m, cfg, offscreen=True)
    fig = scene.fig
    if save.lower().endswith((".png", ".jpg", ".jpeg")):
        scene.step(len(scene.frames) - 1)
        fig.savefig(save, dpi=cfg.dpi, facecolor=fig.get_facecolor())
        return save

    mark = max(1, len(scene.frames) // 20)

    def report(i, total):
        if progress and i % mark == 0:
            print("frame", i, "of", total, flush=True)

    ffmpeg = shutil.which(plt.rcParams["animation.ffmpeg_path"])
    if ffmpeg:
        return encode(scene, cfg, save, ffmpeg, report)
    if not save.lower().endswith(".gif"):
        raise ValueError("saving %s needs FFmpeg on your PATH, or save a .gif instead" % save)
    anim = FuncAnimation(fig, scene.step, frames=len(scene.frames), init_func=lambda: scene.step(0),
                         interval=1000 / cfg.fps, blit=False)
    anim.save(save, writer="pillow", fps=min(cfg.fps, 20), dpi=cfg.dpi,
              savefig_kwargs={"facecolor": fig.get_facecolor()}, progress_callback=report)
    return save
