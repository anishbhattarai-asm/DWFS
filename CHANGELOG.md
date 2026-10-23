# Changelog

## Unreleased

* Browser version at https://anishbhattarai-asm.github.io/DWFS/ that traces photos, drawings,
  SVG files and text, animates them with the same chains, lens and controls, records video
  and exports path files for the dwfs command, all without uploading anything

## 0.3.0

* SVG input: `dwfs make logo.svg` draws from the exact vector outlines, with paths, shapes,
  transforms and `use` references, and refuses files with DOCTYPE or entity declarations
* Text input: `dwfs text "Hello"` writes words in one continuous line, as a centerline or as
  letter outlines, with automatic font choice and proper shaping for Nepali and other scripts
* Labels in any script are shaped properly, and explicit labels keep their capitalization
* Live Theme and Style buttons in the window, plus `t`, `s`, `,` and `.` keys to switch theme,
  switch style and jump to the previous or next N
* The browser stipple tool finds neighbors with a grid, so twelve thousand points route in
  milliseconds instead of tens of seconds
* GitHub Actions pinned to exact commits, with Dependabot keeping them current
* Video export is about ten times faster: only the moving parts are redrawn each frame and the
  frames go straight to FFmpeg. A full default MP4 now takes about as long as it plays
* GIF export uses FFmpeg with an optimized palette, at up to 20 frames per second
* Inside the lens, the main chains no longer show through the panel
* Temporary files from saving in the window are cleaned up
* Export errors are reported as a short message instead of a traceback
* Every setting and path file is checked first, with clear messages instead of crashes for
  values like `frames=0`, an even `block`, an empty path or an unsupported output type
* Saving from the window can no longer pick up a stray `dwfs` file in the current folder
  instead of the installed package
* Without a screen, DWFS now says so instead of silently showing nothing
* Labels in non Latin scripts use an installed font that has their letters
* MP4 export works with FFmpeg builds that lack H.264, and GIF export works without FFmpeg
* Closing the window during a save says the save is still finishing
* GitHub workflows run with read only permissions and do not keep the checkout token

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
