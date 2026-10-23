import json
import os
import shutil
import subprocess
from types import SimpleNamespace

import cv2
import matplotlib
import numpy as np
import pytest

matplotlib.use("Agg")

import dwfs
import dwfs.drawing as drawing
import dwfs.player as player
from dwfs.cli import main


def ring():
    img = np.full((200, 260, 3), 255, np.uint8)
    cv2.circle(img, (130, 100), 60, (0, 0, 0), 3)
    return dwfs.trace(img, resample=300)


QUICK = {"stage_frames": 2, "frames": 6, "hold": 0, "latex": False, "dpi": 30}


@pytest.mark.parametrize("option", [
    {"frames": 0}, {"fps": 0}, {"dpi": 0}, {"zoom": 0}, {"growth": 1}, {"draw_circles": 0},
    {"ghost_alpha": 2}, {"frames": True}, {"fps": float("nan")},
])
def test_drawing_settings_are_checked(option, tmp_path):
    with pytest.raises(ValueError):
        dwfs.draw(ring(), tmp_path / "x.png", **option)


@pytest.mark.parametrize("option", [{"block": 20}, {"maxdim": 0}, {"resample": 1}, {"min_stroke": 0}])
def test_tracing_settings_are_checked(option):
    with pytest.raises(ValueError):
        dwfs.trace(np.full((50, 50, 3), 255, np.uint8), **option)


@pytest.mark.parametrize("path", [[], [[1, 1], [2, 2]], [[5, 5]] * 4, [[1, "a"], [2, 2], [3, 1]],
                                  [[0, 0], [1, float("inf")], [2, 0]]])
def test_bad_paths_are_rejected(path, tmp_path):
    with pytest.raises(ValueError):
        dwfs.draw({"width": 10, "height": 10, "path": path}, tmp_path / "x.png", latex=False)


def test_bad_outputs_are_rejected(tmp_path):
    with pytest.raises(ValueError, match="cannot save"):
        dwfs.draw(ring(), tmp_path / "x.webm", **QUICK)
    with pytest.raises(ValueError, match="does not exist"):
        dwfs.draw(ring(), tmp_path / "missing" / "x.mp4", **QUICK)


def test_cli_reports_bad_json(tmp_path, capsys):
    bad = tmp_path / "bad.json"
    bad.write_text("not json")
    assert main(["draw", str(bad), str(tmp_path / "x.png")]) == 2
    assert "not a DWFS path file" in capsys.readouterr().err


def test_live_window_needs_a_display():
    with pytest.raises(ValueError, match="no window"):
        dwfs.draw(ring(), latex=False)


def test_gif_without_ffmpeg_uses_pillow(tmp_path, monkeypatch):
    monkeypatch.setattr(drawing.shutil, "which", lambda name: None)
    out = dwfs.draw(ring(), tmp_path / "x.gif", **QUICK)
    assert os.path.getsize(out) > 0
    with pytest.raises(ValueError, match="FFmpeg"):
        dwfs.draw(ring(), tmp_path / "x.mp4", **QUICK)


@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="needs ffmpeg")
def test_mp4_falls_back_when_ffmpeg_lacks_h264(tmp_path, monkeypatch):
    monkeypatch.setattr(drawing, "has_h264", lambda ffmpeg: False)
    out = dwfs.draw(ring(), tmp_path / "x.mp4", **QUICK)
    assert os.path.getsize(out) > 0


def test_window_saves_run_from_the_package_folder(tmp_path, monkeypatch):
    calls = {}

    class Fake:
        def __init__(self, args, **kwargs):
            calls.update(kwargs, args=args)
            self.stdout = iter(())

        def poll(self):
            return 0

        def wait(self):
            return 0

    data = ring()
    cfg = drawing.settings(drawing.DEFAULTS, dict(QUICK, image="relative.png"))
    scene = drawing.build(drawing.model(data, cfg), cfg, controls=player.BAND)
    p = player.Player(scene, data, cfg)
    monkeypatch.setattr(player.subprocess, "Popen", Fake)
    monkeypatch.setattr(player, "ask_path", lambda fig, ext, default: str(tmp_path / "x.png"))
    p.save(".png")
    assert calls["cwd"] == player.HOME
    assert os.path.isdir(os.path.join(player.HOME, "dwfs"))
    assert "image=" + os.path.abspath("relative.png") in calls["args"]
