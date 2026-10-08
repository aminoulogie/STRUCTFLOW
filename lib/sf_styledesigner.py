# -*- coding: utf-8 -*-
"""Style Designer: dimension styles and text types on a live canvas.
The preview is drawn at paper size (x zoom) with your pen table; Apply
writes the values to the Revit type, Save as new duplicates it first."""
import math
import os

import clr
clr.AddReference("PresentationCore")
clr.AddReference("PresentationFramework")
clr.AddReference("WindowsBase")
from System.Windows import FontStyles, FontWeights, Point, Size, TextDecorations
from System.Windows.Controls import Canvas, TextBlock
from System.Windows.Media import Brushes, Color, FontFamily, PointCollection, SolidColorBrush
from System.Windows.Shapes import Ellipse, Line, Polygon, Rectangle

from pyrevit import forms
from Autodesk.Revit.DB import (
    DimensionType, ElementId, ElementType, FilteredElementCollector, StorageType,
    TextNoteType, Transaction,
)

import sf_audit as au
import sf_beamrebar as br

MM = br.MM
XAML = os.path.join(os.path.dirname(__file__), "ui_style_designer.xaml")
FONTS = ["Arial", "Arial Narrow", "ISOCPEUR", "Calibri", "Segoe UI", "Tahoma", "Verdana"]
KINDS = ["Dimension styles", "Text types"]

# field: (parameter name on dimension types, on text types, kind)
PARAMS = {
    "font": ("Text Font", "Text Font", "str"),
    "size": ("Text Size", "Text Size", "mm"),
    "width": ("Width Factor", "Width Factor", "float"),
    "bold": ("Bold", "Bold", "bool"),
    "italic": ("Italic", "Italic", "bool"),
    "underline": ("Underline", "Underline", "bool"),
    "colour": ("Color", "Color", "colour"),
    "pen": ("Line Weight", "Line Weight", "int"),
    "opaque": ("Text Background", "Background", "opaque"),
    "tick": ("Tick Mark", None, "id"),
    "tick_pen": ("Tick Mark Line Weight", None, "int"),
    "gap": ("Witness Line Gap to Element", None, "mm"),
    "ext": ("Witness Line Extension", None, "mm"),
    "dimext": ("Dimension Line Extension", None, "mm"),
    "offset": ("Text Offset", None, "mm"),
    "prefix": ("Dimension Prefix", None, "str"),
    "suffix": ("Dimension Suffix", None, "str"),
    "border": (None, "Show Border", "bool"),
    "border_offset": (None, "Leader/Border Offset", "mm"),
    "leader": (None, "Leader Arrowhead", "id"),
}


def arrowheads(doc):
    out = {"(none)": ElementId.InvalidElementId}
    for t in FilteredElementCollector(doc).OfClass(ElementType):
        try:
            if t.FamilyName == "Arrowhead":
                out[br.ename(t)] = t.Id
        except Exception:
            pass
    return out


def read(doc, el, is_dim):
    vals = {}
    for key, (dname, tname, kind) in PARAMS.items():
        name = dname if is_dim else tname
        p = el.LookupParameter(name) if name else None
        if p is None:
            continue
        if kind == "str":
            vals[key] = p.AsString() or ""
        elif kind == "mm":
            vals[key] = round(p.AsDouble() / MM, 3)
        elif kind == "float":
            vals[key] = p.AsDouble()
        elif kind in ("bool",):
            vals[key] = bool(p.AsInteger())
        elif kind == "int":
            vals[key] = p.AsInteger()
        elif kind == "opaque":
            vals[key] = p.AsInteger() == 0
        elif kind == "colour":
            c = p.AsInteger()
            vals[key] = "%d,%d,%d" % (c & 255, (c >> 8) & 255, (c >> 16) & 255)
        elif kind == "id":
            vals[key] = p.AsElementId()
    return vals


