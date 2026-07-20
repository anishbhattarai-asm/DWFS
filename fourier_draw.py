import json
import numpy as np
import matplotlib.pyplot as plt
from matplotlib.animation import FuncAnimation

FILE = "tsp.json"
NUM_CIRCLES = 400
FRAMES = 400
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

if NUM_CIRCLES < N:
    coeffs = coeffs[:NUM_CIRCLES]
    freqs = freqs[:NUM_CIRCLES]

fig, ax = plt.subplots(figsize=(7, 7))
fig.patch.set_facecolor("black")
ax.set_facecolor("black")
ax.set_aspect("equal")
ax.axis("off")
lim = np.abs(path).max() * 1.15
ax.set_xlim(-lim, lim)
ax.set_ylim(-lim, lim)

circles = [ax.plot([], [], color=(1, 1, 1, 0.18), lw=0.6)[0] for _ in freqs]
arms, = ax.plot([], [], color="white", lw=0.6)
trace, = ax.plot([], [], color="cyan", lw=1.6)

theta = np.linspace(0, 2 * np.pi, 64)
trace_x = []
trace_y = []


def step(frame):
    t = 2 * np.pi * frame / FRAMES
    x = 0.0
    y = 0.0
    arm_x = [0.0]
    arm_y = [0.0]
    for i in range(len(coeffs)):
        prev_x = x
        prev_y = y
        val = coeffs[i] * np.exp(1j * freqs[i] * t)
        x += val.real
        y += val.imag
        r = abs(coeffs[i])
        circles[i].set_data(prev_x + r * np.cos(theta), prev_y + r * np.sin(theta))
        arm_x.append(x)
        arm_y.append(y)
    arms.set_data(arm_x, arm_y)
    trace_x.append(x)
    trace_y.append(y)
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
