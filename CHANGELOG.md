# Changelog

## 0.2.0

* Interactive window: a timeline you can click or drag, buttons for play, pause, restart,
  speed, lens, follow and reset, keyboard shortcuts, and mouse wheel zoom
* Save to MP4, GIF or PNG straight from the window, rendered in the background with progress
* A zoom lens that follows the tip of a chain or the pen, with its own zoom
* An arrow on every arm, x and y chains in their own colors, circles that fade as they shrink
* The window sizes itself to fit the screen, so the formulas no longer overlap
* Long labels shrink to fit beside N
* New `contrast` tracing setting that recovers soft photo outlines such as a jaw
* New `lens`, `follow` and `zoom` drawing settings
* README rewritten as a full guide with an animated demo, tips, a Python API reference,
  drawing your own paths and troubleshooting, plus richer PyPI metadata and this changelog

## 0.1.0

* First release on PyPI
* Tracing of line art and photos into one continuous path, with automatic detection
* Routing that retraces drawn lines and lifts the pen over gaps between pieces
* Animation with separate x and y epicycle chains, growing N and a live approximation error
* Formulas typeset with LaTeX when available
* `dwfs` command line with `make`, `trace`, `draw`, `stipple` and `options`
* Python API: `trace`, `draw`, `animate` and `stipple`
* Stipple paths in Python and in the browser
