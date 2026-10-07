# StructFlow

pyRevit extension for Revit 2027: concrete beam reinforcement and detailing.

## Install

Clone into your pyRevit extensions folder, then click **pyRevit â†’ Reload** in Revit:

```
git clone https://github.com/aminoulogie/STRUCTFLOW.git "%APPDATA%\pyRevit\Extensions\StructFlow.extension"
```

## Tools

**Rebar panel**
- **Beam Rebar**: top / bottom bars (BS 8666 shapes 00, 11, 21) with covers, A/C legs, optional side-to-side bars through the end supports, laps at 50d/60d in automatic or client-given splice zones, supplier stock length, and links (shape 51) that stop at main beams and columns.
- **Adjust Rebar**: change A / C legs, bar counts, bar types, covers, laps, stock, link spacing or "side to side" on beams that already have bars; empty fields keep each beam's value.
- **Move Splice**: pick a bar by its lap and click the new position; the lap stays exactly lap factor x d and the position is remembered by Rebuild.
- **Rebuild Rebar**: regenerates the bars from the settings stored on each beam (after moving or resizing beams).
- **Link Display**: show all / first-middle-last / 3 in the middle in the active view.
- **Link Map**: colours beams in the active view: green = links non-stop, orange = links stop at junctions.
- **Diagnose**: tests every rebar creation method on one beam and reports what Revit accepts (changes nothing).

**Families panel**
- **Type Maker**: many sizes at once: column / beam types from a list like 300x300, 300x400 (any width / depth parameters), floor types from total thicknesses like 150, 200.
- **Export Families**: save chosen loaded families (title blocks, tags, columns...) as .rfa into a folder, optionally one subfolder per category.

**Views panel**
- **Beam Sheets**: places each beam's long section and its cross sections in a row on your title block, filling sheets top to bottom.
- **Beam Views**: long section + cross sections (start / mid / end of each span) with chosen section type, view templates, scales and tags. Names like A-A, B-B for long sections and A1-A1, A2-A2 for cross sections. Setups can be saved per client.

All lengths in the dialogs are millimetres.

## Status

Early version, tested on Revit 2027. Rebar tagging in generated views is still being debugged.

