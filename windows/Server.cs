using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Drawing;
using System.IO;
using System.Security.Cryptography;
using System.Text;
using System.Text.RegularExpressions;
using System.Threading.Tasks;
using System.Web.Script.Serialization;
using System.Windows.Forms;
using Microsoft.Win32;

internal sealed class ServerBackend
{
    internal readonly string Distro;
    internal Process Serving;
    private readonly JavaScriptSerializer json = new JavaScriptSerializer();
    private readonly string wsl = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.Windows), "System32", "wsl.exe");
    private readonly string logFolder = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "OpenMultiPOS", "Logs");
    private readonly object logLock = new object();

    internal ServerBackend(string distro)
    {
        if (!Regex.IsMatch(distro, @"\AOpenMultiPOS(?:-[A-Za-z0-9-]{1,48})?\z")) throw new ArgumentException("Nombre de servidor inválido.");
        Distro = distro;
    }
    internal static string Quote(string value)
    {
        if (value.Length > 0 && !Regex.IsMatch(value, "[\\s\"]")) return value;
        var result = new StringBuilder("\"");
        int slashes = 0;
        foreach (char c in value)
        {
            if (c == '\\') { slashes++; continue; }
            result.Append('\\', c == '"' ? slashes * 2 + 1 : slashes);
            result.Append(c); slashes = 0;
        }
        return result.Append('\\', slashes * 2).Append('"').ToString();
    }
    private Process Create(string[] args, bool unicode)
    {
        var info = new ProcessStartInfo(wsl) { UseShellExecute = false, CreateNoWindow = true, RedirectStandardInput = true, RedirectStandardOutput = true, RedirectStandardError = true, StandardOutputEncoding = unicode ? Encoding.Unicode : Encoding.UTF8, StandardErrorEncoding = unicode ? Encoding.Unicode : Encoding.UTF8 };
        info.Arguments = String.Join(" ", Array.ConvertAll(args, Quote));
        return new Process { StartInfo = info, EnableRaisingEvents = true };
    }
    private string[] Runtime(string action, params string[] extra)
    {
        var args = new List<string> { "-d", Distro, "-u", "root", "--cd", "/", "--exec", "python3.14", "/usr/local/lib/openmultipos/first_run.py", action };
        args.AddRange(extra); return args.ToArray();
    }
    private void Log(string text)
    {
        lock (logLock)
        {
            try { Directory.CreateDirectory(logFolder);
            File.AppendAllText(Path.Combine(logFolder, Distro + ".log"), DateTime.UtcNow.ToString("o") + " " + text + Environment.NewLine); }
            catch (IOException) { } catch (UnauthorizedAccessException) { }
        }
    }
    private string Execute(string[] args, string input, bool unicode)
    {
        using (Process process = Create(args, unicode))
        {
            process.Start();
            Task<string> output = process.StandardOutput.ReadToEndAsync();
            Task<string> error = process.StandardError.ReadToEndAsync();
            if (input != null)
            {
                var writer = new StreamWriter(process.StandardInput.BaseStream, new UTF8Encoding(false));
                writer.Write(input); writer.Flush();
            }
            process.StandardInput.BaseStream.Close();
            process.WaitForExit();
            Task.WaitAll(output, error);
            Log(output.Result + error.Result);
            if (process.ExitCode != 0) {
                var failure = new InvalidOperationException("La operación no terminó. Consulta el registro local; los datos se conservan.");
                failure.Data["diagnostic"] = "exit=" + process.ExitCode + "\nfolder=" + logFolder + "\nstdout=" + output.Result + "\nstderr=" + error.Result;
                throw failure;
            }
            return output.Result;
        }
    }
    internal bool Registered()
    {
        string list = Execute(new [] { "--list", "--quiet" }, null, true);
        foreach (string line in list.Split(new [] { '\n' })) if (line.Trim('\r', '\n', '\0', '\uFEFF', ' ') == Distro) return true;
        return false;
    }
    internal bool WindowsReady()
    {
        if (!File.Exists(wsl)) return false;
        try { Execute(new [] { "--status" }, null, true); return true; }
        catch (InvalidOperationException) { return false; }
    }
    internal static ProcessStartInfo WindowsPreparation(string executable)
    {
        return new ProcessStartInfo(executable, "--install --no-distribution") { UseShellExecute = true, Verb = "runas" };
    }
    internal async Task PrepareWindows()
    {
        if (!File.Exists(wsl)) throw new InvalidOperationException("Actualiza Windows y consulta Preparar Windows en el manual. Este equipo necesita WSL2.");
        Process preparation;
        try { preparation = Process.Start(WindowsPreparation(wsl)); }
        catch (System.ComponentModel.Win32Exception error)
        {
            if (error.NativeErrorCode == 1223) throw new InvalidOperationException("La preparación se canceló. Pulsa Preparar Windows cuando puedas autorizarla.");
            throw;
        }
        using (Process process = preparation)
        {
            await Task.Run(() => process.WaitForExit());
            if (process.ExitCode != 0 && process.ExitCode != 3010)
                throw new InvalidOperationException("Windows no completó la preparación. Revisa su ventana, la virtualización del equipo y Preparar Windows en el manual.");
        }
    }
    internal static void CheckFreeSpace(long available)
    {
        if (available < 30L * 1024 * 1024 * 1024) throw new IOException("Libera al menos 30 GB en la unidad donde se guardarán los datos y vuelve a instalar el servidor.");
    }
    internal string DataFolder()
    {
        using (RegistryKey root = Registry.CurrentUser.OpenSubKey(@"Software\Microsoft\Windows\CurrentVersion\Lxss"))
        {
            if (root != null) foreach (string name in root.GetSubKeyNames()) using (RegistryKey key = root.OpenSubKey(name))
                if (key != null && Convert.ToString(key.GetValue("DistributionName")) == Distro) { string path = Convert.ToString(key.GetValue("BasePath")); return path.StartsWith(@"\\?\") ? path.Substring(4) : path; }
        }
        return NewDataFolder();
    }
    private string NewDataFolder() { return Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "OpenMultiPOS", Distro == "OpenMultiPOS" ? "Servidor" : Distro); }
    internal Dictionary<string, object> Status()
    {
        var result = json.Deserialize<Dictionary<string, object>>(Execute(Runtime("status"), null, false));
        if (!result.ContainsKey("protocol") || Convert.ToInt32(result["protocol"]) != 1) throw new InvalidOperationException("La versión del servidor necesita un controlador compatible.");
        return result;
    }
    internal void Setup(string password, bool recover)
    {
        Execute(Runtime(recover ? "recover" : "setup", "--stdin"), json.Serialize(new { password = password }), false);
    }
    internal void Backup(bool check) { Execute(Runtime(check ? "restore-check" : "backup"), null, false); }
    internal void VerifyInput()
    {
        string sample = "Fictional ñ \n quote\" slash\\";
        string script = "import json,sys; value=json.load(sys.stdin)['password']; assert chr(241) in value and chr(10) in value and chr(34) in value and chr(92) in value; print('input verified')";
        Execute(new [] { "-d", Distro, "-u", "root", "--cd", "/", "--exec", "python3.14", "-c", script }, json.Serialize(new { password = sample }), false);
    }
    internal static void VerifyImage(string folder)
    {
        if (new FileInfo(Path.Combine(folder, "server-image.json")).Length > 65536) throw new InvalidDataException("El manifiesto es demasiado grande.");
        var data = new JavaScriptSerializer().Deserialize<Dictionary<string, object>>(File.ReadAllText(Path.Combine(folder, "server-image.json")));
        if (data == null || !data.ContainsKey("sha256") || !data.ContainsKey("schema")) throw new InvalidDataException("El manifiesto del servidor está incompleto.");
        string expected = Convert.ToString(data["sha256"]);
        if (Convert.ToInt32(data["schema"]) != 1 || !Regex.IsMatch(expected, @"\A[a-f0-9]{64}\z")) throw new InvalidDataException("El manifiesto del servidor no es válido.");
        using (var stream = File.OpenRead(Path.Combine(folder, "OpenMultiPOS-Server.wsl")))
        using (var sha = SHA256.Create())
        {
            string actual = BitConverter.ToString(sha.ComputeHash(stream)).Replace("-", "").ToLowerInvariant();
            if (actual != expected) throw new InvalidDataException("La imagen no coincide con su manifiesto. Descarga de nuevo el paquete completo.");
        }
    }
    internal void Import(string folder)
    {
        if (Registered()) throw new InvalidOperationException("El servidor ya existe. Revisa su estado antes de instalar.");
        string data = NewDataFolder();
        if (Directory.Exists(data)) throw new IOException("La carpeta de datos ya existe. Se conserva para revisión.");
        CheckFreeSpace(new DriveInfo(Path.GetPathRoot(data)).AvailableFreeSpace);
        VerifyImage(folder);
        Execute(new [] { "--import", Distro, data, Path.Combine(folder, "OpenMultiPOS-Server.wsl"), "--version", "2" }, null, true);
    }
    internal async Task Start()
    {
        if (Serving != null && !Serving.HasExited) throw new InvalidOperationException("El servidor ya está activo en este controlador.");
        var ready = new TaskCompletionSource<bool>();
        Serving = Create(Runtime("serve", "--events"), false);
        Serving.OutputDataReceived += delegate(object sender, DataReceivedEventArgs e) {
            if (e.Data == null) return;
            Log(e.Data);
            if (e.Data.Trim() == "{\"event\": \"ready\", \"protocol\": 1}") ready.TrySetResult(true);
        };
        Serving.ErrorDataReceived += delegate(object sender, DataReceivedEventArgs e) { if (e.Data != null) Log(e.Data); };
        Serving.Exited += delegate { ready.TrySetException(new InvalidOperationException("El servidor se detuvo. Revisa el registro local.")); };
        Serving.Start(); Serving.BeginOutputReadLine(); Serving.BeginErrorReadLine();
        if (await Task.WhenAny(ready.Task, Task.Delay(90000)) != ready.Task)
        {
            await Stop(); throw new TimeoutException("El arranque tardó demasiado. Revisa el registro local.");
        }
        await ready.Task;
    }
    internal async Task Stop()
    {
        if (Serving == null || Serving.HasExited) return;
        Serving.StandardInput.BaseStream.Close();
        if (!await Task.Run(() => Serving.WaitForExit(120000))) throw new TimeoutException("Los servicios siguen cerrándose. Conserva esta ventana abierta.");
        int exit = Serving.ExitCode; Serving.Dispose(); Serving = null;
        if (exit != 0) throw new InvalidOperationException("El cierre necesita revisión en el registro local.");
    }
    internal void OpenLog() { Directory.CreateDirectory(logFolder); Process.Start(new ProcessStartInfo(logFolder) { UseShellExecute = true }); }
}

