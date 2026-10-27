using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.IO.Ports;
using System.Threading;

namespace SimpleStepper
{
    // Register numbers come from the supplied manufacturer's V2.1 application.
    public static class Protocol
    {
        public static byte[] WithCrc(params byte[] data)
        {
            ushort crc = 0xffff;
            foreach (byte b in data)
            {
                crc ^= b;
                for (int i = 0; i < 8; i++)
                    crc = (ushort)(((crc & 1) != 0) ? (crc >> 1) ^ 0xa001 : crc >> 1);
            }
            byte[] result = new byte[data.Length + 2];
            Array.Copy(data, result, data.Length);
            result[data.Length] = (byte)crc;
            result[data.Length + 1] = (byte)(crc >> 8);
            return result;
        }

        public static bool ValidCrc(byte[] frame)
        {
            if (frame == null || frame.Length < 5) return false;
            byte[] data = new byte[frame.Length - 2];
            Array.Copy(frame, data, data.Length);
            byte[] expected = WithCrc(data);
            return expected[frame.Length - 2] == frame[frame.Length - 2]
                && expected[frame.Length - 1] == frame[frame.Length - 1];
        }

        public static byte[] Request(byte address, byte function, ushort register, ushort value)
        {
            if (address < 1 || address > 247) throw new ArgumentOutOfRangeException("address");
            if (function != 3 && function != 6) throw new ArgumentOutOfRangeException("function");
            return WithCrc(address, function, (byte)(register >> 8), (byte)register,
                (byte)(value >> 8), (byte)value);
        }

        // Discard noise, reject corrupt packets, and preserve partial/concatenated packets.
        public static byte[] TakeFrame(List<byte> buffer, byte address, byte function)
        {
            for (int start = 0; start + 4 < buffer.Count; start++)
            {
                if (buffer[start] != address) continue;
                byte f = buffer[start + 1];
                if (f != function && f != (function | 0x80)) continue;
                int size = (f & 0x80) != 0 ? 5 : f == 3 ? buffer[start + 2] + 5 : 8;
                if (size < 5 || size > 255 || start + size > buffer.Count) continue;
                byte[] frame = buffer.GetRange(start, size).ToArray();
                if (!ValidCrc(frame)) continue;
                buffer.RemoveRange(0, start + size);
                return frame;
            }
            if (buffer.Count > 512) buffer.RemoveRange(0, buffer.Count - 255);
            return null;
        }

        public static bool Matches(byte[] request, byte[] response)
        {
            if (!ValidCrc(response) || response[0] != request[0]) return false;
            if (response[1] == (request[1] | 0x80))
                throw new IOException("控制器返回异常码 0x" + response[2].ToString("X2"));
            if (response[1] != request[1]) return false;
            if (request[1] == 6)
            {
                if (response.Length != request.Length) return false;
                for (int i = 0; i < request.Length; i++) if (response[i] != request[i]) return false;
                return true;
            }
            return response[2] == (request[4] * 256 + request[5]) * 2;
        }

        public static short Signed16(byte[] frame) { return unchecked((short)(frame[3] * 256 + frame[4])); }
        public static int Signed32(byte[] frame)
        {
            return unchecked((int)((uint)frame[3] << 24 | (uint)frame[4] << 16 | (uint)frame[5] << 8 | frame[6]));
        }
    }

    public sealed class MotorLink : IDisposable
    {
        private readonly SerialPort port;
        private readonly Action<string> log;
        private readonly List<byte> buffer = new List<byte>();
        private readonly Stopwatch gap = Stopwatch.StartNew();
        public readonly byte Address;

        public MotorLink(string name, int baud, byte address, Parity parity, StopBits stop, Action<string> logger)
        {
            Address = address;
            log = logger;
            port = new SerialPort(name, baud, parity, 8, stop);
            port.ReadTimeout = 20;
            port.WriteTimeout = 300;
            port.DtrEnable = false;
            port.RtsEnable = false;
            try { port.Open(); } catch { port.Dispose(); throw; }
        }

