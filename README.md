# DWFS: Draw With Fourier Series

Turn an image into one continuous path, then redraw it with Fourier epicycles.

The lines of the picture are thinned to single pixel centerlines and walked as one route.
Where a stroke ends, the pen travels back along lines it already drew to reach the next
undrawn part. Pieces that do not touch at all are joined by short gaps, and the pen lifts
over those gaps, so no stray straight lines are drawn. A Fourier transform of that route
drives the epicycle animation.

Both line drawings and photos work. Line art is detected automatically and traced along its
strokes. Photos, logos and flags are smoothed and traced along their edges instead.

## Main pipeline

```
pip install -r requirements.txt
python trace_image.py input.png tsp.json
python fourier_draw.py tsp.json
```

`trace_image.py` reads the image and writes `tsp.json`, a single path that also remembers
the source image. `fourier_draw.py` reads it and animates the epicycles.

Export instead of opening a window by giving an output file:

```
python fourier_draw.py tsp.json out.mp4
python fourier_draw.py tsp.json out.gif
python fourier_draw.py tsp.json still.png
```

A `.png` or `.jpg` saves a single frame of the finished drawing. Space pauses the live window.

## What the animation shows

By default the picture is drawn by two chains of circles. The chain on top is the series for
x, the chain on the left is the series for y, and dashed guides carry each one to the pen:

```
x_N(t) = a_0 + sum over k = 1..N of (a_k cos kt + b_k sin kt)
y_N(t) = c_0 + sum over k = 1..N of (c_k cos kt + d_k sin kt)
```

N starts at 1 and grows each pass until every frequency is in, so you watch a rough loop
sharpen into the full drawing. Under the count is the approximation error, the energy of
the frequencies still missing relative to the whole picture. The source image is shown as a
faint tint behind the drawing, and its file name becomes the label.

The formulas are typeset with real LaTeX when a TeX install is found (MiKTeX or TeX Live with
the `cm-super` and `underscore` packages). Without it they fall back to matplotlib math text
in the same Computer Modern look. The very first LaTeX run takes a while as fonts are built.

Settings at the top of `fourier_draw.py`:

`STYLE` is `"axes"` for the two chains or `"classic"` for one chain of complex epicycles
`THEME` is `"light"` or `"dark"`
`GROW` turns the growing N passes on or off, `False` draws only the full series
`LINEAR` and `GROWTH` set the N schedule, 1 to 8 one by one then times 1.5 each pass
`STAGE_FRAMES` frames per growing pass, `FRAMES` for the final full pass, `HOLD` to rest on it
`DRAW_CIRCLES` how many circles to draw per chain, the pen always uses every frequency
`GHOST`, `GHOST_ALPHA`, `IMAGE` control the background tint, `LABEL` overrides the name
`LIFT` lifts the pen over the gaps between separate pieces, `False` draws them as lines
`LATEX` uses real LaTeX for the formulas when available
`FPS` and `DPI` for exported video

Tuning in `trace_image.py`:

`MODE` is `"auto"`, `"lines"` for drawings or `"photo"` for photos and flat graphics
`BLOCK` and `C` control how much fine detail like hair is captured in line art
`CANNY_LOW` and `CANNY_HIGH` control how many edges are kept in photos, lower keeps more
`LINE_ART` is how thin dark areas must be for auto mode to call an image line art
`MIN_STROKE` drops specks and short spurs, `RESAMPLE` sets the path point count
`RETRACE_COST` sets how much the router prefers going back over drawn lines to making a gap

## Stipple alternative

For tonal images an older stipple based method is also here. It scatters points by
darkness, relaxes them with Voronoi, and joins them with a greedy plus 2-opt tour. It
gives the classic single line maze look rather than smooth curves.

Browser: open `index.html`, load an image, press Build, then Download JSON.
Python: `python tsp_art.py input.png tsp.json`.

## Files

`trace_image.py` image to one smooth path, the main method
`fourier_draw.py` reads tsp.json and animates the epicycles
`tsp_art.py` stipple based path, Python
`index.html` stipple based path, browser
