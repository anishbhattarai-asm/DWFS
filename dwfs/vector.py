import os
import re
import math
import xml.etree.ElementTree as ET
import numpy as np
import cv2
from PIL import Image, ImageDraw, ImageFont, features
from scipy.spatial import cKDTree

from .options import settings
from .tracing import package, route_mask, save_json

SVG_DEFAULTS = {"resample": 6000}
SVG_LIMITS = {"resample": (16, 1000000)}
TEXT_DEFAULTS = {"font": None, "size": 220, "stroke": "center", "resample": 6000, "min_stroke": 6,
                 "retrace_cost": 0.5}
TEXT_LIMITS = {"size": (24, 2000), "resample": (16, 1000000), "min_stroke": (1, 10000),
               "retrace_cost": (0, 1000)}
CANVAS = 800.0
MARGIN = 24.0
MAX_SVG = 20 * 1024 * 1024
MAX_PIXELS = 6000000
SKIP = {"defs", "clipPath", "mask", "symbol", "marker", "pattern", "style", "script", "metadata", "title",
        "desc", "linearGradient", "radialGradient", "filter", "text", "image", "foreignObject"}
NUMBER = re.compile(r"[+-]?(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?")


class Reader:
    def __init__(self, text):
        self.text, self.i = text, 0

    def skip(self):
        while self.i < len(self.text) and self.text[self.i] in " \t\r\n,":
            self.i += 1

    def done(self):
        self.skip()
        return self.i >= len(self.text)

    def command(self):
        self.skip()
        if self.i < len(self.text) and self.text[self.i].isalpha():
            self.i += 1
            return self.text[self.i - 1]
        return None

    def number(self):
        self.skip()
        found = NUMBER.match(self.text, self.i)
        if not found:
            raise ValueError("bad number in SVG path data near %r" % self.text[self.i:self.i + 20])
        self.i = found.end()
        return float(found.group())

    def point(self):
        x = self.number()
        return complex(x, self.number())

    def flag(self):
        self.skip()
        char = self.text[self.i:self.i + 1]
        if char not in ("0", "1"):
            raise ValueError("bad arc flag in SVG path data")
        self.i += 1
        return char == "1"


def cubic(p0, c1, c2, p3, count=32):
    t = np.arange(1, count + 1) / count
    u = 1 - t
    return list(u ** 3 * p0 + 3 * u * u * t * c1 + 3 * u * t * t * c2 + t ** 3 * p3)


def quad(p0, c, p2, count=24):
    t = np.arange(1, count + 1) / count
    u = 1 - t
    return list(u * u * p0 + 2 * u * t * c + t * t * p2)


def arc(p0, rx, ry, rotation, large, sweep, p1):
    if p0 == p1:
        return []
    rx, ry = abs(rx), abs(ry)
    if rx == 0 or ry == 0:
        return [p1]
    phi = math.radians(rotation)
    cos, sin = math.cos(phi), math.sin(phi)
    dx, dy = (p0.real - p1.real) / 2, (p0.imag - p1.imag) / 2
    x1, y1 = cos * dx + sin * dy, cos * dy - sin * dx
    scale = (x1 / rx) ** 2 + (y1 / ry) ** 2
    if scale > 1:
        rx, ry = rx * math.sqrt(scale), ry * math.sqrt(scale)
    num = rx * rx * ry * ry - rx * rx * y1 * y1 - ry * ry * x1 * x1
    den = rx * rx * y1 * y1 + ry * ry * x1 * x1
    coef = math.sqrt(max(0.0, num / den)) if den else 0.0
    if large == sweep:
        coef = -coef
    cx1, cy1 = coef * rx * y1 / ry, -coef * ry * x1 / rx
    cx = cos * cx1 - sin * cy1 + (p0.real + p1.real) / 2
    cy = sin * cx1 + cos * cy1 + (p0.imag + p1.imag) / 2

    def angle(ux, uy, vx, vy):
        return math.atan2(ux * vy - uy * vx, ux * vx + uy * vy)

    start = angle(1, 0, (x1 - cx1) / rx, (y1 - cy1) / ry)
    delta = angle((x1 - cx1) / rx, (y1 - cy1) / ry, (-x1 - cx1) / rx, (-y1 - cy1) / ry)
    if not sweep and delta > 0:
        delta -= 2 * math.pi
    elif sweep and delta < 0:
        delta += 2 * math.pi
    count = max(8, int(abs(delta) / (2 * math.pi) * 96))
    t = start + delta * np.arange(1, count + 1) / count
    xs, ys = rx * np.cos(t), ry * np.sin(t)
    return list((cos * xs - sin * ys + cx) + 1j * (sin * xs + cos * ys + cy))


