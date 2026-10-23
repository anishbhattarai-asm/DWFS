import json

import cv2
import matplotlib
import numpy as np
import pytest

matplotlib.use("Agg")

import dwfs
from dwfs.cli import main
from dwfs.drawing import DEFAULTS, chains, load, spectrum, stages, synth
from dwfs.options import settings


def shapes():
    img = np.full((240, 320, 3), 255, np.uint8)
    cv2.circle(img, (200, 120), 70, (0, 0, 0), 3)
    cv2.rectangle(img, (30, 40), (90, 100), (0, 0, 0), 3)
    return img


@pytest.fixture
def image_file(tmp_path):
    path = tmp_path / "shapes.png"
    cv2.imwrite(str(path), shapes())
    return path


def test_trace_array_gives_closed_path_with_one_gap():
    data = dwfs.trace(shapes())
    assert data["mode"] == "lines"
    assert data["source"] is None
    assert len(data["path"]) > 200
    assert len(data["lift"]) >= 1


def test_trace_file_writes_json(image_file, tmp_path):
    out = tmp_path / "shapes.json"
    data = dwfs.trace(image_file, out, resample=400)
    saved = json.loads(out.read_text())
    assert saved["path"] == data["path"]
    assert len(saved["path"]) == 400
    assert saved["source"] == str(image_file.resolve())


@pytest.mark.parametrize("style", ["axes", "classic"])
def test_epicycles_rebuild_the_path(style):
    z, *_ = load(dwfs.trace(shapes(), resample=600))
    n = len(z)
    c, k = spectrum(z)
    curve = synth(c, k, n // 2, n)
    assert np.abs(curve - z).max() < 1e-6
    parts = chains(z, style)
    tips = [ch["base"] + synth(ch["amps"], ch["ks"], n // 2, n) for ch in parts]
    if style == "classic":
        assert np.abs(tips[0] - z).max() < 1e-6
    else:
        assert np.abs(tips[0].real - z.real).max() < 1e-6
        assert np.abs(tips[1].imag - z.imag).max() < 1e-6


def test_stages_grow_to_every_frequency():
    levels = stages(500, settings(DEFAULTS, {}))
    assert levels[:8] == list(range(1, 9))
    assert levels[-1] == 500
    assert levels == sorted(set(levels))


def test_draw_still_frame(tmp_path):
    out = tmp_path / "still.png"
    dwfs.draw(dwfs.trace(shapes(), resample=600), out, latex=False, theme="dark")
    assert out.stat().st_size > 0


def test_stipple_is_reproducible():
    first = dwfs.stipple(shapes(), points=200, relax=2, seconds=0.5, seed=3)
    second = dwfs.stipple(shapes(), points=200, relax=2, seconds=0.5, seed=3)
    assert len(first["path"]) == 200
    assert first["path"] == second["path"]


def test_unknown_option_is_rejected():
    with pytest.raises(TypeError):
        dwfs.trace(shapes(), colour="red")


def test_cli_trace_and_errors(image_file, tmp_path, capsys):
    out = tmp_path / "cli.json"
    assert main(["trace", str(image_file), str(out), "resample=500", "mode=lines"]) == 0
    assert len(json.loads(out.read_text())["path"]) == 500
    assert main(["trace", str(image_file), "bogus=1"]) == 2
    assert main(["draw", str(out), str(tmp_path / "cli.png"), "latex=no", "grow=off"]) == 0
    assert (tmp_path / "cli.png").exists()
    assert "wrote" in capsys.readouterr().out