internal sealed class ServerWindow : Form
{
    private readonly ServerBackend backend;
    private readonly Label status = new Label { AutoSize = true, MaximumSize = new Size(620, 0), Text = "Comprobando el servidor…" };
    private readonly Label location = new Label { AutoSize = true, MaximumSize = new Size(620, 0) };
    private readonly TextBox password = new TextBox { UseSystemPasswordChar = true, Dock = DockStyle.Fill, MaxLength = 128, AccessibleName = "Contraseña inicial" };
    private readonly TextBox confirm = new TextBox { UseSystemPasswordChar = true, Dock = DockStyle.Fill, MaxLength = 128, AccessibleName = "Confirmar contraseña inicial" };
    private readonly Button import = new Button { Text = "&Instalar servidor", AutoSize = true };
    private readonly Button prepareWindows = new Button { Text = "Preparar &Windows", AutoSize = true };
    private readonly Button setup = new Button { Text = "&Preparar acceso", AutoSize = true };
    private readonly Button recover = new Button { Text = "&Recuperar preparación", AutoSize = true };
    private readonly Button start = new Button { Text = "I&niciar servidor", AutoSize = true };
    private readonly Button stop = new Button { Text = "&Detener servidor", AutoSize = true };
    private readonly Button open = new Button { Text = "&Abrir aplicación", AutoSize = true };
    private readonly Button backup = new Button { Text = "Crear copia", AutoSize = true };
    private readonly Button drill = new Button { Text = "Comprobar recuperación", AutoSize = true };
    private readonly ToolTip help = new ToolTip();
    private bool busy, windowsReady, registered, installed, recoverable, allowClose, wasRunning;

