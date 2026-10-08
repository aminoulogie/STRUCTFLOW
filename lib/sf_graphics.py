# -*- coding: utf-8 -*-
"""StructFlow graphics + materials for structural concrete elements.

How an element looks in Revit comes from two places:
- the category's Object Styles: line weight / colour / pattern (cut and
  projection), plus the 'hidden lines' subcategory used for beams under
  slabs, footings below ground, etc.
- its material: cut pattern (hatch in plan cuts and sections), surface
  pattern (elevations / 3D), shaded colour and transparency.
This module reads and writes both, and holds the presets (EPL = the
recommended UK configuration)."""
import json
import os

from Autodesk.Revit.DB import (
    BuiltInCategory, BuiltInParameter, Color, ElementId, FillPatternElement,
    FillPatternTarget, FilteredElementCollector, GraphicsStyleType,
    LinePatternElement, Material, MaterialAspect, PropertySetElement, StructuralAsset,
    StructuralAssetClass, StructuralBehavior, UnitTypeId, UnitUtils,
)

import sf_beamrebar as br

SETTINGS = os.path.join(os.environ["APPDATA"], "pyRevit", "StructFlow_graphics.json")

# key: (label, category, hidden-lines subcategory)
CATS = {
    "columns": ("Columns", BuiltInCategory.OST_StructuralColumns,
                BuiltInCategory.OST_HiddenStructuralColumnLines),
    "beams": ("Beams", BuiltInCategory.OST_StructuralFraming,
              BuiltInCategory.OST_HiddenStructuralFramingLines),
    "floors": ("Slabs", BuiltInCategory.OST_Floors, BuiltInCategory.OST_HiddenFloorLines),
    "walls": ("Walls", BuiltInCategory.OST_Walls, BuiltInCategory.OST_HiddenWallLines),
    "foundations": ("Foundations", BuiltInCategory.OST_StructuralFoundation,
                    BuiltInCategory.OST_HiddenStructuralFoundationLines),
}

# BS EN 1992-1-1 Table 3.1: grade -> (fck MPa, Ecm GPa)
GRADES = [
    ("C25/30", 25, 31.0), ("C28/35", 28, 32.3), ("C30/37", 30, 33.0),
    ("C32/40", 32, 33.3), ("C35/45", 35, 34.0), ("C40/50", 40, 35.0),
    ("C45/55", 45, 36.0), ("C50/60", 50, 37.0),
]

NAMED_COLOURS = [
    ("Black", "0,0,0"), ("Dark grey", "80,80,80"), ("Mid grey", "128,128,128"),
    ("Light grey", "192,192,192"), ("Concrete", "200,200,195"), ("White", "255,255,255"),
    ("Pink", "255,0,128"), ("Magenta", "255,0,255"), ("Red", "220,30,30"),
    ("Orange", "255,140,0"), ("Yellow", "230,200,0"), ("Green", "0,160,70"),
    ("Cyan", "0,170,220"), ("Blue", "30,80,220"), ("Brown", "140,90,50"),
]


def _g(cut_w, proj_w, colour, cut_fill, cut_fill_colour, shade, hidden="Hidden",
       hidden_w=1, proj_pattern="Solid", surface_fill="None", surface_colour="128,128,128",
       transparency=0):
    return {"cut_w": cut_w, "proj_w": proj_w, "colour": colour, "proj_pattern": proj_pattern,
            "hidden_pattern": hidden, "hidden_w": hidden_w,
            "cut_fill": cut_fill, "cut_fill_colour": cut_fill_colour,
            "surface_fill": surface_fill, "surface_colour": surface_colour,
            "shade": shade, "transparency": transparency}


