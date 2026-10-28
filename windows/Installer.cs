using System;
using System.IO;
using System.Reflection;
using System.Windows.Forms;
using Microsoft.Win32;

internal static class Installer
{
    private const string Key = @"Software\Microsoft\Windows\CurrentVersion\Uninstall\OpenMultiPOSClient";
    private static readonly string Target = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "Programs", "OpenMultiPOS");
    private static readonly string Shortcut = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.Programs), "OpenMultiPOS.lnk");

    private static byte[] Resource(string name)
    {
        using (Stream stream = Assembly.GetExecutingAssembly().GetManifestResourceStream(name))
        using (var output = new MemoryStream())
        {
            if (stream == null) throw new InvalidOperationException("Falta un archivo del instalador.");
            stream.CopyTo(output);
            return output.ToArray();
        }
    }

    private static void Write(string name, byte[] content)
    {
        string path = Path.Combine(Target, name);
        string temporary = path + ".new";
        File.WriteAllBytes(temporary, content);
        if (File.Exists(path)) File.Replace(temporary, path, path + ".previous");
        else File.Move(temporary, path);
    }

    [STAThread]
    private static int Main(string[] args)
    {
        if (Array.IndexOf(args, "--self-test") >= 0)
            return Resource("client").Length > 0 && Resource("manual").Length > 0 && Resource("license").Length > 0 ? 0 : 1;
        Application.EnableVisualStyles();
        try
        {
            if (Array.IndexOf(args, "--uninstall") >= 0)
            {
                if (MessageBox.Show("¿Quitar el cliente OpenMultiPOS? Se conservan la dirección guardada, el servidor y todos sus datos.", "Desinstalar OpenMultiPOS", MessageBoxButtons.YesNo, MessageBoxIcon.Question) != DialogResult.Yes) return 0;
                foreach (string name in new [] { "OpenMultiPOS.exe", "Manual.html", "LICENSE", "Configurar.cmd" })
                {
                    File.Delete(Path.Combine(Target, name));
                    File.Delete(Path.Combine(Target, name + ".previous"));
                }
                File.Delete(Shortcut);
                Registry.CurrentUser.DeleteSubKeyTree(Key, false);
                MessageBox.Show("Cliente desinstalado. Puedes borrar la carpeta del programa cuando cierres este desinstalador. Los datos del servidor se conservan.", "OpenMultiPOS");
                return 0;
            }
            if (MessageBox.Show("Se instalará el cliente para tu usuario de Windows. Necesitas un servidor OpenMultiPOS ya configurado. Este instalador no incluye el servidor ni datos comerciales.\n\n¿Continuar?", "Instalar OpenMultiPOS", MessageBoxButtons.YesNo, MessageBoxIcon.Question) != DialogResult.Yes) return 0;
            Directory.CreateDirectory(Target);
            Write("OpenMultiPOS.exe", Resource("client"));
            Write("Manual.html", Resource("manual"));
            Write("LICENSE", Resource("license"));
            Write("Configurar.cmd", Resource("configure"));
            string setup = Path.Combine(Target, "Desinstalar.exe");
            if (!Path.GetFullPath(Assembly.GetExecutingAssembly().Location).Equals(setup, StringComparison.OrdinalIgnoreCase))
                File.Copy(Assembly.GetExecutingAssembly().Location, setup, true);
            Type shellType = Type.GetTypeFromProgID("WScript.Shell");
            object shell = Activator.CreateInstance(shellType);
            object link = shellType.InvokeMember("CreateShortcut", BindingFlags.InvokeMethod, null, shell, new object[] { Shortcut });
            Type linkType = link.GetType();
            linkType.InvokeMember("TargetPath", BindingFlags.SetProperty, null, link, new object[] { Path.Combine(Target, "OpenMultiPOS.exe") });
            linkType.InvokeMember("WorkingDirectory", BindingFlags.SetProperty, null, link, new object[] { Target });
            linkType.InvokeMember("Save", BindingFlags.InvokeMethod, null, link, new object[0]);
            System.Runtime.InteropServices.Marshal.FinalReleaseComObject(link);
            System.Runtime.InteropServices.Marshal.FinalReleaseComObject(shell);
            using (RegistryKey key = Registry.CurrentUser.CreateSubKey(Key))
            {
                key.SetValue("DisplayName", "OpenMultiPOS · Cliente");
                key.SetValue("DisplayVersion", "0.1.0");
                key.SetValue("Publisher", "OpenMultiPOS contributors");
                key.SetValue("InstallLocation", Target);
                key.SetValue("UninstallString", "\"" + setup + "\" --uninstall");
                key.SetValue("NoModify", 1, RegistryValueKind.DWord);
                key.SetValue("NoRepair", 1, RegistryValueKind.DWord);
            }
            MessageBox.Show("Cliente instalado. Abre OpenMultiPOS desde el menú Inicio y escribe la dirección del servidor. Configurar.cmd permite cambiarla después.", "OpenMultiPOS");
            return 0;
        }
        catch (Exception error)
        {
            MessageBox.Show(error.Message + "\nCierra el cliente antes de actualizar. El instalador conserva el archivo anterior con extensión .previous. No modifica el servidor.", "No se pudo completar la instalación", MessageBoxButtons.OK, MessageBoxIcon.Error);
            return 1;
        }
    }
}
