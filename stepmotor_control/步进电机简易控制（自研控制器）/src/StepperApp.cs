using System;
using System.Drawing;
using System.Globalization;
using System.IO;
using System.IO.Ports;
using System.Linq;
using System.Threading;
using System.Threading.Tasks;
using System.Windows.Forms;

namespace SimpleStepper
{
    public sealed class MainWindow : Form
    {
        private ComboBox ports, baud, parity, stopBits, units, runMode;
        private NumericUpDown station, speed, distance;
        private Button connect, refresh, forward, reverse, pause, resume, stop, read;
        private Label state, actual;
        private RichTextBox output;
        private MotorLink link;
        private bool busy, stopping, closing, motionIssued;
        private bool runningRequested, paused;
        private Task active = Task.FromResult(0);
        private CancellationTokenSource cancellation;
        private string logFile;

        public MainWindow()
        {
            Text = "步进电机简易控制 v1.3 · 操作时间记录";
            Font = new Font("Microsoft YaHei UI", 10);
            ClientSize = new Size(820, 690);
            MinimumSize = new Size(836, 729);
            StartPosition = FormStartPosition.CenterScreen;
            AutoScaleMode = AutoScaleMode.Dpi;
            BackColor = Color.FromArgb(245, 247, 250);
            var layout = new TableLayoutPanel { Dock = DockStyle.Fill, Padding = new Padding(18), ColumnCount = 1, RowCount = 7 };
            foreach (int height in new[] { 40, 110, 138, 70, 68, 40 }) layout.RowStyles.Add(new RowStyle(SizeType.Absolute, height));
            layout.RowStyles.Add(new RowStyle(SizeType.Percent, 100));
            Controls.Add(layout);
            layout.Controls.Add(new Label { Text = "步进电机控制", Font = new Font(Font.FontFamily, 17, FontStyle.Bold), AutoSize = true });

            var connection = Group("1  连接设备");
            var connectionRows = new FlowLayoutPanel { Dock = DockStyle.Fill, Padding = new Padding(5), WrapContents = true };
            connection.Controls.Add(connectionRows);
            ports = Choice(new string[0], 100);
            baud = Choice(new[] { "1200", "2400", "4800", "9600", "19200", "38400", "57600", "115200" }, 90);
            baud.SelectedItem = "9600";
            station = Number(1, 247, 1, 65);
            refresh = Button("刷新", 65, delegate { RefreshPorts(); });
            connect = Button("连接", 90, async delegate { await ToggleConnection(); });
            Add(connectionRows, "串口", ports); connectionRows.Controls.Add(refresh);
            Add(connectionRows, "波特率", baud); Add(connectionRows, "站号", station); connectionRows.Controls.Add(connect);
            connectionRows.SetFlowBreak(connect, true);
            parity = Choice(new[] { "无校验", "奇校验", "偶校验" }, 95);
            stopBits = Choice(new[] { "1", "2" }, 60);
            Add(connectionRows, "校验", parity); Add(connectionRows, "停止位", stopBits);
            connectionRows.Controls.Add(new Label { Text = "数据位固定为 8", AutoSize = true, Margin = new Padding(15, 7, 0, 0) });
            layout.Controls.Add(connection);

            var parameters = Group("2  运行参数（先设置速度，再点击正转 / 反转）");
            var parameterRows = new FlowLayoutPanel { Dock = DockStyle.Fill, Padding = new Padding(5) };
            parameters.Controls.Add(parameterRows);
            speed = Number(1, 800, 10, 85);
            runMode = Choice(new[] { "连续运行（直到停止）", "定量行程" }, 225);
            distance = Number(1, 65535, 90, 90);
            units = Choice(new[] { "角度（°）", "圈数", "脉冲（16位）" }, 130);
            Add(parameterRows, "速度（圈/分）", speed); Add(parameterRows, "运行方式", runMode);
            parameterRows.SetFlowBreak(runMode, true);
            Add(parameterRows, "定量行程", distance); parameterRows.Controls.Add(units);
            var note = new Label { Text = "连续模式无需填写行程。运行中修改速度或方向，请先停止。", AutoSize = true, Margin = new Padding(5, 8, 0, 0) };
            parameterRows.SetFlowBreak(units, true); parameterRows.Controls.Add(note);
            runMode.SelectedIndexChanged += delegate { UpdateControls(); };
            layout.Controls.Add(parameters);

            var actions = new FlowLayoutPanel { Dock = DockStyle.Fill, Padding = new Padding(0, 12, 0, 0) };
            forward = Button("正转", 105, async delegate { await StartMotion(true); });
            reverse = Button("反转", 105, async delegate { await StartMotion(false); });
            pause = Button("暂停", 85, async delegate { await PauseOrResume(true); });
            resume = Button("继续", 85, async delegate { await PauseOrResume(false); });
            stop = Button("停止  Esc", 135, async delegate { await StopMotor(); });
            stop.BackColor = Color.FromArgb(190, 38, 48); stop.ForeColor = Color.White; stop.FlatStyle = FlatStyle.Flat;
            read = Button("读取状态", 110, async delegate { await ReadStatus(); });
            actions.Controls.AddRange(new Control[] { forward, reverse, pause, resume, stop, read });
            layout.Controls.Add(actions);
            actual = new Label { Dock = DockStyle.Fill, Text = "设备参数：尚未读取\r\n位置与限位：尚未读取", Padding = new Padding(6), BackColor = Color.White };
            layout.Controls.Add(actual);
            state = new Label { Dock = DockStyle.Fill, Text = "未连接。选择串口后点击连接。", Padding = new Padding(4, 10, 0, 0) };
            layout.Controls.Add(state);
            output = new RichTextBox { Dock = DockStyle.Fill, ReadOnly = true, BorderStyle = BorderStyle.FixedSingle, BackColor = Color.White, Font = new Font("Consolas", 9) };
            layout.Controls.Add(output);
            KeyPreview = true;
            KeyDown += async delegate(object sender, KeyEventArgs e)
            {
                if (e.KeyCode == Keys.Escape)
                {
                    e.Handled = true; Log("【操作】按 Esc：停止。"); await StopMotor();
                }
            };
            FormClosing += OnClosing;
            try
            {
                string dir = Path.Combine(AppDomain.CurrentDomain.BaseDirectory, "logs");
                Directory.CreateDirectory(dir);
                logFile = Path.Combine(dir, DateTimeOffset.UtcNow.ToOffset(TimeSpan.FromHours(8)).ToString("yyyyMMdd_HHmmss_fff", CultureInfo.InvariantCulture) + ".log");
            }
            catch { logFile = null; }
            RefreshPorts(); UpdateControls();
            Log("日志时间采用 UTC+08:00（Australia/Perth），包含完整日期，精确到毫秒。");
            Log("启动完成。运动由按钮触发；连接时只读取速度，不改变设备参数。");
        }

