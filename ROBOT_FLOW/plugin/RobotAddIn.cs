using System;
using System.Diagnostics;
using System.IO;
using System.Reflection;
using System.Runtime.InteropServices;
using System.Windows.Forms;
using RobotOM;

namespace GCStructFlow.Robot
{
    [ComVisible(true)]
    [Guid("B15C748C-AD54-4D23-9A8A-23BFA175CA80")]
    [ProgId("GCStructFlow.Robot.Modeling")]
    [ClassInterface(ClassInterfaceType.None)]
    public sealed class ModelingAddIn : IRobotAddIn
    {
        private IRobotApplication application;
        private Process panel;
        private static readonly string[] Tabs = { "Levels", "Grids", "Properties", "Draw", "Checks" };

        public bool Connect(RobotApplication robotApp, int addInId, bool firstTime)
        {
            application = robotApp;
            return true;
        }

        public bool Disconnect()
        {
            // Do not kill the user's panel with unsaved reference settings.
            application = null;
            return true;
        }

        public double GetExpectedVersion() { return 10.0; }

        public int InstallCommands(RobotCmdList commands)
        {
            for (int i = 0; i < Tabs.Length; i++)
                commands.New(i + 1, "GCStructFlow - " + Tabs[i]);
            return commands.Count;
        }

        public void DoCommand(int commandId)
        {
            try
            {
                if (application == null || application.Project.IsActive == 0)
                    throw new InvalidOperationException("Open a Robot project first.");
                if (panel != null && !panel.HasExited)
                {
                    MessageBox.Show("GCStructFlow is already open. Switch to its window to continue.", "GCStructFlow");
                    return;
                }
                string bin = Path.GetDirectoryName(Assembly.GetExecutingAssembly().Location);
                string root = Path.GetFullPath(Path.Combine(bin, "..", ".."));
                string python = File.ReadAllText(Path.Combine(bin, "python-path.txt")).Trim();
                string script = Path.Combine(root, "run.py");
                if (!File.Exists(python) || !File.Exists(script))
                    throw new FileNotFoundException("Python or run.py was moved. Run BuildAndInstall.ps1 again.");
                string tab = Tabs[Math.Max(0, Math.Min(commandId - 1, Tabs.Length - 1))];
                string id = application.Project.UniqueId;
                if (String.IsNullOrWhiteSpace(id) || id.Contains("\"") || id.Contains("\r") || id.Contains("\n"))
                    throw new InvalidOperationException("Robot returned an invalid project identifier.");
                ProcessStartInfo start = new ProcessStartInfo(python);
                start.Arguments = "\"" + script + "\" --tab " + tab + " --project-id \"" + id + "\"";
                start.WorkingDirectory = root;
                start.UseShellExecute = false;
                // Keep the Python console visible so startup errors are not hidden.
                start.CreateNoWindow = false;
                start.EnvironmentVariables["ROBOTOM_DLL"] = Path.Combine(bin, "Interop.RobotOM.dll");
                panel = Process.Start(start);
            }
            catch (Exception ex)
            {
                MessageBox.Show(ex.Message, "GCStructFlow launch error", MessageBoxButtons.OK, MessageBoxIcon.Error);
            }
        }
    }
}
