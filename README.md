# DWFS: Draw With Fourier Series

Turn any picture into a single continuous line and redraw it with spinning circles.

![Fourier epicycles drawing a horse as N grows](https://raw.githubusercontent.com/anishbhattarai-asm/DWFS/main/docs/preview.png)

DWFS traces an image into one closed path, takes its Fourier series, and animates the
epicycles that rebuild it. Two chains of circles drive the pen, one for x and one for y,
while the number of terms N grows from a rough loop to the exact drawing.

## Features

* Works with line drawings and with photos, flags and logos, detected automatically
* One continuous route that follows the strokes instead of jumping across the picture
* The pen lifts over the short gaps between separate pieces, so no stray lines are drawn
* Separate x and y epicycle chains with dashed guides to the pen
* N grows pass by pass with a live approximation error readout
* Formulas typeset with real LaTeX when a TeX install is available
* Faint tint of the source image behind the drawing, light and dark themes
* Live window, or export to MP4, GIF or a single PNG frame
* Usable from the command line or as a Python library

## Install

Python 3.9 or newer.

```
pip install dwfs
```

Exporting video needs [FFmpeg](https://ffmpeg.org) on your PATH.

## Command line

```
dwfs make portrait.jpg
```

That traces the image and opens the animation. Press space to pause. Give a second file to
export instead:

```
dwfs make portrait.jpg portrait.mp4
dwfs make portrait.jpg portrait.gif
dwfs make portrait.jpg portrait.png
```

A `.png` or `.jpg` saves the finished frame. Tracing and drawing can also run as separate
steps, with the path kept in a JSON file in between:

```
dwfs trace portrait.jpg portrait.json
dwfs draw portrait.json portrait.mp4
```

Any setting can be added as `key=value`:

```
dwfs make logo.png logo.mp4 theme=dark style=classic
dwfs trace sketch.png sketch.json mode=lines resample=8000
dwfs draw sketch.json sketch.gif grow=false label="My Sketch"
```

`dwfs options` lists every setting with its default, and `dwfs help` shows the usage.
Without installing, `python -m dwfs` works the same from the repository folder.

## Python

```python
import dwfs

path = dwfs.trace("portrait.jpg")
dwfs.draw(path, "portrait.mp4", theme="dark")
```

`trace` takes a file path, a NumPy array or a PIL image and returns the path as a plain
dict, which is also written to JSON when you pass a second argument. `draw` takes that dict
or a JSON file and shows a window, or saves to the file you give it. In a notebook,
`dwfs.animate(path)` returns the matplotlib animation so you can embed it:

```python
from IPython.display import HTML

HTML(dwfs.animate(path, grow=False, frames=300).to_jshtml())
```

`dwfs.stipple(image)` builds the alternative stipple path described below.

## How it works

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
   Each axis becomes a real series
   `x_N(t) = a_0 + sum of (a_k cos kt + b_k sin kt)` for k from 1 to N,
   and likewise for y.
5. **Animate.** Each term is a circle turning k times per cycle. The circles of the x chain
   sit above the picture and those of the y chain sit to its left. Every pass adds more terms
   until all of them are in. The error shown is the share of the picture's energy held by the
   terms still missing.

## Settings

### Tracing

* `mode` is `auto`, `lines` for drawings or `photo` for everything else
* `maxdim` is the size the image is scaled down to before tracing, default 820
* `block` and `c` set how much fine detail such as hair is kept in line art
* `canny_low` and `canny_high` set how many edges are kept in photos. Lower keeps more
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
* `latex` uses real LaTeX for the formulas when it is available
* `fps` and `dpi` for exports

## LaTeX

With a TeX distribution such as MiKTeX or TeX Live that matplotlib can use for usetex, the
formulas are typeset by LaTeX itself. Otherwise they fall back to matplotlib math text in the
same Computer Modern style, so everything still runs without TeX. The first LaTeX run is slow
while fonts are generated. After that it is cached.

## Stipple alternative

For tonal images there is a second way to build the path. It scatters points by darkness,
relaxes them with Voronoi iterations, and joins them into one tour that is refined by
swapping crossing edges. The result is the classic single line maze look.

```
dwfs stipple photo.jpg photo.json points=8000 seconds=15
dwfs draw photo.json
```

The same tool runs in the browser too: open `web/index.html`, load an image, press Build,
then Download JSON.

## Development

```
git clone https://github.com/anishbhattarai-asm/DWFS.git
cd DWFS
pip install -e ".[test]"
pytest
```

## Project layout

```
dwfs/tracing.py    image to one continuous path
dwfs/drawing.py    Fourier series and epicycle animation
dwfs/stipple.py    stipple path for tonal images
dwfs/cli.py        the dwfs command
web/index.html     stipple path in the browser
tests/             test suite
docs/              README preview
```

## License

MIT, see [LICENSE](https://github.com/anishbhattarai-asm/DWFS/blob/main/LICENSE).
