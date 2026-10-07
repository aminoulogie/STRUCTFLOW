# -*- coding: utf-8 -*-
"""Live schematic preview for the Type Maker: plan cut, section /
elevation and a shaded 3D box, drawn with the chosen line weights,
colours, cut / surface patterns and shading. Not a Revit render: a fast
sketch that follows every change in the dialog."""
import clr
clr.AddReference("PresentationCore")
clr.AddReference("PresentationFramework")
clr.AddReference("WindowsBase")
from System.Windows import Point, Thickness
from System.Windows.Controls import Canvas, TextBlock
from System.Windows.Media import Brushes, Color, DoubleCollection, PointCollection, SolidColorBrush
from System.Windows.Shapes import Ellipse, Line, Polygon, Rectangle

import sf_graphics as sg

PANEL_H, GAP, TITLE = 175, 8, 18


def _brush(rgb, alpha=255):
    try:
        r, g, b = sg.parse_rgb(rgb)
    except Exception:
        r, g, b = 0, 0, 0
    return SolidColorBrush(Color.FromArgb(alpha, r, g, b))


def _shade(rgb, k):
    try:
        r, g, b = sg.parse_rgb(rgb)
    except Exception:
        r, g, b = 128, 128, 128
    return "%d,%d,%d" % tuple(max(0, min(255, int(c * k))) for c in (r, g, b))


def _lw(weight):
    """Revit pen 1..16 -> screen pixels."""
    try:
        return 0.6 + 0.35 * (int(weight) - 1)
    except Exception:
        return 1.0


def _line(parent, x1, y1, x2, y2, brush, width, dashed=False):
    ln = Line()
    ln.X1, ln.Y1, ln.X2, ln.Y2 = x1, y1, x2, y2
    ln.Stroke, ln.StrokeThickness = brush, width
    if dashed:
        ln.StrokeDashArray = DoubleCollection([4.0, 3.0])
    parent.Children.Add(ln)


def _text(parent, x, y, text, size=11):
    t = TextBlock()
    t.Text, t.FontSize = text, size
    t.Foreground = Brushes.DimGray
    Canvas.SetLeft(t, x)
    Canvas.SetTop(t, y)
    parent.Children.Add(t)


def _pattern(parent, x, y, w, h, name, rgb):
    """Fill a rectangle with the pattern (solid, concrete stipple or hatch)."""
    if not name or name == "None" or w <= 1 or h <= 1:
        return
    if name == "Solid fill":
        r = Rectangle()
        r.Width, r.Height, r.Fill = w, h, _brush(rgb)
        Canvas.SetLeft(r, x)
        Canvas.SetTop(r, y)
        parent.Children.Add(r)
        return
    box = Canvas()
    box.Width, box.Height, box.ClipToBounds = w, h, True
    Canvas.SetLeft(box, x)
    Canvas.SetTop(box, y)
    br = _brush(rgb)
    if "concrete" in name.lower():
        seed = 7
        n = int(w * h / 90) + 4
        for i in range(n):
            seed = (seed * 1103515245 + 12345) % 2147483648
            px = (seed % 1000) / 1000.0 * w
            seed = (seed * 1103515245 + 12345) % 2147483648
            py = (seed % 1000) / 1000.0 * h
            if i % 4 == 0:  # small aggregate triangles
                pg = Polygon()
                pg.Points = PointCollection([Point(px, py), Point(px + 4, py + 1), Point(px + 1.5, py + 4)])
                pg.Stroke, pg.StrokeThickness = br, 0.6
                box.Children.Add(pg)
            else:
                d = Ellipse()
                d.Width = d.Height = 1.6
                d.Fill = br
                Canvas.SetLeft(d, px)
                Canvas.SetTop(d, py)
                box.Children.Add(d)
    else:
        step = 7.0
        k = -h
        while k < w:
            _line(box, k, h, k + h, 0, br, 0.6)
            k += step
    parent.Children.Add(box)


def _rect(parent, x, y, w, h, stroke, width, dashed=False):
    _line(parent, x, y, x + w, y, stroke, width, dashed)
    _line(parent, x + w, y, x + w, y + h, stroke, width, dashed)
    _line(parent, x + w, y + h, x, y + h, stroke, width, dashed)
    _line(parent, x, y + h, x, y, stroke, width, dashed)


def _fit(dims_w, dims_h, box_w, box_h):
    s = min(box_w / max(dims_w, 1.0), box_h / max(dims_h, 1.0))
    return dims_w * s, dims_h * s


def _cut(parent, cx, cy, w, h, g):
    x, y = cx - w / 2.0, cy - h / 2.0
    _pattern(parent, x, y, w, h, g["cut_fill"], g["cut_fill_colour"])
    _rect(parent, x, y, w, h, _brush(g["colour"]), _lw(g["cut_w"]))


def _proj(parent, cx, cy, w, h, g):
    x, y = cx - w / 2.0, cy - h / 2.0
    _pattern(parent, x, y, w, h, g["surface_fill"], g["surface_colour"])
    _rect(parent, x, y, w, h, _brush(g["colour"]), _lw(g["proj_w"]), g["proj_pattern"] != "Solid")


