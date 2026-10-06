# StructFlow

pyRevit extension for Revit 2027: concrete beam reinforcement and detailing.

## Install

Clone into your pyRevit extensions folder, then click **pyRevit → Reload** in Revit:

```
git clone https://github.com/aminoulogie/STRUCTFLOW.git "%APPDATA%\pyRevit\Extensions\StructFlow.extension"
```

## Tools

**Rebar panel**
- **Beam Rebar**: top / bottom bars (BS 8666 shapes 00, 11, 21) with covers, A/C legs, laps at 50d/60d in automatic or client-given splice zones, supplier stock length, and links (shape 51) that stop at main beams and columns.
- **Rebuild Rebar**: regenerates the bars from the settings stored on each beam (after moving or resizing beams).
- **Link Display**: show all / first-middle-last / 3 in the middle in the active view.
- **Link Map**: colours beams in the active view: green = links non-stop, orange = links stop at junctions.
- **Diagnose**: tests every rebar creation method on one beam and reports what Revit accepts (changes nothing).

**Views panel**
- **Beam Views**: long section + cross sections (start / mid / end of each span) with chosen section type, view templates, scales and tags. Setups can be saved per client.

All lengths in the dialogs are millimetres.

## Status

Early version. Rebar creation is still being debugged on Revit 2027.
