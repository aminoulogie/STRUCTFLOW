import win32com.client as w
app = w.gencache.EnsureDispatch("Robot.Application")
from win32com.client import constants as K
st = app.Project.Structure
cases = st.Cases.GetAll()
print("cases", cases.Count)
for i in range(1, cases.Count + 1):
    c = cases.Get(i)
    print(i, c.Number, repr(c.Name), "type", c.Type, "nature", c.Nature)
    if c.Type == K.I_CT_COMBINATION:
        cc = w.CastTo(c, "IRobotCaseCombination")
        print("   comb type", cc.CombinationType, "count", cc.CaseFactors.Count)
        for k in range(1, cc.CaseFactors.Count + 1):
            f = cc.CaseFactors.Get(k); print("     case", f.CaseNumber, "x", f.Factor)
print("consts ULS SLS ACC", K.I_CBT_ULS, K.I_CBT_SLS, K.I_CBT_ACC)
