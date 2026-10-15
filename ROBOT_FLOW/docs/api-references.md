# Robot API implementation references

These examples establish API patterns, not a claim of Robot 2027 runtime validation.
The installed 2027 SDK and Windows smoke test are the final compatibility checks.

- Autodesk: [Creating an add-in extension](https://download.autodesk.com/us/media/adn/how-to-create-add-in-extension-final.pdf).
  IRobotAddIn Connect/Disconnect/InstallCommands/DoCommand/GetExpectedVersion.
- Autodesk forum: [Add-in registration](https://forums.autodesk.com/t5/robot-structural-analysis-forum/how-to-properly-implement-irobotaddin/td-p/8637346).
  Robot AddIns and MenuExtension registration keys.
- Autodesk: [Creating nodes through the API](https://www.autodesk.com/support/technical/article/caas/sfdcarticles/sfdcarticles/Creating-nodes-using-Robot-API.html).
  Nodes.FreeNumber and Nodes.Create.
- Autodesk forum: [Cartesian structural axes](https://forums.autodesk.com/t5/robot-structural-analysis-forum/api-generating-persistent-labels-for-structural-axis/td-p/12502179).
  AxisMngr.Create, Cartesian grid sequences, relative origin, radians rotation and Save.
- Autodesk: [Separate grid sets and visibility](https://www.autodesk.com/support/technical/article/caas/sfdcarticles/sfdcarticles/Is-it-possible-to-defin-temporary-grid-in-Robot-Structural-Analysis.html).
- Autodesk forum: [Panel geometry and thickness](https://forums.autodesk.com/t5/robot-structural-analysis-forum/panel-assign-thickness-with-api/td-p/9301312).
  Points arrays, CreateContour, Meshed, thickness label, Initialize/Update.
- Autodesk forum: [Selection in a new view](https://forums.autodesk.com/t5/robot-structural-analysis-forum/api-new-window/m-p/10434695).
  Copy all relevant selection types, not just panels, to an isolated view.

Unverified details explicitly requiring host acceptance: sequence origin behavior,
axis activation/visibility semantics, installed interop interface casts, COM active
object attachment, native menu registration and Robot 2027 host compatibility.