def parse_path(d):
    reader = Reader(d or "")
    subpaths, pts = [], []
    cur = start = 0j
    last_cubic = last_quad = None
    cmd = None

    def finish(closed):
        if len(pts) > 1:
            subpaths.append((np.array(pts), closed))
        pts.clear()

    while not reader.done():
        found = reader.command()
        if found is None:
            if cmd is None:
                raise ValueError("SVG path data must start with a command")
            found = cmd
        cmd = found
        upper = found.upper()
        base = cur if found.islower() else 0j
        if upper == "M":
            finish(False)
            cur = start = base + reader.point()
            pts.append(cur)
            last_cubic = last_quad = None
            cmd = "l" if found.islower() else "L"
            continue
        if upper == "Z":
            if pts:
                pts.append(start)
            finish(True)
            cur = start
            last_cubic = last_quad = None
            continue
        if not pts:
            pts.append(cur)
        if upper == "L":
            end = base + reader.point()
            pts.append(end)
            last_cubic = last_quad = None
        elif upper == "H":
            x = reader.number() + (cur.real if found.islower() else 0)
            end = complex(x, cur.imag)
            pts.append(end)
            last_cubic = last_quad = None
        elif upper == "V":
            y = reader.number() + (cur.imag if found.islower() else 0)
            end = complex(cur.real, y)
            pts.append(end)
            last_cubic = last_quad = None
        elif upper == "C":
            c1, c2, end = base + reader.point(), base + reader.point(), base + reader.point()
            pts.extend(cubic(cur, c1, c2, end))
            last_cubic, last_quad = c2, None
        elif upper == "S":
            c1 = 2 * cur - last_cubic if last_cubic is not None else cur
            c2, end = base + reader.point(), base + reader.point()
            pts.extend(cubic(cur, c1, c2, end))
            last_cubic, last_quad = c2, None
        elif upper == "Q":
            c, end = base + reader.point(), base + reader.point()
            pts.extend(quad(cur, c, end))
            last_cubic, last_quad = None, c
        elif upper == "T":
            c = 2 * cur - last_quad if last_quad is not None else cur
            end = base + reader.point()
            pts.extend(quad(cur, c, end))
            last_cubic, last_quad = None, c
        elif upper == "A":
            rx, ry, rotation = reader.number(), reader.number(), reader.number()
            large, sweep = reader.flag(), reader.flag()
            end = base + reader.point()
            pts.extend(arc(cur, rx, ry, rotation, large, sweep, end))
            last_cubic = last_quad = None
        else:
            raise ValueError("unsupported SVG path command %s" % found)
        cur = end
    finish(False)
    return subpaths


def parse_transform(text):
    m = np.eye(3)
    for name, args in re.findall(r"([A-Za-z]+)\s*\(([^)]*)\)", text or ""):
        v = [float(x) for x in NUMBER.findall(args)]
        if not v:
            continue
        if name == "matrix" and len(v) == 6:
            t = [[v[0], v[2], v[4]], [v[1], v[3], v[5]], [0, 0, 1]]
        elif name == "translate":
            t = [[1, 0, v[0]], [0, 1, v[1] if len(v) > 1 else 0], [0, 0, 1]]
        elif name == "scale":
            sy = v[1] if len(v) > 1 else v[0]
            t = [[v[0], 0, 0], [0, sy, 0], [0, 0, 1]]
        elif name == "rotate":
            a = math.radians(v[0])
            t = np.array([[math.cos(a), -math.sin(a), 0], [math.sin(a), math.cos(a), 0], [0, 0, 1]])
            if len(v) == 3:
                move = np.array([[1, 0, v[1]], [0, 1, v[2]], [0, 0, 1]])
                back = np.array([[1, 0, -v[1]], [0, 1, -v[2]], [0, 0, 1]])
                t = move @ t @ back
        elif name == "skewX":
            t = [[1, math.tan(math.radians(v[0])), 0], [0, 1, 0], [0, 0, 1]]
        elif name == "skewY":
            t = [[1, 0, 0], [math.tan(math.radians(v[0])), 1, 0], [0, 0, 1]]
        else:
            continue
        m = m @ np.array(t, dtype=float)
    return m


