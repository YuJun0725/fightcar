#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""传感器实验桌面端。采集和落盘在线程中，Tk 仅负责操作和显示。"""

import argparse
from collections import deque
import csv
import json
import math
from pathlib import Path
import queue
import select
import shutil
import socket
import subprocess
import sys
import threading
import time
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from sensor_analysis import (EXPERIMENTS, SessionStore, build_calibration,
    dynamic_photoelectric, estimate_distance, filter_values, load_session,
    photoelectric_summary, position_at, summarize, validate_calibration)

ROOT = Path(__file__).resolve().parents[2]


class SensorWorker:
    """一个后台线程拥有套接字和记录器，GUI 阻塞不影响保存。"""

    def __init__(self):
        self.commands = queue.Queue(maxsize=100)
        self.events = queue.Queue()
        self.lock = threading.Lock()
        self.recent = deque(maxlen=35000)
        self.connected = False
        self.trial_id = None
        self.store = None
        self.path = None
        self.sample_count = 0
        self.rate = 0.0
        self.latest = None
        self._quit = False
        self._sock = None
        self._last_seq = 0
        self._reason = ""
        self._deadline = None
        self._start_wait = None
        self._last_receive = time.monotonic()
        self._handshake_at = None
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def submit(self, action, **data):
        try:
            self.commands.put_nowait((action, data))
        except queue.Full:
            self._reason = "操作队列已满，本次记录不完整"
            self.events.put(("error", self._reason))
            if self._sock:
                try:
                    self._sock.shutdown(socket.SHUT_RDWR)
                except OSError:
                    pass

    def view(self):
        with self.lock:
            return list(self.recent), self.sample_count, self.rate, self.latest

    def _send(self, packet):
        if self._sock is None:
            raise ConnectionError("尚未连接采集服务")
        packet.setdefault("request_id", str(time.monotonic_ns()))
        self._sock.sendall((json.dumps(packet, ensure_ascii=False) + "\n").encode("utf-8"))

    def _finish(self, complete, reason=""):
        if self.trial_id is None:
            return
        trial_id = self.trial_id
        reason = self._reason or reason
        try:
            self.store.flush()
            self.store.finish_trial(status="complete" if complete and not reason else "incomplete", reason=reason)
        except Exception as error:
            complete = False
            reason = "保存失败，记录不完整：" + str(error)
            self.events.put(("error", reason))
            try:
                self.store.finish_trial(status="incomplete", reason=reason)
            except Exception:
                # 持续的磁盘故障无法写入状态；重开时 recording 会被识别为不完整。
                pass
        finally:
            self.trial_id = None
            self._deadline = self._start_wait = None
            self.events.put(("finished", {"trial_id": trial_id, "path": str(self.path),
                "complete": complete and not reason, "reason": reason}))

    def _disconnect(self, reason="连接已断开"):
        try:
            self._finish(False, reason)
        except Exception as error:
            self.events.put(("error", "记录未完整关闭：" + str(error)))
        if self._sock:
            self._sock.close()
        self._sock = None
        self.connected = False
        self._handshake_at = None
        self.events.put(("disconnected", reason))

    def _command(self, action, data):
        if action == "connect":
            self._disconnect("重新连接")
            self._sock = socket.create_connection((data["host"], data["port"]), timeout=3)
            self._sock.settimeout(1)
            self._last_receive = time.monotonic()
            self._handshake_at = self._last_receive
            return
        if action == "disconnect":
            self._disconnect()
            return
        if action == "close":
            if self.trial_id:
                try:
                    self._send({"type": "stop", "trial_id": self.trial_id})
                except OSError:
                    pass
            self._disconnect("窗口关闭，未收到完整停止确认")
            try:
                if self.store:
                    self.store.close()
            finally:
                self._quit = True
            return
        if action == "new_session":
            if self.trial_id:
                raise ValueError("请先停止当前采集")
            if self.store:
                self.store.close()
            self.store, self.path = None, None
            self.events.put(("new_session", None))
            return
        if action == "start":
            if not self.connected or self.trial_id:
                raise ValueError("请先连接，且不能重复开始采集")
            metadata = data["metadata"]
            if self.store is None:
                self.store = SessionStore(data["root"], metadata["experiment"], metadata)
                self.path = self.store.path
            self.trial_id = self.store.start_trial(metadata)
            self._last_seq, self._reason = 0, ""
            self._point_duration = data.get("duration")
            self._deadline = None
            self._start_wait = time.monotonic()
            self._last_receive = self._start_wait
            self._first_t = None
            with self.lock:
                self.recent.clear()
                self.sample_count, self.rate, self.latest = 0, 0.0, None
            packet = data["packet"]
            packet.update(type="start", trial_id=self.trial_id)
            self._send(packet)
            self.events.put(("recording", {"path": str(self.path), "trial_id": self.trial_id}))
            return
        if action == "stop":
            if self.trial_id:
                self._deadline = None
                self._start_wait = time.monotonic()
                self._send({"type": "stop", "trial_id": self.trial_id})
            return
        if action == "mark":
            if self.trial_id:
                self._send({"type": "mark", "trial_id": self.trial_id,
                    "name": data["name"], "data": data.get("data", {})})
            return
        if action == "save_summary":
            if self.store:
                self.store.save_summary(data["rows"])
            return
        if action == "save_calibration":
            if self.store:
                self.store.save_calibration(data["model"])
            return
        if action == "status" and self.connected:
            self._send({"type": "status"})

    def _packet(self, packet):
        kind = packet.get("type")
        if kind == "hello":
            if packet.get("protocol") != 1:
                raise ValueError("采集协议版本不兼容")
            self.connected = True
            self._handshake_at = None
            self.events.put(("connected", packet))
            return
        if kind == "error":
            if packet.get("fatal") or packet.get("incomplete"):
                self._reason = packet.get("message", "采集服务异常")
            self.events.put(("error", packet.get("message", "服务端错误")))
            return
        if kind == "status":
            self.events.put(("status", packet))
            return
        if packet.get("trial_id") != self.trial_id or self.trial_id is None:
            return
        if kind == "started":
            self._start_wait = None
            if self._point_duration:
                self._deadline = time.monotonic() + self._point_duration
            self.events.put(("started", packet))
        elif kind == "sample":
            seq = int(packet["seq"])
            if seq != self._last_seq + 1:
                self._reason = "采样序号缺失：{} → {}".format(self._last_seq, seq)
                self.events.put(("error", self._reason))
            self._last_seq = seq
            self.store.append_sample(packet)
            current_t = int(packet["t_start_ns"])
            if self._first_t is None:
                self._first_t = current_t
            with self.lock:
                self.recent.append(packet)
                while self.recent and current_t - self.recent[0]["t_start_ns"] > 30000000000:
                    self.recent.popleft()
                self.sample_count += 1
                elapsed = (current_t - self._first_t) / 1e9
                self.rate = (self.sample_count - 1) / elapsed if elapsed > 0 else 0.0
                self.latest = packet
        elif kind == "event":
            self.store.append_event(packet)
            self.events.put(("event", packet))
        elif kind == "stopped":
            complete = packet.get("complete", True) and int(packet.get("last_seq", -1)) == self._last_seq
            if int(packet.get("last_seq", -1)) != self._last_seq:
                self._reason = "停止确认的采样数量与收到的数据不符"
            self._finish(complete, packet.get("reason", "") or ("" if complete else "服务端报告试次不完整"))

    def _run(self):
        buffer = b""
        while not self._quit:
            try:
                for _ in range(20):
                    try:
                        action, data = self.commands.get_nowait()
                    except queue.Empty:
                        break
                    if action in ("connect", "disconnect"):
                        buffer = b""
                    self._command(action, data)
                if self._sock:
                    readable, _, _ = select.select([self._sock], [], [], 0.02)
                    if readable:
                        chunk = self._sock.recv(65536)
                        if not chunk:
                            raise ConnectionError("采集服务已断开")
                        self._last_receive = time.monotonic()
                        buffer += chunk
                        if len(buffer) > 2000000:
                            raise ValueError("服务端帧过长")
                        while b"\n" in buffer:
                            line, buffer = buffer.split(b"\n", 1)
                            if line:
                                self._packet(json.loads(line.decode("utf-8")))
                    if self.trial_id and time.monotonic() - self._last_receive > 5:
                        raise TimeoutError("超过 5 秒未收到采集数据或停止确认")
                    if self._handshake_at and time.monotonic() - self._handshake_at > 5:
                        raise TimeoutError("超过 5 秒未收到协议握手")
                    if self._start_wait and time.monotonic() - self._start_wait > 5:
                        raise TimeoutError("超过 5 秒未收到开始/停止确认")
                    if self._deadline and time.monotonic() >= self._deadline:
                        self._command("stop", {})
                else:
                    time.sleep(0.02)
            except Exception as error:
                self.events.put(("error", str(error)))
                self._disconnect(str(error))
                buffer = b""


