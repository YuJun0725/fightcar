#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Windows小车上位机：标准库Tkinter界面，通过SSH隧道连接开发板。"""

import argparse
import json
import math
import queue
import socket
import threading
import time
import tkinter as tk
from tkinter import ttk

DEFAULT = dict(action="", speed=200, spin_speed=150, track_width=0.30, radius=0.50)


class Connection:
    """网络放在后台线程，Tk控件只在主线程访问。仅保留最新状态。"""
    def __init__(self):
        self.events = queue.Queue()
        self.connected = threading.Event()
        self.wake = threading.Event()
        self.lock = threading.Lock()
        self.state, self.updated = dict(DEFAULT), 0.0
        self.thread = None
        self.finish = threading.Event()

    def publish(self, state):
        with self.lock:
            changed = state["action"] != self.state["action"]
            self.state, self.updated = dict(state), time.monotonic()
        if changed:
            self.wake.set()

    def connect(self, host, port):
        if self.thread and self.thread.is_alive():
            return False
        self.finish = threading.Event()
        self.thread = threading.Thread(target=self.run, args=(host, port, self.finish), daemon=True)
        self.thread.start()
        return True

    def disconnect(self):
        self.finish.set()
        self.wake.set()

    def run(self, host, port, finish):
        sock, state = None, dict(DEFAULT)
        try:
            sock = socket.create_connection((host, port), timeout=3)
            sock.settimeout(1.0)
            self.connected.set()
            self.events.put(("connected", "连接成功"))
            buffer, sequence = b"", 0
            while not finish.is_set():
                with self.lock:
                    state, updated = dict(self.state), self.updated
                # 窗口卡住时，后台线程也不能一直发送旧运动指令。
                if time.monotonic() - updated > 0.4:
                    state["action"] = ""
                sequence += 1
                state["seq"] = sequence
                sock.sendall((json.dumps(state) + "\n").encode("utf-8"))
                while b"\n" not in buffer:
                    data = sock.recv(4096)
                    if not data:
                        raise ConnectionError("开发板已断开")
                    buffer += data
                    if len(buffer) > 8192:
                        raise ValueError("服务端返回内容过长")
                line, buffer = buffer.split(b"\n", 1)
                reply = json.loads(line.decode("utf-8"))
                if reply.get("seq") != sequence or not reply.get("ok"):
                    raise ValueError("服务端响应不匹配")
                self.events.put(("status", reply))
                self.wake.wait(0.1)
                self.wake.clear()
        except (OSError, ValueError) as error:
            self.events.put(("error", str(error)))
        finally:
            if sock:
                try:
                    state["action"] = ""
                    sock.settimeout(0.2)
                    sock.sendall((json.dumps(state) + "\n").encode("utf-8"))
                except OSError:
                    pass
                sock.close()
            self.connected.clear()
            self.events.put(("disconnected", "已断开"))