def length(el, name, default=0.0):
    found = NUMBER.match((el.get(name) or "").strip())
    return float(found.group()) if found else default


def points_of(el):
    v = [float(x) for x in NUMBER.findall(el.get("points") or "")]
    return [complex(v[i], v[i + 1]) for i in range(0, len(v) - 1, 2)]


def shape_path(tag, el):
    if tag == "path":
        return el.get("d")
    if tag == "rect":
        x, y, w, h = length(el, "x"), length(el, "y"), length(el, "width"), length(el, "height")
        if w <= 0 or h <= 0:
            return None
        rx, ry = length(el, "rx", -1), length(el, "ry", -1)
        rx, ry = (ry if rx < 0 else rx), (rx if ry < 0 else ry)
        rx, ry = min(max(rx, 0), w / 2), min(max(ry, 0), h / 2)
        if rx == 0 or ry == 0:
            return "M %r %r H %r V %r H %r Z" % (x, y, x + w, y + h, x)
        return ("M %r %r H %r A %r %r 0 0 1 %r %r V %r A %r %r 0 0 1 %r %r H %r A %r %r 0 0 1 %r %r V %r "
                "A %r %r 0 0 1 %r %r Z" % (x + rx, y, x + w - rx, rx, ry, x + w, y + ry, y + h - ry, rx, ry,
                                           x + w - rx, y + h, x + rx, rx, ry, x, y + h - ry, y + ry, rx, ry,
                                           x + rx, y))
    if tag in ("circle", "ellipse"):
        cx, cy = length(el, "cx"), length(el, "cy")
        rx = length(el, "r") if tag == "circle" else length(el, "rx")
        ry = length(el, "r") if tag == "circle" else length(el, "ry")
        if rx <= 0 or ry <= 0:
            return None
        return "M %r %r A %r %r 0 1 0 %r %r A %r %r 0 1 0 %r %r Z" % (
            cx - rx, cy, rx, ry, cx + rx, cy, rx, ry, cx - rx, cy)
    if tag == "line":
        return "M %r %r L %r %r" % (length(el, "x1"), length(el, "y1"), length(el, "x2"), length(el, "y2"))
    if tag in ("polyline", "polygon"):
        pts = points_of(el)
        if len(pts) < 2:
            return None
        body = " ".join("%r %r" % (p.real, p.imag) for p in pts)
        return "M " + body + (" Z" if tag == "polygon" else "")
    return None


def hidden(el):
    style = (el.get("style") or "").replace(" ", "").lower()
    return el.get("display") == "none" or "display:none" in style or el.get("visibility") == "hidden"


def apply(m, pts):
    x, y = pts.real, pts.imag
    return (m[0, 0] * x + m[0, 1] * y + m[0, 2]) + 1j * (m[1, 0] * x + m[1, 1] * y + m[1, 2])


def collect(el, m, ids, out, depth):
    tag = el.tag.split("}")[-1]
    if tag in SKIP or hidden(el) or depth > 40:
        return
    m = m @ parse_transform(el.get("transform"))
    if tag == "use":
        ref = el.get("{http://www.w3.org/1999/xlink}href") or el.get("href") or ""
        target = ids.get(ref.lstrip("#"))
        if target is not None:
            shift = np.array([[1, 0, length(el, "x")], [0, 1, length(el, "y")], [0, 0, 1]], dtype=float)
            inner = target.tag.split("}")[-1]
            if inner in ("symbol", "defs"):
                for child in target:
                    collect(child, m @ shift, ids, out, depth + 1)
            else:
                collect(target, m @ shift, ids, out, depth + 1)
        return
    d = shape_path(tag, el)
    if d:
        for pts, closed in parse_path(d):
            out.append((apply(m, pts), closed))
    for child in el:
        collect(child, m, ids, out, depth + 1)