# EPL: print-first UK structural drawings.
# - black lines everywhere (crisp on A0 and A3 reductions, no colour printing needed)
# - heavy cut lines on vertical elements (columns / walls) so the structure reads first
# - solid grey cut fill instead of the concrete stipple: stays clean at 1:100 GA,
#   and at 1:20 / 1:25 sections the rebar and tags stand out against it
# - columns and walls a shade darker than beams and slabs in plan
# - no surface patterns (clean elevations), soft concrete greys in 3D
# - beams under slabs and footings below ground shown dashed (hidden lines)
PRESETS = {
    "EPL (recommended UK)": {
        "columns": _g(6, 3, "0,0,0", "Solid fill", "150,150,150", "165,165,160"),
        "walls": _g(5, 2, "0,0,0", "Solid fill", "170,170,170", "180,180,175"),
        "beams": _g(4, 2, "0,0,0", "Solid fill", "205,205,205", "195,195,190"),
        "floors": _g(3, 1, "0,0,0", "Solid fill", "220,220,220", "210,210,205"),
        # below ground: dashed in plans, mid grey cut in sections
        "foundations": _g(4, 2, "0,0,0", "Solid fill", "185,185,185", "150,150,145"),
    },
    # one colour per element type: model reviews and clash coordination
    "Colour coordination": {
        "columns": _g(5, 2, "255,0,128", "Solid fill", "255,190,220", "255,120,180"),
        "walls": _g(5, 2, "255,140,0", "Solid fill", "255,215,170", "255,180,110"),
        "beams": _g(4, 2, "30,80,220", "Solid fill", "190,205,255", "120,150,240"),
        "floors": _g(3, 1, "0,160,70", "Solid fill", "190,235,200", "140,210,160"),
        "foundations": _g(4, 2, "140,90,50", "Solid fill", "225,200,175", "180,140,100"),
    },
    # classic hand-drawn look: concrete stipple in cut, everything black
    "Classic concrete hatch": {
        "columns": _g(5, 2, "0,0,0", "Concrete", "0,0,0", "190,190,190"),
        "walls": _g(5, 2, "0,0,0", "Concrete", "0,0,0", "190,190,190"),
        "beams": _g(4, 2, "0,0,0", "Concrete", "0,0,0", "200,200,200"),
        "floors": _g(3, 1, "0,0,0", "Concrete", "0,0,0", "210,210,210"),
        "foundations": _g(4, 2, "0,0,0", "Concrete", "0,0,0", "180,180,180"),
    },
}

DEFAULT_GRADE = {"columns": "C32/40", "walls": "C32/40", "beams": "C32/40", "floors": "C32/40",
                 "foundations": "C28/35"}  # BS 8500 foundations commonly C28/35 (DC-2 ground)


def default_material(key):
    grade = DEFAULT_GRADE[key]
    fck, ecm = [(f, e) for g, f, e in GRADES if g == grade][0]
    return {"name": "Concrete %s - %s" % (grade, CATS[key][0]), "grade": grade,
            "fck": fck, "ecm": ecm, "density": 2500.0, "poisson": 0.2, "thermal": 10.0,
            "description": "Reinforced concrete, cast in situ, %s to BS 8500 / BS EN 206" % grade,
            "keynote": ""}


# ------------------------------------------------------------ persistence
def load_saved():
    try:
        with open(SETTINGS) as f:
            return json.load(f)
    except Exception:
        return {}


def save(key, graphics, material):
    data = load_saved()
    data[key] = {"graphics": graphics, "material": material}
    try:
        with open(SETTINGS, "w") as f:
            json.dump(data, f, indent=1, sort_keys=True)
    except Exception:
        pass


# --------------------------------------------------------------- helpers
def parse_rgb(text):
    for name, rgb in NAMED_COLOURS:
        if text.strip().lower() == name.lower():
            text = rgb
    parts = [int(float(p)) for p in text.replace(";", ",").split(",")]
    if len(parts) != 3 or any(p < 0 or p > 255 for p in parts):
        raise ValueError("colour must be a name or R,G,B (0-255)")
    return parts


def rgb_text(c):
    return "%d,%d,%d" % (c.Red, c.Green, c.Blue)


def colour_label(rgb):
    for name, val in NAMED_COLOURS:
        if val == rgb:
            return name
    return rgb


def _rcolor(rgb):
    r, g, b = parse_rgb(rgb)
    return Color(r, g, b)


def line_patterns(doc):
    out = {"Solid": LinePatternElement.GetSolidPatternId()}
    for lp in FilteredElementCollector(doc).OfClass(LinePatternElement):
        out[lp.Name] = lp.Id
    return out


def fill_patterns(doc, target=FillPatternTarget.Drafting):
    out = {}
    for fp in FilteredElementCollector(doc).OfClass(FillPatternElement):
        pat = fp.GetFillPattern()
        if pat.Target == target or pat.IsSolidFill:
            out["Solid fill" if pat.IsSolidFill else fp.Name] = fp.Id
    return out


def _pattern_id(table, name):
    if not name or name == "None":
        return ElementId.InvalidElementId
    if name in table:
        return table[name]
    for k, v in table.items():  # loose match, e.g. "Concrete" -> "Concrete [Drafting]"
        if name.lower() in k.lower():
            return v
    return ElementId.InvalidElementId