def _iso(parent, cx, cy, a, b, c, g, box_w, box_h):
    """Shaded box a (x) * b (y) * c (z), isometric, fitted to the panel."""
    import math
    cos30, sin30 = math.cos(math.pi / 6), 0.5
    pts = lambda x, y, z: ((x - y) * cos30, (x + y) * sin30 - z)
    corners = [pts(x, y, z) for x in (0, a) for y in (0, b) for z in (0, c)]
    xs, ys = [p[0] for p in corners], [p[1] for p in corners]
    s = min(box_w / (max(xs) - min(xs) or 1), box_h / (max(ys) - min(ys) or 1))
    ox = cx - (max(xs) + min(xs)) / 2.0 * s
    oy = cy - (max(ys) + min(ys)) / 2.0 * s
    P = lambda x, y, z: Point(ox + pts(x, y, z)[0] * s, oy + pts(x, y, z)[1] * s)
    alpha = int(255 * (100 - int(g["transparency"])) / 100.0)
    faces = [
        ([P(0, b, 0), P(a, b, 0), P(a, b, c), P(0, b, c)], 0.75),   # front-left
        ([P(a, 0, 0), P(a, b, 0), P(a, b, c), P(a, 0, c)], 0.9),    # front-right
        ([P(0, 0, c), P(a, 0, c), P(a, b, c), P(0, b, c)], 1.1),    # top
    ]
    for poly, k in faces:
        pg = Polygon()
        pg.Points = PointCollection(poly)
        pg.Fill = _brush(_shade(g["shade"], k), alpha)
        pg.Stroke, pg.StrokeThickness = _brush(g["colour"]), max(0.6, _lw(g["proj_w"]) * 0.6)
        parent.Children.Add(pg)


def draw(canvas, key, size, g):
    """size: (b, h) for columns / beams, (t,) for slabs / walls, in mm."""
    canvas.Children.Clear()
    W = canvas.Width
    bw, bh = W - 40, PANEL_H - TITLE - 22
    titles = {
        "columns": ("Plan - cut", "Elevation - projection", "3D shaded"),
        "beams": ("Plan - beam below slab (hidden)", "Section - cut", "3D shaded"),
        "floors": ("Plan - slab in projection", "Section - cut", "3D shaded"),
        "walls": ("Plan - cut", "Section - cut", "3D shaded"),
    }[key]
    for i, title in enumerate(titles):
        top = i * (PANEL_H + GAP)
        frame = Rectangle()
        frame.Width, frame.Height = W, PANEL_H
        frame.Stroke, frame.StrokeThickness, frame.Fill = Brushes.Gainsboro, 1, Brushes.White
        Canvas.SetLeft(frame, 0)
        Canvas.SetTop(frame, top)
        canvas.Children.Add(frame)
        _text(canvas, 8, top + 3, title)
    cx = W / 2.0
    cys = [i * (PANEL_H + GAP) + TITLE + (PANEL_H - TITLE) / 2.0 for i in range(3)]

    if key == "columns":
        b, h = size
        w, d = _fit(b, h, bw * 0.6, bh * 0.8)
        _cut(canvas, cx, cys[0], w, d, g)
        w2, d2 = _fit(b, 3000.0, bw, bh)
        _proj(canvas, cx, cys[1], w2, d2, g)
        _iso(canvas, cx, cys[2], b, h, 3000.0, g, bw * 0.7, bh)
        _text(canvas, 8, PANEL_H - 18, "%g x %g" % (b, h))
    elif key == "beams":
        b, h = size
        length = 4000.0
        w, d = _fit(length, b, bw, bh * 0.5)
        x, y = cx - w / 2.0, cys[0] - d / 2.0
        hb, hw = _brush(g["colour"]), _lw(g["hidden_w"])
        _line(canvas, x, y, x + w, y, hb, hw, g["hidden_pattern"] != "Solid")
        _line(canvas, x, y + d, x + w, y + d, hb, hw, g["hidden_pattern"] != "Solid")
        w2, d2 = _fit(b, h, bw * 0.6, bh * 0.8)
        _cut(canvas, cx, cys[1], w2, d2, g)
        _iso(canvas, cx, cys[2], length, b, h, g, bw, bh * 0.8)
        _text(canvas, 8, PANEL_H + GAP + PANEL_H - 18, "%g x %g" % (b, h))
    elif key == "floors":
        t = size[0]
        _proj(canvas, cx, cys[0], bw * 0.8, bh * 0.75, g)
        w2, d2 = _fit(3000.0, t, bw, bh)
        d2 = max(d2, 3)
        _cut(canvas, cx, cys[1], w2, d2, g)
        _iso(canvas, cx, cys[2], 3000.0, 3000.0, t, g, bw, bh)
        _text(canvas, 8, PANEL_H + GAP + PANEL_H - 18, "%g mm" % t)
    else:  # walls
        t = size[0]
        w, d = _fit(3000.0, t, bw, bh)
        _cut(canvas, cx, cys[0], w, max(d, 3), g)
        w2, d2 = _fit(t, 3000.0, bw, bh)
        _cut(canvas, cx, cys[1], max(w2, 3), d2, g)
        _iso(canvas, cx, cys[2], 3000.0, t, 3000.0, g, bw, bh)
        _text(canvas, 8, PANEL_H - 18, "%g mm" % t)
