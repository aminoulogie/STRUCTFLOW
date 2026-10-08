# -*- coding: utf-8 -*-
"""Design dimension styles and text types on a live canvas: font, size,
width factor, bold / italic / underline, colour, pen, background, tick
marks, witness gap / extension, dimension line extension, text offset,
prefix / suffix, border, leader arrow. Apply to a type or save as a new one."""
__title__ = "Style\nDesigner"

from pyrevit import revit

import sf_styledesigner as sd

sd.StyleDesigner(revit.doc).ShowDialog()