def _name_of(table, pid):
    for k, v in table.items():
        if v == pid:
            return k
    return "None"


# ------------------------------------------------------------- read/write
def read_current(doc, key, material=None):
    """Graphics as they are in the model now (object styles + material)."""
    cat = doc.Settings.Categories.get_Item(CATS[key][1])
    hidden = doc.Settings.Categories.get_Item(CATS[key][2])
    lps, fps = line_patterns(doc), fill_patterns(doc)
    g = _g(cat.GetLineWeight(GraphicsStyleType.Cut) or 1,
           cat.GetLineWeight(GraphicsStyleType.Projection) or 1,
           rgb_text(cat.LineColor), "None", "0,0,0", "128,128,128",
           proj_pattern=_name_of(lps, cat.GetLinePatternId(GraphicsStyleType.Projection)))
    if hidden is not None:
        g["hidden_pattern"] = _name_of(lps, hidden.GetLinePatternId(GraphicsStyleType.Projection))
        g["hidden_w"] = hidden.GetLineWeight(GraphicsStyleType.Projection) or 1
    if material is not None:
        g["cut_fill"] = _name_of(fps, material.CutForegroundPatternId)
        g["cut_fill_colour"] = rgb_text(material.CutForegroundPatternColor)
        g["surface_fill"] = _name_of(fill_patterns(doc, FillPatternTarget.Model), material.SurfaceForegroundPatternId)
        g["surface_colour"] = rgb_text(material.SurfaceForegroundPatternColor)
        g["shade"] = rgb_text(material.Color)
        g["transparency"] = material.Transparency
    return g


def view_source(doc, view):
    """The view whose Visibility/Graphics actually apply: its template if it has one."""
    if view is None:
        return None
    tid = view.ViewTemplateId
    if tid is not None and tid != ElementId.InvalidElementId:
        return doc.GetElement(tid)
    return view


def read_with_view(doc, key, material, view):
    """Object styles + material, then the view's (or its template's)
    Visibility/Graphics category overrides on top - that's what you see.
    Returns (graphics, [where each part came from])."""
    g = read_current(doc, key, material)
    notes = ["Object Styles"]
    if material is not None:
        notes.append("material '%s'" % material.Name)
    src = view_source(doc, view)
    if src is None:
        return g, notes
    lps, fps = line_patterns(doc), fill_patterns(doc)
    used = False
    for bic, hidden in ((CATS[key][1], False), (CATS[key][2], True)):
        cat = doc.Settings.Categories.get_Item(bic)
        if cat is None or not src.IsCategoryOverridable(cat.Id):
            continue
        o = src.GetCategoryOverrides(cat.Id)
        if hidden:
            if o.ProjectionLineWeight > 0:
                g["hidden_w"], used = o.ProjectionLineWeight, True
            if o.ProjectionLinePatternId != ElementId.InvalidElementId:
                g["hidden_pattern"], used = _name_of(lps, o.ProjectionLinePatternId), True
            continue
        if o.CutLineWeight > 0:
            g["cut_w"], used = o.CutLineWeight, True
        if o.ProjectionLineWeight > 0:
            g["proj_w"], used = o.ProjectionLineWeight, True
        for col in (o.CutLineColor, o.ProjectionLineColor):
            if col.IsValid:
                g["colour"], used = rgb_text(col), True
                break
        if o.ProjectionLinePatternId != ElementId.InvalidElementId:
            g["proj_pattern"], used = _name_of(lps, o.ProjectionLinePatternId), True
        if o.CutForegroundPatternId != ElementId.InvalidElementId:
            g["cut_fill"], used = _name_of(fps, o.CutForegroundPatternId), True
        if o.CutForegroundPatternColor.IsValid:
            g["cut_fill_colour"], used = rgb_text(o.CutForegroundPatternColor), True
        if o.SurfaceForegroundPatternColor.IsValid:
            g["surface_colour"], used = rgb_text(o.SurfaceForegroundPatternColor), True
    if used:
        notes.append("%s '%s' overrides" % ("view template" if src.IsTemplate else "view", src.Name))
    return g, notes


