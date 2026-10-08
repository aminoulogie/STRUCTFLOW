# -*- coding: utf-8 -*-
"""EPL text and dimension types from epl_standards.jsonc.

plan()  -> what would be created / updated (dry run, changes nothing)
apply() -> does it, one type at a time, logging every step.
Revit has no 'text centred in a broken dimension line' setting: the _Centre
dimension types get text offset 0 and an opaque text background, which is
the closest look Revit allows."""
from Autodesk.Revit.DB import (
    BuiltInParameter, DimensionStyleType, DimensionType, ElementId, ElementType,
    FilteredElementCollector, ForgeTypeId, FormatOptions, StorageType, SubTransaction,
    TextNoteType, Transaction, UnitTypeId,
)

import sf_beamrebar as br

MM = br.MM


def _arrowheads(doc):
    out = {}
    for t in FilteredElementCollector(doc).OfClass(ElementType):
        try:
            if t.FamilyName == "Arrowhead":
                out[br.ename(t)] = t
        except Exception:
            pass
    return out


def _arrow(doc, name):
    heads = _arrowheads(doc)
    if name in heads:
        return heads[name]
    word = name.split()[0].lower()  # 'Diagonal 3mm' -> any 'diagonal...'
    match = sorted(n for n in heads if word in n.lower())
    return heads[match[0]] if match else None


def _set(el, bip, name, value, log=None):
    """Set by built-in parameter, falling back to the English name."""
    p = None
    if bip is not None:
        try:
            p = el.get_Parameter(getattr(BuiltInParameter, bip))
        except Exception:
            p = None
    if p is None and name:
        p = el.LookupParameter(name)
    if p is None or p.IsReadOnly:
        if log:
            log("    (no '%s' on %s)" % (name or bip, br.ename(el)))
        return False
    if p.StorageType == StorageType.ElementId and not isinstance(value, ElementId):
        return False
    p.Set(value)
    return True


def text_specs(cfg, extras):
    """[(name, height, bold, underline, opaque)] from the config + chosen extras."""
    t = cfg["text"]
    out = [("EPL_Text_%gmm" % h, h, False, False, False) for h in t["heights"]]
    if "bold" in extras:
        out += [("EPL_Text_%gmm_Bold" % h, h, True, False, False) for h in (5.0, 7.0, 10.0) if h in t["heights"]]
    if "underline" in extras:
        out += [("EPL_Text_%gmm_Underline" % h, h, False, True, False) for h in (5.0, 7.0) if h in t["heights"]]
    if "mask" in extras:
        out += [("EPL_Text_%gmm_Mask" % h, h, False, False, True) for h in (1.8, 2.5, 3.5) if h in t["heights"]]
    return out


def dim_specs(cfg, wanted):
    """[(name, style, height, tick, centred, suffix, spot)]"""
    out = []
    tick = cfg["dimensions"][0].get("tick", "Diagonal 3mm") if cfg.get("dimensions") else "Diagonal 3mm"
    small_tick = cfg["dimensions"][1].get("tick", "Diagonal 2mm") if len(cfg.get("dimensions", [])) > 1 else tick
    if "linear" in wanted:
        for h, tk in ((2.5, tick), (1.8, small_tick)):
            out.append(("EPL_Dim_%gmm" % h, DimensionStyleType.Linear, h, tk, False, "", False))
            out.append(("EPL_Dim_%gmm_Centre" % h, DimensionStyleType.Linear, h, tk, True, "", False))
    if "angular" in wanted:
        out.append(("EPL_Dim_Angular_2.5mm", DimensionStyleType.Angular, 2.5, "Arrow Filled 15 Degree", False, "", False))
        out.append(("EPL_Dim_Radial_2.5mm", DimensionStyleType.Radial, 2.5, "Arrow Filled 15 Degree", False, "", False))
        out.append(("EPL_Dim_Diameter_2.5mm", DimensionStyleType.Diameter, 2.5, "Arrow Filled 15 Degree", False, "", False))
    if "spot" in wanted:
        out.append(("EPL_SpotElevation_2.5mm", DimensionStyleType.SpotElevation, 2.5, "", False, "", True))
    if "lap" in wanted:
        out.append(("EPL_Dim_Lap", DimensionStyleType.Linear, 2.5, tick, False, " (overlap)", False))
    return out


def plan(doc, cfg, extras, wanted):
    """Dry run: [(kind, name, 'create' / 'update')]."""
    texts = set(br.ename(t) for t in FilteredElementCollector(doc).OfClass(TextNoteType))
    dims = set(br.ename(t) for t in FilteredElementCollector(doc).OfClass(DimensionType))
    rows = [("Text", s[0], "update" if s[0] in texts else "create") for s in text_specs(cfg, extras)]
    rows += [("Dimension", s[0], "update" if s[0] in dims else "create") for s in dim_specs(cfg, wanted)]
    return rows


