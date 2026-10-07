# -*- coding: utf-8 -*-
"""Live preview for the Type Maker: plan, section / elevation and a shaded
3D view drawn from the type's REAL section shape (round, tube, I, RHS,
angle, channel, tee, rectangle) and the model's REAL line patterns, with
the chosen line weights, colours, cut / surface patterns and shading."""
import math

import clr
clr.AddReference("PresentationCore")
clr.AddReference("PresentationFramework")
clr.AddReference("WindowsBase")
from System.Windows import Point
from System.Windows.Controls import Canvas, TextBlock
from System.Windows.Media import Brushes, Color, DoubleCollection, Geometry, PointCollection, SolidColorBrush
from System.Windows.Shapes import Ellipse, Line, Path, Polygon, Rectangle

import sf_graphics as sg
import sf_profiles as sp

PANEL_H, GAP, TITLE = 175, 8, 18
PX_PER_PAPER_MM = 2.5  # how long a 1 mm dash on paper looks in the preview
LENGTH = {"beams": 4000.0, "columns": 3000.0}


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


def _dash(dashes, name, thickness):
    """Revit line pattern -> WPF dash array (in multiples of the stroke)."""
    segs = dashes.get(name) if dashes else None
    if not segs:
        return None
    return DoubleCollection(dash_values(segs, thickness))


def dash_values(segs, thickness):
    """[(kind, mm)] -> alternating [dash, gap, dash, gap...] in stroke units."""
    seq = []
    for kind, length in segs:
        is_gap = kind == "space"
        px = 0.8 if kind == "dot" else length * PX_PER_PAPER_MM
        val = max(px / thickness, 0.2)
        if seq and seq[-1][0] == is_gap:
            seq[-1][1] += val  # merge e.g. dash+dot
        else:
            seq.append([is_gap, val])
    if seq and seq[0][0]:
        seq.append(seq.pop(0))  # WPF arrays start with a dash
    if len(seq) % 2:
        seq.append([True, seq[-1][1]])
    return [v for _, v in seq]


def _stroke(shape, rgb, thickness, dash_array=None):
    shape.Stroke, shape.StrokeThickness = _brush(rgb), thickness
    if dash_array is not None:
        shape.StrokeDashArray = dash_array


def _line(parent, x1, y1, x2, y2, rgb, thickness, dash_array=None):
    ln = Line()
    ln.X1, ln.Y1, ln.X2, ln.Y2 = x1, y1, x2, y2
    _stroke(ln, rgb, thickness, dash_array)
    parent.Children.Add(ln)


def _text(parent, x, y, text):
    t = TextBlock()
    t.Text, t.FontSize, t.Foreground = text, 11, Brushes.DimGray
    Canvas.SetLeft(t, x)
    Canvas.SetTop(t, y)
    parent.Children.Add(t)


def _path_data(rings):
    """Even-odd path through screen-space rings (holes cut out)."""
    parts = ["F0"]
    for ring in rings:
        parts.append("M %.2f,%.2f" % ring[0])
        parts.extend("L %.2f,%.2f" % p for p in ring[1:])
        parts.append("Z")
    return " ".join(parts)


def _hatch(parent, rings, name, rgb):
    """Fill the shape with its cut / surface pattern, clipped to the shape."""
    if not name or name == "None":
        return
    xs = [p[0] for r in rings for p in r]
    ys = [p[1] for r in rings for p in r]
    x0, y0, w, h = min(xs), min(ys), max(xs) - min(xs), max(ys) - min(ys)
    if w < 1 or h < 1:
        return
    box = Canvas()
    box.Width, box.Height = w, h
    Canvas.SetLeft(box, x0)
    Canvas.SetTop(box, y0)
    box.Clip = Geometry.Parse(_path_data([[(x - x0, y - y0) for x, y in r] for r in rings]))
    br = _brush(rgb)
    if name == "Solid fill":
        r = Rectangle()
        r.Width, r.Height, r.Fill = w, h, br
        box.Children.Add(r)
    elif "concrete" in name.lower():
        seed = 7
        for i in range(int(w * h / 90) + 4):
            seed = (seed * 1103515245 + 12345) % 2147483648
            px = (seed % 1000) / 1000.0 * w
            seed = (seed * 1103515245 + 12345) % 2147483648
            py = (seed % 1000) / 1000.0 * h
            if i % 4 == 0:
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
        k = -h
        while k < w:
            ln = Line()
            ln.X1, ln.Y1, ln.X2, ln.Y2 = k, h, k + h, 0
            ln.Stroke, ln.StrokeThickness = br, 0.6
            box.Children.Add(ln)
            k += 7.0
    parent.Children.Add(box)