    internal ServerWindow(string distro)
    {
        backend = new ServerBackend(distro);
        Text = "OpenMultiPOS · Servidor · " + distro;
        Font = new Font("Segoe UI", 10); BackColor = Color.FromArgb(243, 246, 250);
        AutoScaleMode = AutoScaleMode.Dpi; MinimumSize = new Size(700, 540); ClientSize = new Size(740, 540); StartPosition = FormStartPosition.CenterScreen;
        var panel = new TableLayoutPanel { Dock = DockStyle.Fill, AutoScroll = true, Padding = new Padding(24), ColumnCount = 1, RowCount = 10 };
        panel.Controls.Add(new Label { Text = "Servidor de este computador", Font = new Font("Segoe UI", 17, FontStyle.Bold), AutoSize = true });
        panel.Controls.Add(new Label { Text = "Requiere WSL2, virtualización y 30 GB libres. Mantén esta ventana abierta mientras otros equipos usan el servidor. Los datos se guardan por separado del programa, en tu perfil de Windows.", AutoSize = true, MaximumSize = new Size(620, 0), Margin = new Padding(0, 12, 0, 16) });
        panel.Controls.Add(status);
        panel.Controls.Add(new Label { Text = "Contraseña inicial de Administrator", AutoSize = true, Margin = new Padding(0, 16, 0, 4) }); panel.Controls.Add(password);
        panel.Controls.Add(new Label { Text = "Repite la contraseña inicial", AutoSize = true }); panel.Controls.Add(confirm);
        var actions = new FlowLayoutPanel { AutoSize = true, Dock = DockStyle.Fill, WrapContents = true, Margin = new Padding(0, 16, 0, 8) };
        foreach (Button button in new [] { prepareWindows, import, setup, recover, start, stop, open, backup, drill }) actions.Controls.Add(button);
        panel.Controls.Add(actions);
        var details = new FlowLayoutPanel { AutoSize = true, Dock = DockStyle.Fill };
        var refresh = new Button { Text = "Actualizar estado", AutoSize = true }; var log = new Button { Text = "Ver registros locales", AutoSize = true }; var manual = new Button { Text = "Leer manual", AutoSize = true };
        details.Controls.Add(refresh); details.Controls.Add(log); details.Controls.Add(manual); panel.Controls.Add(details);
        panel.Controls.Add(location);
        start.BackColor = Color.FromArgb(36, 95, 164); start.ForeColor = Color.White; start.FlatStyle = FlatStyle.Flat;
        Controls.Add(panel);
        help.SetToolTip(prepareWindows, "Windows pide permiso de administrador para preparar WSL, sin instalar otra distribución. Puede descargar componentes y pedir reinicio. El programa no reinicia el equipo.");
        help.SetToolTip(import, "Requiere WSL2 y la imagen del servidor junto al programa. Verifica su hash antes de importar. Los datos quedan en OpenMultiPOS\\Servidor dentro de tu perfil.");
        help.SetToolTip(setup, "Crea el sitio privado con una contraseña de 12 a 128 caracteres. Después debes completar el asistente de ERPNext en el navegador.");
        help.SetToolTip(recover, "Úsalo tras una preparación interrumpida. Conserva el intento anterior y rechaza sitios con datos comerciales o cuentas personales.");
        help.SetToolTip(stop, "Cierra los servicios de forma ordenada. Los otros equipos perderán conexión hasta volver a iniciar.");
        help.SetToolTip(password, "Solo se envía a la preparación local. El controlador no la guarda en un archivo.");
        help.SetToolTip(backup, "Con el servidor detenido, crea una copia privada verificada de base, archivos y claves. Después vuelve a iniciar.");
        help.SetToolTip(drill, "Crea una copia nueva y la restaura en otro sitio aislado. Conserva el original y el ensayo. Puede tardar y necesita espacio libre.");
        backup.Click += async delegate { await Backup(false); };
        drill.Click += async delegate { await Backup(true); };
        prepareWindows.Click += async delegate { await Work(async () => {
            if (MessageBox.Show(this, "Windows solicitará permiso de administrador para preparar WSL. Puede necesitar internet y un reinicio posterior. Guarda tu trabajo; este programa no reinicia el computador.\n\n¿Preparar Windows?", "Preparar Windows", MessageBoxButtons.YesNo, MessageBoxIcon.Question) != DialogResult.Yes) return;
            status.Text = "Sigue la preparación en la ventana de Windows. No cierres este controlador hasta que termine.";
            await backend.PrepareWindows();
            status.Text = "La preparación terminó. Si Windows pide reiniciar, guarda tu trabajo y hazlo cuando puedas. Después abre este controlador y pulsa Actualizar estado.";
        }); };
        import.Click += async delegate { await Work(async () => { status.Text = "Verificando e importando la imagen. Puede tardar varios minutos."; await Task.Run(() => backend.Import(AppDomain.CurrentDomain.BaseDirectory)); await RefreshState(); }); };
        setup.Click += async delegate { await Prepare(false); }; recover.Click += async delegate { await Prepare(true); };
        start.Click += async delegate { await Work(async () => { status.Text = "Iniciando los servicios…"; await backend.Start(); status.Text = "Servidor activo en http://localhost:8089. Conserva esta ventana abierta."; }); };
        stop.Click += async delegate { await Work(async () => { status.Text = "Deteniendo los servicios…"; await backend.Stop(); status.Text = "Servidor detenido."; }); };
        open.Click += delegate { try { Process.Start(new ProcessStartInfo("http://localhost:8089/omp") { UseShellExecute = true }); } catch { status.Text = "No se pudo abrir el navegador. Usa http://localhost:8089/omp."; } };
        refresh.Click += async delegate { await Work(RefreshState); }; log.Click += delegate { try { backend.OpenLog(); } catch { status.Text = "No se pudo abrir la carpeta de registros de tu perfil."; } };
        manual.Click += delegate { try { Process.Start(new ProcessStartInfo(Path.Combine(AppDomain.CurrentDomain.BaseDirectory, "Manual.html")) { UseShellExecute = true }); } catch { status.Text = "Conserva Manual.html junto al programa para abrir la ayuda."; } };
        Shown += async delegate { await Work(RefreshState); };
        var timer = new Timer { Interval = 1000 }; timer.Tick += delegate { if (wasRunning && !Running && !busy) status.Text = "El servidor se detuvo. Revisa los registros antes de volver a iniciar."; wasRunning = Running; ControlsState(); }; timer.Start();
        FormClosing += async delegate(object sender, FormClosingEventArgs e) {
            if (allowClose) return;
            if (busy) { e.Cancel = true; status.Text = "Espera a que termine la operación antes de cerrar."; return; }
            if (backend.Serving != null && !backend.Serving.HasExited)
            {
                e.Cancel = true;
                if (MessageBox.Show(this, "Cerrar este controlador detiene el servidor y desconecta a los demás equipos. ¿Continuar?", "Detener servidor", MessageBoxButtons.YesNo, MessageBoxIcon.Question) != DialogResult.Yes) return;
                await Work(async () => { await backend.Stop(); allowClose = true; Close(); });
            }
        };
        FormClosed += delegate { timer.Dispose(); help.Dispose(); };
    }
    private bool Running { get { return backend.Serving != null && !backend.Serving.HasExited; } }
    private void ControlsState()
    {
        prepareWindows.Enabled = !busy && !windowsReady && !Running;
        import.Enabled = !busy && windowsReady && !registered; setup.Enabled = !busy && registered && !installed && !Running;
        recover.Enabled = setup.Enabled && recoverable; start.Enabled = !busy && installed && !Running;
        stop.Enabled = !busy && Running; open.Enabled = !busy && Running; password.Enabled = confirm.Enabled = setup.Enabled;
        backup.Enabled = drill.Enabled = !busy && installed && !Running;
        AcceptButton = !windowsReady ? prepareWindows : !registered ? import : installed ? start : setup;
    }
    private async Task Work(Func<Task> action)
    {
        if (busy) return; busy = true; ControlsState();
        try { await action(); } catch (Exception error) { status.Text = error.Message; }
        finally { busy = false; wasRunning = Running; ControlsState(); }
    }
    private async Task RefreshState()
    {
        windowsReady = await Task.Run(() => backend.WindowsReady()); registered = installed = recoverable = false;
        location.Text = "Ubicación de datos: " + backend.DataFolder().Replace(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "%LOCALAPPDATA%");
        if (!windowsReady) { status.Text = "Windows todavía no confirma WSL disponible. Pulsa Preparar Windows. Si ya lo preparaste, revisa el reinicio pendiente y la virtualización. Consulta el manual si continúa."; return; }
        registered = await Task.Run(() => backend.Registered());
        if (!registered) { status.Text = "Servidor sin instalar. Requiere WSL2 y el paquete completo del servidor."; return; }
        var state = await Task.Run(() => backend.Status()); installed = Convert.ToBoolean(state["installed"]); recoverable = Convert.ToBoolean(state["recoverable"]);
        status.Text = Running ? "Servidor activo. Conserva esta ventana abierta." : installed ? "Sitio preparado. Inicia el servidor para abrir la aplicación." : recoverable ? "La preparación está incompleta. Puedes reintentar o recuperar el intento anterior." : "Crea una contraseña inicial para preparar este servidor privado.";
    }
    private async Task Prepare(bool recovery)
    {
        if (password.Text.Length < 12 || password.Text != confirm.Text) { status.Text = "Introduce y confirma la misma contraseña de 12 a 128 caracteres."; password.Focus(); return; }
        string secret = password.Text; password.Clear(); confirm.Clear();
        await Work(async () => { status.Text = "Preparando el sitio privado. La primera vez puede tardar varios minutos."; try { await Task.Run(() => backend.Setup(secret, recovery)); } finally { await RefreshState(); } });
    }
    private async Task Backup(bool check)
    {
        await Work(async () => { status.Text = check ? "Creando copia y comprobando restauración aislada…" : "Creando copia privada verificada…"; await Task.Run(() => backend.Backup(check)); status.Text = check ? "Copia y restauración verificadas. Inicia el servidor y actualiza Recuperación en la aplicación." : "Copia verificada. Inicia el servidor y actualiza Recuperación en la aplicación."; });
    }
}

