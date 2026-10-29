using System;
using System.IO;
using System.Reflection;
using System.Security.Cryptography;
using System.Threading.Tasks;
using System.Windows.Forms;
using Microsoft.Win32;

internal static class ServerInstaller
{
    private const string Key = @"Software\Microsoft\Windows\CurrentVersion\Uninstall\OpenMultiPOSServer";
    private static readonly string Target = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "Programs", "OpenMultiPOS-Server");
    private static readonly string Shortcut = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.Programs), "OpenMultiPOS Servidor.lnk");
    private static readonly string[] Files = { "OpenMultiPOS-Server-Control.exe", "Manual.html", "LICENSE", "LEEME.txt", "source.zip", "OpenMultiPOS-Server.wsl", "server-image.json" };

    private static Stream Resource(string name)
    {
        Stream value = Assembly.GetExecutingAssembly().GetManifestResourceStream(name);
        if (value == null) throw new InvalidDataException("Falta un archivo del instalador.");
        return value;
    }
    private static void Write(string target, string name, Stream source)
    {
        string path = Path.Combine(target, name);
        string temporary = path + ".new";
        using (var output = new FileStream(temporary, FileMode.Create, FileAccess.Write, FileShare.None)) { source.CopyTo(output); output.Flush(true); }
        if (File.Exists(path)) File.Replace(temporary, path, path + ".previous");
        else File.Move(temporary, path);
    }
    private static void Install(string target, string shortcut, string keyPath, string payload)
    {
        ServerBackend.VerifyImage(payload);
        Directory.CreateDirectory(target);
        // Stage and verify the large companion before replacing any installed file.
        string staging = Path.Combine(target, "payload.new");
        Directory.CreateDirectory(staging);
        foreach (string name in new [] { "OpenMultiPOS-Server.wsl", "server-image.json" })
            File.Copy(Path.Combine(payload, name), Path.Combine(staging, name), true);
        ServerBackend.VerifyImage(staging);
        foreach (string name in Files)
        {
            if (name == "OpenMultiPOS-Server.wsl" || name == "server-image.json")
                using (Stream input = File.OpenRead(Path.Combine(staging, name))) Write(target, name, input);
            else using (Stream input = Resource(name)) Write(target, name, input);
        }
        Directory.Delete(staging, true);
        string setup = Path.Combine(target, "Desinstalar.exe");
        if (!Path.GetFullPath(Assembly.GetExecutingAssembly().Location).Equals(setup, StringComparison.OrdinalIgnoreCase))
            using (Stream input = File.OpenRead(Assembly.GetExecutingAssembly().Location)) Write(target, "Desinstalar.exe", input);
        Type shellType = Type.GetTypeFromProgID("WScript.Shell");
        object shell = Activator.CreateInstance(shellType);
        object link = null;
        try
        {
            link = shellType.InvokeMember("CreateShortcut", BindingFlags.InvokeMethod, null, shell, new object[] { shortcut });
            Type type = link.GetType();
            type.InvokeMember("TargetPath", BindingFlags.SetProperty, null, link, new object[] { Path.Combine(target, "OpenMultiPOS-Server-Control.exe") });
            type.InvokeMember("WorkingDirectory", BindingFlags.SetProperty, null, link, new object[] { target });
            type.InvokeMember("Save", BindingFlags.InvokeMethod, null, link, new object[0]);
        }
        finally
        {
            if (link != null) System.Runtime.InteropServices.Marshal.FinalReleaseComObject(link);
            System.Runtime.InteropServices.Marshal.FinalReleaseComObject(shell);
        }
        using (RegistryKey key = Registry.CurrentUser.CreateSubKey(keyPath))
        {
            key.SetValue("DisplayName", "OpenMultiPOS · Servidor propio"); key.SetValue("DisplayVersion", "0.1.0");
            key.SetValue("Publisher", "OpenMultiPOS contributors"); key.SetValue("InstallLocation", target);
            key.SetValue("UninstallString", "\"" + setup + "\" --uninstall");
            key.SetValue("NoModify", 1, RegistryValueKind.DWord); key.SetValue("NoRepair", 1, RegistryValueKind.DWord);
        }
    }
    private static void Uninstall(string target, string shortcut, string keyPath)
    {
        foreach (string name in Files) { File.Delete(Path.Combine(target, name)); File.Delete(Path.Combine(target, name + ".previous")); }
        File.Delete(shortcut);
        Registry.CurrentUser.DeleteSubKeyTree(keyPath, false);
    }
    private static void Busy(Action action)
    {
        Exception failure = null; bool done = false;
        using (var window = new Form { Text = "Preparando OpenMultiPOS", Width = 520, Height = 170, StartPosition = FormStartPosition.CenterScreen, ControlBox = false })
        {
            window.Controls.Add(new Label { Dock = DockStyle.Top, Height = 60, Padding = new Padding(16), Text = "Verificando y copiando el programa. Puede tardar varios minutos. Los datos del servidor se conservan." });
            window.Controls.Add(new ProgressBar { Dock = DockStyle.Bottom, Style = ProgressBarStyle.Marquee });
            window.FormClosing += delegate(object sender, FormClosingEventArgs e) { e.Cancel = !done; };
            window.Shown += async delegate { try { await Task.Run(action); } catch (Exception error) { failure = error; } finally { done = true; window.Close(); } };
            window.ShowDialog();
        }
        if (failure != null) throw failure;
    }
    private static int VerifyInstallation()
    {
        string root = Path.Combine(Path.GetTempPath(), "OpenMultiPOS-InstallerQA-" + Guid.NewGuid().ToString("N"));
        string key = Key + "QA"; string shortcut = Path.Combine(root, "Servidor.lnk");
        Directory.CreateDirectory(root);
        try
        {
            string payload = Path.Combine(root, "payload"); Directory.CreateDirectory(payload);
            byte[] content = System.Text.Encoding.UTF8.GetBytes("fictional clean image");
            File.WriteAllBytes(Path.Combine(payload, "OpenMultiPOS-Server.wsl"), content);
            string hash; using (var sha = SHA256.Create()) hash = BitConverter.ToString(sha.ComputeHash(content)).Replace("-", "").ToLowerInvariant();
            File.WriteAllText(Path.Combine(payload, "server-image.json"), "{\"schema\":1,\"sha256\":\"" + hash + "\"}");
            string target = Path.Combine(root, "program"); string data = Path.Combine(root, "data"); Directory.CreateDirectory(data);
            File.WriteAllText(Path.Combine(data, "preserve.txt"), "fictional business data");
            Install(target, shortcut, key, payload);
            foreach (string name in Files) if (!File.Exists(Path.Combine(target, name))) return 1;
            if (!File.Exists(shortcut)) return 2;
            Install(target, shortcut, key, payload);
            if (!File.Exists(Path.Combine(target, "OpenMultiPOS-Server-Control.exe.previous"))) return 3;
            File.AppendAllText(Path.Combine(payload, "OpenMultiPOS-Server.wsl"), "corrupt");
            try { Install(target, shortcut, key, payload); return 4; } catch (InvalidDataException) { }
            ServerBackend.VerifyImage(target);
            Uninstall(target, shortcut, key);
            foreach (string name in Files) if (File.Exists(Path.Combine(target, name))) return 5;
            return File.ReadAllText(Path.Combine(data, "preserve.txt")) == "fictional business data" && Registry.CurrentUser.OpenSubKey(key) == null && !File.Exists(shortcut) ? 0 : 6;
        }
        finally { Registry.CurrentUser.DeleteSubKeyTree(key, false); Directory.Delete(root, true); }
    }
    [STAThread]
    private static int Main(string[] args)
    {
        if (args.Length == 1 && args[0] == "--self-test") { foreach (string name in Files) if (!name.EndsWith(".wsl") && name != "server-image.json") using (Stream resource = Resource(name)) if (resource.Length == 0) return 1; return 0; }
        if (args.Length == 1 && args[0] == "--verify-installation") return VerifyInstallation();
        Application.EnableVisualStyles();
        try
        {
            if (args.Length == 1 && args[0] == "--uninstall")
            {
                if (MessageBox.Show("Cierra el controlador antes de continuar. Se quitará el programa; la distribución WSL y todos sus datos se conservarán. ¿Continuar?", "Desinstalar OpenMultiPOS", MessageBoxButtons.YesNo) != DialogResult.Yes) return 0;
                Busy(() => Uninstall(Target, Shortcut, Key));
                MessageBox.Show("Programa desinstalado. Los datos WSL permanecen en su ubicación. Puedes quitar la carpeta del programa después de cerrar esta ventana.", "OpenMultiPOS"); return 0;
            }
            if (MessageBox.Show("Edición Servidor propio. Crea una instalación independiente: los datos se guardan en este computador, no en el equipo de los desarrolladores. No incluye negocios, cuentas ni conexiones de otra instalación.\n\nRequiere Windows x64, .NET 4.8, WSL2, virtualización y 30 GB libres. Preparar WSL puede pedir administrador y reinicio. Cierra el controlador antes de actualizar; se conserva el servidor existente y sus datos.\n\n¿Continuar?", "OpenMultiPOS · Servidor propio", MessageBoxButtons.YesNo) != DialogResult.Yes) return 0;
            Busy(() => Install(Target, Shortcut, Key, AppDomain.CurrentDomain.BaseDirectory));
            MessageBox.Show("Abre OpenMultiPOS Servidor desde Inicio. Importa la imagen, crea la contraseña inicial e inicia el servidor. Completa ERPNext y el asistente de OpenMultiPOS en el navegador. Consulta Manual.html.", "OpenMultiPOS"); return 0;
        }
        catch (Exception error) { MessageBox.Show(error.Message + "\nLos datos WSL se conservan. Cierra el controlador y vuelve a ejecutar el mismo instalador para retomar.", "No se pudo completar la instalación", MessageBoxButtons.OK, MessageBoxIcon.Error); return 1; }
    }
}
