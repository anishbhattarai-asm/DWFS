import os
import shutil
import subprocess
from types import SimpleNamespace

import matplotlib
import numpy as np
import pytest

matplotlib.use("Agg")

import dwfs
import dwfs.player as player
from dwfs.drawing import DEFAULTS, build, clean_label, font_for, model
from dwfs.options import settings
from dwfs.vector import parse_path, parse_transform, svg

HERE = os.path.dirname(os.path.abspath(__file__))
SHAPES = """<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" viewBox="0 0 200 120">
  <defs><circle id="dot" cx="0" cy="0" r="6"/></defs>
  <path d="M10 60 C 10 20, 50 20, 50 60 S 90 100, 90 60 Q 110 30 130 60 T 170 60"/>
  <rect x="140" y="80" width="40" height="25" rx="6"/>
  <g transform="translate(100 25) rotate(30)"><polygon points="-10,-8 10,-8 0,10"/></g>
  <use xlink:href="#dot" x="30" y="20"/>
  <path d="M150 10h10v10h-10z" style="display:none"/>
</svg>"""


def test_path_commands_and_compact_numbers():
    subs = parse_path("M0 0 L10 0 H20 V10 Z m1 1 l2 0 2 2")
    assert len(subs) == 2
    first, closed = subs[0]
    assert closed and first[0] == first[-1] and first[2] == 20 + 0j and first[3] == 20 + 10j
    second, closed = subs[1]
    assert not closed and second[-1] == complex(5, 3)
    tight = parse_path("M.5.5-1-2")
    assert tight[0][0][-1] == complex(-1, -2)


def test_arcs_end_where_they_should():
    pts, _ = parse_path("M0 0a5 5 0 1010 0")[0]
    assert abs(pts[-1] - 10) < 1e-9
    assert pts.imag.max() > 4.9 or pts.imag.min() < -4.9


def test_transforms():
    m = parse_transform("rotate(90)")
    assert np.allclose(m @ [1, 0, 1], [0, 1, 1])
    m = parse_transform("translate(5 1) scale(2)")
    assert np.allclose(m @ [1, 1, 1], [7, 3, 1])


def test_svg_shapes_become_one_path():
    data = svg(SHAPES)
    assert data["mode"] == "svg"
    assert data["stats"]["strokes"] == 4
    assert len(data["path"]) == 6000
    assert len(data["lift"]) >= 3


def test_svg_safety_and_errors(tmp_path):
    with pytest.raises(ValueError, match="DOCTYPE"):
        svg('<!DOCTYPE svg [<!ENTITY a "x">]><svg xmlns="http://www.w3.org/2000/svg"/>')
    with pytest.raises(ValueError, match="not a valid SVG"):
        svg("<svg><path></svg")
    with pytest.raises(ValueError, match="no shapes"):
        svg('<svg xmlns="http://www.w3.org/2000/svg"><text>hi</text></svg>')


def test_trace_reads_svg_files(tmp_path):
    path = tmp_path / "shapes.svg"
    path.write_text(SHAPES)
    data = dwfs.trace(path)
    assert data["mode"] == "svg" and data["source"] == str(path.resolve())
    dwfs.draw(data, tmp_path / "shapes.png", latex=False)


@pytest.mark.parametrize("stroke", ["center", "outline"])
def test_text_in_both_strokes(stroke, tmp_path):
    data = dwfs.text("Hi ij", stroke=stroke, size=120)
    assert data["mode"] == "text" and data["title"] == "Hi ij"
    assert len(data["path"]) > 300
    if stroke == "center":
        assert data["stats"]["dots"] == 3
    dwfs.draw(data, tmp_path / "text.png", latex=False)


def test_text_errors():
    with pytest.raises(ValueError):
        dwfs.text("   ")
    with pytest.raises(ValueError):
        dwfs.text("a", stroke="wavy")
    with pytest.raises(ValueError):
        dwfs.text("a", font="No Such Font Anywhere")


def test_devanagari_text_when_a_font_covers_it(tmp_path):
    from matplotlib.ft2font import FT2Font

    words = "अनिश"
    face = FT2Font(font_for(words))
    if not all(face.get_char_index(ord(c)) for c in words):
        pytest.skip("no Devanagari font installed")
    data = dwfs.text(words)
    assert data["title"] == words
    dwfs.draw(data, tmp_path / "np.png", latex=False)


def test_labels_keep_letters_and_marks():
    assert clean_label("अनिश café!") == "अनिश café!"
    assert clean_label("a_b$c^d{e}") == "a b c d e"


def test_title_is_the_default_label():
    data = dwfs.text("Hello", size=80)
    cfg = settings(DEFAULTS, {"latex": False})
    scene = build(model(data, cfg), cfg, offscreen=True)
    assert scene.label == "Hello"


def test_player_switches_theme_style_and_n():
    data = dwfs.text("Hey", size=80, resample=400)
    cfg = settings(DEFAULTS, {"latex": False, "stage_frames": 4, "frames": 10, "hold": 2, "dpi": 40})
    scene = build(model(data, cfg), cfg, controls=player.BAND)
    p = player.Player(scene, data, cfg)
    scene.fig.canvas.draw()
    p.on_key(SimpleNamespace(key="."))
    p.on_key(SimpleNamespace(key="."))
    assert p.s.frames[int(p.pos)][0] == 2
    p.on_key(SimpleNamespace(key=","))
    assert p.s.frames[int(p.pos)][0] == 1
    p.on_key(SimpleNamespace(key="t"))
    assert p.cfg.theme == "dark" and p.s.theme["bg"] != "#f4f5f5"
    p.on_key(SimpleNamespace(key="s"))
    assert p.cfg.style == "classic" and p.s.targets == ["pen"]
    assert p.s.frames[int(p.pos)][0] == 1
    p.on_key(SimpleNamespace(key="s"))
    assert p.cfg.style == "axes"
    p.tick()
    assert "theme=dark" in p.options()


@pytest.mark.skipif(shutil.which("node") is None, reason="needs node")
def test_web_grid_search_matches_brute_force():
    script = r"""
const fs = require("fs");
const html = fs.readFileSync(process.argv[1], "utf8");
const code = html.slice(html.indexOf("function makeGrid"), html.indexOf("async function twoOpt("));
const lib = new Function(code + "; return { makeGrid, greedyTour, buildKnn };")();
let seed = 3;
const rand = () => (seed = (seed * 16807) % 2147483647) / 2147483647;
const N = 800, px = new Float32Array(N), py = new Float32Array(N);
for (let i = 0; i < N; i++) { px[i] = rand() * 300; py[i] = rand() * 200; }
const grid = lib.makeGrid(px, py, N);
const nb = lib.buildKnn(px, py, N, 6, grid);
let bad = 0;
for (let i = 0; i < N; i++) {
  const d = [];
  for (let j = 0; j < N; j++) if (j !== i) d.push((px[j]-px[i])**2 + (py[j]-py[i])**2);
  d.sort((a, b) => a - b);
  for (let n = 0; n < 6; n++) {
    const j = nb[i * 6 + n];
    if (Math.abs((px[j]-px[i])**2 + (py[j]-py[i])**2 - d[n]) > 1e-6) bad++;
  }
}
const order = lib.greedyTour(px, py, N, grid);
console.log(bad === 0 && new Set(order).size === N ? "ok" : "bad " + bad);
"""
    page = os.path.join(HERE, "..", "web", "index.html")
    out = subprocess.run(["node", "-e", script, page], capture_output=True, text=True, timeout=120)
    assert out.stdout.strip() == "ok", out.stdout + out.stderr
