using System;
using System.Diagnostics;
using System.Drawing;
using System.IO;
using System.Windows.Forms;

[assembly: System.Reflection.AssemblyTitle("OpenMultiPOS")]
[assembly: System.Reflection.AssemblyVersion("0.1.0.0")]

internal static class Client
{
    internal static string Address(string text)
    {
        Uri uri;
        if (!Uri.TryCreate(text.Trim(), UriKind.Absolute, out uri)
            || !String.IsNullOrEmpty(uri.UserInfo)
            || !String.IsNullOrEmpty(uri.Query)
            || !String.IsNullOrEmpty(uri.Fragment)
            || (uri.AbsolutePath != "/" && uri.AbsolutePath != "/omp"))
            throw new ArgumentException("Escribe la dirección del servidor, sin usuario, contraseña ni parámetros.");
        bool local = uri.IsLoopback || uri.Host.Equals("omp.localhost", StringComparison.OrdinalIgnoreCase);
        if (uri.Scheme != "https" && !(uri.Scheme == "http" && local))
            throw new ArgumentException("Usa HTTPS para un servidor remoto. HTTP se admite solo en este computador.");
        return uri.GetLeftPart(UriPartial.Authority) + "/omp";
    }

    [STAThread]
    private static int Main(string[] args)
    {
        if (Array.IndexOf(args, "--self-test") >= 0)
        {
            if (Address("http://localhost:8089") != "http://localhost:8089/omp"
                || Address("http://omp.localhost:8000") != "http://omp.localhost:8000/omp"
                || Address("https://pos.example.invalid/omp") != "https://pos.example.invalid/omp") return 1;
            foreach (string bad in new [] { "file:///C:/Windows", "javascript:alert(1)", "http://example.invalid", "https://user:secret@example.invalid", "https://example.invalid/?token=secret", "https://example.invalid/#sales", "https://example.invalid/elsewhere" })
            {
                try { Address(bad); return 1; } catch (ArgumentException) { }
            }
            return 0;
        }
        Application.EnableVisualStyles();
        Application.SetCompatibleTextRenderingDefault(false);
        string folder = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "OpenMultiPOS");
        string config = Path.Combine(folder, "connection.txt");
        try
        {
            if (File.Exists(config) && Array.IndexOf(args, "--configure") < 0)
            {
                Process.Start(new ProcessStartInfo(Address(File.ReadAllText(config))) { UseShellExecute = true });
                return 0;
            }
            using (Form form = new Form())
            {
                form.Text = "OpenMultiPOS · Conectar a mi servidor";
                form.Font = new Font("Segoe UI", 10);
                form.BackColor = Color.FromArgb(243, 246, 250);
                form.AutoScaleMode = AutoScaleMode.Dpi;
                form.MinimumSize = new Size(540, 440);
                form.ClientSize = new Size(600, 420);
                form.StartPosition = FormStartPosition.CenterScreen;
                var panel = new TableLayoutPanel { Dock = DockStyle.Fill, AutoScroll = true, Padding = new Padding(24), ColumnCount = 1, RowCount = 5 };
                panel.RowStyles.Add(new RowStyle(SizeType.AutoSize));
                panel.RowStyles.Add(new RowStyle(SizeType.AutoSize));
                panel.RowStyles.Add(new RowStyle(SizeType.AutoSize));
                panel.RowStyles.Add(new RowStyle(SizeType.AutoSize));
                panel.RowStyles.Add(new RowStyle(SizeType.Percent, 100));
                panel.Controls.Add(new Label { Text = "Conectar a un servidor de tu negocio", AutoSize = true, Font = new Font("Segoe UI", 15, FontStyle.Bold), Margin = new Padding(0, 0, 0, 12) });
                panel.Controls.Add(new Label { Text = "Los datos se guardan en el servidor cuya dirección escribas. No se incluye una conexión a los desarrolladores. Para guardar datos en este equipo, instala la edición Servidor propio. Cambiar de dirección no traslada datos entre servidores.", AutoSize = true, MaximumSize = new Size(540, 0), Margin = new Padding(0, 0, 0, 16) });
                panel.Controls.Add(new Label { Text = "&Dirección HTTPS del servidor", AutoSize = true });
                var address = new TextBox { Dock = DockStyle.Fill, AccessibleName = "Dirección del servidor", Text = File.Exists(config) ? File.ReadAllText(config) : "" };
                panel.Controls.Add(address);
                var actions = new FlowLayoutPanel { Dock = DockStyle.Fill, Padding = new Padding(0, 16, 0, 0), AutoSize = true };
                var open = new Button { Text = "Guardar y abrir", AutoSize = true, BackColor = Color.FromArgb(36, 95, 164), ForeColor = Color.White, FlatStyle = FlatStyle.Flat };
                var manual = new Button { Text = "Leer el manual", AutoSize = true };
                var help = new ToolTip();
                help.SetToolTip(address, "Escribe la dirección de tu propio servidor. En ese computador puedes usar http://localhost:8089. En los demás, usa su dirección HTTPS privada.");
                help.SetToolTip(open, "Guarda solo la dirección en tu perfil de Windows. No guarda tu contraseña.");
                open.Click += delegate {
                    try
                    {
                        string url = Address(address.Text);
                        Directory.CreateDirectory(folder);
                        string temporary = config + ".new";
                        File.WriteAllText(temporary, url);
                        if (File.Exists(config)) File.Replace(temporary, config, null);
                        else File.Move(temporary, config);
                        Process.Start(new ProcessStartInfo(url) { UseShellExecute = true });
                        form.Close();
                    }
                    catch (Exception error) { MessageBox.Show(form, error.Message, "Revisa la conexión", MessageBoxButtons.OK, MessageBoxIcon.Warning); address.Focus(); }
                };
                manual.Click += delegate {
                    try { Process.Start(new ProcessStartInfo(Path.Combine(AppDomain.CurrentDomain.BaseDirectory, "Manual.html")) { UseShellExecute = true }); }
                    catch (Exception error) { MessageBox.Show(form, error.Message, "No se pudo abrir el manual"); }
                };
                actions.Controls.Add(open);
                actions.Controls.Add(manual);
                panel.Controls.Add(actions);
                form.Controls.Add(panel);
                form.AcceptButton = open;
                Application.Run(form);
                help.Dispose();
            }
            return 0;
        }
        catch (Exception error)
        {
            MessageBox.Show(error.Message + "\nAbre Configurar.cmd para revisar la dirección.", "OpenMultiPOS", MessageBoxButtons.OK, MessageBoxIcon.Error);
            return 1;
        }
    }
}
