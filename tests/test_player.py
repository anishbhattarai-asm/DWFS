import os
import time
from types import SimpleNamespace

import cv2
import matplotlib
import numpy as np
import pytest

matplotlib.use("Agg")

import dwfs
import dwfs.player as player
from dwfs.drawing import DEFAULTS, build, model
from dwfs.options import settings


def shapes():
    img = np.full((240, 320, 3), 255, np.uint8)
    cv2.circle(img, (200, 120), 70, (0, 0, 0), 3)
    cv2.rectangle(img, (30, 40), (90, 100), (0, 0, 0), 3)
    return img


@pytest.fixture
def live(tmp_path):
    data = dwfs.trace(shapes(), resample=500)
    cfg = settings(DEFAULTS, {"latex": False, "stage_frames": 4, "frames": 12, "hold": 2, "dpi": 40})
    scene = build(model(data, cfg), cfg, controls=player.BAND)
    p = player.Player(scene, data, cfg)
    scene.fig.canvas.draw()
    return p


def test_player_keys_change_state(live):
    p = live
    assert p.regions and p.backgrounds
    p.on_key(SimpleNamespace(key=" "))
    assert not p.playing
    p.on_key(SimpleNamespace(key="right"))
    assert int(p.pos) == 1
    p.on_key(SimpleNamespace(key="up"))
    assert p.speed == 2
    p.on_key(SimpleNamespace(key="m"))
    assert not p.s.lens["on"]
    p.on_key(SimpleNamespace(key="f"))
    assert p.s.lens["on"] and p.s.lens["target"] == 1
    p.on_key(SimpleNamespace(key="]"))
    assert p.s.lens["zoom"] == pytest.approx(1.5)
    p.tick()
    assert "paused" in p.status()


def test_player_zoom_seek_and_reset(live):
    p = live
    ax = p.s.ax
    width = np.ptp(ax.get_xlim())
    p.on_scroll(SimpleNamespace(button="up", inaxes=ax, xdata=0.0, ydata=0.0))
    assert np.ptp(ax.get_xlim()) < width
    p.on_key(SimpleNamespace(key="r"))
    assert np.ptp(ax.get_xlim()) == pytest.approx(width)
    p.on_press(SimpleNamespace(inaxes=p.timeline, xdata=0.5))
    assert abs(p.pos - 0.5 * (p.total - 1)) < 1
    p.on_release(None)
    assert not p.dragging


def test_player_saves_png_in_background(live, tmp_path, monkeypatch):
    out = str(tmp_path / "saved.png")
    monkeypatch.setattr(player, "ask_path", lambda fig, ext, default: out)
    live.save(".png")
    proc = live.job["proc"]
    deadline = time.time() + 120
    while proc.poll() is None and time.time() < deadline:
        time.sleep(0.2)
    assert proc.returncode == 0, live.job["last"]
    assert os.path.getsize(out) > 0


def test_contrast_option_keeps_more_edges():
    from skimage import data

    photo = data.camera()
    plain = dwfs.trace(photo, mode="photo")["stats"]["ink"]
    boosted = dwfs.trace(photo, mode="photo", contrast=1.5)["stats"]["ink"]
    assert boosted > plain * 1.2
