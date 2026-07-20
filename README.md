# DWFS: Draw With Fourier Series

Turn a line art image into one continuous smooth path, then redraw it with Fourier epicycles.

The strokes of the drawing are thinned to single pixel centerlines, each stroke is traced
in order, and the strokes are joined into one path. A Fourier transform of that path drives
the epicycle animation, so the result traces the picture with clean curves.

Use a line art or grayscale image. Convert colorful photos to line art first.

## Main pipeline

```
pip install -r requirements.txt
python trace_image.py input.png tsp.json
python fourier_draw.py
```

`trace_image.py` reads the image and writes `tsp.json`, a single path.
`fourier_draw.py` reads `tsp.json` and animates the epicycles. Set `SAVE = "out.mp4"`
in it to export a video instead of showing a window.

Tuning in `trace_image.py`: `BLOCK` and `C` control how much fine detail like hair is
captured, `MIN_STROKE` drops the shortest strokes, `RESAMPLE` sets the path point count.

## Stipple alternative

For tonal images an older stipple based method is also here. It scatters points by
darkness, relaxes them with Voronoi, and joins them with a greedy plus 2-opt tour. It
gives the classic single line maze look rather than smooth curves.

Browser: open `index.html`, load an image, press Build, then Download JSON.
Python: `python tsp_art.py input.png tsp.json`.

## Files

`trace_image.py` line art to one smooth path, the main method
`fourier_draw.py` reads tsp.json and animates the epicycles
`tsp_art.py` stipple based path, Python
`index.html` stipple based path, browser
