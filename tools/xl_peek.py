import os, sys
import win32com.client as w
xl = w.DispatchEx("Excel.Application"); xl.Visible = False; xl.DisplayAlerts = False
try:
    wb = xl.Workbooks.Open(os.path.abspath(sys.argv[1]))
    for ref in sys.argv[2:]:
        sh, c = ref.split("!")
        cell = wb.Worksheets(sh).Range(c)
        print(ref, "|", cell.Formula, "|", cell.Text)
    wb.Close(False)
finally:
    xl.Quit()