def read_svg(source):
    if isinstance(source, (str, os.PathLike)) and not str(source).lstrip().startswith("<"):
        if os.path.getsize(source) > MAX_SVG:
            raise ValueError("SVG files larger than 20 MB are not supported")
        with open(source, encoding="utf-8", errors="replace") as f:
            return f.read()
    return str(source)


def svg_strokes(markup):
    lowered = markup.lower()
    if "<!doctype" in lowered or "<!entity" in lowered:
        raise ValueError("SVG files with a DOCTYPE or entity declarations are not supported, for safety")
    try:
        root = ET.fromstring(markup)
    except ET.ParseError as exc:
        raise ValueError("not a valid SVG file: %s" % exc) from None
    ids = {el.get("id"): el for el in root.iter() if el.get("id")}
    out = []
    collect(root, np.eye(3), ids, out, 0)
    return [(pts, closed) for pts, closed in out if len(pts) > 1 and np.isfinite(pts).all()]


def chain_strokes(strokes):
    ends, owner, which = [], [], []
    for s, (pts, closed) in enumerate(strokes):
        picks = range(len(pts)) if closed else (0, len(pts) - 1)
        for v in picks:
            ends.append(pts[v])
            owner.append(s)
            which.append(v)
    ends = np.array(ends)
    owner, which = np.array(owner), np.array(which)
    tree = cKDTree(np.column_stack([ends.real, ends.imag]))
    remaining = np.ones(len(strokes), dtype=bool)
    first = max(range(len(strokes)), key=lambda s: np.abs(np.diff(strokes[s][0])).sum())
    order = [(first, 0)]
    remaining[first] = False
    pts, closed = strokes[first]
    cur = pts[-1]
    pieces = [pts]
    while remaining.any():
        k = 8
        while True:
            _, idx = tree.query([cur.real, cur.imag], k=min(k, len(ends)))
            idx = np.atleast_1d(idx)
            live = [i for i in idx if i < len(ends) and remaining[owner[i]]]
            if live or k >= len(ends):
                break
            k *= 4
        i = live[0]
        s, v = owner[i], which[i]
        pts, closed = strokes[s]
        if closed:
            body = pts[:-1] if abs(pts[0] - pts[-1]) < 1e-9 else pts
            ring = np.roll(body, -int(np.argmin(np.abs(body - ends[i]))))
            piece = np.append(ring, ring[:1])
        else:
            piece = pts if v == 0 else pts[::-1]
        pieces.append(piece)
        remaining[s] = False
        cur = piece[-1]
    cuts, walk = [], []
    for piece in pieces:
        if walk:
            cuts.append(len(walk))
        walk.extend(piece)
    walk = np.array(walk)
    return np.column_stack([walk.real, walk.imag]), cuts


def fit(strokes):
    every = np.concatenate([pts for pts, _ in strokes])
    x0, x1 = every.real.min(), every.real.max()
    y0, y1 = every.imag.min(), every.imag.max()
    size = max(x1 - x0, y1 - y0)
    if not size > 0:
        raise ValueError("the drawing has no size")
    scale = (CANVAS - 2 * MARGIN) / size
    shift = complex(MARGIN - x0 * scale, MARGIN - y0 * scale)
    moved = [(pts * scale + shift, closed) for pts, closed in strokes]
    return moved, (x1 - x0) * scale + 2 * MARGIN, (y1 - y0) * scale + 2 * MARGIN


def svg(source, out=None, **options):
    cfg = settings(SVG_DEFAULTS, options, SVG_LIMITS)
    strokes = svg_strokes(read_svg(source))
    if not strokes:
        raise ValueError("no shapes found in the SVG")
    strokes, w, h = fit(strokes)
    walk, cuts = chain_strokes(strokes)
    path = isinstance(source, (str, os.PathLike)) and not str(source).lstrip().startswith("<")
    data = package(walk, cuts, {"strokes": len(strokes)}, round(w, 2), round(h, 2), "svg",
                   os.path.abspath(os.fspath(source)) if path else None, cfg.resample, fill=True)
    if out:
        save_json(data, out)
    return data


