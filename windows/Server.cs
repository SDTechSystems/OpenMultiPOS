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
        // Otherwise the first import opens Microsoft's WSL welcome window over the installer.
        using (RegistryKey key = Registry.CurrentUser.CreateSubKey(@"Software\Microsoft\Windows\CurrentVersion\Lxss")) key.SetValue("OOBEComplete", 1, RegistryValueKind.DWord);
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
    private string PreparedMarker { get { return Path.Combine(logFolder, Distro + ".prepared"); } }
    internal void MarkPrepared() { Directory.CreateDirectory(logFolder); File.WriteAllText(PreparedMarker, DateTime.UtcNow.Ticks.ToString()); }
    // wsl --status can succeed before the Virtual Machine Platform is active; only a restart completes it.
    internal bool RestartPending()
    {
        using (RegistryKey key = Registry.LocalMachine.OpenSubKey(@"SOFTWARE\Microsoft\Windows\CurrentVersion\Component Based Servicing\RebootPending"))
            if (key != null) return true;
        long ticks;
        if (!File.Exists(PreparedMarker) || !long.TryParse(File.ReadAllText(PreparedMarker).Trim(), out ticks)) return false;
        DateTime boot = DateTime.UtcNow - TimeSpan.FromMilliseconds(unchecked((uint)Environment.TickCount));
        return PreparedAfterBoot(new DateTime(ticks, DateTimeKind.Utc), boot);
    }
    internal static bool PreparedAfterBoot(DateTime prepared, DateTime boot) { return prepared > boot; }
}

// Per-user Windows startup entries; no service, scheduled task or elevation.
internal static class Autostart
{
    private const string RunKey = @"Software\Microsoft\Windows\CurrentVersion\Run";
    private const string ResumeKey = @"Software\Microsoft\Windows\CurrentVersion\RunOnce";
    private const string Name = "OpenMultiPOS Servidor";
    internal static string Command(string executable, string flag) { return ServerBackend.Quote(executable) + " " + flag; }
    internal static bool Enabled
    {
        get { using (RegistryKey key = Registry.CurrentUser.OpenSubKey(RunKey)) return key != null && key.GetValue(Name) != null; }
    }
    internal static void Set(bool enabled, string executable)
    {
        using (RegistryKey key = Registry.CurrentUser.CreateSubKey(RunKey))
            if (enabled) key.SetValue(Name, Command(executable, "--autostart")); else key.DeleteValue(Name, false);
    }
    internal static void ResumeAfterRestart(string executable)
    {
        using (RegistryKey key = Registry.CurrentUser.CreateSubKey(ResumeKey)) key.SetValue(Name, Command(executable, "--resume"));
    }
    internal static void Remove()
    {
        foreach (string path in new [] { RunKey, ResumeKey })
            using (RegistryKey key = Registry.CurrentUser.OpenSubKey(path, true)) if (key != null) key.DeleteValue(Name, false);
    }
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
    private readonly Button next = new Button { Text = "Continuar", AutoSize = true, Font = new Font("Segoe UI", 12, FontStyle.Bold), Padding = new Padding(12, 4, 12, 4) };
    private readonly CheckBox startWithWindows = new CheckBox { Text = "Iniciar el servidor al encender Windows", AutoSize = true, Margin = new Padding(0, 4, 0, 4) };
    private readonly ProgressBar progress = new ProgressBar { Style = ProgressBarStyle.Marquee, MarqueeAnimationSpeed = 30, Dock = DockStyle.Top, Height = 10, Visible = false, Margin = new Padding(0, 8, 0, 2), AccessibleName = "Trabajando" };
    private readonly Label elapsed = new Label { AutoSize = true, MaximumSize = new Size(620, 0), Visible = false };
    private readonly Label passwordHint = new Label { AutoSize = true, MaximumSize = new Size(620, 0), Margin = new Padding(0, 6, 0, 0), Font = new Font("Segoe UI", 10, FontStyle.Bold) };
    private readonly ToolTip help = new ToolTip();
    private readonly string mode;
    private static readonly Color ErrorColor = Color.FromArgb(170, 20, 20), GoodColor = Color.FromArgb(20, 110, 60);
    private bool busy, windowsReady, restartPending, registered, installed, recoverable, allowClose, wasRunning;
    private DateTime busySince;
    private static string Executable { get { return Application.ExecutablePath; } }