def apply_object_styles(doc, key, g):
    """Category-wide: affects every element of this category in the model."""
    cat = doc.Settings.Categories.get_Item(CATS[key][1])
    lps = line_patterns(doc)
    cat.SetLineWeight(int(g["cut_w"]), GraphicsStyleType.Cut)
    cat.SetLineWeight(int(g["proj_w"]), GraphicsStyleType.Projection)
    cat.LineColor = _rcolor(g["colour"])
    cat.SetLinePatternId(_pattern_id(lps, g["proj_pattern"]) if g["proj_pattern"] != "Solid"
                         else LinePatternElement.GetSolidPatternId(), GraphicsStyleType.Projection)
    hidden = doc.Settings.Categories.get_Item(CATS[key][2])
    if hidden is not None:
        hidden.SetLineWeight(int(g["hidden_w"]), GraphicsStyleType.Projection)
        hidden.LineColor = _rcolor(g["colour"])
        pid = _pattern_id(lps, g["hidden_pattern"])
        if pid != ElementId.InvalidElementId:
            hidden.SetLinePatternId(pid, GraphicsStyleType.Projection)


def find_material(doc, name):
    for m in FilteredElementCollector(doc).OfClass(Material):
        if m.Name == name:
            return m
    return None


def apply_material(doc, key, g, m):
    """Create or update the material: identity and structural asset. Its
    graphics are written only when g is given - normally the look lives in
    the family / type view filters (sf_filters), not in the material."""
    mat = find_material(doc, m["name"])
    if mat is None:
        mat = doc.GetElement(Material.Create(doc, m["name"]))
    mat.MaterialClass = "Concrete"
    if g is not None:
        fps, mps = fill_patterns(doc), fill_patterns(doc, FillPatternTarget.Model)
        mat.CutForegroundPatternId = _pattern_id(fps, g["cut_fill"])
        mat.CutForegroundPatternColor = _rcolor(g["cut_fill_colour"])
        mat.SurfaceForegroundPatternId = _pattern_id(mps, g["surface_fill"])
        mat.SurfaceForegroundPatternColor = _rcolor(g["surface_colour"])
        mat.Color = _rcolor(g["shade"])
        mat.Transparency = int(g["transparency"])
    for bip, val in ((BuiltInParameter.ALL_MODEL_DESCRIPTION, m.get("description")),
                     (BuiltInParameter.KEYNOTE_PARAM, m.get("keynote"))):
        p = mat.get_Parameter(bip)
        if val and p is not None and not p.IsReadOnly:
            p.Set(val)

    # Revit refuses two property sets with the same name, so a material
    # StructFlow made before gets its own set updated in place
    asset_name = "StructFlow " + m["name"]
    pse = None
    if mat.StructuralAssetId != ElementId.InvalidElementId:
        current = doc.GetElement(mat.StructuralAssetId)
        if current is not None and current.Name == asset_name:
            pse = current
    if pse is None:
        taken = set(e.Name for e in FilteredElementCollector(doc).OfClass(PropertySetElement))
        i = 2
        base = asset_name
        while asset_name in taken:
            asset_name = "%s (%d)" % (base, i)
            i += 1
    asset = pse.GetStructuralAsset() if pse is not None else StructuralAsset(asset_name, StructuralAssetClass.Concrete)
    asset.Behavior = StructuralBehavior.Isotropic
    asset.SubClass = "Concrete"
    asset.Density = UnitUtils.ConvertToInternalUnits(float(m["density"]), UnitTypeId.KilogramsPerCubicMeter)
    asset.ConcreteCompression = UnitUtils.ConvertToInternalUnits(float(m["fck"]), UnitTypeId.Megapascals)
    asset.SetYoungModulus(UnitUtils.ConvertToInternalUnits(float(m["ecm"]) * 1000.0, UnitTypeId.Megapascals))
    asset.SetPoissonRatio(float(m["poisson"]))
    asset.SetThermalExpansionCoefficient(
        UnitUtils.ConvertToInternalUnits(float(m["thermal"]) * 1e-6, UnitTypeId.InverseDegreesCelsius))
    if pse is not None:
        pse.SetStructuralAsset(asset)
    else:
        pse = PropertySetElement.Create(doc, asset)
        mat.SetMaterialAspectByPropertySet(MaterialAspect.Structural, pse.Id)
    return mat


