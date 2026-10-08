# -*- coding: utf-8 -*-
"""Symbol Designer: build EPL annotation families (grid / level heads,
section heads and tails, callouts, elevation marks, view titles, north
arrow, spot elevation, span direction, tags...) on a canvas. Drag shapes
and labels with the mouse or type exact values; the labels come from a
base family you pick. Builds the family, saves it into the EPL library
and loads it into the model."""
__title__ = "Symbol\nDesigner"

import os

import clr
clr.AddReference("PresentationCore")
clr.AddReference("PresentationFramework")
clr.AddReference("WindowsBase")
from System.Windows import Point, Size
from System.Windows.Controls import Canvas, TextBlock
from System.Windows.Media import Brushes, Color, DoubleCollection, FontFamily, PointCollection, SolidColorBrush
from System.Windows.Shapes import Ellipse, Line, Polygon, Rectangle

from pyrevit import forms, revit, script

import sf_audit as au
import sf_symbols as sy

doc = revit.doc
cfg = au.load_config()
PENS = cfg["line_weights"]["annotation"]
HEIGHTS = [str(h) for h in cfg["text"]["heights"]]
BLUE = SolidColorBrush(Color.FromRgb(30, 110, 230))
FIELDS = {
    "circle": (("X centre", "Y centre", "Radius", ""), True, False),
    "line": (("X1", "Y1", "X2", "Y2"), False, False),
    "rect": (("X corner", "Y corner", "Width", "Height"), True, False),
    "triangle": (("X centre", "Y centre", "Width", "Height"), True, True),
    "text": (("X", "Y", "", ""), False, False),
    "arrow": (("X start", "Y start", "X tip", "Y tip"), True, False),
    "dot": (("X centre", "Y centre", "Radius", ""), False, False),
    "polygon": (("", "", "", ""), True, False),
    "arc": (("X centre", "Y centre", "Radius", ""), False, False),
}


def num(text, default=None):
    try:
        return float(str(text).replace(",", "."))
    except Exception:
        return default


