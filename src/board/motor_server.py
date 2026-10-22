#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""开发板服务端。默认仅监听本机，通过SSH隧道接收Windows窗口指令。"""

import argparse
import json
import math
import signal
import socket
import time

# 板端程序集中放在同一目录，直接复用键盘程序的运动控制函数。
from keyboard_car import wheel_speeds, send, stop, REFRESH_INTERVAL

WATCHDOG = 0.7
DEFAULT = dict(action="", speed=200, spin_speed=150, track_width=0.30, radius=0.50)


def validate(packet):
    """只接受完整的控制状态，避免不合法参数保留旧运动。"""
    if not isinstance(packet, dict) or packet.get("action") not in ("", "w", "s", "a", "d", "j", "l"):
        raise ValueError("无效的运动指令")
    state = dict(packet)
    for name in ("speed", "spin_speed"):
        value = state.get(name)
        if type(value) is not int or not 1 <= value <= 1023:
            raise ValueError(name + " 必须为1~1023的整数")
    for name in ("track_width", "radius"):
        value = state.get(name)
        if type(value) not in (int, float) or not math.isfinite(value) or value <= 0:
            raise ValueError(name + " 必须是大于0的有限数值")
    return {name: state[name] for name in DEFAULT}


class Controller:
    """所有硬件调用都在服务端同一线程执行，复用原键盘程序的映射。"""
    def __init__(self, up, ids=(1, 2), reverse=False):
        self.up, self.ids, self.reverse = up, ids, reverse
        self.previous = (0, 0)
        self.last_send = float("-inf")

    def apply(self, state):
        target = wheel_speeds(state["action"], state["speed"], state["spin_speed"],
                              state["track_width"], state["radius"])
        if target != self.previous:
            if target == (0, 0) or any(a * b < 0 for a, b in zip(self.previous, target)):
                self.halt()
            self.previous, self.last_send = target, float("-inf")
        if target != (0, 0) and time.monotonic() - self.last_send >= REFRESH_INTERVAL:
            send(self.up, self.ids, target, self.reverse)
            self.last_send = time.monotonic()
        return target

    def halt(self):
        stop(self.up, self.ids)
        self.previous = (0, 0)


class SimulatedHardware:
    """用于在电脑上验证窗口和网络，不加载电机库。"""
    def CDS_Open(self):
        pass

    def CDS_Close(self):
        pass

    def CDS_SetMode(self, motor_id, mode):
        pass

    def CDS_SetSpeed(self, motor_id, speed):
        pass


def serve_client(client, controller, simulate=False):
    client.settimeout(0.1)
    buffer, state = b"", dict(DEFAULT)
    last_packet = time.monotonic()
    try:
        while True:
            packet = None
            try:
                data = client.recv(4096)
            except socket.timeout:
                data = None
            if data == b"":
                break
            if data:
                buffer += data
                if len(buffer) > 8192:
                    raise ValueError("指令过长")
                while b"\n" in buffer:
                    line, buffer = buffer.split(b"\n", 1)
                    packet = json.loads(line.decode("utf-8"))
                    state = validate(packet)
                    last_packet = time.monotonic()
            if time.monotonic() - last_packet >= WATCHDOG:
                state["action"] = ""
            target = controller.apply(state)
            if packet is not None:
                # 这是发送目标，不是编码器读数或电机执行成功的应答。
                reply = dict(ok=True, seq=packet.get("seq"), action=state["action"],
                             left=target[0], right=target[1], simulated=simulate)
                client.sendall((json.dumps(reply) + "\n").encode("utf-8"))
    finally:
        controller.halt()


def interrupted(signum, frame):
    raise KeyboardInterrupt


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--left-id", type=int, default=1)
    parser.add_argument("--right-id", type=int, default=2)
    parser.add_argument("--reverse", action="store_true")
    parser.add_argument("--simulate", action="store_true", help="模拟硬件，不控制真实电机")
    args = parser.parse_args()
    ids = (args.left_id, args.right_id)
    if ids[0] == ids[1] or not all(1 <= i <= 253 for i in ids):
        parser.error("左右ID须不同且在1~253之间")
    if not 1 <= args.port <= 65535:
        parser.error("端口须为1~65535")
    if args.simulate:
        up = SimulatedHardware()
    else:
        from uptech import UpTech
        up = UpTech()
    for sig in (signal.SIGTERM, signal.SIGINT):
        signal.signal(sig, interrupted)
    if hasattr(signal, "SIGHUP"):
        signal.signal(signal.SIGHUP, interrupted)

    with socket.socket() as listener:
        listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        listener.bind((args.host, args.port))
        listener.listen(1)
        listener.settimeout(0.2)
        controller = Controller(up, ids, args.reverse)
        try:
            up.CDS_Open()
            if not args.simulate:
                time.sleep(0.5)
            controller.halt()
            for motor_id in ids:
                up.CDS_SetMode(motor_id, 1)
                time.sleep(0.1)
            if not args.simulate:
                time.sleep(2.0)
            print("READY {}:{} mode={}".format(args.host, args.port,
                  "SIMULATION" if args.simulate else "HARDWARE"), flush=True)
            while True:
                try:
                    client, address = listener.accept()
                except socket.timeout:
                    continue
                print("Connected: " + str(address), flush=True)
                with client:
                    try:
                        serve_client(client, controller, args.simulate)
                    except (OSError, ValueError, TypeError) as error:
                        print("Connection closed: " + str(error), flush=True)
        except KeyboardInterrupt:
            pass
        finally:
            try:
                controller.halt()
            finally:
                up.CDS_Close()


if __name__ == "__main__":
    main()
