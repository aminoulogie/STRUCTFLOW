# -*- coding: utf-8 -*-
"""The look of a family or of single types, independent of materials:
a view filter per family ('SF <Family>') or per type ('SF <Family> - <Type>')
with rules on Family Name / Type Name, added to view templates with the
line / fill / 3D overrides."""
from System.Collections.Generic import List
from Autodesk.Revit.DB import (
    BuiltInParameter, ElementId, ElementParameterFilter, FillPatternTarget,
    FilterRule, FilteredElementCollector, OverrideGraphicSettings,
    ParameterFilterElement, ParameterFilterRuleFactory, View, ViewType,
)

import sf_graphics as sg

PREFIX = "SF "
SCOPES = [("templates", "All view templates"),
          ("active", "The active view's template (or the view)"),
          ("all", "All view templates and views without a template")]


def filter_name(family_name, type_name=None):
    return PREFIX + family_name + ((" - " + type_name) if type_name else "")


def _ensure_filter(doc, key, family_name, type_name):
    name = filter_name(family_name, type_name)
    rules = [ParameterFilterRuleFactory.CreateEqualsRule(
        ElementId(BuiltInParameter.ALL_MODEL_FAMILY_NAME), family_name)]
    if type_name:
        rules.append(ParameterFilterRuleFactory.CreateEqualsRule(
            ElementId(BuiltInParameter.ALL_MODEL_TYPE_NAME), type_name))
    rule_filter = ElementParameterFilter(List[FilterRule](rules))
    cats = List[ElementId]([doc.Settings.Categories.get_Item(sg.CATS[key][1]).Id])
    for f in FilteredElementCollector(doc).OfClass(ParameterFilterElement):
        if f.Name == name:
            f.SetCategories(cats)
            f.SetElementFilter(rule_filter)
            return f
    return ParameterFilterElement.Create(doc, name, cats, rule_filter)


def overrides(doc, g, three_d=False):
    """Lines, cut fill, surface fill; in 3D the shaded colour as a solid
    surface fill; transparency."""
    lps, fps = sg.line_patterns(doc), sg.fill_patterns(doc)
    mps = sg.fill_patterns(doc, FillPatternTarget.Model)
    col = sg._rcolor(g["colour"])
    o = OverrideGraphicSettings()
    o.SetProjectionLineColor(col).SetCutLineColor(col)
    o.SetProjectionLineWeight(int(g["proj_w"])).SetCutLineWeight(int(g["cut_w"]))
    if g["proj_pattern"] != "Solid":
        pid = sg._pattern_id(lps, g["proj_pattern"])
        if pid != ElementId.InvalidElementId:
            o.SetProjectionLinePatternId(pid)
    cid = sg._pattern_id(fps, g["cut_fill"])
    if cid != ElementId.InvalidElementId:
        o.SetCutForegroundPatternId(cid).SetCutForegroundPatternColor(sg._rcolor(g["cut_fill_colour"]))
        o.SetCutForegroundPatternVisible(True)
    if three_d:
        solid = sg._pattern_id(fps, "Solid fill")
        if solid != ElementId.InvalidElementId:
            o.SetSurfaceForegroundPatternId(solid).SetSurfaceForegroundPatternColor(sg._rcolor(g["shade"]))
    else:
        sid = sg._pattern_id(mps, g["surface_fill"])
        if sid != ElementId.InvalidElementId:
            o.SetSurfaceForegroundPatternId(sid).SetSurfaceForegroundPatternColor(sg._rcolor(g["surface_colour"]))
    if int(g["transparency"]):
        o.SetSurfaceTransparency(int(g["transparency"]))
    return o


SKIP = ("Schedule", "DrawingSheet", "ProjectBrowser", "SystemBrowser", "Legend", "Internal",
        "Report", "CostReport", "LoadsReport", "PresureLossReport", "PanelSchedule", "ColumnSchedule")


def target_views(doc, scope, active_view):
    if scope == "active":
        src = sg.view_source(doc, active_view)
        return [src] if src is not None else []
    out = []
    for v in FilteredElementCollector(doc).OfClass(View):
        if str(v.ViewType) in SKIP:
            continue
        if v.IsTemplate or (scope == "all" and v.ViewTemplateId == ElementId.InvalidElementId):
            out.append(v)
    return out


def apply(doc, key, g, family_name, type_names, views):
    """One filter for the family (no type names) or one per type, added to
    the views with the look. Returns (number of filters, views touched)."""
    filters = [_ensure_filter(doc, key, family_name, t) for t in (type_names or [None])]
    flat, three = overrides(doc, g), overrides(doc, g, True)
    n = 0
    for v in views:
        try:
            for f in filters:
                if not v.IsFilterApplied(f.Id):
                    v.AddFilter(f.Id)
                v.SetFilterVisibility(f.Id, True)
                v.SetFilterOverrides(f.Id, three if v.ViewType == ViewType.ThreeD else flat)
            n += 1
        except Exception:
            pass  # a view that cannot take filters
    return len(filters), n


def read_look(doc, g, view, family_name, type_name=None):
    """Lay an existing StructFlow filter's overrides (type first, then family)
    over g. Returns (g, filter name or None)."""
    src = sg.view_source(doc, view)
    if src is None:
        return g, None
    lps, fps = sg.line_patterns(doc), sg.fill_patterns(doc)
    names = ([filter_name(family_name, type_name)] if type_name else []) + [filter_name(family_name)]
    by_name = dict((f.Name, f) for f in FilteredElementCollector(doc).OfClass(ParameterFilterElement))
    for name in names:
        f = by_name.get(name)
        if f is None or not src.IsFilterApplied(f.Id):
            continue
        o = src.GetFilterOverrides(f.Id)
        g = dict(g)
        if o.CutLineWeight > 0:
            g["cut_w"] = o.CutLineWeight
        if o.ProjectionLineWeight > 0:
            g["proj_w"] = o.ProjectionLineWeight
        for col in (o.ProjectionLineColor, o.CutLineColor):
            if col.IsValid:
                g["colour"] = sg.rgb_text(col)
                break
        if o.ProjectionLinePatternId != ElementId.InvalidElementId:
            g["proj_pattern"] = sg._name_of(lps, o.ProjectionLinePatternId)
        if o.CutForegroundPatternId != ElementId.InvalidElementId:
            g["cut_fill"] = sg._name_of(fps, o.CutForegroundPatternId)
        if o.CutForegroundPatternColor.IsValid:
            g["cut_fill_colour"] = sg.rgb_text(o.CutForegroundPatternColor)
        return g, name
    return g, None