    // mode: "" (normal), "--autostart" (Windows sign-in) or "--resume" (after the preparation restart).
    internal ServerWindow(string distro, string mode)
    {
        this.mode = mode;
        backend = new ServerBackend(distro);
        Text = "OpenMultiPOS · Servidor propio · " + distro;
        Font = new Font("Segoe UI", 10); BackColor = Color.FromArgb(243, 246, 250);
        AutoScaleMode = AutoScaleMode.Dpi; MinimumSize = new Size(700, 540); ClientSize = new Size(740, 620); StartPosition = FormStartPosition.CenterScreen;
        var panel = new TableLayoutPanel { Dock = DockStyle.Fill, AutoScroll = true, Padding = new Padding(24), ColumnCount = 1, RowCount = 10 };
        panel.Controls.Add(new Label { Text = "OpenMultiPOS en este computador", Font = new Font("Segoe UI", 17, FontStyle.Bold), AutoSize = true });
        panel.Controls.Add(new Label { Text = "Funciona en este computador: no necesitas otro equipo. Tus datos se quedan aquí, separados del programa, y no se envían a los desarrolladores. Necesita virtualización activa y 30 GB libres; el programa prepara lo demás. Si conectas otros computadores, deja esta ventana abierta.", AutoSize = true, MaximumSize = new Size(620, 0), Margin = new Padding(0, 12, 0, 16) });
        panel.Controls.Add(status); panel.Controls.Add(progress); panel.Controls.Add(elapsed);
        next.Margin = new Padding(0, 12, 0, 4); panel.Controls.Add(next); panel.Controls.Add(startWithWindows);
        panel.Controls.Add(new Label { Text = "Contraseña inicial de Administrator (se pide en el paso 4)", AutoSize = true, Margin = new Padding(0, 16, 0, 4) }); panel.Controls.Add(password);
        panel.Controls.Add(new Label { Text = "Repite la contraseña inicial", AutoSize = true }); panel.Controls.Add(confirm); panel.Controls.Add(passwordHint);
        var actions = new FlowLayoutPanel { AutoSize = true, Dock = DockStyle.Fill, WrapContents = true, Margin = new Padding(0, 16, 0, 8) };
        foreach (Button button in new [] { prepareWindows, import, setup, recover, start, stop, open, backup, drill }) actions.Controls.Add(button);
        panel.Controls.Add(actions);
        var details = new FlowLayoutPanel { AutoSize = true, Dock = DockStyle.Fill };
        var refresh = new Button { Text = "Actualizar estado", AutoSize = true }; var log = new Button { Text = "Ver registros locales", AutoSize = true }; var manual = new Button { Text = "Leer manual", AutoSize = true };
        details.Controls.Add(refresh); details.Controls.Add(log); details.Controls.Add(manual); panel.Controls.Add(details);
        panel.Controls.Add(location);
        next.BackColor = Color.FromArgb(36, 95, 164); next.ForeColor = Color.White; next.FlatStyle = FlatStyle.Flat;
        next.FlatAppearance.BorderColor = Color.FromArgb(14, 40, 80); next.FlatAppearance.BorderSize = 2;
        next.Enter += delegate { next.FlatAppearance.BorderColor = Color.Gold; next.FlatAppearance.BorderSize = 4; };
        next.Leave += delegate { next.FlatAppearance.BorderColor = Color.FromArgb(14, 40, 80); next.FlatAppearance.BorderSize = 2; };
        foreach (Button button in new [] { prepareWindows, import, setup, recover, start, stop, open, backup, drill, refresh, log, manual })
        {
            Button target = button;
            target.Enter += delegate { target.BackColor = Color.FromArgb(255, 226, 120); };
            target.Leave += delegate { target.UseVisualStyleBackColor = true; };
        }
        password.TextChanged += delegate { UpdatePasswordHint(false); }; confirm.TextChanged += delegate { UpdatePasswordHint(false); };
        Controls.Add(panel);
        help.SetToolTip(prepareWindows, "Windows pide permiso de administrador para preparar WSL, sin instalar otra distribución. Puede descargar componentes. Después hay que reiniciar; el programa pregunta antes.");
        help.SetToolTip(import, "Requiere WSL2 y la imagen del servidor junto al programa. Verifica su hash antes de importar. Los datos quedan en OpenMultiPOS\\Servidor dentro de tu perfil.");
        help.SetToolTip(setup, "Crea el sitio privado con una contraseña de 12 a 128 caracteres. Después debes completar el asistente de ERPNext en el navegador.");
        help.SetToolTip(recover, "Úsalo tras una preparación interrumpida. Conserva el intento anterior y rechaza sitios con datos comerciales o cuentas personales.");
        help.SetToolTip(stop, "Cierra los servicios de forma ordenada. Los otros equipos perderán conexión hasta volver a iniciar.");
        help.SetToolTip(password, "Solo se envía a la preparación local. El controlador no la guarda en un archivo.");
        help.SetToolTip(backup, "Con el servidor detenido, crea una copia privada verificada de base, archivos y claves. Después vuelve a iniciar.");
        help.SetToolTip(drill, "Crea una copia nueva y la restaura en otro sitio aislado. Conserva el original y el ensayo. Puede tardar y necesita espacio libre.");
        backup.Click += async delegate { await Backup(false); };
        drill.Click += async delegate { await Backup(true); };
        help.SetToolTip(next, "Hace el siguiente paso pendiente. Puedes pulsarlo hasta que el servidor quede activo; tras el reinicio de Windows continúa solo.");
        help.SetToolTip(startWithWindows, "Al iniciar sesión en Windows abre este controlador minimizado e inicia el servidor. No crea servicios ni pide administrador.");
        prepareWindows.Click += async delegate { await Work(PrepareWindowsStep); };
        import.Click += async delegate { await Work(ImportStep); };
        setup.Click += async delegate { await Prepare(false); }; recover.Click += async delegate { await Prepare(true); };
        start.Click += async delegate { await Work(StartStep); };
        stop.Click += async delegate { await Work(async () => { status.Text = "Deteniendo los servicios…"; await backend.Stop(); status.Text = "Servidor detenido."; }); };
        open.Click += delegate { OpenApp(); };
        next.Click += async delegate { await Next(); };
        startWithWindows.Checked = Autostart.Enabled;
        startWithWindows.CheckedChanged += delegate { try { Autostart.Set(startWithWindows.Checked, Executable); } catch { status.Text = "No se pudo cambiar el inicio con Windows en tu perfil."; } };
        refresh.Click += async delegate { await Work(RefreshState); }; log.Click += delegate { try { backend.OpenLog(); } catch { status.Text = "No se pudo abrir la carpeta de registros de tu perfil."; } };
        manual.Click += delegate { try { Process.Start(new ProcessStartInfo(Path.Combine(AppDomain.CurrentDomain.BaseDirectory, "Manual.html")) { UseShellExecute = true }); } catch { status.Text = "Conserva Manual.html junto al programa para abrir la ayuda."; } };
        if (mode == "--autostart") WindowState = FormWindowState.Minimized;
        Shown += async delegate {
            await Work(RefreshState);
            // After sign-in start quietly; after the preparation restart continue the guided flow.
            if (mode == "--autostart" && installed && !Running) await Work(StartStep);
            else if (mode == "--resume" && windowsReady && !restartPending && !registered) await Next();
        };
        var timer = new Timer { Interval = 1000 }; timer.Tick += delegate { if (wasRunning && !Running && !busy) status.Text = "El servidor se detuvo. Revisa los registros antes de volver a iniciar."; wasRunning = Running; ControlsState(); ShowProgress(); }; timer.Start();
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
        import.Enabled = !busy && windowsReady && !restartPending && !registered; setup.Enabled = !busy && registered && !installed && !Running;
        recover.Enabled = setup.Enabled && recoverable; start.Enabled = !busy && installed && !Running;
        stop.Enabled = !busy && Running; open.Enabled = !busy && Running; password.Enabled = confirm.Enabled = setup.Enabled;
        backup.Enabled = drill.Enabled = !busy && installed && !Running;
        next.Enabled = !busy; next.Text = busy ? "Trabajando…" : NextLabel(); AcceptButton = next;
        next.BackColor = busy ? Color.FromArgb(205, 215, 230) : Color.FromArgb(36, 95, 164);
    }
    private string NextLabel()
    {
        if (!windowsReady) return "Paso 1 de 5 · Preparar Windows";
        if (restartPending) return "Paso 2 de 5 · Reiniciar Windows";
        if (!registered) return "Paso 3 de 5 · Instalar servidor";
        if (!installed) return "Paso 4 de 5 · Crear acceso";
        return Running ? "Abrir OpenMultiPOS" : "Paso 5 de 5 · Iniciar y abrir";
    }
    private async Task Next()
    {
        if (busy) return;
        if (!windowsReady) await Work(PrepareWindowsStep);
        else if (restartPending) RestartStep();
        else if (!registered) await Work(ImportStep);
        else if (!installed) await Prepare(false);
        else if (!Running) await Work(StartStep);
        else OpenApp();
    }
    private async Task PrepareWindowsStep()
    {
        if (MessageBox.Show(this, "Windows solicitará permiso de administrador para preparar WSL. Puede necesitar internet. Al terminar hay que reiniciar Windows; te preguntaremos antes.\n\n¿Preparar Windows?", "Preparar Windows", MessageBoxButtons.YesNo, MessageBoxIcon.Question) != DialogResult.Yes) return;
        status.Text = "Sigue la preparación en la ventana de Windows. No cierres este controlador hasta que termine.";
        await backend.PrepareWindows();
        backend.MarkPrepared();
        await RefreshState();
        if (restartPending) RestartStep();
    }
    private void RestartStep()
    {
        status.Text = "Reinicia Windows para terminar la preparación. Al volver, este programa se abrirá solo y continuará.";
        try { Autostart.ResumeAfterRestart(Executable); } catch { status.Text = "Reinicia Windows y después abre de nuevo OpenMultiPOS Servidor para continuar."; }
        if (MessageBox.Show(this, "Windows necesita reiniciarse para terminar la preparación. Guarda tu trabajo y cierra otros programas.\n\nAl volver a entrar, OpenMultiPOS Servidor se abrirá solo y continuará la instalación.\n\n¿Reiniciar ahora?", "Reiniciar Windows", MessageBoxButtons.YesNo, MessageBoxIcon.Question) != DialogResult.Yes) return;
        try { Process.Start(new ProcessStartInfo("shutdown.exe", "/r /t 15 /c \"OpenMultiPOS: reinicio para terminar la preparación\"") { UseShellExecute = false, CreateNoWindow = true }); }
        catch { status.Text = "No se pudo pedir el reinicio. Reinicia Windows desde el menú Inicio."; }
    }
    private async Task ImportStep()
    {
        status.Text = "Paso 3: verificando e instalando el servidor. Suele tardar unos 3 minutos.";
        await Task.Run(() => backend.Import(AppDomain.CurrentDomain.BaseDirectory));
        await RefreshState();
        if (registered && !installed)
        {
            status.Text = "Paso 4: crea una contraseña de 12 o más caracteres para la cuenta Administrator, repítela y pulsa Continuar. Anótala: la usarás para entrar.";
            password.Focus();
        }
    }
    private async Task StartServer()
    {
        status.Text = "Iniciando los servicios…";
        await backend.Start();
        status.Text = ActiveText();
    }
    private async Task StartStep()
    {
        await StartServer();
        if (mode != "--autostart") OpenApp();
    }
    private static string ActiveText() { return "Servidor activo en http://localhost:8089. Usuario inicial: Administrator. Conserva esta ventana abierta."; }
    private void OpenApp()
    {
        try { Process.Start(new ProcessStartInfo("http://localhost:8089/omp") { UseShellExecute = true }); }
        catch { status.Text = "No se pudo abrir el navegador. Usa http://localhost:8089/omp."; }
    }
    private async Task Work(Func<Task> action)
    {
        if (busy) return; busy = true; busySince = DateTime.UtcNow; status.ForeColor = SystemColors.ControlText; ControlsState();
        try { await action(); }
        catch (Exception error) { status.ForeColor = ErrorColor; status.Text = error.Message; System.Media.SystemSounds.Exclamation.Play(); }
        finally { busy = false; wasRunning = Running; ControlsState(); ShowProgress(); }
    }
    // Quick refreshes stay quiet; anything longer shows that the program is still working.
    private void ShowProgress()
    {
        TimeSpan time = DateTime.UtcNow - busySince;
        bool visible = busy && time.TotalSeconds >= 3;
        progress.Visible = elapsed.Visible = visible;
        if (visible) elapsed.Text = ElapsedText(time);
    }
    internal static string ElapsedText(TimeSpan time)
    {
        return "Sigue trabajando… " + (int)time.TotalMinutes + ":" + time.Seconds.ToString("00") + ". No cierres esta ventana.";
    }
    // Returns what is still wrong, or null when the password can be used.
    internal static string PasswordProblem(string value, string repeat)
    {
        if (value.Length < 12) return "Faltan " + (12 - value.Length) + " caracteres: usa 12 o más, con letras y números.";
        bool letters = false, digits = false;
        foreach (char c in value) { letters |= char.IsLetter(c); digits |= char.IsDigit(c); }
        if (!letters || !digits) return "Combina letras y números: así es más difícil de adivinar.";
        if (value != repeat) return repeat.Length == 0 ? "Repite la contraseña en el segundo campo." : "Las dos contraseñas no coinciden.";
        return null;
    }
    private void UpdatePasswordHint(bool alert)
    {
        string problem = PasswordProblem(password.Text, confirm.Text);
        bool untouched = !alert && password.TextLength == 0 && confirm.TextLength == 0;
        passwordHint.Text = untouched ? "" : problem ?? "La contraseña es válida. Pulsa Continuar.";
        passwordHint.ForeColor = problem == null ? GoodColor : ErrorColor;
        if (alert && problem != null) System.Media.SystemSounds.Exclamation.Play();
    }
    private async Task RefreshState()
    {
        windowsReady = await Task.Run(() => backend.WindowsReady()); registered = installed = recoverable = restartPending = false;
        location.Text = "Ubicación de datos: " + backend.DataFolder().Replace(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "%LOCALAPPDATA%");
        if (!windowsReady) { status.Text = "Paso 1: pulsa Continuar para preparar Windows. Si ya lo preparaste, reinicia y revisa la virtualización. Consulta el manual si continúa."; return; }
        restartPending = await Task.Run(() => backend.RestartPending());
        if (restartPending) { status.Text = "Paso 2: Windows necesita reiniciarse para terminar la preparación. Pulsa Continuar."; return; }
        registered = await Task.Run(() => backend.Registered());
        if (!registered) { status.Text = "Paso 3: pulsa Continuar para instalar el servidor. Requiere el paquete completo junto al programa."; return; }
        var state = await Task.Run(() => backend.Status()); installed = Convert.ToBoolean(state["installed"]); recoverable = Convert.ToBoolean(state["recoverable"]);
        status.Text = Running ? ActiveText() : installed ? "Sitio preparado. Pulsa Continuar para iniciar el servidor y abrir OpenMultiPOS." : recoverable ? "La preparación está incompleta. Escribe la contraseña y pulsa Continuar, o recupera el intento anterior." : "Paso 4: crea una contraseña de 12 o más caracteres para la cuenta Administrator, repítela y pulsa Continuar.";
    }
    private async Task Prepare(bool recovery)
    {
        if (PasswordProblem(password.Text, confirm.Text) != null) { UpdatePasswordHint(true); password.Focus(); return; }
        string secret = password.Text; password.Clear(); confirm.Clear(); passwordHint.Text = "";
        await Work(async () => {
            status.Text = "Paso 4: preparando tu sitio. Suele tardar unos 5 minutos.";
            try { await Task.Run(() => backend.Setup(secret, recovery)); } finally { await RefreshState(); }
            if (!installed) return;
            // A shop till must come back by itself after Windows restarts; the owner can untick it.
            if (!startWithWindows.Checked) startWithWindows.Checked = true;
            await StartServer();
            // Shown before the browser opens so it cannot end up hidden behind it.
            MessageBox.Show(this, "OpenMultiPOS está listo. Al pulsar Aceptar se abrirá en el navegador.\n\nPara entrar la primera vez:\n• Usuario: Administrator\n• Contraseña: la que acabas de crear\n\nSi el navegador muestra pantallas de bienvenida, ciérralas primero. Después el asistente te pedirá crear tu cuenta personal.", "Primer inicio de sesión", MessageBoxButtons.OK, MessageBoxIcon.Information);
            OpenApp();
        });
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
            if (Autostart.Command(@"C:\Program Files\OMP\Control.exe", "--autostart") != "\"C:\\Program Files\\OMP\\Control.exe\" --autostart") return 1;
            foreach (string weak in new [] { "", "abc1", "123456789012", "abcdefghijkl" }) if (ServerWindow.PasswordProblem(weak, weak) == null) return 1;
            if (ServerWindow.PasswordProblem("prueba-fictic1a", "prueba-fictic1a") != null || ServerWindow.PasswordProblem("prueba-fictic1a", "otra") == null) return 1;
            if (!ServerWindow.ElapsedText(TimeSpan.FromSeconds(65)).Contains("1:05")) return 1;
            var boot = new DateTime(2026, 1, 1, 8, 0, 0, DateTimeKind.Utc);
            if (!ServerBackend.PreparedAfterBoot(boot.AddMinutes(5), boot) || ServerBackend.PreparedAfterBoot(boot.AddMinutes(-5), boot)) return 1;
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
        string distro = args.Length >= 2 && args[0] == "--distro" ? args[1] : "OpenMultiPOS";
        string last = args.Length > 0 ? args[args.Length - 1] : "";
        string mode = last == "--autostart" || last == "--resume" ? last : "";
        try
        {
            using (var singleton = new System.Threading.Mutex(false, "Local\\OpenMultiPOS.Server." + new ServerBackend(distro).Distro))
            {
                if (!singleton.WaitOne(0)) { MessageBox.Show("El controlador de este servidor ya está abierto.", "OpenMultiPOS"); return 0; }
                try { Application.EnableVisualStyles(); Application.SetCompatibleTextRenderingDefault(false); Application.Run(new ServerWindow(distro, mode)); }
                finally { singleton.ReleaseMutex(); }
            }
            return 0;
        }
        catch (Exception error) { MessageBox.Show(error.Message, "No se pudo abrir el controlador"); return 1; }
    }
}
