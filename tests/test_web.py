import os
import shutil
import subprocess

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
ENGINE = os.path.join(HERE, "..", "docs", "dwfs.js")

SCRIPT = r"""
const D = require(process.argv[1]);
const out = [];
const n = D.POINTS;
const ring = (cx, cy, r, k) => Array.from({ length: k }, (_, i) => [cx + r * Math.cos(2 * Math.PI * i / k), cy + r * Math.sin(2 * Math.PI * i / k)]);
const fake = { width: 200, height: 200, lift: [], path: D.resample(ring(100, 100, 60, 500), n) };
for (const style of ["axes", "classic"]) {
  const m = D.analyze(fake, style, 120);
  const s = m.levels.length - 1, [cr, ci] = m.curves[s];
  let worst = 0;
  fake.path.forEach(([x, y], i) => { worst = Math.max(worst, Math.hypot(cr[i] - (x - 100), ci[i] + (y - 100))); });
  out.push(worst < 1e-6 ? "exact " + style : "bad " + style + " " + worst);
}
const w = 220, h = 160, data = new Uint8ClampedArray(w * h * 4).fill(255);
const ink = (x, y) => { const i = (y * w + x) * 4; data[i] = data[i + 1] = data[i + 2] = 0; };
for (let t = 0; t < 2000; t++) {
  const a = 2 * Math.PI * t / 2000;
  for (let d = -1; d <= 1; d++) {
    ink(Math.round(60 + (40 + d) * Math.cos(a)), Math.round(80 + (40 + d) * Math.sin(a)));
    ink(Math.round(160 + (30 + d) * Math.cos(a)), Math.round(80 + (30 + d) * Math.sin(a)));
  }
}
const two = D.traceImage({ width: w, height: h, data });
out.push(two.mode === "lines" && two.path.length === n && two.lift.length >= 1 ? "traced" : "bad trace " + JSON.stringify(two.lift));
const field = new Float32Array(60 * 40);
for (let y = 10; y < 30; y++) for (let x = 10; x < 50; x++) field[y * 60 + x] = 1;
const loops = D.contours(field, 60, 40, 0.5);
out.push(loops.length === 1 ? "contour" : "bad contour " + loops.length);
const joined = D.chainStrokes([{ closed: false, pts: [[0, 0], [10, 0]] }, { closed: false, pts: [[30, 0], [12, 0]] }]);
out.push(joined.walk.length === 4 && joined.cuts.length === 1 && joined.walk[0][0] === 30 && joined.walk[2][0] === 10 ? "chained" : "bad chain");
console.log(out.join("\n"));
"""


@pytest.mark.skipif(shutil.which("node") is None, reason="needs node")
def test_browser_engine():
    result = subprocess.run(["node", "-e", SCRIPT, os.path.abspath(ENGINE)], capture_output=True, text=True,
                            timeout=300)
    lines = result.stdout.split()
    assert result.returncode == 0, result.stderr
    assert lines == ["exact", "axes", "exact", "classic", "traced", "contour", "chained"], result.stdout