internal static class ServerProgram
{
    [STAThread]
    private static int Main(string[] args)
    {
        if (args.Length == 1 && args[0] == "--self-test")
        {
            var preparation = ServerBackend.WindowsPreparation("wsl.exe");
            if (preparation.Arguments != "--install --no-distribution" || preparation.Verb != "runas" || !preparation.UseShellExecute) return 1;
            ServerBackend.CheckFreeSpace(30L * 1024 * 1024 * 1024);
            try { ServerBackend.CheckFreeSpace(30L * 1024 * 1024 * 1024 - 1); return 1; } catch (IOException) { }
            if (ServerBackend.Quote("a b") != "\"a b\"" || ServerBackend.Quote("a b\\") != "\"a b\\\\\"" || ServerBackend.Quote("a\"b") != "\"a\\\"b\"") return 1;
            if (ServerBackend.Quote("--list") != "--list" || ServerBackend.Quote("") != "\"\"") return 1;
            foreach (string bad in new [] { "Ubuntu", "OpenMultiPOS;bad", "OpenMultiPOS bad", "../OpenMultiPOS" }) { try { new ServerBackend(bad); return 1; } catch (ArgumentException) { } }
            string folder = Path.Combine(Path.GetTempPath(), "omp-controller-test-" + Guid.NewGuid().ToString("N"));
            Directory.CreateDirectory(folder);
            try
            {
                string image = Path.Combine(folder, "OpenMultiPOS-Server.wsl");
                File.WriteAllText(image, "fictional image fixture");
                string digest;
                using (var sha = SHA256.Create()) digest = BitConverter.ToString(sha.ComputeHash(File.ReadAllBytes(image))).Replace("-", "").ToLowerInvariant();
                File.WriteAllText(Path.Combine(folder, "server-image.json"), new JavaScriptSerializer().Serialize(new { schema = 1, sha256 = digest }));
                ServerBackend.VerifyImage(folder);
                File.AppendAllText(image, "corrupt");
                try { ServerBackend.VerifyImage(folder); return 1; } catch (InvalidDataException) { }
                File.WriteAllText(Path.Combine(folder, "server-image.json"), "{}");
                try { ServerBackend.VerifyImage(folder); return 1; } catch (InvalidDataException) { }
            }
            finally { Directory.Delete(folder, true); }
            return 0;
        }
        if (args.Length == 2 && args[0] == "--verify-server")
        {
            if (!Regex.IsMatch(args[1], @"\AOpenMultiPOS-[A-Za-z0-9-]*QA\z")) return 2;
            var backend = new ServerBackend(args[1]);
            try { if (!backend.WindowsReady() || !backend.Registered() || !Convert.ToBoolean(backend.Status()["installed"]) || !Directory.Exists(backend.DataFolder())) return 3; backend.VerifyInput(); backend.Start().GetAwaiter().GetResult(); backend.Stop().GetAwaiter().GetResult(); return 0; }
            catch (Exception error) { File.WriteAllText(Path.Combine(AppDomain.CurrentDomain.BaseDirectory, "verification-error.txt"), error.ToString() + "\n" + Convert.ToString(error.Data["diagnostic"])); return 4; }
            finally { try { backend.Stop().GetAwaiter().GetResult(); } catch { } }
        }
        if (args.Length == 3 && args[0] == "--verify-import")
        {
            if (!Regex.IsMatch(args[1], @"\AOpenMultiPOS-[A-Za-z0-9-]*QA\z")) return 2;
            var backend = new ServerBackend(args[1]);
            try { backend.Import(args[2]); return !Convert.ToBoolean(backend.Status()["installed"]) && Directory.Exists(backend.DataFolder()) ? 0 : 3; }
            catch (Exception error) { File.WriteAllText(Path.Combine(AppDomain.CurrentDomain.BaseDirectory, "verification-error.txt"), error.ToString() + "\n" + Convert.ToString(error.Data["diagnostic"])); return 4; }
        }
        string distro = args.Length == 2 && args[0] == "--distro" ? args[1] : "OpenMultiPOS";
        try
        {
            using (var singleton = new System.Threading.Mutex(false, "Local\\OpenMultiPOS.Server." + new ServerBackend(distro).Distro))
            {
                if (!singleton.WaitOne(0)) { MessageBox.Show("El controlador de este servidor ya está abierto.", "OpenMultiPOS"); return 0; }
                try { Application.EnableVisualStyles(); Application.SetCompatibleTextRenderingDefault(false); Application.Run(new ServerWindow(distro)); }
                finally { singleton.ReleaseMutex(); }
            }
            return 0;
        }
        catch (Exception error) { MessageBox.Show(error.Message, "No se pudo abrir el controlador"); return 1; }
    }
}
