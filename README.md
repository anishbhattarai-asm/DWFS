# DWFS: Draw With Fourier Series

Turn an image into a Travelling Salesman art path, then redraw it with Fourier epicycles.

The image is stippled by tone (dark areas get more points), the points are spread out
with Voronoi relaxation, then stitched into one continuous closed path with a greedy
tour plus 2-opt. A Fourier transform of that single path drives the epicycle animation.

Use a line art or grayscale image. Convert colorful photos to line art first. No edge
detection is used.

## Pipeline

Image to a single path, two ways:

Browser: open `index.html`, load an image, press Build, then Download JSON.

Command line:

```
pip install -r requirements.txt
python tsp_art.py input.png tsp.json
```

Then draw it with Fourier:

```
python fourier_draw.py
```

Set `SAVE = "out.mp4"` in `fourier_draw.py` to export a video instead of showing a window.

## Files

`index.html` browser stippling and TSP engine, exports tsp.json
`tsp_art.py` same pipeline in Python, image to tsp.json
`fourier_draw.py` reads tsp.json and animates the epicycles
