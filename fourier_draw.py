import json
import numpy as np
import matplotlib.pyplot as plt
from matplotlib.animation import FuncAnimation

FILE = "tsp.json"
DRAW_CIRCLES = 140
FRAMES = 600
SAVE = None

with open(FILE) as f:
    data = json.load(f)

path = np.array(data["path"], dtype=float)
w = float(data.get("width", path[:, 0].max()))
h = float(data.get("height", path[:, 1].max()))

path[:, 0] -= w / 2.0
path[:, 1] -= h / 2.0
path[:, 1] *= -1.0

z = path[:, 0] + 1j * path[:, 1]
N = len(z)

coeffs = np.fft.fft(z) / N
freqs = np.fft.fftfreq(N, d=1.0 / N).astype(int)

order = np.argsort(-np.abs(coeffs))
coeffs = coeffs[order]
freqs = freqs[order]

fig, ax = plt.subplots(figsize=(7, 8))
fig.patch.set_facecolor("black")
ax.set_facecolor("black")
ax.set_aspect("equal")
ax.axis("off")
lim = np.abs(path).max() * 1.15
ax.set_xlim(-lim, lim)
ax.set_ylim(-lim, lim)

k = min(DRAW_CIRCLES, N)
circles = [ax.plot([], [], color=(1, 1, 1, 0.16), lw=0.5)[0] for _ in range(k)]
arms, = ax.plot([], [], color=(1, 1, 1, 0.55), lw=0.5)
trace, = ax.plot([], [], color="cyan", lw=1.3)

theta = np.linspace(0, 2 * np.pi, 48)
trace_x = []
trace_y = []


def step(frame):
    t = 2 * np.pi * frame / FRAMES
    vecs = coeffs * np.exp(1j * freqs * t)
    pos = np.concatenate([[0], np.cumsum(vecs)])

    arms.set_data(pos.real, pos.imag)

    for i in range(k):
        r = abs(coeffs[i])
        circles[i].set_data(pos[i].real + r * np.cos(theta),
                            pos[i].imag + r * np.sin(theta))

    tip = pos[-1]
    trace_x.append(tip.real)
    trace_y.append(tip.imag)
    if len(trace_x) > FRAMES:
        del trace_x[0]
        del trace_y[0]
    trace.set_data(trace_x, trace_y)
    return circles + [arms, trace]


anim = FuncAnimation(fig, step, frames=FRAMES, interval=20, blit=True)

if SAVE:
    anim.save(SAVE, fps=30, dpi=120)
else:
    plt.show()
