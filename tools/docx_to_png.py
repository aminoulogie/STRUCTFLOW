"""Export pages of a .docx to PNG via Word (COM) + PyMuPDF, for visual checks."""
import os, sys
import win32com.client as w
src = os.path.abspath(sys.argv[1]); pdf = src[:-5] + ".pdf"
pages = [int(p) for p in sys.argv[2].split(",")] if len(sys.argv) > 2 else [1]
word = w.DispatchEx("Word.Application"); word.Visible = False
try:
    doc = word.Documents.Open(src, ReadOnly=True)
    doc.ExportAsFixedFormat(pdf, 17)
    doc.Close(False)
finally:
    word.Quit()
import pymupdf
d = pymupdf.open(pdf)
print("pages", d.page_count)
for p in pages:
    d[p - 1].get_pixmap(dpi=110).save(f"{src[:-5]}_p{p}.png")
