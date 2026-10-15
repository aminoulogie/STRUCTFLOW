import win32com.client as w
app = w.dynamic.Dispatch("Robot.Application")
st = app.Project.Structure
nodes = st.Nodes.GetAll()
n = nodes.Get(1)
print("node dyn", n.Number)
c = st.Cases.Get(26)
print("case dyn", c.Name, c.Type)
cf = c.CaseFactors
print("factors", cf.Count, cf.Get(1).CaseNumber, cf.Get(1).Factor, "combtype", c.CombinationType)