class Designer(forms.WPFWindow):
    def __init__(self):
        forms.WPFWindow.__init__(self, os.path.join(os.path.dirname(__file__), "ui.xaml"))
        self._loading = True
        self.sel = None
        self.drag = None
        self.design = None
        self.base_labels = []
        self.fam_map = {}
        self.fam_names = []
        for k in sy.KINDS:
            self.kinds.Items.Add(k[1])
        for i in range(1, 17):
            self.f_pen.Items.Add(str(i))
        for d in ("up", "down", "left", "right"):
            self.f_dir.Items.Add(d)
        for h in HEIGHTS:
            self.f_h.Items.Add(h)
        self.out_root.Text = os.path.join(os.environ["USERPROFILE"], "Desktop", "EPL_FAMILIES")
        self.canvas.SizeChanged += lambda s, e: self.redraw()
        self._loading = False
        self.kinds.SelectedIndex = 0

    # ------------------------------------------------------------ design
    def kind_key(self):
        return sy.KINDS[max(self.kinds.SelectedIndex, 0)][0]

    def kind_changed(self, sender, args):
        """List every loaded family of this kind; the first EPL one opens."""
        self.fam_map = sy.families_of_kind(doc, self.kind_key())
        self.fam_names = sorted(self.fam_map, key=lambda n: (not n.startswith("EPL"), n.lower()))
        self._loading = True
        self.fams.Items.Clear()
        for n in self.fam_names:
            tb = TextBlock()
            tb.Text = n
            self.fams.Items.Add(tb)
        self._loading = False
        if self.fam_names:
            self.fams.SelectedIndex = 0
        else:
            self.base_info.Text = "No family of this kind is loaded: starting from the EPL preset."
            self.set_design(sy.preset(self.kind_key(), cfg))

    def fam_picked(self, sender, args):
        if self._loading or self.fams.SelectedIndex < 0:
            return
        name = self.fam_names[self.fams.SelectedIndex]
        try:
            d = sy.import_family(doc, self.fam_map[name], self.kind_key())
        except Exception as ex:
            self.base_info.Text = "could not read %s: %s" % (name, ex)
            return
        self.base_labels = [(lab.get("shows", "label"), lab["x"], lab["y"], lab["h"]) for lab in d["labels"]]
        self.base_info.Text = "%d shapes, %d label(s): %s" % (
            len(d["shapes"]), len(d["labels"]), ", ".join(l.get("shows", "") for l in d["labels"]) or "none")
        if not name.startswith("EPL"):
            d["name"] = sy.KIND[self.kind_key()][2]  # building makes an EPL copy by default
        self.set_design(d)

    def set_design(self, d):
        self.design = d
        self.sel = None
        self.out_name.Text = d.get("name", "")
        self.out_folder.Text = d.get("folder", "")
        self.refresh_lists()
        self.redraw()

    def reset_preset(self, sender, args):
        self.set_design(sy.preset(self.kind_key(), cfg))

    def base_family(self):
        i = self.fams.SelectedIndex
        return self.fam_map.get(self.fam_names[i]) if 0 <= i < len(self.fam_names) else None

    def read_labels(self, sender, args):
        fam = self.base_family()
        if fam is None:
            forms.alert("Pick a base family first.")
            return
        self.base_labels = sy.family_labels(doc, fam)
        labs = self.design["labels"]
        # keep the designed positions; add labels the design does not know yet
        for i, (text, x, y, h) in enumerate(self.base_labels):
            if i >= len(labs):
                labs.append({"x": round(x, 1), "y": round(y, 1), "h": h, "font": cfg["text"]["font"]})
        del labs[len(self.base_labels):]
        self.base_info.Text = "%d label(s): %s" % (len(self.base_labels),
                                                   ", ".join(t for t, _, _, _ in self.base_labels) or "none")
        self.refresh_lists()
        self.redraw()

    def open_design(self, sender, args):
        if not os.path.isdir(sy.DESIGNS):
            os.makedirs(sy.DESIGNS)
        path = forms.pick_file(file_ext="json", init_dir=sy.DESIGNS)
        if path:
            self.set_design(sy.load_design(path))

    def save_design(self, sender, args):
        if not os.path.isdir(sy.DESIGNS):
            os.makedirs(sy.DESIGNS)
        self._sync_out()
        path = forms.save_file(file_ext="json", init_dir=sy.DESIGNS, default_name=self.design["name"])
        if path:
            sy.save_design(self.design, path)
            self.status.Text = "design saved: " + path

    # ------------------------------------------------------------ shapes
    def _add(self, s):
        self.design["shapes"].append(s)
        self.sel = ("shape", len(self.design["shapes"]) - 1)
        self.refresh_lists()
        self.redraw()

    def add_circle(self, sender, args):
        self._add(sy._c(0, 0, 4, 1))

    def add_line(self, sender, args):
        self._add(sy._l(-5, 0, 5, 0, 1))

    def add_rect(self, sender, args):
        self._add(sy._r(-5, -2.5, 10, 5, 1))

    def add_triangle(self, sender, args):
        self._add(sy._t(0, 0, 4, 4, "up", 1, True))

    def add_arrow(self, sender, args):
        self._add({"type": "arrow", "x1": -5, "y1": 0, "x2": 5, "y2": 0, "head": 2.5, "pen": 1, "fill": True})

    def add_dot(self, sender, args):
        self._add({"type": "dot", "x": 0, "y": 0, "r": 0.75, "pen": 1, "fill": True})

    def add_polygon(self, sender, args):
        self._add({"type": "polygon", "pts": [[-3, -2], [3, -2], [4, 2], [-2, 3]], "pen": 1, "fill": False})

    def _rotate(self, deg):
        item = self.current()
        if item is not None and self.sel[0] == "shape":
            item["rot"] = (float(item.get("rot", 0) or 0) + deg) % 360
            self.fill_props()
            self._update_list_text()
            self.redraw()

    def rot_left(self, sender, args):
        self._rotate(-15)

    def rot_right(self, sender, args):
        self._rotate(15)

    def add_text(self, sender, args):
        self._add({"type": "text", "x": 0, "y": 0, "text": "TEXT", "h": 2.5, "pen": 1})

    def duplicate(self, sender, args):
        if self.sel and self.sel[0] == "shape":
            s = dict(self.design["shapes"][self.sel[1]])
            sy.move(s, 2, -2)
            self._add(s)

    def delete(self, sender, args):
        if self.sel and self.sel[0] == "shape":
            del self.design["shapes"][self.sel[1]]
            self.sel = None
            self.refresh_lists()
            self.redraw()

    # ------------------------------------------------------- side lists
    def describe(self, s):
        t = s["type"]
        if t == "circle":
            return "Circle  r%g  pen %d%s" % (s["r"], s["pen"], "  filled" if s.get("fill") else "")
        if t == "line":
            return "Line  (%g,%g)-(%g,%g)  pen %d" % (s["x1"], s["y1"], s["x2"], s["y2"], s["pen"])
        if t == "rect":
            return "Rectangle  %gx%g  pen %d" % (s["w"], s["h"], s["pen"])
        if t == "triangle":
            return "Triangle %s  %gx%g%s" % (s["dir"], s["w"], s["h"], "  filled" if s.get("fill") else "")
        if t == "arrow":
            return "Arrow  (%g,%g)->(%g,%g)  head %g" % (s["x1"], s["y1"], s["x2"], s["y2"], s.get("head", 2.5))
        if t == "dot":
            return "Dot  r%g" % s["r"]
        if t == "polygon":
            return "Polygon  %d points%s" % (len(s["pts"]), "  filled" if s.get("fill") else "")
        if t == "arc":
            return "Arc  r%g  %g-%g deg  pen %d" % (s["r"], s["a0"], s["a1"], s.get("pen", 1))
        return "Text '%s'  %gmm" % (s.get("text", ""), s.get("h", 2.5))

    def refresh_lists(self):
        self._loading = True
        self.shapes.Items.Clear()
        for s in self.design["shapes"]:
            self.shapes.Items.Add(self.describe(s))
        self.labels.Items.Clear()
        for i, lab in enumerate(self.design["labels"]):
            self.labels.Items.Add(self._label_line(i, lab))
        if self.sel:
            lst = self.shapes if self.sel[0] == "shape" else self.labels
            lst.SelectedIndex = self.sel[1]
        self._loading = False
        self.fill_props()

    def _label_line(self, i, lab):
        name = lab.get("shows") or (self.base_labels[i][0] if i < len(self.base_labels) else "label %d" % (i + 1))
        return "%s  %gmm %s (%g, %g)" % (name, lab["h"], lab.get("font", ""), lab["x"], lab["y"])

    def shape_picked(self, sender, args):
        if not self._loading and self.shapes.SelectedIndex >= 0:
            self.sel = ("shape", self.shapes.SelectedIndex)
            self.labels.SelectedIndex = -1
            self.fill_props()
            self.redraw()

    def label_picked(self, sender, args):
        if not self._loading and self.labels.SelectedIndex >= 0:
            self.sel = ("label", self.labels.SelectedIndex)
            self.shapes.SelectedIndex = -1
            self.fill_props()
            self.redraw()

    # -------------------------------------------------------- properties
    def current(self):
        if not self.sel:
            return None
        kind, i = self.sel
        items = self.design["shapes"] if kind == "shape" else self.design["labels"]
        return items[i] if i < len(items) else None

    def fill_props(self):
        item = self.current()
        self._loading = True
        for f in (self.f_x, self.f_y, self.f_a, self.f_b, self.f_text, self.f_font):
            f.Text = ""
        if item is not None:
            if self.sel[0] == "label":
                names, can_fill, has_dir = ("X", "Y", "", ""), False, False
            else:
                names, can_fill, has_dir = FIELDS[item["type"]]
            for lbl, name in zip((self.l_x, self.l_y, self.l_a, self.l_b), names):
                lbl.Text = name
            if self.sel[0] == "shape" and item["type"] in ("line", "arrow"):
                vals = (item["x1"], item["y1"], item["x2"], item["y2"])
            elif self.sel[0] == "shape" and item["type"] == "polygon":
                vals = (None, None, None, None)
            else:
                vals = (item.get("x"), item.get("y"),
                        item.get("r", item.get("w")), item.get("h") if item.get("type") in ("rect", "triangle") else None)
            for box, v in zip((self.f_x, self.f_y, self.f_a, self.f_b), vals):
                box.Text = "" if v is None else "%g" % v
            self.f_pen.SelectedItem = str(int(item.get("pen", 1)))
            self.f_fill.IsChecked = bool(item.get("fill"))
            self.f_fill.IsEnabled = can_fill
            self.f_dir.IsEnabled = has_dir
            if has_dir:
                self.f_dir.SelectedItem = item.get("dir", "up")
            is_text = self.sel[0] == "label" or item["type"] == "text"
            is_poly = self.sel[0] == "shape" and item["type"] == "polygon"
            self.f_text.IsEnabled = self.sel[0] == "shape" and item["type"] in ("text", "polygon")
            if is_poly:
                self.f_text.Text = "; ".join("%g,%g" % (x, y) for x, y in item["pts"])
            else:
                self.f_text.Text = item.get("text", "") if self.f_text.IsEnabled else ""
            self.f_rot.IsEnabled = self.sel[0] == "shape"
            self.f_rot.Text = "%g" % float(item.get("rot", 0) or 0) if self.sel[0] == "shape" else ""
            self.f_head.IsEnabled = self.sel[0] == "shape" and item["type"] == "arrow"
            self.f_head.Text = "%g" % item.get("head", 2.5) if self.f_head.IsEnabled else ""
            self.f_h.IsEnabled = self.f_font.IsEnabled = is_text
            if is_text:
                self.f_h.Text = "%g" % item.get("h", 2.5)
                self.f_font.Text = item.get("font", cfg["text"]["font"])
            is_label = self.sel[0] == "label"
            self.f_sample.IsEnabled = is_label
            self.f_sample.Text = item.get("sample", "") if is_label else ""
            self.f_box.IsEnabled = self.f_gap.IsEnabled = is_label
            self.f_box.IsChecked = bool(item.get("box")) if is_label else False
            self.f_gap.Text = "%g" % item.get("box_offset", 1.0) if is_label else ""
        self._loading = False

    def prop_changed(self, sender, args):
        if self._loading:
            return
        item = self.current()
        if item is None:
            return
        x, y, a, b = num(self.f_x.Text), num(self.f_y.Text), num(self.f_a.Text), num(self.f_b.Text)
        if self.sel[0] == "shape" and item["type"] in ("line", "arrow"):
            for k, v in zip(("x1", "y1", "x2", "y2"), (x, y, a, b)):
                if v is not None:
                    item[k] = v
        elif self.sel[0] == "shape" and item["type"] == "polygon":
            pts = []
            for part in self.f_text.Text.split(";"):
                xy = [num(v) for v in part.split(",")]
                if len(xy) == 2 and None not in xy:
                    pts.append(xy)
            if len(pts) >= 2:
                item["pts"] = pts
        else:
            if x is not None:
                item["x"] = x
            if y is not None:
                item["y"] = y
            if self.sel[0] == "shape":
                if item["type"] in ("circle", "dot", "arc") and a:
                    item["r"] = a
                if item["type"] in ("rect", "triangle"):
                    if a:
                        item["w"] = a
                    if b:
                        item["h"] = b
        if self.sel[0] == "shape":
            if self.f_pen.SelectedItem:
                item["pen"] = int(self.f_pen.SelectedItem)
            item["fill"] = bool(self.f_fill.IsChecked) if self.f_fill.IsEnabled else item.get("fill", False)
            if item["type"] == "triangle" and self.f_dir.SelectedItem:
                item["dir"] = str(self.f_dir.SelectedItem)
            if item["type"] == "text":
                item["text"] = self.f_text.Text
            rot = num(self.f_rot.Text)
            if rot is not None:
                item["rot"] = rot
            if item["type"] == "arrow":
                head = num(self.f_head.Text)
                if head:
                    item["head"] = head
        if self.f_h.IsEnabled:
            picked = getattr(args, "AddedItems", None)
            h = num(picked[0]) if (sender is self.f_h and picked is not None and picked.Count) else num(self.f_h.Text)
            if h:
                item["h"] = h
            if self.f_font.Text.strip():
                item["font"] = self.f_font.Text.strip()
        if self.sel[0] == "label":
            item["sample"] = self.f_sample.Text
            item["box"] = bool(self.f_box.IsChecked)
            gap = num(self.f_gap.Text)
            if gap is not None:
                item["box_offset"] = gap
        self._update_list_text()
        self.redraw()

    def _update_list_text(self):
        self._loading = True
        kind, i = self.sel
        if kind == "shape":
            self.shapes.Items[i] = self.describe(self.design["shapes"][i])
            self.shapes.SelectedIndex = i
        else:
            lab = self.design["labels"][i]
            self.labels.Items[i] = self._label_line(i, lab)
            self.labels.SelectedIndex = i
        self._loading = False

    # ------------------------------------------------------------ canvas
    def _z(self):
        return float(self.zoom.Value)

    def _origin(self):
        return self.canvas.ActualWidth / 2.0, self.canvas.ActualHeight / 2.0

    def to_px(self, x, y):
        ox, oy = self._origin()
        return ox + x * self._z(), oy - y * self._z()

    def to_mm(self, px, py):
        ox, oy = self._origin()
        return (px - ox) / self._z(), (oy - py) / self._z()

    def _pen_px(self, pen):
        mm = PENS[max(0, min(len(PENS) - 1, int(pen) - 1))]
        return max(1.0, mm * self._z())

    def _ln(self, x1, y1, x2, y2, brush, w, dash=None):
        ln = Line()
        ln.X1, ln.Y1, ln.X2, ln.Y2 = x1, y1, x2, y2
        ln.Stroke, ln.StrokeThickness = brush, w
        if dash:
            ln.StrokeDashArray = DoubleCollection(dash)
        self.canvas.Children.Add(ln)

    def redraw(self):
        c = self.canvas
        if self.design is None or c.ActualWidth <= 0:
            return
        c.Children.Clear()
        z, W, H = self._z(), c.ActualWidth, c.ActualHeight
        ox, oy = self._origin()
        light = SolidColorBrush(Color.FromRgb(240, 240, 240))
        mid = SolidColorBrush(Color.FromRgb(215, 215, 215))
        k = int(-ox / z) - 1
        while ox + k * z < W:
            if z >= 8 or k % 5 == 0:
                self._ln(ox + k * z, 0, ox + k * z, H, mid if k % 5 == 0 else light, 1)
            k += 1
        k = int(-oy / z) - 1
        while oy + k * z < H:
            if z >= 8 or k % 5 == 0:
                self._ln(0, oy + k * z, W, oy + k * z, mid if k % 5 == 0 else light, 1)
            k += 1
        red = SolidColorBrush(Color.FromRgb(220, 60, 60))
        self._ln(ox - 12, oy, ox + 12, oy, red, 1)
        self._ln(ox, oy - 12, ox, oy + 12, red, 1)

        self.draw_context()
        for i, s in enumerate(self.design["shapes"]):
            brush = BLUE if self.sel == ("shape", i) else Brushes.Black
            self.draw_shape(s, brush)
        for i, lab in enumerate(self.design["labels"]):
            text = lab.get("sample") or (self.base_labels[i][0] if i < len(self.base_labels) else "LABEL %d" % (i + 1))
            self.draw_text(lab["x"], lab["y"], text, lab["h"],
                           BLUE if self.sel == ("label", i) else SolidColorBrush(Color.FromRgb(90, 90, 90)), True,
                           lab.get("box_offset", 1.0) if lab.get("box") else None)

    def draw_context(self):
        """What the symbol sits on in a drawing, in grey: grid / level /
        section line, a leader, or the element a tag points at."""
        grey = SolidColorBrush(Color.FromRgb(150, 150, 150))
        k, w = self.kind_key(), self._pen_px(1)
        ox, oy = self.to_px(0, 0)
        z = self._z()
        dash = [8.0, 3.0, 1.5, 3.0]
        if k == "grid_head":
            self._ln(ox, oy, ox, oy + 60 * z, grey, w, dash)
        elif k == "level_head":
            self._ln(ox, oy, ox - 80 * z, oy, grey, w, dash)
        elif k in ("section_head", "section_tail"):
            self._ln(ox, oy, ox, oy + 60 * z, grey, self._pen_px(3), dash)
        elif k == "callout_head":
            self._ln(ox, oy, ox - 20 * z, oy + 12 * z, grey, w)
        elif k in ("rebar_tag", "column_tag", "beam_tag", "foundation_tag"):
            r = Rectangle()
            r.Width, r.Height = 40 * z, 6 * z
            r.Stroke, r.StrokeThickness = grey, w
            Canvas.SetLeft(r, ox - 20 * z)
            Canvas.SetTop(r, oy + 12 * z)
            self.canvas.Children.Add(r)
            self._ln(ox, oy + 3 * z, ox, oy + 12 * z, grey, w)

    def draw_shape(self, s, brush):
        t, w = s["type"], self._pen_px(s.get("pen", 1))
        if t != "text":
            for p in sy.pieces(s):
                if p["kind"] == "arc":
                    pts = sy.arc_points(p)
                    for i in range(len(pts) - 1):
                        x1, y1 = self.to_px(*pts[i])
                        x2, y2 = self.to_px(*pts[i + 1])
                        self._ln(x1, y1, x2, y2, brush, w)
                    continue
                if p["kind"] == "circle":
                    e = Ellipse()
                    e.Width = e.Height = 2 * p["r"] * self._z()
                    e.Stroke, e.StrokeThickness = brush, w
                    if p.get("fill"):
                        e.Fill = brush
                    px, py = self.to_px(p["x"] - p["r"], p["y"] + p["r"])
                    Canvas.SetLeft(e, px)
                    Canvas.SetTop(e, py)
                    self.canvas.Children.Add(e)
                elif p.get("closed"):
                    pg = Polygon()
                    pg.Points = PointCollection([Point(*self.to_px(x, y)) for x, y in p["pts"]])
                    pg.Stroke, pg.StrokeThickness = brush, w
                    if p.get("fill"):
                        pg.Fill = brush
                    self.canvas.Children.Add(pg)
                else:
                    pts = p["pts"]
                    for i in range(len(pts) - 1):
                        x1, y1 = self.to_px(*pts[i])
                        x2, y2 = self.to_px(*pts[i + 1])
                        self._ln(x1, y1, x2, y2, brush, w)
            return
        if t == "line":
            x1, y1 = self.to_px(s["x1"], s["y1"])
            x2, y2 = self.to_px(s["x2"], s["y2"])
            self._ln(x1, y1, x2, y2, brush, w)
        elif t == "circle":
            e = Ellipse()
            e.Width = e.Height = 2 * s["r"] * self._z()
            e.Stroke, e.StrokeThickness = brush, w
            if s.get("fill"):
                e.Fill = brush
            px, py = self.to_px(s["x"] - s["r"], s["y"] + s["r"])
            Canvas.SetLeft(e, px)
            Canvas.SetTop(e, py)
            self.canvas.Children.Add(e)
        elif t in ("rect", "triangle"):
            if t == "rect":
                pts = [(s["x"], s["y"]), (s["x"] + s["w"], s["y"]), (s["x"] + s["w"], s["y"] + s["h"]),
                       (s["x"], s["y"] + s["h"])]
            else:
                pts = sy.triangle_points(s)
            pg = Polygon()
            pg.Points = PointCollection([Point(*self.to_px(x, y)) for x, y in pts])
            pg.Stroke, pg.StrokeThickness = brush, w
            if s.get("fill"):
                pg.Fill = brush
            self.canvas.Children.Add(pg)
        else:
            self.draw_text(s["x"], s["y"], s.get("text", ""), s.get("h", 2.5), brush, False)

    def draw_text(self, x, y, text, h, brush, boxed, border=None):
        tb = TextBlock()
        tb.Text = text
        tb.FontFamily = FontFamily(cfg["text"]["font"])
        tb.FontSize = max(6.0, h * self._z() / 0.72)  # Revit text height = capital height
        tb.Foreground = brush
        tb.Measure(Size(1e4, 1e4))
        tw, th = tb.DesiredSize.Width, tb.DesiredSize.Height
        px, py = self.to_px(x, y)
        Canvas.SetLeft(tb, px - tw / 2)
        Canvas.SetTop(tb, py - th / 2)
        self.canvas.Children.Add(tb)
        if border is not None:
            g = border * self._z()
            frame = Rectangle()
            frame.Width, frame.Height = tw + 2 * g, th + 2 * g
            frame.Stroke, frame.StrokeThickness = Brushes.Black, self._pen_px(1)
            Canvas.SetLeft(frame, px - tw / 2 - g)
            Canvas.SetTop(frame, py - th / 2 - g)
            self.canvas.Children.Add(frame)
        if boxed:
            r = Rectangle()
            r.Width, r.Height = tw + 4, th
            r.Stroke, r.StrokeThickness = brush, 1
            r.StrokeDashArray = DoubleCollection([3.0, 2.0])
            Canvas.SetLeft(r, px - tw / 2 - 2)
            Canvas.SetTop(r, py - th / 2)
            self.canvas.Children.Add(r)

    def zoom_changed(self, sender, args):
        self.redraw()

    # ------------------------------------------------------------- mouse
    def _hit(self, mx, my):
        tol = 6.0 / self._z()
        for i in range(len(self.design["labels"]) - 1, -1, -1):
            lab = self.design["labels"][i]
            if abs(lab["x"] - mx) <= lab["h"] * 2 + tol and abs(lab["y"] - my) <= lab["h"] / 2 + tol:
                return ("label", i)
        for i in range(len(self.design["shapes"]) - 1, -1, -1):
            x0, y0, x1, y1 = sy.bounds(self.design["shapes"][i])
            if x0 - tol <= mx <= x1 + tol and y0 - tol <= my <= y1 + tol:
                return ("shape", i)
        return None

    def canvas_down(self, sender, args):
        p = args.GetPosition(self.canvas)
        mx, my = self.to_mm(p.X, p.Y)
        self.sel = self._hit(mx, my)
        self.drag = (mx, my) if self.sel else None
        if self.sel:
            self.canvas.CaptureMouse()
        self.refresh_lists()
        self.redraw()

    def canvas_move(self, sender, args):
        p = args.GetPosition(self.canvas)
        mx, my = self.to_mm(p.X, p.Y)
        self.cursor.Text = "x %.1f   y %.1f mm" % (mx, my)
        if not self.drag or not self.sel:
            return
        dx, dy = mx - self.drag[0], my - self.drag[1]
        step = 0.5 if self.snap.IsChecked else 0.0
        if step:
            dx, dy = round(dx / step) * step, round(dy / step) * step
        if dx == 0 and dy == 0:
            return
        item = self.current()
        if self.sel[0] == "shape":
            sy.move(item, dx, dy)
        else:
            item["x"] += dx
            item["y"] += dy
        self.drag = (self.drag[0] + dx, self.drag[1] + dy)
        self.fill_props()
        self.redraw()

    def canvas_up(self, sender, args):
        if self.drag:
            self.canvas.ReleaseMouseCapture()
            self.drag = None
            if self.sel:
                self._update_list_text()

    # ------------------------------------------------------------- build
    def _sync_out(self):
        fam = self.base_family()
        self.design["base"] = fam.Name if fam else self.design.get("base", "")
        self.design["name"] = self.out_name.Text.strip()
        self.design["folder"] = self.out_folder.Text.strip()
        self.design["font"] = cfg["text"]["font"]

    def build_click(self, sender, args):
        self._sync_out()
        if not self.design["base"]:
            forms.alert("Pick a base family (it provides the labels).")
            return
        choice = forms.CommandSwitchWindow.show(
            ["Save as EPL copy '%s' (keep the original)" % self.design["name"],
             "Overwrite '%s' in this model" % self.design["base"]],
            message="What should happen to the original family?")
        if not choice:
            return
        mode = "copy" if choice.startswith("Save as") else "overwrite"
        log = []
        try:
            sy.build(doc, self.design, mode, self.out_root.Text.strip(),
                     bool(self.save_file.IsChecked), bool(self.load_model.IsChecked), log.append)
            if self.load_model.IsChecked:
                built = self.design["name"] if mode == "copy" else self.design["base"]
                log += sy.verify(doc, self.design, built, self.kind_key())
            self.status.Text = "\n".join(log) or "done"
            keep = self.design["name"]
            self.kind_changed(None, None)
            if keep in self.fam_names:
                self.fams.SelectedIndex = self.fam_names.index(keep)
        except Exception as ex:
            self.status.Text = "FAILED: %s" % ex
        path = au.write_log(["Symbol Designer: %s" % self.design["name"]] + log, cfg, "symbol_designer")
        self.status.Text += "\nlog: " + path


Designer().ShowDialog()