        private byte[] Exchange(byte[] request, CancellationToken cancel, int timeout)
        {
            cancel.ThrowIfCancellationRequested();
            // More than 3.5 character times, including at 1200 baud.
            int silentMs = Math.Max(8, (int)Math.Ceiling(40.0 * 1000 / port.BaudRate));
            while (gap.ElapsedMilliseconds < silentMs) { cancel.ThrowIfCancellationRequested(); Thread.Sleep(2); }
            buffer.Clear();
            port.DiscardInBuffer();
            cancel.ThrowIfCancellationRequested();
            port.Write(request, 0, request.Length);
            gap.Restart();
            log("TX  " + BitConverter.ToString(request).Replace('-', ' '));
            Stopwatch watch = Stopwatch.StartNew();
            while (watch.ElapsedMilliseconds < timeout)
            {
                cancel.ThrowIfCancellationRequested();
                int count = port.BytesToRead;
                if (count > 0)
                {
                    byte[] data = new byte[count];
                    int n = port.Read(data, 0, data.Length);
                    for (int i = 0; i < n; i++) buffer.Add(data[i]);
                    gap.Restart();
                    log("RX  " + BitConverter.ToString(data, 0, n).Replace('-', ' '));
                }
                byte[] frame;
                while ((frame = Protocol.TakeFrame(buffer, Address, request[1])) != null)
                    if (Protocol.Matches(request, frame)) return frame;
                Thread.Sleep(5);
            }
            throw new TimeoutException("未收到有效回复。请检查串口、站号、波特率、供电和 A/B 接线。");
        }

        public byte[] Read(ushort register, ushort words, CancellationToken cancel)
        {
            return Exchange(Protocol.Request(Address, 3, register, words), cancel, 900);
        }
        public ushort ReadWord(ushort register, CancellationToken cancel)
        {
            byte[] data = Read(register, 1, cancel);
            return (ushort)(data[3] * 256 + data[4]);
        }

        public void SetAndVerify(ushort register, ushort value, CancellationToken cancel)
        {
            VerifySetting(register, value,
                delegate { Exchange(Protocol.Request(Address, 6, register, value), cancel, 450); },
                delegate { return ReadWord(register, cancel); }, log);
        }

        // KWL-US-M02A manufacturer's register table: 0x05 travel = 0 means
        // rotate continuously. This sets a mode; it does not start motion.
        // Manufacturer's KWL-US-M02A register table: 0x05=0 means continuous.
        public void SetContinuousTravel(CancellationToken cancel)
        {
            SetAndVerify(5, 0, cancel);
            log("连续运行行程已核对：0 脉冲（由停止指令结束）。");
        }

        // The vendor writes circles/degrees to 0x06/0x07, but its travel read
        // always targets 0x05. Do not interpret a same-address read of these
        // write selectors as a readback of the entered circles/degrees value.
        internal static void VerifySetting(ushort register, ushort value,
            Action writeWithValidatedEcho, Func<ushort> readBack, Action<string> logger)
        {
            bool usesWriteEcho = register == 6 || register == 7;
            try { writeWithValidatedEcho(); }
            catch (TimeoutException)
            {
                if (usesWriteEcho)
                    throw new IOException("未收到行程写入确认，未发送运动指令。请检查通信后重试。");
                logger("写入未收到回显，正在读取参数核对（不重发写入）。");
            }
            if (usesWriteEcho)
            {
                logger("行程写入确认成功（" + value + (register == 7 ? "°" : " 圈")
                    + "）；此模式不使用同地址读回核对。");
                return;
            }
            ushort actual = readBack();
            if (actual != value) throw new IOException("参数核对失败，寄存器 0x" + register.ToString("X2")
                + "：期望 " + value + "，读到 " + actual + "。未发送运动指令。");
        }

        public bool Command(ushort register, ushort value, CancellationToken cancel)
        {
            try { Exchange(Protocol.Request(Address, 6, register, value), cancel, 500); return true; }
            catch (TimeoutException) { return false; } // Never retry a motion command.
        }
        public void Dispose() { port.Dispose(); }
    }
}