def _outline(parent, rings, rgb, thickness, dash_array=None):
    p = Path()
    p.Data = Geometry.Parse(_path_data(rings))
    _stroke(p, rgb, thickness, dash_array)
    parent.Children.Add(p)


def _shape2d(parent, outer, holes, cx, cy, scale, fill, fill_rgb, rgb, thickness, dash_array=None):
    """Draw a profile (mm, y up) centred at (cx, cy)."""
    to_screen = lambda ring: [(cx + x * scale, cy - y * scale) for x, y in ring]
    rings = [to_screen(outer)] + [to_screen(h) for h in holes]
    _hatch(parent, rings, fill, fill_rgb)
    _outline(parent, rings, rgb, thickness, dash_array)


def _scale_for(w, h, box_w, box_h):
    return min(box_w / max(w, 1.0), box_h / max(h, 1.0))


def _extrusion(parent, outer, holes, axis, length, g, cx, cy, box_w, box_h):
    """Shaded isometric extrusion of the profile. axis 'x' = beam along x,
    profile in (y, z); axis 'z' = column / wall, profile in (x, y)."""
    if axis == "x":
        P3 = lambda u, v, s: (s, u, v)
    else:
        P3 = lambda u, v, s: (u, v, s)
    c30 = math.cos(math.pi / 6)
    iso = lambda p: ((p[0] - p[1]) * c30, (p[0] + p[1]) * 0.5 - p[2])
    pts = [P3(u, v, s) for u, v in outer for s in (0.0, length)]
    xs = [iso(p)[0] for p in pts]
    ys = [iso(p)[1] for p in pts]
    sc = min(box_w / ((max(xs) - min(xs)) or 1), box_h / ((max(ys) - min(ys)) or 1))
    ox = cx - (max(xs) + min(xs)) / 2.0 * sc
    oy = cy - (max(ys) + min(ys)) / 2.0 * sc
    S = lambda p: (ox + iso(p)[0] * sc, oy + iso(p)[1] * sc)
    alpha = int(255 * (100 - int(g["transparency"])) / 100.0)
    centre = (sum(u for u, v in outer) / len(outer), sum(v for u, v in outer) / len(outer))
    faces = []
    n = len(outer)
    for i in range(n):
        (u1, v1), (u2, v2) = outer[i], outer[(i + 1) % n]
        nu, nv = v2 - v1, -(u2 - u1)  # edge normal, pointed away from the centre
        mu, mv = (u1 + u2) / 2.0 - centre[0], (v1 + v2) / 2.0 - centre[1]
        if nu * mu + nv * mv < 0:
            nu, nv = -nu, -nv
        nrm = P3(nu, nv, 0.0)
        quad = [P3(u1, v1, 0.0), P3(u2, v2, 0.0), P3(u2, v2, length), P3(u1, v1, length)]
        faces.append((quad, nrm))
    cap_n = P3(0.0, 0.0, 1.0)
    for quad, nrm in sorted(faces, key=lambda f: sum(p[0] + p[1] + p[2] for p in f[0])):
        ln = math.sqrt(sum(c * c for c in nrm)) or 1.0
        nx, ny, nz = [c / ln for c in nrm]
        if nx + ny + nz <= 0.01:
            continue  # facing away
        pg = Polygon()
        pg.Points = PointCollection([Point(*S(p)) for p in quad])
        pg.Fill = _brush(_shade(g["shade"], 0.72 + 0.18 * nx + 0.08 * ny + 0.35 * nz), alpha)
        pg.Stroke, pg.StrokeThickness = _brush(g["colour"]), 0.5
        parent.Children.Add(pg)
    # the end cap facing the viewer, with holes
    rings = [[S(P3(u, v, length)) for u, v in outer]] + [[S(P3(u, v, length)) for u, v in h] for h in holes]
    cap = Path()
    cap.Data = Geometry.Parse(_path_data(rings))
    cap.Fill = _brush(_shade(g["shade"], 1.1), alpha)
    cap.Stroke, cap.StrokeThickness = _brush(g["colour"]), max(0.6, _lw(g["proj_w"]) * 0.6)
    parent.Children.Add(cap)


