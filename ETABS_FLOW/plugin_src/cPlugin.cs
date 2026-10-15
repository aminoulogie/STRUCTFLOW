using System;
using System.Diagnostics;
using System.IO;
using System.Windows.Forms;
using ETABSv1;

namespace GCStructFlow
{
    // ETABS: Tools > Add/Show Plug-Ins > Plugin Name = GCStructFlow, Path = this DLL.
    // Starts the GCStructFlow – ETABS window, which attaches to this running ETABS through the API.
    public class cPlugin : cPluginContract
    {
        public void Main(ref cSapModel SapModel, ref cPluginCallback ISapPlugin)
        {
            int ret = 0;
            try
            {
                string dir = Path.GetDirectoryName(typeof(cPlugin).Assembly.Location);
                string app = Path.GetFullPath(Path.Combine(dir, "..", "etabsflow.py"));
                string py = FindPythonw();
                if (!File.Exists(app)) throw new FileNotFoundException("etabsflow.py introuvable", app);
                var psi = new ProcessStartInfo(py, "\"" + app + "\"") { WorkingDirectory = Path.GetDirectoryName(app), UseShellExecute = false };
                Process.Start(psi);
            }
            catch (Exception ex)
            {
                MessageBox.Show("GCStructFlow : " + ex.Message, "GCStructFlow");
                ret = 1;
            }
            ISapPlugin.Finish(ret);
        }

        public int Info(ref string Text)
        {
            Text = "GCStructFlow – ETABS : plan AutoCAD → modèle, sections, RPA 2024, combinaisons, résultats, notes.";
            return 0;
        }

        static string FindPythonw()
        {
            string local = Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData);
            foreach (var v in new[] { "Python312", "Python313", "Python311", "Python314" })
            {
                string p = Path.Combine(local, "Programs", "Python", v, "pythonw.exe");
                if (File.Exists(p)) return p;
            }
            return "pythonw.exe";
        }
    }
}