def load_font(name, words, size):
    from .drawing import font_for
    path = name if name and os.path.isfile(name) else font_for(words, name)
    engine = ImageFont.Layout.RAQM if features.check("raqm") else ImageFont.Layout.BASIC
    return ImageFont.truetype(path, size, layout_engine=engine)


def render(words, name, size):
    while True:
        font = load_font(name, words, size)
        probe = ImageDraw.Draw(Image.new("L", (1, 1)))
        spacing = size // 4
        box = probe.multiline_textbbox((0, 0), words, font=font, spacing=spacing)
        pad = size // 2
        w, h = box[2] - box[0] + 2 * pad, box[3] - box[1] + 2 * pad
        if w * h <= MAX_PIXELS or size <= 24:
            break
        size = max(24, int(size * math.sqrt(MAX_PIXELS / (w * h)) * 0.95))
    img = Image.new("L", (w, h), 255)
    ImageDraw.Draw(img).multiline_text((pad - box[0], pad - box[1]), words, font=font, fill=0, spacing=spacing)
    return np.asarray(img) < 128


def smooth(ring, width=5):
    pad = width // 2
    wrapped = np.concatenate([ring[-pad:], ring, ring[:pad]])
    return np.convolve(wrapped, np.ones(width) / width, mode="valid")


def centerline(mask, cfg):
    count, labels, boxes, _ = cv2.connectedComponentsWithStats(mask.astype(np.uint8), connectivity=8)
    reach = 2 * int(cfg.min_stroke) + 4
    dots = [i for i in range(1, count)
            if max(boxes[i, cv2.CC_STAT_WIDTH], boxes[i, cv2.CC_STAT_HEIGHT]) <= reach * 3
            and min(boxes[i, cv2.CC_STAT_WIDTH], boxes[i, cv2.CC_STAT_HEIGHT]) * 2
            >= max(boxes[i, cv2.CC_STAT_WIDTH], boxes[i, cv2.CC_STAT_HEIGHT])]
    body = mask & ~np.isin(labels, dots)
    if body.any():
        walk, cuts, stats = route_mask(body.astype(np.uint8) * 255, cfg.min_stroke, cfg.retrace_cost)
        walk, cuts = list(walk), list(cuts)
    else:
        walk, cuts, stats = [], [], {}
    for i in dots:
        part = (labels == i).astype(np.uint8)
        part = cv2.erode(part, np.ones((3, 3), np.uint8)) if part.sum() > 40 else part
        contours, _ = cv2.findContours(part, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
        if not contours:
            continue
        c = max(contours, key=len)[:, 0, :].astype(float)
        ring = np.vstack([c, c[:1]])
        if walk:
            cuts.append(len(walk))
        walk.extend(ring)
    if not walk:
        raise ValueError("no lines found in the text")
    stats["dots"] = len(dots)
    return np.array(walk, dtype=float), cuts, stats


def text(words, out=None, **options):
    cfg = settings(TEXT_DEFAULTS, options, TEXT_LIMITS)
    if cfg.stroke not in ("center", "outline"):
        raise ValueError("stroke must be center or outline")
    words = str(words).replace("\\n", "\n").strip()
    if not words:
        raise ValueError("there is no text to draw")
    mask = render(words, cfg.font, int(cfg.size))
    if not mask.any():
        raise ValueError("the font has no visible letters for this text")
    h, w = mask.shape
    if cfg.stroke == "center":
        walk, cuts, stats = centerline(mask, cfg)
    else:
        contours, _ = cv2.findContours(mask.astype(np.uint8), cv2.RETR_LIST, cv2.CHAIN_APPROX_NONE)
        strokes = []
        for c in contours:
            if len(c) >= 8:
                ring = smooth(c[:, 0, 0] + 1j * c[:, 0, 1])
                strokes.append((np.append(ring, ring[:1]), True))
        if not strokes:
            raise ValueError("no letter outlines found")
        walk, cuts = chain_strokes(strokes)
        stats = {"strokes": len(strokes)}
    data = package(walk, cuts, stats, w, h, "text", None, cfg.resample, title=" ".join(words.split()),
                   fill=cfg.stroke == "outline")
    if out:
        save_json(data, out)
    return data