def draw(canvas, key, prof, g, dashes=None):
    """prof: profile dict (sf_profiles) for columns / beams,
    {'shape': 'layer', 't': mm} for slabs / walls."""
    canvas.Children.Clear()
    W = canvas.Width
    bw, bh = W - 40, PANEL_H - TITLE - 22
    titles = {
        "columns": ("Plan - cut", "Elevation - projection", "3D shaded"),
        "beams": ("Plan - beam below slab (hidden lines)", "Section - cut", "3D shaded"),
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
    cut_w, proj_w, hid_w = _lw(g["cut_w"]), _lw(g["proj_w"]), _lw(g["hidden_w"])
    proj_dash = _dash(dashes, g["proj_pattern"], proj_w)
    hid_dash = _dash(dashes, g["hidden_pattern"], hid_w)
    if hid_dash is None and g["hidden_pattern"] not in ("Solid", "") and not dashes:
        hid_dash = DoubleCollection([4.0, 3.0])

    if key in ("columns", "beams"):
        outer, holes = sp.polygons(prof)
        w, h = prof["w"], prof["h"]
        label = "%s  %g x %g" % (prof.get("name", ""), round(w, 1), round(h, 1))
        if key == "columns":
            sc = _scale_for(w, h, bw * 0.6, bh * 0.85)
            _shape2d(canvas, outer, holes, cx, cys[0], sc, g["cut_fill"], g["cut_fill_colour"],
                     g["colour"], cut_w)
            # elevation: the silhouette width over a storey height
            sc2 = _scale_for(w, 3000.0, bw, bh)
            ew, eh = w * sc2, 3000.0 * sc2
            rect = [(cx - ew / 2, cys[1] - eh / 2), (cx + ew / 2, cys[1] - eh / 2),
                    (cx + ew / 2, cys[1] + eh / 2), (cx - ew / 2, cys[1] + eh / 2)]
            _hatch(canvas, [rect], g["surface_fill"], g["surface_colour"])
            _outline(canvas, [rect], g["colour"], proj_w, proj_dash)
            _extrusion(canvas, outer, holes, "z", 3000.0, g, cx, cys[2], bw * 0.7, bh)
            _text(canvas, 8, PANEL_H - 18, label)
        else:
            # plan: beam below the slab = its two edges in the hidden-line style
            sc = _scale_for(LENGTH["beams"], w, bw, bh * 0.5)
            x0, x1 = cx - LENGTH["beams"] * sc / 2, cx + LENGTH["beams"] * sc / 2
            for yy in (cys[0] - w * sc / 2, cys[0] + w * sc / 2):
                _line(canvas, x0, yy, x1, yy, g["colour"], hid_w, hid_dash)
            sc2 = _scale_for(w, h, bw * 0.6, bh * 0.85)
            _shape2d(canvas, outer, holes, cx, cys[1], sc2, g["cut_fill"], g["cut_fill_colour"],
                     g["colour"], cut_w)
            _extrusion(canvas, outer, holes, "x", LENGTH["beams"], g, cx, cys[2], bw, bh * 0.85)
            _text(canvas, 8, PANEL_H + GAP + PANEL_H - 18, label)
        return

    t = prof["t"]
    if key == "floors":
        rect = [(cx - bw * 0.4, cys[0] - bh * 0.37), (cx + bw * 0.4, cys[0] - bh * 0.37),
                (cx + bw * 0.4, cys[0] + bh * 0.37), (cx - bw * 0.4, cys[0] + bh * 0.37)]
        _hatch(canvas, [rect], g["surface_fill"], g["surface_colour"])
        _outline(canvas, [rect], g["colour"], proj_w, proj_dash)
        sec = [(-1500.0, -t / 2), (1500.0, -t / 2), (1500.0, t / 2), (-1500.0, t / 2)]
        sc = _scale_for(3000.0, max(t, 1.0), bw, bh)
        _shape2d(canvas, sec, [], cx, cys[1], sc, g["cut_fill"], g["cut_fill_colour"], g["colour"], cut_w)
        slab = [(-1500.0, -1500.0), (1500.0, -1500.0), (1500.0, 1500.0), (-1500.0, 1500.0)]
        _extrusion(canvas, slab, [], "z", t, g, cx, cys[2], bw, bh)
        _text(canvas, 8, PANEL_H + GAP + PANEL_H - 18, "%g mm" % t)
    else:
        plan = [(-1500.0, -t / 2), (1500.0, -t / 2), (1500.0, t / 2), (-1500.0, t / 2)]
        sc = _scale_for(3000.0, max(t, 1.0), bw, bh)
        _shape2d(canvas, plan, [], cx, cys[0], sc, g["cut_fill"], g["cut_fill_colour"], g["colour"], cut_w)
        sec = [(-t / 2, -1500.0), (t / 2, -1500.0), (t / 2, 1500.0), (-t / 2, 1500.0)]
        sc2 = _scale_for(max(t, 1.0), 3000.0, bw, bh)
        _shape2d(canvas, sec, [], cx, cys[1], sc2, g["cut_fill"], g["cut_fill_colour"], g["colour"], cut_w)
        _extrusion(canvas, plan, [], "z", 3000.0, g, cx, cys[2], bw, bh)
        _text(canvas, 8, PANEL_H - 18, "%g mm" % t)
