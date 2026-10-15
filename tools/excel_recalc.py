"""Recalculate a workbook with Microsoft Excel (COM), save cached values, report formula errors."""
import os, sys
import win32com.client as w
path = os.path.abspath(sys.argv[1])
xl = w.DispatchEx("Excel.Application")
xl.Visible = False
xl.DisplayAlerts = False
try:
    wb = xl.Workbooks.Open(path)
    xl.CalculateFull()
    errs = []
    for ws in wb.Worksheets:
        ur = ws.UsedRange
        vals = ur.Value
        if not isinstance(vals, tuple):
            continue
        r0, c0 = ur.Row, ur.Column
        for i, row in enumerate(vals):
            for j, v in enumerate(row):
                if isinstance(v, int) and v < -2146820000:  # COM error codes (#DIV/0!, #VALUE!, #REF!, #NAME? ...)
                    errs.append(f"{ws.Name}!{ws.Cells(r0 + i, c0 + j).Address}")
    wb.Save()
    wb.Close()
    print("errors:", len(errs), errs[:40])
finally:
    xl.Quit()
