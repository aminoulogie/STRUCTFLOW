# -*- coding: utf-8 -*-
"""StructFlow family helpers: make or edit many types from a size list
(columns, beams, slabs, walls) and export loaded families to a folder."""
import os
import re

from Autodesk.Revit.DB import (
    BuiltInCategory, Family, FilteredElementCollector, FloorType,
    SaveAsOptions, SpecTypeId, StorageType, WallKind, WallType,
)

import sf_beamrebar as br

MM = br.MM

# (key, label, category, kind): kind 'family' = loadable b x h, 'host' = thickness
CATEGORIES = [
    ("columns", "Structural columns", BuiltInCategory.OST_StructuralColumns, "family"),
    ("beams", "Beams (structural framing)", BuiltInCategory.OST_StructuralFraming, "family"),
    ("floors", "Slabs (floors)", BuiltInCategory.OST_Floors, "host"),
    ("walls", "Walls", BuiltInCategory.OST_Walls, "host"),
]


# ------------------------------------------------------------ type maker
def families_of(doc, bic):
    return dict((f.Name, f) for f in FilteredElementCollector(doc).OfClass(Family)
                if f.FamilyCategory is not None and br.is_category_id(f.FamilyCategory, bic)
                and not f.IsInPlace)


def host_types(doc, key):
    if key == "floors":
        return dict((br.ename(t), t) for t in FilteredElementCollector(doc).OfClass(FloorType))
    return dict((br.ename(t), t) for t in FilteredElementCollector(doc).OfClass(WallType)
                if t.Kind == WallKind.Basic)


def first_symbol(doc, family):
    ids = list(family.GetFamilySymbolIds())
    return doc.GetElement(ids[0]) if ids else None


def symbols_of(doc, family):
    return [doc.GetElement(i) for i in family.GetFamilySymbolIds()]


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
    """Entries separated by commas or new lines, optionally named:
    '300x300, C1: 300x400'  ->  [(None, (300, 300)), ('C1', (300, 400))]
    '150, Slab A: 200'       ->  [(None, (150,)), ('Slab A', (200,))]"""
    out = []
    for tok in re.split(r"[,;\n]+", text):
        if not tok.strip():
            continue
        name = None
        if ":" in tok:
            name, tok = tok.rsplit(":", 1)
            name = name.strip() or None
        nums = re.findall(r"\d+(?:\.\d+)?", tok)
        if not nums:
            continue
        if two:
            if len(nums) < 2:
                raise ValueError("'%s' needs two numbers, e.g. 300x600" % tok.strip())
            out.append((name, (float(nums[0]), float(nums[1]))))
        else:
            out.append((name, (float(nums[0]),)))
    if not out:
        raise ValueError("type at least one size")
    return out


def _fmt(n):
    return "%g" % n


def type_name(pattern, size):
    name = pattern.replace("{b}", _fmt(size[0])).replace("{t}", _fmt(size[0]))
    if len(size) > 1:
        name = name.replace("{h}", _fmt(size[1]))
    return name


def thickness_of(host_type):
    cs = host_type.GetCompoundStructure()
    return sum(cs.GetLayerWidth(i) for i in range(cs.LayerCount)) / MM if cs else 0.0


def describe_existing(doc, key, base, p_w=None, p_h=None):
    """Existing types as editable 'Name: size' lines."""
    lines = []
    if key in ("floors", "walls"):
        for name, t in sorted(host_types(doc, key).items()):
            lines.append("%s: %g" % (name, round(thickness_of(t), 1)))
    else:
        for sym in sorted(symbols_of(doc, base), key=lambda s: br.ename(s)):
            pw, ph = sym.LookupParameter(p_w), sym.LookupParameter(p_h)
            if pw is None or ph is None:
                continue
            lines.append("%s: %gx%g" % (br.ename(sym), round(pw.AsDouble() / MM, 1),
                                        round(ph.AsDouble() / MM, 1)))
    return "\n".join(lines)


def make_family_types(doc, family, pattern, entries, p_w, p_h, update, log):
    base = first_symbol(doc, family)
    existing = dict((br.ename(s), s) for s in symbols_of(doc, family))
    touched = []
    for name, size in entries:
        name = name or type_name(pattern, size)
        sym = existing.get(name)
        if sym is not None and not update:
            log("skipped %s (exists)" % name)
            continue
        verb = "updated" if sym is not None else "created"
        if sym is None:
            sym = base.Duplicate(name)
            existing[name] = sym
        for pname, val in ((p_w, size[0]), (p_h, size[1])):
            p = sym.LookupParameter(pname)
            if p is None or p.IsReadOnly:
                raise ValueError("type parameter '%s' not found or read-only" % pname)
            p.Set(val * MM)
        touched.append(sym)
        log("%s %s" % (verb, name))
    return touched