def _units(dt, spot, log):
    try:
        if spot:
            fo = FormatOptions(UnitTypeId.Meters)
            fo.Accuracy = 0.001
            fo.UsePlusPrefix = True
        else:
            fo = FormatOptions(UnitTypeId.Millimeters)
            fo.Accuracy = 1.0
        fo.UseDefault = False
        fo.SetSymbolTypeId(ForgeTypeId())  # no unit symbol: 5000, not 5000 mm
        dt.SetUnitsFormatOptions(fo)
    except Exception as ex:
        log("    units not set on %s: %s" % (br.ename(dt), br._err(ex)))


def apply(doc, cfg, extras, wanted, log):
    t = cfg["text"]
    font = t.get("font", "Arial")
    gap, ext = 1.5, 2.0
    pen = cfg["dimensions"][0].get("pen", 1) if cfg.get("dimensions") else 1
    leader = _arrow(doc, t.get("leader_arrow", "Arrow Filled 15 Degree")) if "leader" in extras else None
    ok = failed = 0
    tr = Transaction(doc, "StructFlow annotation styles")
    tr.Start()
    texts = dict((br.ename(x), x) for x in FilteredElementCollector(doc).OfClass(TextNoteType))
    base_text = list(texts.values())[0] if texts else None
    for name, h, bold, underline, opaque in text_specs(cfg, extras):
        st = SubTransaction(doc)
        st.Start()
        try:
            tt = texts.get(name) or base_text.Duplicate(name)
            _set(tt, "TEXT_FONT", "Text Font", font)
            _set(tt, "TEXT_SIZE", "Text Size", h * MM)
            _set(tt, "TEXT_WIDTH_SCALE", "Width Factor", float(t.get("width_factor", 1.0)))
            _set(tt, "LINE_COLOR", "Color", 0)
            _set(tt, "TEXT_STYLE_BOLD", "Bold", 1 if bold else 0)
            _set(tt, "TEXT_STYLE_UNDERLINE", "Underline", 1 if underline else 0)
            _set(tt, "TEXT_BACKGROUND", "Background", 0 if opaque else 1)  # 0 opaque, 1 transparent
            if leader is not None:
                _set(tt, "LEADER_ARROWHEAD", "Leader Arrowhead", leader.Id)
            st.Commit()
            ok += 1
            log("text      %s  %gmm%s%s%s" % (name, h, " bold" if bold else "", " underline" if underline else "",
                                              " opaque" if opaque else ""))
        except Exception as ex:
            st.RollBack()
            failed += 1
            log("FAILED    %s: %s" % (name, br._err(ex)))

    all_dims = list(FilteredElementCollector(doc).OfClass(DimensionType))
    for name, style, h, tick, centred, suffix, spot in dim_specs(cfg, wanted):
        st = SubTransaction(doc)
        st.Start()
        try:
            same = [d for d in all_dims if d.StyleType == style]
            existing = [d for d in same if br.ename(d) == name]
            if not same:
                raise ValueError("no %s dimension type in the model to start from" % style)
            dt = existing[0] if existing else same[0].Duplicate(name)
            _set(dt, "TEXT_FONT", "Text Font", font)
            _set(dt, "TEXT_SIZE", "Text Size", h * MM)
            _set(dt, "TEXT_WIDTH_SCALE", "Width Factor", 1.0)
            _set(dt, "LINE_COLOR", "Color", 0)
            _set(dt, "LINE_PEN", "Line Weight", int(pen))
            if not spot:
                _set(dt, "WITNS_LINE_GAP_TO_ELT", "Witness Line Gap to Element", gap * MM)
                _set(dt, "WITNS_LINE_EXTENSION", "Witness Line Extension", ext * MM)
                _set(dt, "TEXT_DIST_TO_LINE", "Text Offset", 0.0 if centred else 1.0 * MM)
                _set(dt, "DIM_TEXT_BACKGROUND", "Text Background", 0 if centred else 1)
            arrow = _arrow(doc, tick) if tick else None
            if arrow is not None:
                if not _set(dt, "DIM_LEADER_ARROWHEAD", "Tick Mark", arrow.Id):
                    _set(dt, "WITNS_LINE_TICK_MARK", None, arrow.Id)
            elif tick:
                log("    no '%s' arrowhead in the model: tick left as it was on %s" % (tick, name))
            if suffix:
                _set(dt, "DIM_SUFFIX", "Suffix", suffix)
            if style in (DimensionStyleType.Linear, DimensionStyleType.SpotElevation):
                _units(dt, spot, log)
            st.Commit()
            ok += 1
            log("dimension %s  %gmm%s%s" % (name, h, " centred" if centred else "", (" suffix '%s'" % suffix) if suffix else ""))
        except Exception as ex:
            st.RollBack()
            failed += 1
            log("FAILED    %s: %s" % (name, br._err(ex)))
    tr.Commit()
    return ok, failed
