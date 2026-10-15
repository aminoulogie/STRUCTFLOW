import clr, sys, time
clr.AddReference(r'C:\Program Files\Computers and Structures\ETABS 22\ETABSv1.dll')
import ETABSv1 as E
from System import Array, String, Double, Int32
t = time.time()
helper = E.cHelper(E.Helper())
app = helper.GetObject("CSI.ETABS.API.ETABSObject")
m = app.SapModel
m.InitializeNewModel(E.eUnits.kN_m_C)
print("grid", m.File.NewGridOnly(3, 3.06, 3.4, 4, 3, 5.0, 4.0))
D = m.DatabaseTables
for key in ["Grid Definitions - Grid Lines", "Mass Source Definition", "Functions - Response Spectrum - User Defined",
            "Load Case Definitions - Response Spectrum", "Frame Assignments - Rebar Override"]:
    ret = D.GetTableForEditingArray(key, "", 0, None, 0, None)
    print("==", key, "ret", ret[0], "ver", ret[1]); print("  fields", list(ret[2]) if ret[2] else None); 
    n = ret[3]; data = list(ret[4]) if ret[4] else []
    nf = len(ret[2]) if ret[2] else 1
    for i in range(min(n, 4)): print("  ", data[i*nf:(i+1)*nf])
ret = D.GetAvailableTables(0, None, None, None)
names = list(ret[2]); print(len(names)); print([n for n in names if any(k in n for k in ("Spectrum", "Mass", "Spring", "Soil", "Rebar", "Diaphragm"))])