def make_host_types(doc, key, base, pattern, entries, update, log):
    """Slab / wall types: the structural layer takes up whatever the
    finish layers leave of the total thickness."""
    existing = host_types(doc, key)
    touched = []
    for name, size in entries:
        name = name or type_name(pattern, size)
        t = existing.get(name)
        if t is not None and not update:
            log("skipped %s (exists)" % name)
            continue
        verb = "updated" if t is not None else "created"
        if t is None:
            t = base.Duplicate(name)
            existing[name] = t
        cs = t.GetCompoundStructure()
        idx = cs.StructuralMaterialIndex
        if idx < 0:
            idx = [i for i in range(cs.LayerCount) if cs.IsCoreLayer(i)][0]
        others = sum(cs.GetLayerWidth(i) for i in range(cs.LayerCount) if i != idx)
        width = size[0] * MM - others
        if width <= 0:
            raise ValueError("%s: the finishes are thicker than %g mm" % (name, size[0]))
        cs.SetLayerWidth(idx, width)
        t.SetCompoundStructure(cs)
        touched.append(t)
        log("%s %s" % (verb, name))
    return touched


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


# ----------------------------------------------------------- EPL library
LIBRARY = os.path.join(os.path.dirname(__file__), "epl_library.json")


def load_library():
    import json
    with open(LIBRARY) as f:
        return json.load(f)


def plan_library(doc, lib):
    """Match the model's families to the EPL standard.
    Returns (planned [(family, rel_path)], unmapped [family], missing [old name],
    to_delete [family])."""
    by_new = dict((rel.split("\\")[-1], rel) for rel in lib["map"].values())
    planned, unmapped, to_delete, seen = [], [], [], set()
    for cat, fams in exportable_families(doc).items():
        for f in fams:
            name = f.Name
            if name in lib["map"]:
                planned.append((f, lib["map"][name]))
                seen.add(name)
            elif name in by_new:  # already renamed to its EPL name
                planned.append((f, by_new[name]))
                seen.update(k for k, v in lib["map"].items() if v == by_new[name])
            elif re.match(r"^\d{2}$", name):  # BS 8666 rebar shape keeps its code
                planned.append((f, lib["rebar_shape_folder"] + "\\" + name))
            elif name in lib["delete"]:
                to_delete.append(f)
            elif name not in lib["system"]:
                unmapped.append(f)
    missing = sorted(k for k in lib["map"] if k not in seen)
    planned.sort(key=lambda p: p[1])
    return planned, unmapped, missing, to_delete


def export_library(doc, planned, root, log):
    """Save each family as root/rel_path.rfa (outside a transaction)."""
    done = 0
    for f, rel in planned:
        path = os.path.join(root, rel + ".rfa")
        folder = os.path.dirname(path)
        if not os.path.isdir(folder):
            os.makedirs(folder)
        fdoc = None
        try:
            fdoc = doc.EditFamily(f)
            opts = SaveAsOptions()
            opts.OverwriteExistingFile = True
            opts.MaximumBackups = 1
            fdoc.SaveAs(path, opts)
            done += 1
            log("saved   %s" % rel)
            stem = os.path.basename(rel)
            for fn in os.listdir(folder):
                if re.match(re.escape(stem) + r"\.\d{4}\.rfa$", fn):
                    os.remove(os.path.join(folder, fn))
        except Exception as ex:
            log("FAILED  %s (%s): %s" % (rel, f.Name, br._err(ex)))
        finally:
            if fdoc is not None:
                fdoc.Close(False)
    return done


def rename_to_library(doc, planned, log):
    """Rename families in the model to their EPL names (inside a transaction)."""
    taken = set(f.Name for fams in exportable_families(doc).values() for f in fams)
    n = 0
    for f, rel in planned:
        new = rel.split("\\")[-1]
        if f.Name == new:
            continue
        if new in taken:
            log("not renamed %s: '%s' already exists" % (f.Name, new))
            continue
        old = f.Name
        f.Name = new
        taken.add(new)
        n += 1
        log("renamed %s -> %s" % (old, new))
    return n


# ------------------------------------------------- export wizard (naming)
ELEMENT_BY_CAT = {
    "Structural Columns": "Column", "Structural Framing": "Beam",
    "Structural Foundations": "Foundation", "Structural Trusses": "Truss",
    "Title Blocks": "TitleBlock", "Profiles": "Profile", "Detail Items": "Detail",
    "Structural Rebar Couplers": "Coupler", "Generic Annotations": "Symbol",
}
MATERIAL_KEY = {"Structural Columns": "columns", "Structural Framing": "beams"}


def _camel(text):
    words = re.findall(r"[A-Za-z0-9]+", text)
    return "".join(w[:1].upper() + w[1:] for w in words)


def category_code(f):
    cat = f.FamilyCategory.Name if f.FamilyCategory is not None else ""
    low = cat.lower()
    if low.endswith("tags"):
        return "TAG"
    if low == "title blocks":
        return "TB"
    if low == "profiles":
        return "PRF"
    if low == "detail items":
        return "DET"
    if "analytical" in low or "boundary" in low:
        return "ANL"
    if low.startswith("structural") or low in ("rebar shape",):
        return "STR"
    try:
        from Autodesk.Revit.DB import CategoryType
        if f.FamilyCategory.CategoryType == CategoryType.Annotation:
            return "ANN"
    except Exception:
        pass
    return "ARC"