def write(doc, el, is_dim, vals, log):
    for key, val in vals.items():
        dname, tname, kind = PARAMS[key]
        name = dname if is_dim else tname
        p = el.LookupParameter(name) if name else None
        if p is None or p.IsReadOnly:
            continue
        try:
            if kind == "str":
                p.Set(val)
            elif kind == "mm":
                p.Set(float(val) * MM)
            elif kind == "float":
                p.Set(float(val))
            elif kind == "bool":
                p.Set(1 if val else 0)
            elif kind == "int":
                p.Set(int(val))
            elif kind == "opaque":
                p.Set(0 if val else 1)
            elif kind == "colour":
                r, g, b = [int(x) for x in str(val).split(",")]
                p.Set(r + g * 256 + b * 65536)
            elif kind == "id":
                p.Set(val)
        except Exception as ex:
            log("%s not set: %s" % (name, br._err(ex)))


def _num(text, default=None):
    try:
        return float(str(text).replace(",", "."))
    except Exception:
        return default


class StyleDesigner(forms.WPFWindow):
    def __init__(self, doc, start=None):
        forms.WPFWindow.__init__(self, XAML)
        self.doc = doc
        self.cfg = au.load_config()
        self.pens = self.cfg["line_weights"]["annotation"]
        self._loading = True
        self.heads = arrowheads(doc)
        for k in KINDS:
            self.kind.Items.Add(k)
        for f in FONTS:
            self.font.Items.Add(f)
        for h in self.cfg["text"]["heights"]:
            self.size.Items.Add("%g" % h)
        for i in range(1, 17):
            self.pen.Items.Add(str(i))
            self.tick_pen.Items.Add(str(i))
        for name in sorted(self.heads):
            self.tick.Items.Add(name)
            self.leader.Items.Add(name)
        self.sample.Text = "5000"
        self.sample_text.Text = "TYPICAL NOTE TEXT"
        self.canvas.SizeChanged += lambda s, e: self.redraw()
        self._loading = False
        self.kind.SelectedIndex = 1 if isinstance(start, TextNoteType) else 0
        if start is not None:
            for i, t in enumerate(self.type_list):
                if t.Id == start.Id:
                    self.types.SelectedIndex = i

    # ----------------------------------------------------------- types
    @property
    def is_dim(self):
        return self.kind.SelectedIndex == 0

    def kind_changed(self, sender, args):
        cls = DimensionType if self.is_dim else TextNoteType
        self.type_list = sorted([t for t in FilteredElementCollector(self.doc).OfClass(cls) if br.ename(t)],
                                key=lambda t: br.ename(t).lower())
        self.types.Items.Clear()
        for t in self.type_list:
            tb = TextBlock()
            tb.Text = br.ename(t)
            self.types.Items.Add(tb)
        from System.Windows import Visibility
        self.dim_panel.Visibility = Visibility.Visible if self.is_dim else Visibility.Collapsed
        self.text_panel.Visibility = Visibility.Collapsed if self.is_dim else Visibility.Visible
        if self.type_list:
            self.types.SelectedIndex = 0

    def current(self):
        i = self.types.SelectedIndex
        return self.type_list[i] if 0 <= i < len(self.type_list) else None

    def type_changed(self, sender, args):
        self.load_values()

    def load_values(self):
        el = self.current()
        if el is None:
            return
        v = read(self.doc, el, self.is_dim)
        self._loading = True
        self.font.Text = v.get("font", "Arial")
        self.size.Text = "%g" % v.get("size", 2.5)
        self.width.Text = "%g" % v.get("width", 1.0)
        for k in ("bold", "italic", "underline", "opaque", "border"):
            getattr(self, k).IsChecked = bool(v.get(k, False))
        self.colour.Text = v.get("colour", "0,0,0")
        self.pen.SelectedItem = str(v.get("pen", 1))
        self.tick_pen.SelectedItem = str(v.get("tick_pen", v.get("pen", 1)))
        for k in ("gap", "ext", "dimext", "offset", "border_offset"):
            getattr(self, k).Text = "%g" % v.get(k, 0.0)
        self.prefix.Text = v.get("prefix", "")
        self.suffix.Text = v.get("suffix", "")
        for combo, key in ((self.tick, "tick"), (self.leader, "leader")):
            name = [n for n, i in self.heads.items() if i == v.get(key)]
            combo.SelectedItem = name[0] if name else "(none)"
        self.new_name.Text = br.ename(el) + " copy"
        self._loading = False
        self.redraw()

    def values(self):
        def picked(combo, args_sender=None):
            return combo.Text
        v = {"font": self.font.Text.strip() or "Arial", "size": _num(self.size.Text, 2.5),
             "width": _num(self.width.Text, 1.0), "colour": self.colour.Text.strip() or "0,0,0"}
        for k in ("bold", "italic", "underline", "opaque"):
            v[k] = bool(getattr(self, k).IsChecked)
        if self.pen.SelectedItem:
            v["pen"] = int(self.pen.SelectedItem)
        if self.is_dim:
            for k in ("gap", "ext", "dimext", "offset"):
                v[k] = _num(getattr(self, k).Text, 0.0)
            if self.tick_pen.SelectedItem:
                v["tick_pen"] = int(self.tick_pen.SelectedItem)
            v["prefix"], v["suffix"] = self.prefix.Text, self.suffix.Text
            if self.tick.SelectedItem:
                v["tick"] = self.heads[str(self.tick.SelectedItem)]
        else:
            v["border"] = bool(self.border.IsChecked)
            v["border_offset"] = _num(self.border_offset.Text, 1.0)
            if self.leader.SelectedItem:
                v["leader"] = self.heads[str(self.leader.SelectedItem)]
        return v

    def changed(self, sender, args):
        if self._loading:
            return
        picked = getattr(args, "AddedItems", None)
        if picked is not None and picked.Count and sender in (self.size, self.font):
            sender.Text = str(picked[0])
        self.redraw()

    def redraw_evt(self, sender, args):
        self.redraw()

    # --------------------------------------------------------- preview
    def _pen(self, pen):
        mm = self.pens[max(0, min(len(self.pens) - 1, int(pen) - 1))]
        return max(1.0, mm * float(self.zoom.Value))

    def _brush(self, rgb):
        try:
            r, g, b = [int(x) for x in rgb.split(",")]
            return SolidColorBrush(Color.FromRgb(r, g, b))
        except Exception:
            return Brushes.Black

    def _ln(self, x1, y1, x2, y2, brush, w):
        ln = Line()
        ln.X1, ln.Y1, ln.X2, ln.Y2 = x1, y1, x2, y2
        ln.Stroke, ln.StrokeThickness = brush, w
        self.canvas.Children.Add(ln)

    def _text(self, v, text, cx, base_y):
        """Text sitting on base_y (screen), centred on cx. Returns (x0, y0, w, h)."""
        z = float(self.zoom.Value)
        tb = TextBlock()
        tb.Text = text
        try:
            tb.FontFamily = FontFamily(v["font"])
        except Exception:
            pass
        tb.FontSize = max(5.0, v["size"] * z / 0.72)  # Revit size = capital height
        if v.get("bold"):
            tb.FontWeight = FontWeights.Bold
        if v.get("italic"):
            tb.FontStyle = FontStyles.Italic
        if v.get("underline"):
            tb.TextDecorations = TextDecorations.Underline
        tb.Foreground = self._brush(v["colour"])
        from System.Windows.Media import ScaleTransform
        tb.LayoutTransform = ScaleTransform(max(0.3, v.get("width", 1.0)), 1.0)
        tb.Measure(Size(1e5, 1e5))
        w, h = tb.DesiredSize.Width, tb.DesiredSize.Height
        x0, y0 = cx - w / 2.0, base_y - h
        if v.get("opaque"):
            r = Rectangle()
            r.Width, r.Height, r.Fill = w, h, Brushes.White
            Canvas.SetLeft(r, x0)
            Canvas.SetTop(r, y0)
            self.canvas.Children.Add(r)
        Canvas.SetLeft(tb, x0)
        Canvas.SetTop(tb, y0)
        self.canvas.Children.Add(tb)
        return x0, y0, w, h

    def _tick(self, x, y, name, brush, w, direction):
        z = float(self.zoom.Value)
        s = 1.5 * z
        low = (name or "").lower()
        if "dot" in low:
            e = Ellipse()
            e.Width = e.Height = 1.2 * z
            e.Fill = brush
            Canvas.SetLeft(e, x - 0.6 * z)
            Canvas.SetTop(e, y - 0.6 * z)
            self.canvas.Children.Add(e)
        elif "arrow" in low:
            pg = Polygon()
            d = direction
            pg.Points = PointCollection([Point(x, y), Point(x + d * 2.5 * z, y - 0.7 * z), Point(x + d * 2.5 * z, y + 0.7 * z)])
            pg.Stroke, pg.StrokeThickness = brush, 1
            if "filled" in low:
                pg.Fill = brush
            self.canvas.Children.Add(pg)
        elif name and name != "(none)":
            self._ln(x - s, y + s, x + s, y - s, brush, w)

    def redraw(self):
        c = self.canvas
        if c.ActualWidth <= 0 or self.current() is None:
            return
        c.Children.Clear()
        try:
            v = self.values()
        except Exception:
            return
        z = float(self.zoom.Value)
        W, H = c.ActualWidth, c.ActualHeight
        cx, cy = W / 2.0, H / 2.0
        brush = self._brush(v["colour"])
        grey = SolidColorBrush(Color.FromRgb(160, 160, 160))
        if self.is_dim:
            half = min(W * 0.35, 40 * z)
            dim_y = cy - 8 * z
            for x in (cx - half, cx + half):
                self._ln(x, cy + 10 * z, x, cy, grey, 2)  # the dimensioned element
                self._ln(x, cy - v["gap"] * z, x, dim_y - v["ext"] * z, brush, self._pen(v.get("pen", 1)))
            de = v["dimext"] * z
            self._ln(cx - half - de, dim_y, cx + half + de, dim_y, brush, self._pen(v.get("pen", 1)))
            tick = str(self.tick.SelectedItem or "")
            tp = self._pen(v.get("tick_pen", v.get("pen", 1)))
            self._tick(cx - half, dim_y, tick, brush, tp, 1)
            self._tick(cx + half, dim_y, tick, brush, tp, -1)
            self._text(v, "%s%s%s" % (v.get("prefix", ""), self.sample.Text, v.get("suffix", "")),
                       cx, dim_y - v["offset"] * z - 0.5)
        else:
            x0, y0, w, h = self._text(v, self.sample_text.Text, cx, cy)
            if v.get("border"):
                g = v["border_offset"] * z
                r = Rectangle()
                r.Width, r.Height = w + 2 * g, h + 2 * g
                r.Stroke, r.StrokeThickness = brush, self._pen(v.get("pen", 1))
                Canvas.SetLeft(r, x0 - g)
                Canvas.SetTop(r, y0 - g)
                c.Children.Add(r)
            # a leader to show the arrowhead
            lx, ly = x0 - 3 * z, y0 + h / 2.0
            ex, ey = lx - 15 * z, ly + 10 * z
            self._ln(lx, ly, ex + 1, ey - 1, brush, self._pen(v.get("pen", 1)))
            self._tick(ex, ey, str(self.leader.SelectedItem or ""), brush, self._pen(v.get("pen", 1)), 1)

    # ------------------------------------------------------------ save
    def _write(self, el):
        log = []
        t = Transaction(self.doc, "StructFlow Style Designer")
        t.Start()
        try:
            write(self.doc, el, self.is_dim, self.values(), log.append)
            t.Commit()
        except Exception as ex:
            t.RollBack()
            log.append("nothing saved: %s" % br._err(ex))
        return log

    def apply_click(self, sender, args):
        el = self.current()
        if el is None:
            return
        log = self._write(el)
        self.status.Text = "\n".join(log) or "saved to %s" % br.ename(el)

    def save_new_click(self, sender, args):
        el = self.current()
        name = self.new_name.Text.strip()
        if el is None or not name:
            return
        t = Transaction(self.doc, "StructFlow new style")
        t.Start()
        try:
            new = el.Duplicate(name)
            write(self.doc, new, self.is_dim, self.values(), lambda m: None)
            t.Commit()
        except Exception as ex:
            t.RollBack()
            self.status.Text = "not created: %s" % br._err(ex)
            return
        self.kind_changed(None, None)
        for i, ty in enumerate(self.type_list):
            if ty.Id == new.Id:
                self.types.SelectedIndex = i
        self.status.Text = "created %s" % name

    def revert_click(self, sender, args):
        self.load_values()
