import os
import re
import json
import shutil
import subprocess
import numpy as np
import matplotlib.pyplot as plt
from matplotlib.animation import FuncAnimation
from matplotlib.colors import to_rgb
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
    "latex": True,
    "fps": 30,
    "dpi": 120,
}
THEMES = {
    "light": {"bg": "#f4f5f5", "ink": "#141414", "circle": (0, 0, 0, 0.2), "arm": (0, 0, 0, 0.45),
              "guide": (0, 0, 0, 0.35), "accent": "#2e8b72", "text": "#3b4252", "width": 1.1},
    "dark": {"bg": "#000000", "ink": "cyan", "circle": (1, 1, 1, 0.16), "arm": (1, 1, 1, 0.55),
             "guide": (1, 1, 1, 0.35), "accent": "#5ad1b0", "text": "#d8dee9", "width": 1.3},
}
THETA = np.linspace(0, 2 * np.pi, 49)
FORMULAS = {
    "axes": [r"x_N(t) = a_0 + \sum_{k=1}^{N} \left(a_k \cos kt + b_k \sin kt\right)",
             r"y_N(t) = c_0 + \sum_{k=1}^{N} \left(c_k \cos kt + d_k \sin kt\right)"],
    "classic": [r"z_N(t) = \sum_{k=-N}^{N} c_k\, e^{ikt}"],
}


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
    xs = centers.real[:, None] + radii[:, None] * np.cos(THETA)
    ys = centers.imag[:, None] + radii[:, None] * np.sin(THETA)
    gap = np.full((len(centers), 1), np.nan)
    return np.hstack([xs, gap]).ravel(), np.hstack([ys, gap]).ravel()


def tinted(source, w, h, color, alpha):
    img = Image.open(source).convert("L").resize((max(1, int(round(w))), max(1, int(round(h)))))
    dark = 1.0 - np.asarray(img, dtype=float) / 255.0
    rgba = np.zeros(dark.shape + (4,))
    rgba[..., :3] = to_rgb(color)
    rgba[..., 3] = dark ** 0.8 * alpha
    return rgba


def even_inches(inches, dpi):
    return (2 * np.ceil(inches * dpi / 2) + 0.01) / dpi