def name_parts(f, lib=None):
    """(element, variant) for the EPL name: from the library standard when the
    family is in it, otherwise derived from the category and family name."""
    lib = lib or load_library()
    rel = lib["map"].get(f.Name)
    if rel is None:
        by_new = dict((r.split("\\")[-1], r) for r in lib["map"].values())
        rel = by_new.get(f.Name)
    if rel is not None:
        parts = rel.split("\\")[-1].split("_")
        if len(parts) >= 3:
            return parts[2], "_".join(parts[3:])
    cat = f.FamilyCategory.Name if f.FamilyCategory is not None else ""
    if cat.lower().endswith("tags"):
        element = _camel(cat[:-4].replace("Structural", "Str"))
    else:
        element = ELEMENT_BY_CAT.get(cat, _camel(cat))
    variant = "-".join(re.findall(r"[A-Za-z0-9]+", f.Name))
    return element, variant


def library_folder(f, lib=None):
    lib = lib or load_library()
    rel = lib["map"].get(f.Name)
    if rel is None:
        by_new = dict((r.split("\\")[-1], r) for r in lib["map"].values())
        rel = by_new.get(f.Name)
    if rel is not None:
        return "\\".join(rel.split("\\")[:-1])
    if re.match(r"^\d{2}$", f.Name):
        return lib["rebar_shape_folder"]
    return "UNSORTED"


def build_name(f, opts, grade=None, lib=None):
    """opts: company (text or ''), code, element, variant, material (bools)."""
    if not opts.get("rename"):
        base = _safe(f.Name)
        return base + ("_" + grade.replace("/", "-") if grade and opts.get("material") else "")
    element, variant = name_parts(f, lib)
    parts = []
    if opts.get("company"):
        parts.append(opts["company"])
    if opts.get("code"):
        parts.append(category_code(f))
    if opts.get("element"):
        parts.append(element)
    if opts.get("variant") and variant:
        parts.append(variant)
    if opts.get("material") and grade:
        parts.append(grade.replace("/", "-"))
    return _safe("_".join(parts) or f.Name)


def _material_param(fm):
    from Autodesk.Revit.DB import BuiltInParameter
    for p in fm.Parameters:
        d = p.Definition
        try:
            if d.BuiltInParameter == BuiltInParameter.STRUCTURAL_MATERIAL_PARAM:
                return p
        except Exception:
            pass
    for p in fm.Parameters:
        if p.Definition.Name in ("Structural Material", "Material"):
            return p
    return None


def export_jobs(doc, jobs, log):
    """jobs: dicts {family, types (set of names or None), path, key, material (dict or None),
    graphics (dict or None)}. Each family is opened, trimmed to the chosen types,
    given the material / graphics, saved as path, and closed (the model is not changed)."""
    import sf_graphics as sg
    from Autodesk.Revit.DB import Transaction
    done = 0
    for job in jobs:
        f, path = job["family"], job["path"]
        folder = os.path.dirname(path)
        if not os.path.isdir(folder):
            os.makedirs(folder)
        fdoc = None
        try:
            fdoc = doc.EditFamily(f)
            fm = fdoc.FamilyManager
            t = Transaction(fdoc, "StructFlow export")
            t.Start()
            if job["types"] is not None:
                for ft in list(fm.Types):
                    if ft.Name not in job["types"] and fm.Types.Size > 1:
                        fm.CurrentType = ft
                        fm.DeleteCurrentType()
            key = job["key"]
            if key and job["graphics"] is not None:
                sg.apply_object_styles(fdoc, key, job["graphics"])
            if key and job["material"] is not None:
                g = job["graphics"] or sg.PRESETS["EPL (recommended UK)"][key]
                mat = sg.apply_material(fdoc, key, g, job["material"])
                p = _material_param(fm)
                if p is None:
                    log("note: %s has no material parameter, material not set" % f.Name)
                else:
                    for ft in list(fm.Types):
                        fm.CurrentType = ft
                        fm.Set(p, mat.Id)
            t.Commit()
            opts = SaveAsOptions()
            opts.OverwriteExistingFile = True
            opts.MaximumBackups = 1
            fdoc.SaveAs(path, opts)
            done += 1
            log("saved   %s" % path)
            stem = os.path.splitext(os.path.basename(path))[0]
            for fn in os.listdir(folder):
                if re.match(re.escape(stem) + r"\.\d{4}\.rfa$", fn):
                    os.remove(os.path.join(folder, fn))
        except Exception as ex:
            log("FAILED  %s: %s" % (f.Name, br._err(ex)))
        finally:
            if fdoc is not None:
                fdoc.Close(False)
    return done