def assign_material(doc, element_type, mat):
    """Columns / beams: 'Structural Material' type parameter.
    Floors / walls: the structural layer of the compound structure."""
    p = element_type.get_Parameter(BuiltInParameter.STRUCTURAL_MATERIAL_PARAM)
    if p is not None and not p.IsReadOnly:
        p.Set(mat.Id)
        return True
    get_cs = getattr(element_type, "GetCompoundStructure", None)
    if get_cs is not None:
        cs = get_cs()
        if cs is not None:
            idx = cs.StructuralMaterialIndex
            if idx < 0:
                idx = [i for i in range(cs.LayerCount) if cs.IsCoreLayer(i)][0]
            cs.SetMaterialId(idx, mat.Id)
            element_type.SetCompoundStructure(cs)
            return True
    return False


def material_of(doc, element_type):
    p = element_type.get_Parameter(BuiltInParameter.STRUCTURAL_MATERIAL_PARAM)
    if p is not None and p.AsElementId() != ElementId.InvalidElementId:
        return doc.GetElement(p.AsElementId())
    get_cs = getattr(element_type, "GetCompoundStructure", None)
    if get_cs is not None and get_cs() is not None:
        cs = get_cs()
        idx = cs.StructuralMaterialIndex
        if idx >= 0:
            return doc.GetElement(cs.GetMaterialId(idx))
    return None


def apply_view_overrides(doc, key, g, view):
    """Write the same settings into the view's template (or the view) V/G
    overrides, so a template that overrides the category shows them too."""
    from Autodesk.Revit.DB import OverrideGraphicSettings
    src = view_source(doc, view)
    if src is None:
        return None
    lps, fps = line_patterns(doc), fill_patterns(doc)
    cat = doc.Settings.Categories.get_Item(CATS[key][1])
    o = OverrideGraphicSettings()
    col = _rcolor(g["colour"])
    o.SetCutLineWeight(int(g["cut_w"])).SetProjectionLineWeight(int(g["proj_w"]))
    o.SetCutLineColor(col).SetProjectionLineColor(col)
    if g["proj_pattern"] != "Solid":
        o.SetProjectionLinePatternId(_pattern_id(lps, g["proj_pattern"]))
    fid = _pattern_id(fps, g["cut_fill"])
    if fid != ElementId.InvalidElementId:
        o.SetCutForegroundPatternId(fid).SetCutForegroundPatternColor(_rcolor(g["cut_fill_colour"]))
    src.SetCategoryOverrides(cat.Id, o)
    hidden = doc.Settings.Categories.get_Item(CATS[key][2])
    if hidden is not None and src.IsCategoryOverridable(hidden.Id):
        h = OverrideGraphicSettings().SetProjectionLineWeight(int(g["hidden_w"])).SetProjectionLineColor(col)
        hid = _pattern_id(lps, g["hidden_pattern"])
        if hid != ElementId.InvalidElementId:
            h.SetProjectionLinePatternId(hid)
        src.SetCategoryOverrides(hidden.Id, h)
    return src.Name


def read_material(doc, mat, key):
    """Material tab values from an existing material (falls back to defaults)."""
    m = default_material(key)
    if mat is None:
        return m
    m["name"] = mat.Name
    p = mat.get_Parameter(BuiltInParameter.ALL_MODEL_DESCRIPTION)
    m["description"] = (p.AsString() if p else "") or ""
    p = mat.get_Parameter(BuiltInParameter.KEYNOTE_PARAM)
    m["keynote"] = (p.AsString() if p else "") or ""
    pse = doc.GetElement(mat.StructuralAssetId) if mat.StructuralAssetId != ElementId.InvalidElementId else None
    asset = pse.GetStructuralAsset() if pse is not None else None
    if asset is not None:
        conv = UnitUtils.ConvertFromInternalUnits
        m["density"] = round(conv(asset.Density, UnitTypeId.KilogramsPerCubicMeter), 1)
        if asset.ConcreteCompression:
            m["fck"] = round(conv(asset.ConcreteCompression, UnitTypeId.Megapascals), 1)
        if asset.YoungModulus is not None:
            m["ecm"] = round(conv(asset.YoungModulus.X, UnitTypeId.Megapascals) / 1000.0, 1)
        if asset.PoissonRatio is not None:
            m["poisson"] = round(asset.PoissonRatio.X, 3)
        if asset.ThermalExpansionCoefficient is not None:
            m["thermal"] = round(conv(asset.ThermalExpansionCoefficient.X,
                                      UnitTypeId.InverseDegreesCelsius) * 1e6, 2)
        # nearest standard grade for the dropdown
        m["grade"] = min(GRADES, key=lambda gr: abs(gr[1] - m["fck"]))[0]
    return m