def setup(data, cfg):
    if cfg.style not in FORMULAS:
        raise ValueError("style must be axes or classic")
    if cfg.theme not in THEMES:
        raise ValueError("theme must be light or dark")
    z, w, h, source, lift = load(data)
    theme = THEMES[cfg.theme]
    n = len(z)
    c, k = spectrum(z)
    levels = stages(n // 2, cfg)
    curves = [synth(c, k, N, n) for N in levels]
    curves = [np.append(cv, cv[:1]) for cv in curves]
    if not cfg.lift:
        lift = np.zeros(n, dtype=bool)
    inked = []
    for cv in curves:
        ink = cv.copy()
        ink[:-1][lift] = np.nan
        inked.append(ink)
    errors = [error(c, k, N) for N in levels]
    chain_list = chains(z, cfg.style)
    for ch in chain_list:
        prepare(ch, levels, n, cfg.draw_circles)

    image = cfg.image or source
    ghost = bool(cfg.ghost and image and os.path.exists(image))
    x0, x1, y0, y1 = place(chain_list, z, w, h, ghost, cfg.style)

    scale = min(7.5 / (x1 - x0), 8.0 / (y1 - y0))
    main_w, main_h = (x1 - x0) * scale, (y1 - y0) * scale
    top, bottom = 1.7, 1.4
    fig_w = even_inches(max(main_w + 0.6, 6.4), cfg.dpi)
    fig_h = even_inches(main_h + top + bottom, cfg.dpi)

    fig = plt.figure(figsize=(fig_w, fig_h), facecolor=theme["bg"])
    ax = fig.add_axes([(fig_w - main_w) / 2 / fig_w, bottom / fig_h, main_w / fig_w, main_h / fig_h])
    head = fig.add_axes([0, (bottom + main_h) / fig_h, 1, top / fig_h])
    foot = fig.add_axes([0, 0, 1, bottom / fig_h])
    for a in (ax, head, foot):
        a.set_facecolor(theme["bg"])
        a.axis("off")
    ax.set_xlim(x0, x1)
    ax.set_ylim(y0, y1)
    ax.set_aspect("equal")

    if ghost:
        ax.imshow(tinted(image, w, h, theme["accent"], cfg.ghost_alpha), extent=(-w / 2, w / 2, -h / 2, h / 2),
                  zorder=0, interpolation="bilinear")
        ax.add_patch(Rectangle((-w / 2, -h / 2), w, h, fill=False, ec=theme["accent"], lw=0.8, alpha=0.6, zorder=0))

    tex = bool(cfg.latex) and latex_ready()
    for i, text in enumerate(FORMULAS[cfg.style]):
        head.text(0.04, 0.72 - 0.44 * i, (r"$\displaystyle %s$" if tex else "$%s$") % text, usetex=tex,
                  math_fontfamily="cm", color=theme["text"], fontsize=14, va="center")

    label = cfg.label if cfg.label is not None else source and os.path.splitext(os.path.basename(source))[0]
    label = re.sub(r"[\W_]+", " ", label or "").strip().title()
    if label:
        foot.text(0.04, 0.55, r"$\mathrm{%s}$" % label.replace(" ", r"\ "), math_fontfamily="cm",
                  color=theme["text"], fontsize=17, va="center")
    foot.text(0.5, 0.6, r"$N \;=$", math_fontfamily="cm", color=theme["ink"], fontsize=32, ha="right", va="center")
    n_text = foot.text(0.515, 0.6, "", math_fontfamily="cm", color=theme["accent"], fontsize=32, ha="left", va="center")
    e_text = foot.text(0.5, 0.2, "", math_fontfamily="cm", color=theme["text"], fontsize=13, ha="center", va="center")

    trace, = ax.plot([], [], color=theme["ink"], lw=theme["width"], zorder=3)
    pen, = ax.plot([], [], "o", color=theme["ink"], ms=4, zorder=4)
    parts = []
    for ch in chain_list:
        circ, = ax.plot([], [], color=theme["circle"], lw=0.6, zorder=2)
        arm, = ax.plot([], [], color=theme["arm"], lw=0.7, zorder=2)
        tip, = ax.plot([], [], "o", color=theme["arm"], ms=2.5, zorder=2)
        guide, = ax.plot([], [], color=theme["guide"], lw=0.8, ls=(0, (4, 4)), zorder=1)
        parts.append((ch, circ, arm, tip, guide))

    frames = []
    for s in range(len(levels)):
        count = cfg.frames if s == len(levels) - 1 else cfg.stage_frames
        frames += [(s, int(round((q + 1) * n / count))) for q in range(count)]
    frames += [(len(levels) - 1, n)] * (cfg.hold if cfg.grow else 0)

    def step(i):
        s, j = frames[i]
        t = 2 * np.pi * j / n
        curve, ink = curves[s], inked[s]
        trace.set_data(ink.real[:j + 1], ink.imag[:j + 1])
        point = curve[j]
        pen.set_data([point.real], [point.imag])
        pen.set_markerfacecolor("none" if lift[j % n] else theme["ink"])
        for ch, circ, arm, tip, guide in parts:
            amps, ks = ch["draw"][s]
            o = ch["origin"]
            centers = o + np.concatenate([[0], np.cumsum(amps * np.exp(1j * ks * t))])
            end = o + ch["tips"][s][j % n]
            circ.set_data(*rings(centers[:-1], np.abs(amps)))
            arm.set_data(np.append(centers.real, end.real), np.append(centers.imag, end.imag))
            tip.set_data([end.real], [end.imag])
            if cfg.style == "axes":
                guide.set_data([end.real, point.real], [end.imag, point.imag])
        n_text.set_text(r"$%d$" % levels[s])
        e_text.set_text(r"$\mathrm{approximation\ error} = %.2f\%%$" % errors[s])
        return [trace, pen, n_text, e_text] + [a for p in parts for a in p[1:]]

    return fig, step, frames


def animate(data, **options):
    cfg = settings(DEFAULTS, options)
    fig, step, frames = setup(data, cfg)
    return FuncAnimation(fig, step, frames=len(frames), init_func=lambda: step(0),
                         interval=1000 / cfg.fps, blit=True)


def draw(data, save=None, progress=False, **options):
    cfg = settings(DEFAULTS, options)
    fig, step, frames = setup(data, cfg)

    if save and str(save).lower().endswith((".png", ".jpg", ".jpeg")):
        step(len(frames) - 1)
        fig.savefig(save, dpi=cfg.dpi, facecolor=fig.get_facecolor())
        plt.close(fig)
        return save

    anim = FuncAnimation(fig, step, frames=len(frames), init_func=lambda: step(0),
                         interval=1000 / cfg.fps, blit=True)
    if save:
        mark = max(1, len(frames) // 20)

        def report(i, total):
            if progress and i % mark == 0:
                print("frame", i, "of", total, flush=True)

        anim.save(save, fps=cfg.fps, dpi=cfg.dpi, savefig_kwargs={"facecolor": fig.get_facecolor()},
                  progress_callback=report)
        plt.close(fig)
        return save

    state = {"paused": False}

    def key(event):
        if event.key == " ":
            (anim.resume if state["paused"] else anim.pause)()
            state["paused"] = not state["paused"]

    fig.canvas.mpl_connect("key_press_event", key)
    plt.show()
    return None
