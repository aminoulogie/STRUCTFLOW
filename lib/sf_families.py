# -*- coding: utf-8 -*-
"""StructFlow family helpers: make many types from a size list (columns,
beams, floors) and export loaded families to a folder."""
import os
import re

from Autodesk.Revit.DB import (
    BuiltInCategory, Family, FamilySymbol, FilteredElementCollector,
    FloorType, SaveAsOptions, SpecTypeId, StorageType,
)

import sf_beamrebar as br

MM = br.MM

CATEGORIES = [
    ("Structural columns", BuiltInCategory.OST_StructuralColumns),
    ("Beams (structural framing)", BuiltInCategory.OST_StructuralFraming),
    ("Floors", BuiltInCategory.OST_Floors),
]


# ------------------------------------------------------------ type maker
def families_of(doc, bic):
    return dict((f.Name, f) for f in FilteredElementCollector(doc).OfClass(Family)
                if f.FamilyCategory is not None and br.is_category_id(f.FamilyCategory, bic)
                and not f.IsInPlace)


def floor_types(doc):
    return dict((br.ename(t), t) for t in FilteredElementCollector(doc).OfClass(FloorType))


def first_symbol(doc, family):
    ids = list(family.GetFamilySymbolIds())
    return doc.GetElement(ids[0]) if ids else None


def length_params(symbol):
    """Names of editable length type parameters (b, h, Width, Depth...)."""
    out = []
    for p in symbol.Parameters:
        if p.IsReadOnly or p.StorageType != StorageType.Double:
            continue
        try:
            if p.Definition.GetDataType() != SpecTypeId.Length:
                continue
        except Exception:
            pass
        out.append(p.Definition.Name)
    return sorted(set(out))


def guess(names, wanted):
    low = dict((n.lower(), n) for n in names)
    for w in wanted:
        if w in low:
            return low[w]
    return names[0] if names else ""


def parse_sizes(text, two):
    """'300x300, 300x400' -> [(300, 300), (300, 400)];  '150, 200' -> [(150,), (200,)]"""
    out = []
    for tok in re.split(r"[,;\n]+", text):
        nums = re.findall(r"\d+(?:\.\d+)?", tok)
        if not nums:
            continue
        if two:
            if len(nums) < 2:
                raise ValueError("'%s' needs two numbers, e.g. 300x600" % tok.strip())
            out.append((float(nums[0]), float(nums[1])))
        else:
            out.append((float(nums[0]),))
    if not out:
        raise ValueError("type at least one size")
    return out


def _fmt(n):
    return ("%g" % n)


def type_name(pattern, size):
    name = pattern.replace("{b}", _fmt(size[0])).replace("{t}", _fmt(size[0]))
    if len(size) > 1:
        name = name.replace("{h}", _fmt(size[1]))
    return name


def make_family_types(doc, family, pattern, sizes, p_w, p_h, update, log):
    base = first_symbol(doc, family)
    existing = dict((br.ename(doc.GetElement(i)), doc.GetElement(i)) for i in family.GetFamilySymbolIds())
    for size in sizes:
        name = type_name(pattern, size)
        sym = existing.get(name)
        if sym is not None and not update:
            log("skipped %s (exists)" % name)
            continue
        if sym is None:
            sym = base.Duplicate(name)
            existing[name] = sym
            verb = "created"
        else:
            verb = "updated"
        for pname, val in ((p_w, size[0]), (p_h, size[1])):
            p = sym.LookupParameter(pname)
            if p is None or p.IsReadOnly:
                raise ValueError("type parameter '%s' not found or read-only" % pname)
            p.Set(val * MM)
        log("%s %s" % (verb, name))


def make_floor_types(doc, base, pattern, sizes, update, log):
    existing = floor_types(doc)
    for size in sizes:
        name = type_name(pattern, size)
        ft = existing.get(name)
        if ft is not None and not update:
            log("skipped %s (exists)" % name)
            continue
        verb = "updated" if ft is not None else "created"
        if ft is None:
            ft = base.Duplicate(name)
            existing[name] = ft
        cs = ft.GetCompoundStructure()
        idx = cs.StructuralMaterialIndex
        if idx < 0:
            idx = [i for i in range(cs.LayerCount) if cs.IsCoreLayer(i)][0]
        # total thickness = size: the structural layer takes what the other layers leave
        others = sum(cs.GetLayerWidth(i) for i in range(cs.LayerCount) if i != idx)
        width = size[0] * MM - others
        if width <= 0:
            raise ValueError("%s: the finishes are thicker than %g mm" % (name, size[0]))
        cs.SetLayerWidth(idx, width)
        ft.SetCompoundStructure(cs)
        log("%s %s" % (verb, name))


# ---------------------------------------------------------------- export
def exportable_families(doc):
    """{category name: [family]} for loaded, editable families."""
    out = {}
    for f in FilteredElementCollector(doc).OfClass(Family):
        if f.IsInPlace or not f.IsEditable:
            continue
        cat = f.FamilyCategory.Name if f.FamilyCategory is not None else "Other"
        out.setdefault(cat, []).append(f)
    for cat in out:
        out[cat].sort(key=lambda f: f.Name)
    return out


def _safe(name):
    return re.sub(r'[<>:"/\\|?*]', "_", name).strip()


def export_families(doc, families, folder, by_category, overwrite, log):
    """Save each family as <folder>[/<category>]/<name>.rfa. Must run
    outside a transaction."""
    done = 0
    for f in families:
        cat = f.FamilyCategory.Name if f.FamilyCategory is not None else "Other"
        target = os.path.join(folder, _safe(cat)) if by_category else folder
        if not os.path.isdir(target):
            os.makedirs(target)
        path = os.path.join(target, _safe(f.Name) + ".rfa")
        if os.path.exists(path) and not overwrite:
            log("skipped %s (file exists)" % path)
            continue
        fdoc = None
        try:
            fdoc = doc.EditFamily(f)
            opts = SaveAsOptions()
            opts.OverwriteExistingFile = True
            opts.MaximumBackups = 1
            fdoc.SaveAs(path, opts)
            done += 1
            log("saved %s" % path)
            # Revit keeps name.0001.rfa backups when overwriting: the client doesn't need them
            stem = _safe(f.Name)
            for fn in os.listdir(target):
                if re.match(re.escape(stem) + r"\.\d{4}\.rfa$", fn):
                    os.remove(os.path.join(target, fn))
        except Exception as ex:
            log("FAILED %s: %s" % (f.Name, br._err(ex)))
        finally:
            if fdoc is not None:
                fdoc.Close(False)
    return done