        private static GroupBox Group(string name) { return new GroupBox { Text = name, Dock = DockStyle.Fill, Padding = new Padding(8) }; }
        private static ComboBox Choice(string[] items, int width)
        {
            var c = new ComboBox { DropDownStyle = ComboBoxStyle.DropDownList, Width = width, Margin = new Padding(4, 4, 8, 4) };
            c.Items.AddRange(items); if (items.Length > 0) c.SelectedIndex = 0; return c;
        }
        private static NumericUpDown Number(int min, int max, int value, int width)
        {
            return new NumericUpDown { Minimum = min, Maximum = max, Value = value, Width = width, Margin = new Padding(4, 4, 8, 4) };
        }
        private Button Button(string text, int width, EventHandler click)
        {
            var b = new Button { Text = text, Width = width, Height = 34, Margin = new Padding(3), UseVisualStyleBackColor = true };
            b.Click += delegate(object sender, EventArgs e)
            {
                Log("【操作】点击“" + b.Text + "”。");
                click(sender, e);
            };
            return b;
        }
        private static void Add(FlowLayoutPanel row, string text, Control control)
        {
            row.Controls.Add(new Label { Text = text, AutoSize = true, Margin = new Padding(4, 8, 0, 0) }); row.Controls.Add(control);
        }
        private void RefreshPorts()
        {
            string previous = ports.Text;
            string[] names = SerialPort.GetPortNames().OrderBy(n => n.Length).ThenBy(n => n).ToArray();
            ports.Items.Clear(); ports.Items.AddRange(names);
            if (names.Contains(previous)) ports.SelectedItem = previous;
            else if (names.Contains("COM9")) ports.SelectedItem = "COM9";
            else if (names.Length > 0) ports.SelectedIndex = 0;
        }
        private void UpdateControls()
        {
            bool opened = link != null, idle = !busy && !stopping;
            ports.Enabled = baud.Enabled = station.Enabled = parity.Enabled = stopBits.Enabled = refresh.Enabled = !opened && idle;
            connect.Enabled = idle; connect.Text = opened ? "断开" : "连接";
            forward.Enabled = reverse.Enabled = opened && idle && !runningRequested;
            pause.Enabled = opened && idle && runningRequested && !paused;
            resume.Enabled = opened && idle && runningRequested && paused;
            read.Enabled = opened && idle;
            speed.Enabled = runMode.Enabled = idle && !runningRequested;
            distance.Enabled = units.Enabled = idle && !runningRequested && runMode.SelectedIndex == 1;
            stop.Enabled = opened && !stopping;
        }
        private void Log(string text)
        {
            LogAt(DateTimeOffset.UtcNow, text);
        }
        // Capture event time before dispatching to the UI, so a busy output
        // window cannot change the recorded time of a serial/action event.
        private void LogAt(DateTimeOffset occurredAt, string text)
        {
            if (IsDisposed) return;
            if (InvokeRequired)
            {
                try { BeginInvoke(new Action<DateTimeOffset, string>(LogAt), occurredAt, text); }
                catch (InvalidOperationException) { }
                return;
            }
            string line = occurredAt.ToOffset(TimeSpan.FromHours(8)).ToString("yyyy-MM-dd HH:mm:ss.fff zzz", CultureInfo.InvariantCulture)
                + "  " + text + Environment.NewLine;
            if (output.TextLength > 80000) output.Clear();
            output.AppendText(line); output.ScrollToCaret();
            if (logFile != null) { try { File.AppendAllText(logFile, line, System.Text.Encoding.UTF8); } catch { } }
        }
        private void Status(string message)
        {
            Log(message);
            if (InvokeRequired) { BeginInvoke(new Action(delegate { state.Text = message; })); return; }
            state.Text = message;
        }
        private async Task Run(Action<CancellationToken> action)
        {
            if (busy || stopping || link == null) return;
            busy = true; UpdateControls();
            var current = new CancellationTokenSource(); cancellation = current;
            try
            {
                active = Task.Run(delegate { action(current.Token); });
                await active;
            }
            catch (OperationCanceledException) { Log("当前操作已中断，停止指令优先。"); }
            catch (Exception ex) { Status("操作失败：" + ex.Message); }
            finally
            {
                if (cancellation == current) cancellation = null;
                current.Dispose(); busy = false; UpdateControls();
            }
        }
        private async Task ToggleConnection()
        {
            if (link != null) { await Disconnect(); return; }
            if (String.IsNullOrEmpty(ports.Text)) { Status("没有可用串口，请插入 USB 转 RS485 转换器后刷新。"); return; }
            try
            {
                Parity p = parity.SelectedIndex == 1 ? Parity.Odd : parity.SelectedIndex == 2 ? Parity.Even : Parity.None;
                string portName = ports.Text;
                Log("【连接】请求打开 " + portName + "；波特率 " + baud.Text + "；站号 " + station.Value
                    + "；8 数据位；" + parity.Text + "；" + stopBits.Text + " 停止位。");
                link = new MotorLink(portName, Int32.Parse(baud.Text), (byte)station.Value, p,
                    stopBits.SelectedIndex == 1 ? StopBits.Two : StopBits.One, Log);
                Status("串口已打开，正在验证通信……"); UpdateControls();
                await Run(delegate(CancellationToken token)
                {
                    ushort value = link.ReadWord(4, token);
                    Status("通信正常：" + portName + "，设备速度 " + value + " 圈/分。设置速度后点击正转或反转。");
                });
            }
            catch (Exception ex)
            {
                if (link != null) link.Dispose(); link = null;
                Status("连接失败：" + ex.Message); UpdateControls();
            }
        }
        private async Task StartMotion(bool positive)
        {
            if (busy || stopping || link == null || runningRequested) return;
            ushort rpm = (ushort)speed.Value, travel = (ushort)distance.Value;
            ushort register = units.SelectedIndex == 0 ? (ushort)7 : units.SelectedIndex == 1 ? (ushort)6 : (ushort)5;
            bool continuous = runMode.SelectedIndex == 0, sent = false;
            Log("【操作】开始" + (positive ? "正转" : "反转") + "；速度 " + rpm + " 圈/分；"
                + (continuous ? "连续运行。" : "行程 " + travel + " " + units.Text + "。"));
            runningRequested = true; paused = false;
            await Run(delegate(CancellationToken token)
            {
                link.SetAndVerify(4, rpm, token);
                if (continuous) link.SetContinuousTravel(token);
                else link.SetAndVerify(register, travel, token);
                token.ThrowIfCancellationRequested();
                motionIssued = true; sent = true;
                bool confirmed = link.Command(1, positive ? (ushort)3 : (ushort)4, token);
                Status((positive ? "正转" : "反转") + " " + rpm + " 圈/分 · "
                    + (continuous ? "连续运行，点击停止结束。" : "定量行程；完成后点击停止可重新设置。")
                    + (confirmed ? "指令已确认。" : "未收到启动确认，请观察设备。"));
            });
            if (!sent) runningRequested = false;
            UpdateControls();
        }
        private async Task PauseOrResume(bool shouldPause)
        {
            if (!runningRequested || busy || stopping || paused == shouldPause) return;
            bool confirmed = false;
            await Run(delegate(CancellationToken token)
            {
                confirmed = link.Command(2, shouldPause ? (ushort)0 : (ushort)1, token);
                Status((shouldPause ? "暂停" : "继续") + (confirmed ? "指令已确认。" : "指令已发送，未收到确认；可点击停止。"));
            });
            if (confirmed && runningRequested) paused = shouldPause;
            UpdateControls();
        }
        private async Task ReadStatus()
        {
            await Run(delegate(CancellationToken token)
            {
                ushort rpm = link.ReadWord(4, token), limit = link.ReadWord(23, token);
                short angle = Protocol.Signed16(link.Read(22, 1, token));
                int pulses = Protocol.Signed32(link.Read(24, 2, token));
                string[] states = { "未触发", "正转限位触发", "反转限位触发", "两个限位均触发" };
                string info = "设备速度：" + rpm + " 圈/分    限位：" + (limit < 4 ? states[limit] : limit.ToString())
                    + "\r\n相对原点位置：" + angle + "°    脉冲位置：" + pulses + "    读取时间："
                    + DateTimeOffset.UtcNow.ToOffset(TimeSpan.FromHours(8)).ToString("HH:mm:ss zzz", CultureInfo.InvariantCulture);
                BeginInvoke(new Action(delegate { actual.Text = info; }));
                Status("状态读取成功。位置与限位为本次读取值。");
            });
        }
        private async Task StopMotor()
        {
            if (link == null || stopping) return;
            Log("【操作】请求停止电机。");
            stopping = true; UpdateControls();
            if (cancellation != null) cancellation.Cancel();
            try { await active; } catch { }
            try
            {
                MotorLink target = link;
                bool confirmed = await Task.Run(delegate { return target.Command(3, 1, CancellationToken.None); });
                if (confirmed) { motionIssued = false; runningRequested = false; paused = false; }
                Status(confirmed ? "停止指令已确认。" : "停止指令已发送，未收到确认。请现场确认电机已停止。");
            }
            catch (Exception ex) { Status("停止失败：" + ex.Message + " 请现场停止电机。"); }
            finally { stopping = false; UpdateControls(); }
        }
        private async Task Disconnect()
        {
            if (link == null) return;
            Log("【连接】开始断开；本次发送过运动指令时，先尝试停止。");
            if (motionIssued) await StopMotor();
            if (link != null) link.Dispose(); link = null; motionIssued = false; runningRequested = false; paused = false;
            Status("已断开。"); UpdateControls();
        }
        private async void OnClosing(object sender, FormClosingEventArgs e)
        {
            if (closing) { Log("程序已关闭。"); return; }
            Log("【操作】请求关闭程序。");
            if (busy || stopping) { e.Cancel = true; Status("请等待当前操作完成，或点击停止后关闭窗口。"); return; }
            if (link == null) { Log("程序已关闭。"); return; }
            e.Cancel = true;
            await Disconnect(); closing = true; Close();
        }

        public void SavePreview(string path)
        {
            using (var bitmap = new Bitmap(Width, Height)) { DrawToBitmap(bitmap, new Rectangle(0, 0, Width, Height)); bitmap.Save(path); }
        }
    }

    internal static class Program
    {
        [STAThread]
        private static void Main(string[] args)
        {
            Application.EnableVisualStyles(); Application.SetCompatibleTextRenderingDefault(false);
            var window = new MainWindow();
            if (args.Length == 2 && args[0] == "--preview")
            {
                var timer = new System.Windows.Forms.Timer { Interval = 350 };
                timer.Tick += delegate { timer.Stop(); window.SavePreview(args[1]); window.Close(); timer.Dispose(); };
                window.Shown += delegate { timer.Start(); };
            }
            Application.Run(window);
        }
    }
}
