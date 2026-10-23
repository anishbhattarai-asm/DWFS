# DWFS: Draw With Fourier Series

[![PyPI](https://img.shields.io/pypi/v/dwfs)](https://pypi.org/project/dwfs/)
[![Python](https://img.shields.io/pypi/pyversions/dwfs)](https://pypi.org/project/dwfs/)
[![License](https://img.shields.io/pypi/l/dwfs)](https://github.com/anishbhattarai-asm/DWFS/blob/main/LICENSE)
[![Tests](https://github.com/anishbhattarai-asm/DWFS/actions/workflows/tests.yml/badge.svg)](https://github.com/anishbhattarai-asm/DWFS/actions/workflows/tests.yml)

**Turn any picture into one continuous line, then watch spinning circles draw it.**

![Two chains of circles drawing a horse while N grows](https://raw.githubusercontent.com/anishbhattarai-asm/DWFS/main/docs/demo.gif)

```
pip install dwfs
dwfs make photo.jpg
```

That is all it takes. DWFS traces the picture into a single closed path, works out its
Fourier series, and opens a window where two chains of circles redraw it, sharpening from
a rough loop into the exact drawing.

## Features

* Works with line drawings, photos, logos and flags, and detects which kind it was given
* Traces one continuous route along the strokes instead of jumping across the picture
* Lifts the pen over the short gaps between separate pieces, so no stray lines appear
* Draws with separate x and y circle chains, an arrow on every arm, joined to the pen by
  dashed guides
* Grows the number of terms N pass by pass and shows the approximation error live
* A zoom lens follows the tiny circles at the end of a chain so you can see them work
* An interactive window with a timeline, play controls and one click saving to MP4, GIF or PNG
* Typesets the formulas with real LaTeX when a TeX install is found
* Shows a faint tint of the source picture behind the drawing, in a light or dark theme
* Runs from the command line or as a Python library

## Quick start

**1. Install.** Python 3.10 or newer.

```
pip install dwfs
```

Exporting MP4 needs [FFmpeg](https://ffmpeg.org) on your PATH. GIF and PNG work without it.

**2. Draw something.**

```
dwfs make photo.jpg
```

A window opens and the drawing begins. The buttons along the bottom play, pause, change the
speed and save the animation, as described under The interactive window below.

**3. Save it.** Add an output file and DWFS renders to it instead of opening a window.

```
dwfs make photo.jpg photo.mp4
dwfs make photo.jpg photo.gif
dwfs make photo.jpg photo.png
```

A `.png` or `.jpg` saves only the finished frame, which is handy for a quick preview.

**4. Tune it.** Every setting can be added as `key=value`.

```
dwfs make photo.jpg photo.mp4 theme=dark label="My Portrait"
dwfs make logo.png logo.gif style=classic grow=false
```

Run `dwfs options` to see every setting with its default.

## What you are looking at

* **The blue chain on top** is the Fourier series for x. Its tip sets how far left or right
  the pen is.
* **The red chain on the left** is the series for y. Its tip sets how high the pen is.
* **Each arrow** is one term of the series, a vector turning k times per cycle. The circle
  around it shows its whole path.
* **The dashed guides** carry both tips to the pen, which draws the black line.
* **N** is how many circles each chain uses. It starts at 1 and grows each pass until
  every frequency in the path is included, at which point the drawing is exact.
* **The approximation error** is the share of the picture's detail still missing. It falls
  to 0% at the full N.
* **A hollow pen** means the pen is lifted while it crosses a gap between separate pieces.
* **The lens** in the top left corner is a magnified view of the dashed square, which follows
  the tip of a chain so the smallest circles are visible.

With `style=classic` the picture is drawn by a single chain of rotating complex circles
instead, the classic Fourier epicycle look.

## The interactive window

When no output file is given, DWFS opens a window with a timeline and a row of buttons.

* **Timeline**: click or drag anywhere on it to jump through the animation. The small marks
  are the points where N grows.
* **Pause** and **Restart**, **Slower** and **Faster** control playback.
* **Lens** shows or hides the magnifier, and **Follow** switches it between the x chain, the y
  chain and the pen.
* **Reset** undoes any zooming.
* **MP4**, **GIF** and **PNG** ask where to save, then render in the background with the same
  settings and lens you are looking at, while the window keeps playing. Progress shows in
  the bottom right corner.
* **Keys** lists the keyboard shortcuts.

The mouse wheel zooms the picture around the pointer, and zooms the lens when the pointer
is over it. Keyboard shortcuts:

```
space         pause or play
left, right   step one frame
up, down      faster or slower
0             start over
r             reset the zoom
m             show or hide the lens
f             change what the lens follows
[  ]          zoom the lens out or in
h             show or hide the help
```

The window sizes itself to fit your screen.

## Getting good results

* **Line drawings** give the cleanest result. Dark strokes on a plain light background are
  recognized automatically and traced along their centers.
* **Photos** work best with a plain background and clear lighting. Lower `canny_low` and
  `canny_high` to keep more edges, raise them to keep fewer.
* **Part of an outline is missing in a photo**, such as a jaw or cheek: that edge is too soft,
  usually skin against a background of similar brightness or a jaw shaded into the neck. Add
  `contrast=1.5` to boost local contrast before edges are found. It also brings out more
  texture, so it is off by default.
* **Too much clutter**, such as hair or grass turning into small loops: raise `min_stroke`,
  or trace with `mode=photo`.
* **More detail**: raise `resample`, for example `resample=10000`. Rendering gets slower.
* **Faster renders**: use `grow=false` to draw only the full series, or lower
  `stage_frames` and `frames`.
* **Tonal pictures** with lots of shading can look better as a stipple path, described
  under Stipple paths below.

## Command line

```
dwfs make IMAGE [OUT] [key=value ...]       trace an image and animate it
dwfs trace IMAGE [JSON] [key=value ...]     trace an image into a path file
dwfs draw [JSON] [OUT] [key=value ...]      animate a path file
dwfs stipple IMAGE [JSON] [key=value ...]   build a stipple path for tonal images
dwfs options                                list every setting with its default
dwfs help                                   show the usage
```

`JSON` defaults to `path.json`. Leaving out `OUT` opens a live window. Tracing once and
drawing many times is quicker when you are trying out drawing settings:

```
dwfs trace photo.jpg photo.json
dwfs draw photo.json photo.mp4 theme=dark
dwfs draw photo.json photo.gif style=classic
```

Settings take numbers, text, `true` or `false` (also `yes`, `no`, `on`, `off`), or `none`
to clear one. Without installing, `python -m dwfs` works the same from the repository folder.

## Python

```python
import dwfs

path = dwfs.trace("photo.jpg")
dwfs.draw(path)
dwfs.draw(path, "photo.mp4", theme="dark")
```

* `dwfs.trace(image, out=None, **settings)` traces a file path, a NumPy array (RGB or
  grayscale) or a PIL image, and returns the path as a dict. Pass `out` to also save it
  as JSON.
* `dwfs.draw(path, save=None, progress=False, **settings)` takes that dict or a JSON file.
  With `save` it writes an `.mp4`, `.gif`, `.png` or `.jpg` and returns the file name,
  without it the interactive window opens. `progress=True` prints rendering progress.
* `dwfs.animate(path, **settings)` returns the matplotlib animation, useful in notebooks:

  ```python
  from IPython.display import HTML

  HTML(dwfs.animate(path, grow=False, frames=300).to_jshtml())
  ```

* `dwfs.stipple(image, out=None, **settings)` builds a stipple path, described below.

### Drawing your own paths

`draw` accepts any dict with a `width`, a `height` and a `path` of points in pixel
coordinates, where y grows downward. This draws a heart from its formula:

```python
import numpy as np
import dwfs

t = np.linspace(0, 2 * np.pi, 2000, endpoint=False)
x = 16 * np.sin(t) ** 3
y = 13 * np.cos(t) - 5 * np.cos(2 * t) - 2 * np.cos(3 * t) - np.cos(4 * t)
path = {"width": 40, "height": 40, "path": [[20 + a, 20 - b] for a, b in zip(x, y)]}
dwfs.draw(path, label="Heart")
```

Paths made by `trace` also carry `lift`, a list of `[first, last]` point index ranges where
the pen is lifted, and `source`, the image used for the background tint.

## How it works

![The drawing at N = 3, N = 18 and the full N](https://raw.githubusercontent.com/anishbhattarai-asm/DWFS/main/docs/preview.png)

1. **Find the lines.** Line art is recognized by its plain background and thin dark strokes,
   and is traced along the strokes. Anything else is smoothed with a bilateral filter and
   traced along its edges.
2. **Thin them.** Lines are reduced to single pixel centerlines. Specks and tiny spurs are
   dropped.
3. **Route one path.** The pen walks the centerlines, preferring to go straight through
   junctions. At a dead end it travels back over lines it already drew to reach the nearest
   undrawn part. Pieces that do not touch are joined by the shortest gap, and those gaps are
   marked so the pen lifts over them.
4. **Take the Fourier series.** The path is resampled evenly and transformed with the FFT.
   Each axis becomes a real series, for x

   `x_N(t) = a_0 + sum over k = 1..N of (a_k cos kt + b_k sin kt)`

   and the same for y.
5. **Animate.** Each term is a circle turning k times per cycle. Every pass adds more terms
   until all of them are in.

## Settings

### Tracing

* `mode` is `auto`, `lines` for drawings or `photo` for everything else
* `maxdim` is the size the image is scaled down to before tracing, default 820
* `block` and `c` set how much fine detail such as hair is kept in line art
* `canny_low` and `canny_high` set how many edges are kept in photos. Lower keeps more
* `contrast` boosts local contrast in photos before finding edges, 0 is off, try 1.5
* `line_art` and `background` tune the automatic line art detection
* `min_stroke` drops specks and spurs shorter than this many pixels
* `resample` is the number of points in the final path, default 6000
* `retrace_cost` weighs going back over drawn lines against jumping a gap

### Drawing

* `style` is `axes` for the two chains or `classic` for one chain of complex epicycles
* `theme` is `light` or `dark`
* `grow` turns the growing passes on or off. With `false` only the full series is drawn
* `linear` and `growth` set the schedule of N: one by one up to 8, then times 1.5 each pass
* `stage_frames` frames per growing pass, `frames` for the final pass, `hold` to rest at the end
* `draw_circles` circles drawn per chain. The pen always uses every term
* `ghost`, `ghost_alpha` and `image` control the background tint
* `label` sets the caption, which defaults to the image file name
* `lift` lifts the pen over gaps. With `false` the gaps are drawn as straight lines
* `lens` shows the magnifier, `follow` picks what it follows (`auto`, `x`, `y` or `pen`) and
  `zoom` multiplies its magnification
* `latex` uses real LaTeX for the formulas when it is available
* `fps` and `dpi` for exports. GIFs play at up to 20 frames per second to stay small

### Stipple

* `points` is how many dots make up the path, default 8000
* `relax` is how many Voronoi relaxation rounds spread the dots evenly
* `seconds` is the time limit for improving the tour
* `gamma` and `white_cutoff` shape how darkness turns into dot density
* `maxdim` is the size the image is scaled down to, default 400
* `knn` is how many neighbors each dot considers while improving the tour
* `seed` makes the result repeatable

## Stipple paths

For pictures with lots of shading there is a second way to build the path. It scatters
points by darkness, relaxes them with Voronoi iterations, and joins them into one tour that
is refined by swapping crossing edges. The result is the classic single line maze look.

```
dwfs stipple photo.jpg photo.json points=8000 seconds=15
dwfs draw photo.json
```

The same tool also runs in the browser: open
[`web/index.html`](https://github.com/anishbhattarai-asm/DWFS/blob/main/web/index.html),
load an image, press Build, then Download JSON.

## LaTeX

With a TeX distribution such as MiKTeX or TeX Live that matplotlib can use for usetex, the
formulas are typeset by LaTeX itself. Otherwise they fall back to matplotlib math text in the
same Computer Modern style, so everything still runs without TeX. The first LaTeX run is slow
while fonts are generated. After that it is cached.

## Troubleshooting

* **MP4 export fails with a message about ffmpeg.** Install [FFmpeg](https://ffmpeg.org)
  and make sure it is on your PATH, or export a `.gif` instead.
* **The first run with LaTeX seems stuck.** MiKTeX may be waiting to install missing
  packages or building fonts. Let it finish, or draw with `latex=false`.
* **A jaw or cheek outline is missing from a photo.** Trace with `contrast=1.5`, see
  Getting good results.
* **The drawing has too many tiny loops.** Raise `min_stroke`, lower `maxdim`, or try the
  other `mode`.
* **Another tool broke after installing.** DWFS depends on `opencv-python`. If you also have
  `opencv-python-headless` or `opencv-contrib-python`, they share one `cv2` folder, so
  install all of them at the same version.

## Development

```
git clone https://github.com/anishbhattarai-asm/DWFS.git
cd DWFS
pip install -e ".[test]"
pytest
```

## Releasing

Releases go to PyPI automatically. Raise `__version__` in `dwfs/__init__.py`, add the
changes to `CHANGELOG.md`, push, then publish a GitHub release whose tag is that version
with a `v` in front, such as `v0.2.0`. The publish workflow runs the tests, checks the tag
against the version, builds the package and uploads it through PyPI trusted publishing, so
no token is stored anywhere.

## Project layout

```
dwfs/tracing.py    image to one continuous path
dwfs/drawing.py    Fourier series and epicycle animation
dwfs/stipple.py    stipple path for tonal images
dwfs/player.py     the interactive window
dwfs/cli.py        the dwfs command
web/index.html     stipple path in the browser
tests/             test suite
docs/              README images
.github/           test and publish workflows
```

## License

MIT, see [LICENSE](https://github.com/anishbhattarai-asm/DWFS/blob/main/LICENSE).