class SensorWindow:
    """Tk 主窗口；公开 vars/connect/start_capture/stop_capture 供模拟验收。"""

    def __init__(self, root, args):
        self.root, self.args = root, args
        self.worker = SensorWorker()
        self.capture = False
        self.dataset = None
        self.summaries = []
        self.calibration = None
        self.baseline = None
        self.history_path = None
        self.simulator = None
        self.events_by_trial = {}
        self._last_plot = 0
        self._closing = False
        self.plot_mode = "live"
        self.paused = False
        self._settings = []
        defaults = dict(host=args.host, port=str(args.port), experiment="P1", sensor_id="sensor_1",
            model="待核实", rate="50", duration="3", distance="20", unit="cm", phase="接近",
            repetition="1", target="target_1", surface="白色", roughness="普通", angle="0",
            light="室内正常照明", knob="保持不变", gray="0.5", light_factor="1",
            speed="5", direction="接近", active="0", stable="3", main_channel="IO0",
            output=str(ROOT / "measurements"), filter="原始", window="5", group="表面",
            calibration_method="分段插值", validation="否", visible="全部", notes="")
        self.vars = {key: tk.StringVar(root, value=value) for key, value in defaults.items()}
        self.io_vars = [tk.BooleanVar(root, value=(i == 0)) for i in range(8)]
        self.adc_vars = [tk.BooleanVar(root, value=False) for _ in range(9)]
        self.status = tk.StringVar(root, value="尚未连接")
        self.readout = tk.StringVar(root, value="主通道：—   记录 0 帧")
        self.path_text = tk.StringVar(root, value="尚未创建实验记录")
        self.root.title("FightCar 传感器实验上位机")
        self.root.geometry("1380x900")
        self.root.minsize(1080, 720)
        self._build()
        self.vars["experiment"].trace_add("write", self._template_changed)
        self.root.protocol("WM_DELETE_WINDOW", self.close)
        self._tick_job = self.root.after(100, self.tick)

    def _entry(self, parent, row, label, key, choices=None, width=19):
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w", padx=5, pady=3)
        if choices:
            widget = ttk.Combobox(parent, textvariable=self.vars[key], values=choices, state="readonly", width=width)
        else:
            widget = ttk.Entry(parent, textvariable=self.vars[key], width=width)
        widget.grid(row=row, column=1, sticky="ew", padx=5, pady=3)
        self._settings.append((widget, "readonly" if choices else "normal"))
        return widget

    def _build(self):
        from matplotlib import rcParams
        from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg, NavigationToolbar2Tk
        from matplotlib.figure import Figure
        rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei", "DejaVu Sans"]
        rcParams["axes.unicode_minus"] = False
        top = ttk.Frame(self.root, padding=7)
        top.pack(fill="x")
        for key, label, width in (("host", "服务地址", 16), ("port", "端口", 7)):
            ttk.Label(top, text=label).pack(side="left", padx=3)
            ttk.Entry(top, textvariable=self.vars[key], width=width).pack(side="left", padx=3)
        ttk.Button(top, text="连接", command=self.connect).pack(side="left", padx=3)
        ttk.Button(top, text="断开", command=lambda: self.worker.submit("disconnect")).pack(side="left", padx=3)
        ttk.Button(top, text="SSH / 启动说明", command=self.connection_help).pack(side="left", padx=3)
        ttk.Label(top, textvariable=self.status).pack(side="left", padx=12)
        body = ttk.Panedwindow(self.root, orient="horizontal")
        body.pack(fill="both", expand=True, padx=7)
        left = ttk.Frame(body, width=350)
        right = ttk.Frame(body)
        body.add(left, weight=0)
        body.add(right, weight=1)
        canvas = tk.Canvas(left, width=330, highlightthickness=0)
        scroll = ttk.Scrollbar(left, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=scroll.set)
        scroll.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)
        form = ttk.Frame(canvas)
        canvas.create_window((0, 0), window=form, anchor="nw")
        form.bind("<Configure>", lambda _event: canvas.configure(scrollregion=canvas.bbox("all")))
        form.columnconfigure(1, weight=1)
        rows = [
            ("实验模板", "experiment", list(EXPERIMENTS)), ("传感器编号", "sensor_id", None),
            ("传感器型号", "model", None), ("请求读取频率 Hz", "rate", None),
            ("静态点采时长 s", "duration", None), ("测点 / 起始距离", "distance", None),
            ("距离单位", "unit", ["cm", "mm"]), ("静态方向", "phase", ["接近", "释放"]),
            ("重复次数编号", "repetition", None), ("目标编号", "target", None),
            ("表面 / 颜色", "surface", ["白色", "黑色", "本色", "深灰", "中灰", "浅灰"]),
            ("粗糙度 / 材质", "roughness", None), ("角度 °（正对为0）", "angle", None),
            ("环境光描述", "light", None), ("光电旋钮设置", "knob", None),
            ("样本排序值0黑～1白", "gray", None), ("模拟光强系数", "light_factor", None),
            ("运动速度 cm/s", "speed", None), ("运动方向", "direction", ["接近", "远离"]),
            ("光电有效电平", "active", ["0", "1"]), ("稳定判定帧数", "stable", None),
            ("独立验证点", "validation", ["否", "是"]), ("备注", "notes", None)]
        for row, (label, key, choices) in enumerate(rows):
            self._entry(form, row, label, key, choices)
        self.template_label = ttk.Label(form, text=EXPERIMENTS["P1"], wraplength=295)
        self.template_label.grid(row=len(rows), column=0, columnspan=2, pady=6)
        channels = ttk.LabelFrame(form, text="同时采集的通道（按实际接线）")
        channels.grid(row=len(rows) + 1, column=0, columnspan=2, sticky="ew", padx=4)
        for family, values, offset in (("IO", self.io_vars, 0), ("ADC", self.adc_vars, 2)):
            for i, value in enumerate(values):
                button = ttk.Checkbutton(channels, text=family + str(i), variable=value, command=self._refresh_main_channels)
                button.grid(row=offset + i // 5, column=i % 5, sticky="w")
                self._settings.append((button, "normal"))
        self._entry(form, len(rows) + 2, "统计主通道", "main_channel", ["IO0"])
        self.main_combo = self._settings[-1][0]
        note = ttk.Notebook(right)
        self.notebook = note
        note.pack(fill="both", expand=True)
        plot_page, records_page, calibration_page = ttk.Frame(note), ttk.Frame(note), ttk.Frame(note)
        note.add(plot_page, text="实时曲线 / 对比")
        note.add(records_page, text="实验记录 / 统计")
        note.add(calibration_page, text="距离标定 / 验证")
        controls = ttk.Frame(plot_page, padding=4)
        controls.pack(fill="x")
        ttk.Label(controls, text="滤波").pack(side="left")
        ttk.Combobox(controls, textvariable=self.vars["filter"], values=["原始", "滑动平均", "中值"], width=10, state="readonly").pack(side="left", padx=3)
        ttk.Label(controls, text="窗口").pack(side="left")
        ttk.Spinbox(controls, from_=1, to=1001, textvariable=self.vars["window"], width=5).pack(side="left", padx=3)
        ttk.Label(controls, text="显示").pack(side="left")
        ttk.Combobox(controls, textvariable=self.vars["visible"], values=["全部", "仅主通道", "仅IO", "仅ADC"], width=10, state="readonly").pack(side="left", padx=3)
        ttk.Button(controls, text="历史 / 实时曲线", command=self.plot_history).pack(side="left", padx=3)
        ttk.Button(controls, text="暂停 / 继续绘图", command=self.pause_plot).pack(side="left", padx=3)
        ttk.Button(controls, text="PNG", command=self.export_png).pack(side="left", padx=3)
        self.figure = Figure(figsize=(8, 6), dpi=100)
        self.ax = self.figure.add_subplot(211)
        self.io_ax = self.ax.twinx()
        self.distance_ax = self.figure.add_subplot(212)
        self.figure.subplots_adjust(hspace=0.5, left=0.1, right=0.90, bottom=0.10)
        self.canvas = FigureCanvasTkAgg(self.figure, master=plot_page)
        self.canvas.get_tk_widget().pack(fill="both", expand=True)
        self.toolbar = NavigationToolbar2Tk(self.canvas, plot_page, pack_toolbar=False)
        self.toolbar.pack(fill="x")
        self.cursor_text = ttk.Label(plot_page, text="移动光标查看坐标；工具栏支持缩放和平移")
        self.cursor_text.pack(anchor="w", padx=6)
        self.canvas.mpl_connect("motion_notify_event", self._cursor)
        self.plot_mode = "live"
        record_tools = ttk.Frame(records_page, padding=5)
        record_tools.pack(fill="x")
        ttk.Button(record_tools, text="打开历史", command=self.open_history).pack(side="left", padx=3)
        ttk.Button(record_tools, text="重新分析", command=self.analyze).pack(side="left", padx=3)
        ttk.Button(record_tools, text="统计 CSV", command=self.export_csv).pack(side="left", padx=3)
        ttk.Button(record_tools, text="原始 CSV", command=lambda: self.export_csv(raw=True)).pack(side="left", padx=3)
        ttk.Label(record_tools, text="分组").pack(side="left", padx=3)
        ttk.Combobox(record_tools, textvariable=self.vars["group"], values=["表面", "角度", "光照", "速度", "灰度样本", "传感器"], width=10, state="readonly").pack(side="left")
        ttk.Button(record_tools, text="分组对比图", command=self.plot_groups).pack(side="left", padx=3)
        self.table = ttk.Treeview(records_page, columns=("trial", "exp", "channel", "distance", "surface", "angle", "count", "mean", "std", "status"), show="headings", selectmode="extended")
        for key, label in zip(self.table["columns"], ["试次", "实验", "主通道", "距离cm", "表面", "角度°", "样本数", "均值", "标准差", "状态"]):
            self.table.heading(key, text=label)
            self.table.column(key, width=80, minwidth=50)
        self.table.pack(fill="both", expand=True, padx=4)
        self.details = tk.Text(records_page, height=10, wrap="word", state="disabled")
        self.details.pack(fill="x", padx=4, pady=4)
        cal_tools = ttk.Frame(calibration_page, padding=7)
        cal_tools.pack(fill="x")
        ttk.Combobox(cal_tools, textvariable=self.vars["calibration_method"], values=["分段插值", "线性拟合"], width=12, state="readonly").pack(side="left", padx=3)
        for label, callback in [("用静态点建立标定", self.make_calibration), ("验证独立点", self.validate), ("载入标定", self.load_calibration), ("导出标定", self.export_calibration)]:
            ttk.Button(cal_tools, text=label, command=callback).pack(side="left", padx=3)
        ttk.Label(calibration_page, text="默认使用同一传感器静态点；验证点不参与建模。超出标定范围不外推。\n可在记录表选择若干试次，再点击建立标定；未选择时使用全部合格点。", padding=8).pack(anchor="w")
        self.cal_text = tk.Text(calibration_page, wrap="word")
        self.cal_text.pack(fill="both", expand=True, padx=6, pady=4)
        bottom = ttk.Frame(self.root, padding=7)
        bottom.pack(fill="x")
        for text, callback in [("开始连续采集", self.start_capture), ("静态点采样", lambda: self.start_capture(point=True)), ("停止", self.stop_capture), ("下一次重复", self.next_repeat), ("运动开始", lambda: self.mark_motion("motion_start")), ("运动结束", lambda: self.mark_motion("motion_end")), ("新建实验", self.new_session)]:
            ttk.Button(bottom, text=text, command=callback).pack(side="left", padx=3)
        ttk.Label(self.root, textvariable=self.readout, padding=(10, 2)).pack(fill="x")
        output = ttk.Frame(self.root, padding=(8, 2))
        output.pack(fill="x")
        ttk.Label(output, text="保存到").pack(side="left")
        ttk.Entry(output, textvariable=self.vars["output"]).pack(side="left", fill="x", expand=True, padx=4)
        ttk.Button(output, text="选择目录", command=self.choose_output).pack(side="left")
        ttk.Label(self.root, textvariable=self.path_text, padding=(10, 3)).pack(fill="x")

    def _refresh_main_channels(self):
        channels = ["IO" + str(i) for i, v in enumerate(self.io_vars) if v.get()]
        channels += ["ADC" + str(i) for i, v in enumerate(self.adc_vars) if v.get()]
        self.main_combo.configure(values=channels)
        if channels and self.vars["main_channel"].get() not in channels:
            self.vars["main_channel"].set(channels[0])

    def _template_changed(self, *_args):
        code = self.vars["experiment"].get()
        self.template_label.configure(text=EXPERIMENTS.get(code, ""))
        if not self.capture:
            for value in self.io_vars + self.adc_vars:
                value.set(False)
            (self.io_vars if code.startswith("P") else self.adc_vars)[0].set(True)
            self._refresh_main_channels()
            self.vars["validation"].set("是" if code == "D5" else "否")

    def _number(self, key, minimum=None):
        value = float(self.vars[key].get())
        if not math.isfinite(value) or (minimum is not None and value < minimum):
            raise ValueError("{} 数值不正确".format(key))
        return value

    def _metadata(self, point=False):
        code = self.vars["experiment"].get()
        if code not in EXPERIMENTS:
            raise ValueError("请选择实验模板")
        rate = self._number("rate", 1)
        if rate > 1000:
            raise ValueError("请求读取频率应在 1～1000 Hz")
        distance = self._number("distance", 0) / (10 if self.vars["unit"].get() == "mm" else 1)
        if not self.vars["sensor_id"].get().strip():
            raise ValueError("请填写传感器编号")
        stable = self._number("stable", 1)
        if int(stable) != stable:
            raise ValueError("稳定判定帧数必须是整数")
        gray = self._number("gray", 0)
        if gray > 1:
            raise ValueError("灰度样本值应在 0～1")
        metadata = {key: value.get() for key, value in self.vars.items()}
        metadata.update(experiment=code, distance_cm=distance, rate_hz=rate,
            sensor_id=self.vars["sensor_id"].get().strip(), point=bool(point),
            validation=self.vars["validation"].get() == "是", phase="approach" if self.vars["phase"].get() == "接近" else "release",
            angle_deg=self._number("angle"), gray_level=gray,
            speed_cm_s=self._number("speed", 0), active_level=int(self.vars["active"].get()), stable_count=int(stable))
        io_channels = [i for i, var in enumerate(self.io_vars) if var.get()]
        adc_channels = [i for i, var in enumerate(self.adc_vars) if var.get()]
        if not io_channels and not adc_channels:
            raise ValueError("请至少选择一个采集通道")
        if metadata["main_channel"] not in ["IO" + str(i) for i in io_channels] + ["ADC" + str(i) for i in adc_channels]:
            raise ValueError("统计主通道必须包含在采集通道中")
        if code.startswith("P") and not metadata["main_channel"].startswith("IO"):
            raise ValueError("光电实验的统计主通道应选择IO")
        if code.startswith(("D", "G")) and not metadata["main_channel"].startswith("ADC"):
            raise ValueError("距离和灰度实验的统计主通道应选择ADC")
        metadata["io_channels"], metadata["adc_channels"] = io_channels, adc_channels
        metadata["position_source"] = "ruler_static" if point else "none"
        simulation = dict(distance_cm=distance, sensor_kind="photoelectric" if code.startswith("P") else "grayscale" if code.startswith("G") else "distance",
            surface=metadata["surface"], phase=metadata["phase"], angle_deg=metadata["angle_deg"], gray_level=gray, light=self._number("light_factor", 0))
        return metadata, dict(rate_hz=rate, io_channels=io_channels, adc_channels=adc_channels, simulation=simulation)

    def connect(self):
        try:
            self.worker.submit("connect", host=self.vars["host"].get().strip(), port=int(self.vars["port"].get()))
            self.status.set("正在连接…")
        except ValueError as error:
            self._error(str(error))

    def start_capture(self, point=False):
        try:
            if self.capture:
                raise ValueError("当前采集尚未结束")
            if not self.worker.connected:
                raise ValueError("请先连接采集服务")
            if self.worker.path and Path(self.vars["output"].get()).resolve() != Path(self.worker.path).parent.resolve():
                raise ValueError("保存目录已改变，请点击“新建实验”后开始；已有记录仍保存在原目录")
            metadata, packet = self._metadata(point)
            duration = self._number("duration", 0.01) if point else None
            self.capture = True
            self.plot_mode = "live"
            self._lock_settings(True)
            self.worker.submit("start", metadata=metadata, packet=packet, root=self.vars["output"].get(), duration=duration)
        except (ValueError, OSError) as error:
            self._error(str(error))

    def stop_capture(self):
        self.worker.submit("stop")

    def next_repeat(self):
        if self.capture:
            self._error("请先停止采集并等待保存确认")
            return
        try:
            self.vars["repetition"].set(str(int(self.vars["repetition"].get()) + 1))
        except ValueError:
            self.vars["repetition"].set("1")

    def mark_motion(self, name):
        try:
            if not self.capture:
                raise ValueError("请先开始连续采集")
            metadata, _ = self._metadata()
            self.worker.submit("mark", name=name, data=dict(start_distance_cm=metadata["distance_cm"],
                speed_cm_s=metadata["speed_cm_s"], direction="approach" if self.vars["direction"].get() == "接近" else "release"))
        except ValueError as error:
            self._error(str(error))

    def _lock_settings(self, locked):
        for widget, state in self._settings:
            widget.configure(state="disabled" if locked else state)

    def _error(self, text):
        self.status.set("异常：" + text)
        if hasattr(self, "details"):
            self._details("异常：" + text)

    def _details(self, text):
        self.details.configure(state="normal")
        self.details.insert("end", str(text) + "\n")
        self.details.see("end")
        self.details.configure(state="disabled")

    def choose_output(self):
        if self.capture:
            self._error("请先停止，再更换保存位置")
            return
        path = filedialog.askdirectory(initialdir=self.vars["output"].get(), parent=self.root)
        if path:
            self.vars["output"].set(path)

    def new_session(self):
        if self.capture:
            self._error("请先停止采集")
            return
        self.worker.submit("new_session")
        self.dataset, self.summaries, self.history_path = None, [], None
        self.events_by_trial.clear()
        self.table.delete(*self.table.get_children())

    def connection_help(self):
        try:
            config = json.loads((ROOT / "config" / "board.json").read_text(encoding="utf-8-sig"))
        except (OSError, ValueError):
            config = dict(host="开发板IP", user="用户名", port=22, remote_dir="~/hsy/ceshi")
        port = self.vars["port"].get()
        messagebox.showinfo("手动建立采集连接", "在 Windows 终端运行：\nssh -p {ssh_port} -L {p}:127.0.0.1:{p} {u}@{h}\n\n在板端手动运行（保持 SSH 打开）：\ncd {d}\npython3 sensor_server.py --port {p}\n\n然后连接本窗口 127.0.0.1:{p}。采集服务仅访问 ADC/IO。\n模拟体验：py -3 src/desktop/sensor_client.py --simulate".format(ssh_port=config.get("port", 22), p=port, u=config.get("user", "用户名"), h=config.get("host", "开发板IP"), d=config.get("remote_dir", "~/hsy/ceshi")), parent=self.root)

    def _cursor(self, event):
        if event.inaxes and event.xdata is not None:
            self.cursor_text.configure(text="横坐标 {:.4f}   纵坐标 {:.4f}".format(event.xdata, event.ydata))

    def tick(self):
        if self._closing:
            return
        try:
            for _ in range(100):
                try:
                    kind, data = self.worker.events.get_nowait()
                except queue.Empty:
                    break
                if kind == "connected":
                    self.status.set("已连接 · " + ("模拟数据" if data.get("simulated") else "真实 ADC/IO"))
                elif kind == "disconnected":
                    self.status.set(data)
                    if self.capture and self.worker.trial_id is None:
                        self.capture = False
                        self._lock_settings(False)
                elif kind == "error":
                    self._error(str(data))
                elif kind == "recording":
                    self.history_path = Path(data["path"])
                    self.events_by_trial[data["trial_id"]] = []
                    self.path_text.set("实验记录：" + data["path"])
                elif kind == "finished":
                    self.capture = False
                    self._lock_settings(False)
                    self.history_path = Path(data["path"])
                    self.status.set("已保存" if data["complete"] else "记录不完整：" + data["reason"])
                    self.analyze()
                elif kind == "event":
                    self.events_by_trial.setdefault(data["trial_id"], []).append(data)
                    self._details("运动标记：" + str(data.get("name", "")) + "（位置为匀速模型估计）")
                elif kind == "new_session":
                    self.path_text.set("下一次采集将创建新实验目录")
            samples, count, rate, latest = self.worker.view()
            value = "—"
            if latest:
                channel = self.vars["main_channel"].get()
                family = "io" if channel.startswith("IO") else "adc"
                value = latest.get(family, {}).get(channel[2:] if family == "io" else channel[3:], "—")
            self.readout.set("主通道 {} = {}    已记录 {} 帧    实测读取 {:.1f} Hz（非硬件刷新率）".format(self.vars["main_channel"].get(), value, count, rate))
            if self.plot_mode == "live" and samples and not self.paused and not self.toolbar.mode:
                self._plot_samples(samples, self.events_by_trial.get(samples[-1]["trial_id"], []))
        except Exception as error:
            self._error(str(error))
        self._tick_job = self.root.after(100, self.tick)

    def _plot_samples(self, samples, events):
        self.ax.clear()
        self.io_ax.clear()
        self.distance_ax.clear()
        origin = samples[0]["t_start_ns"]
        stride = max(1, len(samples) // 1200)
        channels = [(family, channel) for family in ("io", "adc") for channel in samples[-1].get(family, {})]
        self.io_ax.set_visible(any(family == "io" for family, _ in channels))
        view = self.vars["visible"].get()
        method = {"原始": "raw", "滑动平均": "mean", "中值": "median"}[self.vars["filter"].get()]
        try:
            window = max(1, int(self.vars["window"].get()))
        except ValueError:
            window = 5
        for family, channel in channels:
            name = ("IO" if family == "io" else "ADC") + str(channel)
            if view == "仅主通道" and name != self.vars["main_channel"].get():
                continue
            if view == "仅IO" and family != "io" or view == "仅ADC" and family != "adc":
                continue
            values, xs, previous = [], [], None
            for sample in samples:
                if previous is not None and (sample["trial_id"] != previous["trial_id"] or sample["seq"] != previous["seq"] + 1):
                    xs.append((sample["t_start_ns"] - origin) / 1e9)
                    values.append(None)
                xs.append((sample["t_start_ns"] - origin) / 1e9)
                values.append(sample.get(family, {}).get(channel))
                previous = sample
            filtered = values if family == "io" else filter_values(values, method, window)
            axis = self.io_ax if family == "io" else self.ax
            axis.plot(xs[::stride], values[::stride], label=name + " 原始", alpha=0.4 if method != "raw" and family == "adc" else 1, drawstyle="steps-post" if family == "io" else "default")
            if method != "raw" and family == "adc":
                self.ax.plot(xs[::stride], filtered[::stride], label=name + " " + self.vars["filter"].get())
        xs = [(sample["t_start_ns"] - origin) / 1e9 for sample in samples[::stride]]
        positions = [position_at(sample["t_start_ns"], [event for event in events if event.get("trial_id") == sample["trial_id"]]).get("distance_cm") for sample in samples[::stride]]
        if any(value is not None for value in positions):
            self.distance_ax.plot(xs, positions, label="轨道距离（匀速模型估计）")
        main = self.vars["main_channel"].get()
        if self.calibration and main.startswith("ADC"):
            measured = [estimate_distance(self.calibration, sample.get("adc", {}).get(main[3:])) if self._calibration_matches(self._trial_metadata(sample["trial_id"])) and sample.get("adc", {}).get(main[3:]) is not None else None for sample in samples[::stride]]
            self.distance_ax.plot(xs, measured, label="ADC 标定换算距离")
            if method != "raw":
                values, indices, previous = [], [], None
                for sample in samples:
                    if previous is not None and (sample["trial_id"] != previous["trial_id"] or sample["seq"] != previous["seq"] + 1):
                        values.append(None)
                    indices.append(len(values))
                    values.append(sample.get("adc", {}).get(main[3:]))
                    previous = sample
                filtered = filter_values(values, method, window)
                smoothed = [filtered[index] for index in indices]
                filtered_distance = [estimate_distance(self.calibration, value) if self._calibration_matches(self._trial_metadata(sample["trial_id"])) and value is not None else None
                    for sample, value in zip(samples[::stride], smoothed[::stride])]
                self.distance_ax.plot(xs, filtered_distance, label="滤波后标定距离（含窗口滞后）")
        self.ax.set(xlabel="时间 s", ylabel="ADC 原始值", title="最近 30 秒（全部原始数据持续保存）" if self.plot_mode == "live" else "历史曲线")
        self.io_ax.set(ylabel="IO 状态", ylim=(-0.1, 1.3), yticks=[0, 1])
        self.io_ax.yaxis.set_label_position("right")
        self.io_ax.yaxis.set_ticks_position("right")
        self.distance_ax.set(xlabel="时间 s", ylabel="距离 cm")
        for axis in (self.ax, self.io_ax, self.distance_ax):
            axis.grid(True, alpha=0.25)
            if axis.lines:
                line_count = len(axis.get_legend_handles_labels()[0])
                columns = 2 if axis is self.io_ax and line_count > 4 else max(1, math.ceil(line_count / 6))
                axis.legend(loc="upper left" if axis is self.io_ax else "upper right", fontsize=7, ncol=columns)
        self.canvas.draw_idle()

    def analyze(self):
        if self.capture or not self.history_path:
            return
        try:
            self.dataset = load_session(self.history_path)
            if self.dataset.get("calibration") and self.calibration is None:
                self.calibration = self.dataset["calibration"]
            for warning in self.dataset.get("warnings", []):
                self._details("数据完整性：" + warning)
            rows, photo_groups = [], {}
            by_trial = {}
            for sample in self.dataset["samples"]:
                by_trial.setdefault(sample["trial_id"], []).append(sample)
            trials = self.dataset["metadata"].get("trials", [])
            for trial in trials:
                metadata = trial["metadata"]
                trial_id = trial["trial_id"]
                samples = by_trial.get(trial_id, [])
                channel = metadata.get("main_channel", "IO0")
                family = "io" if channel.startswith("IO") else "adc"
                number = channel[2:] if family == "io" else channel[3:]
                values, previous_seq = [], 0
                for sample in samples:
                    if sample["seq"] != previous_seq + 1:
                        values.append(None)
                    values.append(sample.get(family, {}).get(number))
                    previous_seq = sample["seq"]
                result = summarize(values)
                row = dict(metadata)
                row.update(result, trial_id=trial_id, channel=channel, status=trial["status"],
                    reason=trial.get("reason", ""), kind="point" if metadata.get("point") else "continuous",
                    adc_mean=result["mean"] if family == "adc" else None)
                raw_std = result["std"]
                for filter_method in ("mean", "median"):
                    filtered_values = filter_values(values, filter_method, 5)
                    row[filter_method + "_5_std"] = summarize(filtered_values)["std"]
                row["raw_std"] = raw_std
                rows.append(row)
                if metadata.get("experiment") in ("P1", "P2", "P3") and metadata.get("point") and trial["status"] == "complete" and family == "io":
                    key = self._condition_key(metadata) + (str(metadata.get("repetition", "1")),)
                    photo_groups.setdefault(key, []).append((row, values))
            baseline_groups = {}
            for key, points in photo_groups.items():
                metadata = points[0][0]
                result = photoelectric_summary([dict(phase=row["phase"], distance_cm=row["distance_cm"], io_values=values) for row, values in points],
                    active_level=int(metadata.get("active_level", 0)), stable_count=int(metadata.get("stable_count", 3)))
                baseline_groups.setdefault(key[:-1], []).append(result)
                group_row = dict(metadata)
                group_row.update(result, trial_id=" + ".join(row["trial_id"] for row, _ in points),
                    kind="photoelectric_static", count=sum(len(values) for _, values in points))
                rows.append(group_row)
                self._details("光电静态（{}，第{}次）：触发 {} cm，释放 {} cm，回差 {} cm；边界区间 {} / {}".format(metadata.get("surface"), metadata.get("repetition"),
                    result["trigger_distance_cm"], result["release_distance_cm"], result["hysteresis_cm"], result["approach_interval_cm"], result["release_interval_cm"]))
            baselines = {}
            for key, results in baseline_groups.items():
                baseline = dict(results[-1])
                for field in ("trigger_distance_cm", "release_distance_cm", "hysteresis_cm"):
                    baseline[field] = summarize([result[field] for result in results])["mean"]
                intervals = [result.get("reliable_interval_cm") for result in results]
                if intervals and all(intervals):
                    lo, hi = max(interval[0] for interval in intervals), min(interval[1] for interval in intervals)
                    baseline["reliable_interval_cm"] = [lo, hi] if lo < hi else None
                else:
                    baseline["reliable_interval_cm"] = None
                baselines[key] = baseline
            dynamic_groups = {}
            for row in rows:
                if row["kind"] != "continuous" or not row.get("experiment", "").startswith("P") or row["status"] != "complete":
                    continue
                if not row["channel"].startswith("IO"):
                    continue
                events = [event for event in self.dataset["events"] if event["trial_id"] == row["trial_id"]]
                baseline = baselines.get(self._condition_key(row))
                if baseline is None and self.baseline and self._condition_key(row) == self.baseline[0]:
                    baseline = self.baseline[1]
                result = dynamic_photoelectric(by_trial.get(row["trial_id"], []), events, baseline=baseline,
                    active_level=int(row.get("active_level", 0)), stable_count=int(row.get("stable_count", 3)), io_channel=int(row["channel"][2:]))
                row.update(result)
                dynamic_groups.setdefault(self._condition_key(row) + (str(row.get("speed_cm_s", "")),), []).append(row)
                self._details("{} 动态：触发 {} cm（估计位置），原始跳变 {} 次；{}".format(row["trial_id"], result["trigger_distance_cm"], result["raw_edge_count"], result["reason"]))
            for group in dynamic_groups.values():
                counts = {state: sum(row.get("miss_status") == state for row in group) for state in ("detected", "missed", "undetermined")}
                determined = counts["detected"] + counts["missed"]
                trigger_stats = summarize([row.get("trigger_distance_cm") for row in group])
                row = dict(group[0])
                row.update(kind="photoelectric_dynamic_group", trial_id="动态重复汇总", counts=counts,
                    determined_count=determined, miss_rate=counts["missed"] / determined if determined else None,
                    trigger_mean_cm=trigger_stats["mean"], trigger_std_cm=trigger_stats["std"], repetitions=len(group))
                rows.append(row)
                self._details("动态重复（{}，{} cm/s）：检测{}，漏检{}，未判定{}；漏检率{}；触发距离均值{} cm，标准差{} cm。".format(
                    row.get("surface"), row.get("speed_cm_s"), counts["detected"], counts["missed"], counts["undetermined"],
                    "未判定" if not determined else "{:.1%}".format(row["miss_rate"]), trigger_stats["mean"], trigger_stats["std"]))
            if baselines:
                self.baseline = next(reversed(list(baselines.items())))
            if self.calibration:
                for row in rows:
                    if row.get("kind") == "point" and row.get("validation") and row.get("status") == "complete" and row.get("adc_mean") is not None and self._calibration_matches(row):
                        result = validate_calibration(self.calibration, [dict(distance_cm=row["distance_cm"], adc_mean=row["adc_mean"])])
                        row.update({key: value for key, value in result["rows"][0].items() if key in ("estimated_distance_cm", "error_cm", "in_range")})
            self.summaries = rows
            self._show_table()
            if self.worker.path and Path(self.worker.path) == self.history_path:
                self.worker.submit("save_summary", rows=rows)
            self._details("已分析 {} 个试次，共 {} 帧。ADC 使用样本标准差；5点滤波波动列随统计CSV保存。".format(len(trials), len(self.dataset["samples"])))
            return rows
        except (OSError, ValueError, KeyError, TypeError) as error:
            self._error("分析失败：" + str(error))

    @staticmethod
    def _condition_key(metadata):
        return tuple(str(metadata.get(key, "")) for key in ("sensor_id", "model", "target", "main_channel", "surface", "roughness", "angle_deg", "light", "knob", "active_level", "stable_count"))

    def _trial_metadata(self, trial_id):
        if self.worker.store and self.capture:
            for trial in self.worker.store.metadata["trials"]:
                if trial["trial_id"] == trial_id:
                    return trial["metadata"]
        if self.dataset:
            for trial in self.dataset["metadata"].get("trials", []):
                if trial["trial_id"] == trial_id:
                    return trial["metadata"]
        return {}

    def _calibration_matches(self, metadata):
        if not self.calibration or not metadata.get("experiment", "").startswith("D"):
            return False
        conditions = self.calibration.get("conditions", {})
        return self.calibration.get("sensor_id") == metadata.get("sensor_id") and conditions.get("main_channel") == metadata.get("main_channel")

    def _show_table(self):
        self.table.delete(*self.table.get_children())
        for i, row in enumerate(self.summaries):
            def display(value):
                return "" if value is None else "{:.4f}".format(value) if isinstance(value, float) else str(value)
            self.table.insert("", "end", iid=str(i), values=[display(row.get(key)) for key in ("trial_id", "experiment", "main_channel", "distance_cm", "surface", "angle_deg", "count", "mean", "std", "status")])

    def _selected_rows(self):
        selection = self.table.selection()
        return [self.summaries[int(index)] for index in selection] if selection else list(self.summaries)

    def open_history(self, path=None):
        if self.capture:
            self._error("请先停止采集，再打开历史")
            return
        if path is None:
            path = filedialog.askdirectory(parent=self.root, title="选择含 metadata.json 的实验目录", initialdir=self.vars["output"].get())
        if path:
            self.history_path = Path(path)
            self.calibration = None
            self.path_text.set("历史记录：" + str(path))
            self.analyze()
            if self.dataset:
                self.events_by_trial = {}
                for event in self.dataset["events"]:
                    self.events_by_trial.setdefault(event["trial_id"], []).append(event)
                self.plot_history()

    def plot_history(self):
        if self.capture:
            self.plot_mode, self.paused = "live", False
            self.notebook.select(0)
            return
        if not self.dataset or not self.dataset["samples"]:
            return
        self.plot_mode = "history"
        rows = self._selected_rows()
        selected = {row["trial_id"] for row in rows if row.get("kind") != "photoelectric_static"}
        samples = [sample for sample in self.dataset["samples"] if sample["trial_id"] in selected]
        if samples:
            self._plot_samples(samples, self.dataset["events"])
            self.notebook.select(0)

    def pause_plot(self):
        self.paused = not self.paused
        self._details("实时绘图已暂停，采集与保存继续" if self.paused else "实时绘图已继续")

    def plot_groups(self):
        try:
            rows = [row for row in self._selected_rows() if row.get("kind") == "point" and row.get("status") == "complete"]
            if not rows:
                raise ValueError("请先采集静态点，或在记录表选择完整的静态点试次")
            self.plot_mode = "group"
            self.ax.clear()
            self.io_ax.clear()
            self.io_ax.set_visible(False)
            self.distance_ax.clear()
            key = {"表面": "surface", "角度": "angle_deg", "光照": "light", "速度": "speed_cm_s", "灰度样本": "gray_level", "传感器": "sensor_id"}[self.vars["group"].get()]
            groups = {}
            for row in rows:
                groups.setdefault(str(row.get(key, "")) + " / " + str(row.get("main_channel", "")), []).append(row)
            code = rows[0]["experiment"]
            xkey = "gray_level" if code == "G2" else "light" if code == "G3" else "distance_cm"
            categories = list(dict.fromkeys(str(row.get(xkey, "")) for row in rows)) if code == "G3" else None
            for label, points in groups.items():
                points = sorted(points, key=lambda row: str(row.get(xkey)) if categories else float(row.get(xkey, 0)))
                xs = [categories.index(str(row.get(xkey))) if categories else row.get(xkey) for row in points]
                self.ax.errorbar(xs, [row.get("mean") for row in points], yerr=[row.get("std") or 0 for row in points], fmt="o-", capsize=3, label=label)
            if categories:
                self.ax.set_xticks(range(len(categories)), categories)
            self.ax.set(xlabel="光照条件" if code == "G3" else "灰度样本（自定义0～1）" if code == "G2" else "距离 cm", ylabel="ADC / IO 均值 ± 样本标准差", title="静态条件对比（各点单独保留）")
            self.ax.legend(fontsize=8)
            self.ax.grid(True, alpha=0.25)
            self.canvas.draw_idle()
            self.notebook.select(0)
        except (ValueError, KeyError, TypeError) as error:
            self._error(str(error))

    def make_calibration(self):
        try:
            if self.capture:
                raise ValueError("请先停止采集")
            selected = bool(self.table.selection())
            rows = [row for row in self._selected_rows() if row.get("kind") == "point" and row.get("status") == "complete"
                and str(row.get("main_channel", "")).startswith("ADC") and row.get("experiment") in ("D1", "D3", "D4")
                and not row.get("validation") and row.get("adc_mean") is not None]
            if not selected:
                rows = [row for row in rows if row.get("experiment") == "D1" and row.get("sensor_id") == self.vars["sensor_id"].get()
                    and row.get("main_channel") == self.vars["main_channel"].get()]
            if not rows:
                raise ValueError("没有合格标定点：请使用D1静态点，或在记录表选择同一条件的D1/D3/D4静态点。D5与独立验证点不参与建模")
            conditions = {tuple(str(row.get(key, "")) for key in ("sensor_id", "model", "target", "main_channel", "surface", "roughness", "angle_deg", "light")) for row in rows}
            if len(conditions) > 1:
                raise ValueError("所选标定点包含不同传感器、通道或条件，请在记录表选择同一组条件")
            first = rows[0]
            model = build_calibration([dict(distance_cm=row["distance_cm"], adc_mean=row["adc_mean"]) for row in rows],
                method="piecewise" if self.vars["calibration_method"].get() == "分段插值" else "linear", sensor_id=first["sensor_id"],
                conditions={key: first.get(key) for key in ("main_channel", "surface", "roughness", "angle_deg", "light", "model", "target")})
            model["source_trials"] = [row["trial_id"] for row in rows]
            self.calibration = model
            if self.worker.path and self.history_path == Path(self.worker.path):
                self.worker.submit("save_calibration", model=model)
            self._show_calibration("标定已建立，仅在覆盖范围内使用。", model)
            self._plot_calibration()
            return model
        except (ValueError, KeyError, TypeError) as error:
            self._error(str(error))

    def _show_calibration(self, title, result):
        self.cal_text.delete("1.0", "end")
        self.cal_text.insert("end", title + "\n\n" + json.dumps(result, ensure_ascii=False, indent=2))

    def validate(self):
        try:
            if self.capture:
                raise ValueError("请先停止采集")
            if not self.calibration:
                raise ValueError("请先建立或载入标定")
            rows = [row for row in self._selected_rows() if row.get("kind") == "point" and row.get("status") == "complete"
                and row.get("validation") and self._calibration_matches(row) and row.get("adc_mean") is not None]
            if not rows:
                raise ValueError("没有匹配的独立验证点：选择D5或将独立验证点设为是，并使用标定对应的传感器/通道")
            calibration_distances = [point["distance_cm"] for point in self.calibration["points"]]
            if any(row["distance_cm"] in calibration_distances for row in rows):
                raise ValueError("验证点包含参与标定的距离，请另选新的距离点")
            result = validate_calibration(self.calibration, [dict(trial_id=row["trial_id"], distance_cm=row["distance_cm"], adc_mean=row["adc_mean"]) for row in rows])
            for row in result["rows"]:
                target = next(value for value in self.summaries if value.get("trial_id") == row["trial_id"] and value.get("kind") == "point")
                target.update(row)
            self.validation_result = result
            if self.worker.path and self.history_path == Path(self.worker.path):
                self.worker.submit("save_summary", rows=self.summaries)
            self._show_calibration("独立验证：误差 = 估计距离 − 尺量距离，单位cm；范围外的点不计入误差。", result)
            self._plot_calibration(result)
            return result
        except (ValueError, KeyError, TypeError) as error:
            self._error(str(error))

    def _plot_calibration(self, validation=None):
        self.plot_mode = "calibration"
        self.ax.clear()
        self.io_ax.clear()
        self.io_ax.set_visible(False)
        self.distance_ax.clear()
        points = self.calibration["points"]
        self.ax.scatter([point["adc_mean"] for point in points], [point["distance_cm"] for point in points], label="标定均值点")
        lo, hi = self.calibration["adc_range"]
        xs = [lo + (hi - lo) * index / 200 for index in range(201)]
        self.ax.plot(xs, [estimate_distance(self.calibration, value) for value in xs], label="ADC→距离换算")
        self.ax.set(xlabel="ADC 原始均值", ylabel="距离 cm", title="标定：{} / {}".format(self.calibration.get("sensor_id", ""), self.calibration.get("conditions", {}).get("main_channel", "")))
        if validation:
            rows = [row for row in validation["rows"] if row.get("error_cm") is not None]
            self.distance_ax.scatter([row["distance_cm"] for row in rows], [row["error_cm"] for row in rows], label="独立验证误差")
        self.distance_ax.axhline(0, color="gray", linestyle="--")
        self.distance_ax.set(xlabel="实际距离 cm", ylabel="估计 − 实际 cm")
        for axis in (self.ax, self.distance_ax):
            axis.grid(True, alpha=0.25)
            if axis.get_legend_handles_labels()[1]:
                axis.legend(fontsize=8)
        self.canvas.draw_idle()
        self.notebook.select(0)

    def load_calibration(self, path=None):
        if self.capture:
            self._error("请先停止采集，再更换标定")
            return
        if path is None:
            path = filedialog.askopenfilename(parent=self.root, filetypes=[("标定 JSON", "*.json")])
        if path:
            try:
                model = json.loads(Path(path).read_text(encoding="utf-8-sig"))
                estimate_distance(model, model["adc_range"][0])
                if not model.get("sensor_id") or not model.get("conditions", {}).get("main_channel"):
                    raise ValueError("标定缺少传感器编号或主通道信息")
                self.calibration = model
                self._show_calibration("标定已载入。仅应用到匹配的距离传感器和通道。", model)
            except (OSError, ValueError, KeyError, TypeError) as error:
                self._error("载入标定失败：" + str(error))

    def export_calibration(self, path=None):
        if not self.calibration:
            self._error("尚无标定结果")
            return
        if path is None:
            path = filedialog.asksaveasfilename(parent=self.root, defaultextension=".json", filetypes=[("JSON", "*.json")], initialdir=str(self.history_path or ROOT), initialfile="calibration.json")
        if path:
            try:
                Path(path).write_text(json.dumps(self.calibration, ensure_ascii=False, indent=2), encoding="utf-8")
            except OSError as error:
                self._error(str(error))

    def export_csv(self, path=None, raw=False):
        if self.capture:
            self._error("请先停止采集再导出；原始数据正在后台自动保存")
            return
        if not self.history_path:
            self._error("尚无实验记录")
            return
        if path is None:
            path = filedialog.asksaveasfilename(parent=self.root, defaultextension=".csv", filetypes=[("CSV", "*.csv")], initialdir=str(self.history_path), initialfile="raw_export.csv" if raw else "summary_export.csv")
        if not path:
            return
        try:
            if raw:
                source = self.history_path / "samples.csv"
                if Path(path).resolve() != source.resolve():
                    shutil.copyfile(source, path)
            else:
                fields = list(dict.fromkeys(key for row in self.summaries for key in row))
                with Path(path).open("w", encoding="utf-8-sig", newline="") as handle:
                    writer = csv.DictWriter(handle, fields)
                    writer.writeheader()
                    writer.writerows([{key: json.dumps(value, ensure_ascii=False) if isinstance(value, (dict, list)) else value for key, value in row.items()} for row in self.summaries])
        except OSError as error:
            self._error(str(error))

    def export_png(self, path=None):
        if path is None:
            path = filedialog.asksaveasfilename(parent=self.root, defaultextension=".png", filetypes=[("PNG", "*.png")], initialdir=str(self.history_path or ROOT))
        if path:
            self.figure.savefig(path, dpi=150)

    def close(self):
        if self._closing:
            return
        self._closing = True
        if self._tick_job:
            self.root.after_cancel(self._tick_job)
        idle_draw = getattr(self.canvas, "_idle_draw_id", None)
        if idle_draw:
            # 回调注册在绘图控件；由同一控件取消，避免销毁时重复删除 Tcl 命令。
            self.canvas.get_tk_widget().after_cancel(idle_draw)
            self.canvas._idle_draw_id = None
        self.worker.submit("close")
        self._close_deadline = time.monotonic() + 5
        self.worker._thread.join(timeout=0.1)
        self._poll_close()

    def _poll_close(self):
        if self.worker._thread.is_alive() and time.monotonic() < self._close_deadline:
            self.status.set("正在关闭采集并保存记录…")
            self.root.after(50, self._poll_close)
            return
        if self.simulator:
            self.simulator.terminate()
            try:
                self.simulator.wait(timeout=2)
            except subprocess.TimeoutExpired:
                self.simulator.kill()
        self.root.destroy()


def main():
    try:
        config = json.loads((ROOT / "config" / "board.json").read_text(encoding="utf-8-sig"))
    except (ValueError, OSError):
        config = {}
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=config.get("sensor_port", 8766))
    parser.add_argument("--simulate", action="store_true", help="启动本机模拟服务并自动连接")
    args = parser.parse_args()
    root = tk.Tk()
    app = SensorWindow(root, args)
    if args.simulate:
        with socket.socket() as probe:
            probe.bind(("127.0.0.1", 0))
            port = probe.getsockname()[1]
        app.vars["host"].set("127.0.0.1")
        app.vars["port"].set(str(port))
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        app.simulator = subprocess.Popen([sys.executable, "-X", "utf8", str(ROOT / "src" / "board" / "sensor_server.py"), "--simulate", "--host", "127.0.0.1", "--port", str(port)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=flags)
        root.after(800, app.connect)
    root.mainloop()


if __name__ == "__main__":
    try:
        main()
    except ImportError as error:
        print("缺少绘图依赖，请在项目根目录运行：py -3 -m pip install -r src/desktop/requirements.txt\n" + str(error))
        raise SystemExit(1)
