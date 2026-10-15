import clr, sys
a = clr.AddReference(r'C:\Program Files\Computers and Structures\ETABS 22\ETABSv1.dll')
want = {l.split('.')[0]: None for l in sys.argv[1:]}
for t in a.GetExportedTypes():
    for arg in sys.argv[1:]:
        cls, _, meth = arg.partition('.')
        if t.Name != cls: continue
        for m in t.GetMethods():
            if meth and not m.Name.startswith(meth): continue
            ps = ", ".join(("ref " if p.ParameterType.IsByRef else "") + p.ParameterType.Name.replace("&", "") + " " + p.Name for p in m.GetParameters())
            print(f"{cls}.{m.Name}({ps})")
        for p in t.GetProperties():
            if not meth: print(f"{cls}.[prop] {p.Name}: {p.PropertyType.Name}")
