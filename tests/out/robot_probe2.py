import win32com.client as w
from win32com.client import constants as K
app = w.gencache.EnsureDispatch("Robot.Application")
st = app.Project.Structure
nodes = st.Nodes.GetAll()
sup = []
for i in range(1, nodes.Count + 1):
    n = w.CastTo(nodes.Get(i), "IRobotNode")
    if n.HasLabel(K.I_LT_SUPPORT):
        sup.append(n.Number)
print("nodes", nodes.Count, "supports", len(sup), sup[:40])
print("results available", st.Results.Available)
r = st.Results.Nodes.Reactions.Value(sup[0], 26)
print("node", sup[0], "case 26", r.FX, r.FY, r.FZ, r.MX, r.MY, r.MZ)
r = st.Results.Nodes.Reactions.Value(sup[0], 1)
print("node", sup[0], "case 1", r.FX, r.FY, r.FZ, r.MX, r.MY, r.MZ)