class CarWindow:
    def __init__(self, root, host="127.0.0.1", port=8765):
        self.root, self.link = root, Connection()
        self.action, self.held_key = "", ""
        self.host = tk.StringVar(value=host)
        self.port = tk.StringVar(value=str(port))
        self.speed = tk.IntVar(value=200)
        self.spin_speed = tk.IntVar(value=150)
        self.width = tk.StringVar(value="0.30")
        self.radius = tk.StringVar(value="0.50")
        self.status = tk.StringVar(value="未连接 · 请先建立SSH隧道并启动开发板服务")
        self.input_status = tk.StringVar(value="参数可直接调整；按住运动，松开停车")
        self.target = tk.StringVar(value="发送目标：左 0 / 右 0")
        root.title("小车控制台 · Windows")
        root.geometry("850x650")
        root.minsize(780, 620)
        root.configure(background="#eef2f7")
        style = ttk.Style()
        style.theme_use("clam")
        style.configure("TFrame", background="#eef2f7")
        style.configure("TLabel", background="#eef2f7", font=("Microsoft YaHei UI", 10))
        style.configure("Title.TLabel", font=("Microsoft YaHei UI", 21, "bold"), foreground="#152f50")
        style.configure("TButton", font=("Microsoft YaHei UI", 11), padding=9)
        style.configure("Stop.TButton", background="#b7333c", foreground="white")
        self.build()
        root.bind("<KeyPress>", self.key_press)
        root.bind("<KeyRelease>", self.key_release)
        root.bind_all("<ButtonRelease-1>", lambda event: self.stop_motion())
        root.bind("<FocusOut>", lambda event: root.after_idle(self.check_focus))
        root.protocol("WM_DELETE_WINDOW", self.close)
        self.tick()

    def build(self):
        outer = ttk.Frame(self.root, padding=24)
        outer.pack(fill="both", expand=True)
        ttk.Label(outer, text="小车控制台", style="Title.TLabel").pack(anchor="w")
        ttk.Label(outer, text="独立调速 · 原地旋转 · 半径转弯", foreground="#526783").pack(anchor="w", pady=(2, 14))
        connection = ttk.Frame(outer)
        connection.pack(fill="x")
        ttk.Label(connection, text="地址").pack(side="left")
        ttk.Entry(connection, textvariable=self.host, width=18).pack(side="left", padx=8)
        ttk.Label(connection, text="端口").pack(side="left")
        ttk.Entry(connection, textvariable=self.port, width=7).pack(side="left", padx=8)
        ttk.Button(connection, text="连接", command=self.connect).pack(side="left", padx=4)
        ttk.Button(connection, text="断开", command=self.disconnect).pack(side="left", padx=4)
        ttk.Label(outer, textvariable=self.status, foreground="#315c91").pack(anchor="w", pady=10)

        settings = ttk.Frame(outer)
        settings.pack(fill="x", pady=(0, 12))
        settings.columnconfigure(1, weight=1)
        for row, title, variable in ((0, "行驶速度", self.speed), (1, "原地旋转速度", self.spin_speed)):
            ttk.Label(settings, text=title, width=14).grid(row=row, column=0, sticky="w", pady=7)
            tk.Scale(settings, from_=1, to=1023, orient="horizontal", variable=variable,
                     showvalue=False, background="#eef2f7", highlightthickness=0,
                     troughcolor="#d6e3f3", command=lambda value: self.publish()).grid(row=row, column=1, sticky="ew", padx=12)
            ttk.Spinbox(settings, from_=1, to=1023, textvariable=variable, width=8,
                        command=self.publish).grid(row=row, column=2)
        geometry = ttk.Frame(outer)
        geometry.pack(fill="x", pady=(0, 12))
        ttk.Label(geometry, text="轮距（米）").pack(side="left")
        ttk.Spinbox(geometry, from_=0.01, to=5, increment=0.01, textvariable=self.width,
                    width=9, command=self.publish).pack(side="left", padx=(8, 24))
        ttk.Label(geometry, text="转弯半径（米）").pack(side="left")
        ttk.Spinbox(geometry, from_=0.01, to=100, increment=0.05, textvariable=self.radius,
                    width=9, command=self.publish).pack(side="left", padx=8)
        ttk.Label(outer, text="轮距0.30米、半径0.50米为示例；半径是开环估算值。",
                  foreground="#6f5b32").pack(anchor="w", pady=(0, 12))

        buttons = ttk.Frame(outer)
        buttons.pack(fill="x")
        for column in range(3):
            buttons.columnconfigure(column, weight=1)
        self.motion_buttons = []
        for row, column, text, action in ((0, 0, "J  半径左转", "j"), (0, 1, "W / ↑  前进", "w"),
                (0, 2, "L  半径右转", "l"), (1, 0, "A / ←  原地左旋", "a"),
                (1, 1, "S / ↓  后退", "s"), (1, 2, "D / →  原地右旋", "d")):
            button = ttk.Button(buttons, text=text, state="disabled")
            button.grid(row=row, column=column, sticky="ew", padx=4, pady=5)
            button.bind("<ButtonPress-1>", lambda event, value=action: self.start_motion(value))
            self.motion_buttons.append(button)
        ttk.Button(outer, text="停车  ·  空格 / Esc", style="Stop.TButton",
                   command=self.stop_motion).pack(fill="x", pady=12)
        ttk.Label(outer, textvariable=self.target).pack(anchor="w")
        ttk.Label(outer, textvariable=self.input_status, foreground="#526783").pack(anchor="w", pady=6)
        ttk.Label(outer, text="按住按钮或方向键运动；切走窗口、松键或断开连接后停车。\n"
                  "仅显示发送目标，不代表电机实测轮速。", foreground="#526783").pack(anchor="w")

    def read_state(self):
        state = dict(action=self.action, speed=self.speed.get(), spin_speed=self.spin_speed.get(),
                     track_width=float(self.width.get()), radius=float(self.radius.get()))
        if not all(1 <= state[name] <= 1023 for name in ("speed", "spin_speed")):
            raise ValueError("速度应为1~1023")
        if not all(math.isfinite(state[name]) and state[name] > 0 for name in ("track_width", "radius")):
            raise ValueError("轮距和半径须大于0")
        return state

    def publish(self):
        try:
            state = self.read_state()
        except (ValueError, tk.TclError) as error:
            self.action = ""
            state = dict(DEFAULT)
            self.input_status.set("参数无效，已请求停车：" + str(error))
        else:
            self.input_status.set("参数实时生效 · 行驶速度与原地旋转速度互不影响")
        self.link.publish(state)

    def start_motion(self, action):
        if self.link.connected.is_set():
            self.action = action
            self.root.focus_set()
            self.publish()
        return "break"

    def stop_motion(self):
        self.action, self.held_key = "", ""
        self.publish()

    def key_press(self, event):
        key = event.keysym.lower()
        if key in ("space", "escape"):
            self.stop_motion()
            return "break"
        if event.widget.winfo_class() in ("Entry", "TEntry", "Spinbox", "TSpinbox"):
            return
        action = {"up": "w", "down": "s", "left": "a", "right": "d"}.get(key, key)
        if action in ("w", "s", "a", "d", "j", "l"):
            self.held_key = key
            return self.start_motion(action)

    def key_release(self, event):
        if event.keysym.lower() == self.held_key:
            self.stop_motion()

    def check_focus(self):
        widget = self.root.focus_displayof()
        if widget is None or widget.winfo_toplevel() != self.root:
            self.stop_motion()

    def connect(self):
        self.stop_motion()
        try:
            port = int(self.port.get())
            if not 1 <= port <= 65535:
                raise ValueError("端口须为1~65535")
            started = self.link.connect(self.host.get().strip(), port)
            self.status.set("连接中…" if started else "连接仍在运行，请先断开并稍候")
        except ValueError as error:
            self.status.set(str(error))

    def disconnect(self):
        self.stop_motion()
        self.link.disconnect()

    def tick(self):
        self.publish()
        while True:
            try:
                kind, value = self.link.events.get_nowait()
            except queue.Empty:
                break
            if kind == "status":
                self.status.set("已连接 · 模拟模式（不控制电机）" if value["simulated"] else "已连接 · 开发板控制模式")
                self.target.set(f"发送目标：左 {value['left']} / 右 {value['right']}")
            elif kind == "error":
                self.status.set("连接错误：" + value)
                self.action, self.held_key = "", ""
            elif kind == "disconnected":
                if not self.status.get().startswith("连接错误"):
                    self.status.set(value)
                self.action, self.held_key = "", ""
                self.target.set("发送目标：左 0 / 右 0（连接已断开）")
            else:
                self.status.set(value)
        enabled = "normal" if self.link.connected.is_set() else "disabled"
        for button in self.motion_buttons:
            button.configure(state=enabled)
        self.root.after(50, self.tick)

    def close(self):
        self.disconnect()
        self.root.destroy()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    root = tk.Tk()
    CarWindow(root, args.host, args.port)
    root.mainloop()


if __name__ == "__main__":
    main()
