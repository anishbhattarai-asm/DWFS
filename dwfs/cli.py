import sys

from . import __version__
from .tracing import DEFAULTS as TRACE, trace
from .drawing import DEFAULTS as DRAW, draw
from .stipple import DEFAULTS as STIPPLE, stipple

USAGE = """dwfs %s, draw any picture with Fourier series epicycles

usage:
  dwfs make IMAGE [OUT] [key=value ...]       trace an image and animate it
  dwfs trace IMAGE [JSON] [key=value ...]     trace an image into a path file
  dwfs draw [JSON] [OUT] [key=value ...]      animate a path file
  dwfs stipple IMAGE [JSON] [key=value ...]   build a stipple path for tonal images
  dwfs options                                list every option with its default

JSON defaults to path.json. OUT ending in .mp4 or .gif saves a video, .png or .jpg
saves the finished frame, and leaving it out opens the interactive window, where the
buttons save too and h shows the keyboard shortcuts.

examples:
  dwfs make portrait.jpg
  dwfs make portrait.jpg portrait.mp4 theme=dark
  dwfs trace logo.png logo.json mode=photo resample=8000
  dwfs draw logo.json logo.gif style=classic grow=false
"""


def parse(value, default):
    low = value.strip().lower()
    if low in ("none", "null"):
        return None
    if isinstance(default, bool):
        if low in ("1", "true", "yes", "on"):
            return True
        if low in ("0", "false", "no", "off"):
            return False
        raise ValueError("expected true or false, got %s" % value)
    if isinstance(default, int):
        return int(value)
    if isinstance(default, float):
        return float(value)
    return value


def split(args, *tables):
    positional, chosen = [], [{} for _ in tables]
    for arg in args:
        if "=" not in arg:
            positional.append(arg)
            continue
        key, value = arg.split("=", 1)
        key = key.strip().lower()
        for table, picked in zip(tables, chosen):
            if key in table:
                picked[key] = parse(value, table[key])
                break
        else:
            names = sorted(set().union(*tables))
            raise ValueError("unknown option %s, valid options are %s" % (key, ", ".join(names)))
    return positional, chosen


def describe(data, out):
    stats = data.get("stats", {})
    parts = ["mode %s" % data.get("mode", "unknown"), "%d points" % len(data["path"])]
    if "lift" in data:
        parts.append("%d gaps" % len(data["lift"]))
    if "route" in stats:
        parts.append("route %s px" % stats["route"])
    print(", ".join(parts) + (", wrote %s" % out if out else ""))


def finish(saved):
    if saved:
        print("wrote", saved)


def options():
    for title, table in (("trace", TRACE), ("draw", DRAW), ("stipple", STIPPLE)):
        print(title)
        for key, value in table.items():
            print("  %s=%s" % (key, value))


def run(argv):
    if not argv or argv[0] in ("help", "h", "?"):
        print(USAGE % __version__)
        return 0
    command, rest = argv[0], argv[1:]
    if command == "options":
        options()
        return 0
    if command == "version":
        print(__version__)
        return 0
    if command == "make":
        args, (topts, dopts) = split(rest, TRACE, DRAW)
        if not args:
            raise ValueError("make needs an image")
        data = trace(args[0], **topts)
        describe(data, None)
        finish(draw(data, args[1] if len(args) > 1 else None, progress=True, **dopts))
        return 0
    if command == "trace":
        args, (topts,) = split(rest, TRACE)
        if not args:
            raise ValueError("trace needs an image")
        out = args[1] if len(args) > 1 else "path.json"
        describe(trace(args[0], out, **topts), out)
        return 0
    if command == "stipple":
        args, (sopts,) = split(rest, STIPPLE)
        if not args:
            raise ValueError("stipple needs an image")
        out = args[1] if len(args) > 1 else "path.json"
        describe(stipple(args[0], out, **sopts), out)
        return 0
    if command == "draw":
        args, (dopts,) = split(rest, DRAW)
        source = args[0] if args else "path.json"
        finish(draw(source, args[1] if len(args) > 1 else None, progress=True, **dopts))
        return 0
    raise ValueError("unknown command %s, run dwfs help" % command)


def main(argv=None):
    try:
        return run(sys.argv[1:] if argv is None else argv)
    except (ValueError, TypeError, FileNotFoundError) as exc:
        print("dwfs:", exc, file=sys.stderr)
        return 2
