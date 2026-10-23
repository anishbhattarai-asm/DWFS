import os
import re
import sys
import json
import time
import shutil
import tempfile
import threading
import subprocess
import matplotlib.pyplot as plt
from matplotlib.transforms import Bbox
from matplotlib.widgets import Button

from .drawing import build, layout

BAND = 0.62
KEYS = {
    "keymap.fullscreen": ["ctrl+f"],
    "keymap.home": ["home"],
    "keymap.back": ["backspace"],
    "keymap.forward": [],
}
HELP = "\n".join([
    "space          pause or play",
    "left, right    step one frame",
    "up, down       faster or slower",
    "0              start over",
    "scroll         zoom where the mouse is",
    "r              reset the zoom",
    "m              show or hide the lens",
    "f              change what the lens follows",
    "[  ]           zoom the lens out or in",
    "h              hide this help",
])
KINDS = {".mp4": "MP4 video", ".gif": "GIF animation", ".png": "PNG image"}


def screen_dpi(width, height):
    base = plt.rcParams["figure.dpi"]
    probe = plt.figure()
    try:
        window = probe.canvas.manager.window
        ratio = float(window.tk.call("tk", "scaling")) / (96 / 72)
        wide, tall = window.winfo_screenwidth(), window.winfo_screenheight()
    except Exception:
        return None
    finally:
        plt.close(probe)
    fit = min(1.0, 0.8 * tall / (height * base * ratio), 0.94 * wide / (width * base * ratio))
    return base * fit


def ask_path(fig, ext, default):
    try:
        import tkinter
        from tkinter import filedialog
        window = fig.canvas.manager.window
        if not isinstance(window, tkinter.Misc):
            return default
        path = filedialog.asksaveasfilename(parent=window, initialdir=os.path.dirname(default),
                                            initialfile=os.path.basename(default), defaultextension=ext,
                                            filetypes=[(KINDS[ext], "*" + ext)])
    except Exception:
        return default
    return path or None


def free_name(stem, ext):
    path = os.path.abspath(stem + ext)
    count = 2
    while os.path.exists(path):
        path = os.path.abspath("%s_%d%s" % (stem, count, ext))
        count += 1
    return path


class Player:
    def __init__(self, scene, data, cfg):
        self.s, self.data, self.cfg = scene, data, cfg
        self.fig = scene.fig
        self.total = len(scene.frames)
        self.pos, self.speed, self.playing = 0.0, 1.0, True
        self.dragging = False
        self.regions, self.backgrounds = [], []
        self.job = None
        self.note_text, self.note_until = "", 0.0
        theme = scene.theme
        fig = self.fig
        tall = scene.layout.fig_h

        self.timeline = fig.add_axes([0.04, (BAND - 0.2) / tall, 0.92, 0.14 / tall])
        self.timeline.set_xlim(0, 1)
        self.timeline.set_ylim(0, 1)
        self.timeline.axis("off")
        self.timeline.plot([0, 1], [0.5, 0.5], color=theme["text"], alpha=0.25, lw=3, solid_capstyle="round")
        starts = [i for i in range(1, self.total) if scene.frames[i][0] != scene.frames[i - 1][0]]
        self.timeline.plot([i / self.total for i in starts], [0.5] * len(starts), "|", color=theme["text"],
                           alpha=0.35, ms=6)
        self.bar, = self.timeline.plot([], [], color=theme["accent"], lw=3, solid_capstyle="round")
        self.knob, = self.timeline.plot([], [], "o", color=theme["accent"], ms=8)

        actions = [("Pause", self.toggle), ("Restart", self.restart), ("Slower", self.slower),
                   ("Faster", self.faster), ("Lens", self.toggle_lens), ("Follow", self.follow),
                   ("Reset", self.reset_view), ("MP4", lambda e: self.save(".mp4")),
                   ("GIF", lambda e: self.save(".gif")), ("PNG", lambda e: self.save(".png")),
                   ("Keys", self.toggle_help)]
        width = 0.92 / len(actions)
        self.buttons = {}
        for i, (name, action) in enumerate(actions):
            bax = fig.add_axes([0.04 + i * width + 0.003, 0.08 / tall, width - 0.006, 0.3 / tall])
            button = Button(bax, name, color=theme["button"], hovercolor=theme["hover"])
            button.label.set_color(theme["text"])
            button.label.set_fontsize(9)
            for spine in bax.spines.values():
                spine.set_visible(False)
            button.on_clicked(action)
            self.buttons[name] = button

        self.help = fig.text(0.5, 0.55, HELP, ha="center", va="center", ma="left", family="monospace", fontsize=10,
                             color=theme["text"], visible=False, zorder=20,
                             bbox={"boxstyle": "round,pad=0.8", "facecolor": theme["panel"],
                                   "edgecolor": theme["accent"], "alpha": 0.96})
        self.top_artists = scene.animated + [self.help]
        self.line_artists = [self.bar, self.knob]
        for a in self.top_artists + self.line_artists:
            a.set_animated(True)

        canvas = fig.canvas
        canvas.mpl_connect("draw_event", self.on_draw)
        canvas.mpl_connect("key_press_event", self.on_key)
        canvas.mpl_connect("scroll_event", self.on_scroll)
        canvas.mpl_connect("button_press_event", self.on_press)
        canvas.mpl_connect("motion_notify_event", self.on_motion)
        canvas.mpl_connect("button_release_event", self.on_release)
        try:
            canvas.manager.set_window_title("DWFS" + ("   " + scene.label if scene.label else ""))
        except Exception:
            pass
        self.s.step(0)
        self.timer = canvas.new_timer(interval=max(1, int(1000 / cfg.fps)))
        self.timer.add_callback(self.tick)
        self.timer.start()

    def on_draw(self, event):
        canvas = self.fig.canvas
        box = self.fig.bbox
        cut = box.y0 + box.height * BAND / self.s.layout.fig_h
        self.regions = [(Bbox.from_extents(box.x0, cut, box.x1, box.y1), self.top_artists),
                        (self.timeline.bbox.frozen(), self.line_artists)]
        self.backgrounds = [canvas.copy_from_bbox(region) for region, _ in self.regions]
        self.paint()

    def paint(self):
        canvas = self.fig.canvas
        for (region, artists), background in zip(self.regions, self.backgrounds):
            canvas.restore_region(background)
            for a in artists:
                if a.get_visible():
                    self.fig.draw_artist(a)
            canvas.blit(region)

    def tick(self):
        if self.playing and not self.dragging:
            self.pos = (self.pos + self.speed) % self.total
        frame = int(self.pos)
        self.s.step(frame)
        x = frame / max(1, self.total - 1)
        self.bar.set_data([0, x], [0.5, 0.5])
        self.knob.set_data([x], [0.5])
        self.s.status.set_text(self.status())
        self.paint()

    def status(self):
        parts = []
        if not self.playing:
            parts.append("paused")
        if self.speed != 1:
            parts.append("speed ×%g" % self.speed)
        job = self.job
        if job:
            code = job["proc"].poll()
            kind = job["kind"]
            if code is None:
                parts.append("saving %s %d%%" % (kind, 100 * job["done"]))
            elif time.time() < job["until"]:
                parts.append("saved %s" % job["out"] if code == 0 else "%s failed: %s" % (kind, job["last"]))
            elif job["until"] == 0:
                job["until"] = time.time() + 8
        if time.time() < self.note_until:
            parts.append(self.note_text)
        return "   ".join(parts)

    def note(self, text):
        self.note_text, self.note_until = text, time.time() + 4

    def toggle(self, event=None):
        self.playing = not self.playing
        self.buttons["Pause"].label.set_text("Pause" if self.playing else "Play")
        self.fig.canvas.draw_idle()

    def restart(self, event=None):
        self.pos = 0.0
        if not self.playing:
            self.toggle()

    def slower(self, event=None):
        self.speed = max(0.125, self.speed / 2)

    def faster(self, event=None):
        self.speed = min(16.0, self.speed * 2)

    def toggle_lens(self, event=None):
        self.s.set_lens(not self.s.lens["on"])
        self.fig.canvas.draw_idle()

    def follow(self, event=None):
        if not self.s.lens["on"]:
            self.toggle_lens()
        self.s.lens["target"] = (self.s.lens["target"] + 1) % len(self.s.targets)

    def reset_view(self, event=None):
        x0, x1, y0, y1 = self.s.home
        self.s.ax.set_xlim(x0, x1)
        self.s.ax.set_ylim(y0, y1)
        self.s.lens["zoom"] = float(self.cfg.zoom)
        self.fig.canvas.draw_idle()

    def toggle_help(self, event=None):
        self.help.set_visible(not self.help.get_visible())

    def lens_zoom(self, factor):
        self.s.lens["zoom"] = min(200.0, max(0.05, self.s.lens["zoom"] * factor))

    def on_key(self, event):
        key = event.key
        if key == " ":
            self.toggle()
        elif key in ("right", "left"):
            if self.playing:
                self.toggle()
            self.pos = (int(self.pos) + (1 if key == "right" else -1)) % self.total
        elif key == "up":
            self.faster()
        elif key == "down":
            self.slower()
        elif key == "0":
            self.restart()
        elif key == "r":
            self.reset_view()
        elif key == "m":
            self.toggle_lens()
        elif key == "f":
            self.follow()
        elif key == "]":
            self.lens_zoom(1.5)
        elif key == "[":
            self.lens_zoom(1 / 1.5)
        elif key == "h":
            self.toggle_help()

    def on_scroll(self, event):
        closer = event.button == "up"
        if event.inaxes is self.s.lens_ax and self.s.lens["on"]:
            self.lens_zoom(1.25 if closer else 1 / 1.25)
        elif event.inaxes is self.s.ax and event.xdata is not None:
            factor = 1 / 1.25 if closer else 1.25
            ax = self.s.ax
            x0, x1 = ax.get_xlim()
            y0, y1 = ax.get_ylim()
            cx, cy = event.xdata, event.ydata
            ax.set_xlim(cx + (x0 - cx) * factor, cx + (x1 - cx) * factor)
            ax.set_ylim(cy + (y0 - cy) * factor, cy + (y1 - cy) * factor)
            self.fig.canvas.draw_idle()

    def seek(self, event):
        if event.xdata is not None:
            self.pos = min(max(event.xdata, 0.0), 1.0) * (self.total - 1)

    def on_press(self, event):
        if event.inaxes is self.timeline:
            self.dragging = True
            self.seek(event)

    def on_motion(self, event):
        if self.dragging and event.inaxes is self.timeline:
            self.seek(event)

    def on_release(self, event):
        self.dragging = False

    def options(self):
        values = dict(vars(self.cfg))
        values["lens"] = self.s.lens["on"]
        values["follow"] = self.s.targets[self.s.lens["target"]]
        values["zoom"] = self.s.lens["zoom"]
        return ["%s=%s" % (key, value) for key, value in values.items()]

    def source_file(self):
        if isinstance(self.data, (str, os.PathLike)):
            return os.path.abspath(os.fspath(self.data))
        handle, path = tempfile.mkstemp(prefix="dwfs_", suffix=".json")
        with os.fdopen(handle, "w") as f:
            json.dump(self.data, f)
        return path

    def save(self, ext):
        if self.job and self.job["proc"].poll() is None:
            self.note("already saving, please wait")
            return
        if ext == ".mp4" and not shutil.which(plt.rcParams["animation.ffmpeg_path"]):
            self.note("MP4 needs FFmpeg, try GIF")
            return
        stem = re.sub(r"[\W_]+", "_", self.s.label or "dwfs").strip("_").lower() or "dwfs"
        out = ask_path(self.fig, ext, free_name(stem, ext))
        if not out:
            return
        source = self.source_file()
        temporary = not isinstance(self.data, (str, os.PathLike))
        args = [sys.executable, "-m", "dwfs", "draw", source, out] + self.options()
        proc = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                                env=dict(os.environ, MPLBACKEND="Agg"),
                                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        job = {"proc": proc, "out": out, "kind": ext[1:].upper(), "done": 0.0, "last": "", "until": 0}

        def read():
            for line in proc.stdout:
                line = line.strip()
                if line:
                    job["last"] = line
                found = re.match(r"frame (\d+) of (\d+)", line)
                if found:
                    job["done"] = int(found.group(1)) / max(1, int(found.group(2)))
            proc.wait()
            if temporary:
                try:
                    os.remove(source)
                except OSError:
                    pass

        threading.Thread(target=read, daemon=True).start()
        self.job = job


def play(data, m, cfg):
    with plt.rc_context(KEYS):
        g = layout(m, cfg, BAND)
        scene = build(m, cfg, dpi=screen_dpi(g.fig_w, g.fig_h), controls=BAND)
        player = Player(scene, data, cfg)
        plt.show()
    return player
