#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""传感器 JSONL 采集服务；仅使用 ADC/IO，默认通过 SSH 隧道连接。

在电脑验证：python sensor_server.py --simulate
板端实物采集：sudo python3 sensor_server.py（由用户手动执行）。
采样频率是软件读取请求频率，不表示传感器或 ADC 的实际刷新频率。
"""

import argparse
import json
import math
import queue
import random
import select
import signal
import socket
import threading
import time


PROTOCOL = 1
IO_CHANNELS = tuple(range(8))
ADC_CHANNELS = tuple(range(9))
MAX_LINE_BYTES = 65536
ACQUISITION_TIMEOUT = 5.0


def _finite_number(value, name, minimum=None):
    try:
        finite = type(value) in (int, float) and math.isfinite(value)
    except OverflowError:
        finite = False
    if not finite:
        raise ValueError(name + " 必须是有限数值")
    if minimum is not None and value < minimum:
        raise ValueError(name + " 不得小于 " + str(minimum))
    return float(value)


def _channels(value, allowed, name):
    if not isinstance(value, list) or any(type(item) is not int or item not in allowed for item in value):
        raise ValueError(name + " 包含无效通道")
    if len(set(value)) != len(value):
        raise ValueError(name + " 不得包含重复通道")
    return list(value)


def validate_start(packet):
    """验证并复制 start 请求；不访问硬件。"""
    if not isinstance(packet, dict) or packet.get("type") != "start":
        raise ValueError("需要 start 请求")
    trial_id = packet.get("trial_id")
    if not isinstance(trial_id, str) or not trial_id.strip() or len(trial_id) > 200:
        raise ValueError("trial_id 必须是 1～200 字符的非空字符串")
    rate = _finite_number(packet.get("rate_hz", 50), "rate_hz", 1)
    if rate > 1000:
        raise ValueError("rate_hz 必须为 1～1000")
    io = _channels(packet.get("io_channels", []), IO_CHANNELS, "io_channels")
    adc = _channels(packet.get("adc_channels", []), ADC_CHANNELS, "adc_channels")
    if not io and not adc:
        raise ValueError("请至少选择一个 IO 或 ADC 通道")
    simulation = packet.get("simulation", {})
    if not isinstance(simulation, dict):
        raise ValueError("simulation 必须是对象")
    # 真实硬件不使用这些参数，但仍限制模拟输入，避免非有限值进入数据。
    for name in ("distance_cm", "angle_deg", "gray_level", "light", "noise_adc"):
        if name in simulation:
            _finite_number(simulation[name], name)
    kind = simulation.get("sensor_kind", "distance")
    if kind not in ("photoelectric", "distance", "grayscale"):
        raise ValueError("未知模拟 sensor_kind")
    return dict(type="start", request_id=packet.get("request_id"), trial_id=trial_id,
                rate_hz=rate, io_channels=io, adc_channels=adc, simulation=dict(simulation))


class SimulatedHardware:
    """用于界面与分析验证的合成数据，不代表实物量程或 ADC 位数。

    所有 ADC 值限制在 0～4095，仅为模拟选择。光电正对基准为
    接近 30 cm 触发、远离 35 cm 释放；距离 ADC 为非线性反函数。
    """

    def __init__(self, conditions=None):
        self.conditions = dict(conditions or {})
        self.opened = False
        # 每个静态点会重新开始试次；release 表示已从近处触发后远离，
        # 因此在回差区内仍应维持已触发状态。
        self.detected = self.conditions.get("phase") == "release"
        self.distance = max(0.1, float(self.conditions.get("distance_cm", 50)))
        self.motion = None
        self.random = random.Random(20261022)
        self.adc = [0] * 10
        self.io = [1] * 8

    def ADC_IO_Open(self):
        self.opened = True

    def ADC_IO_Close(self):
        self.opened = False

    def ADC_IO_SetIOMode(self, index, mode):
        if index not in IO_CHANNELS or mode != 0:
            raise ValueError("模拟器仅接受 IO 输入模式")

    def _distance(self, now_ns=None):
        if self.motion is None:
            return self.distance
        start_ns, start, speed = self.motion
        elapsed = ((now_ns or time.monotonic_ns()) - start_ns) / 1e9
        return max(0.1, start + speed * elapsed)

    def mark(self, name, data, now_ns):
        if name == "motion_start":
            start = _finite_number(data.get("start_distance_cm", self._distance(now_ns)),
                                   "start_distance_cm", 0)
            speed = _finite_number(data.get("speed_cm_s", 1), "speed_cm_s", 0)
            direction = data.get("direction", "approach")
            if direction not in ("approach", "release"):
                raise ValueError("direction 必须为 approach 或 release")
            self.motion = (now_ns, start, -speed if direction == "approach" else speed)
        elif name == "motion_end":
            self.distance = self._distance(now_ns)
            self.motion = None

    def _reflectance(self):
        surface = str(self.conditions.get("surface", "white")).lower()
        reflectance = {"black": 0.55, "黑色": 0.55, "白色": 1.0,
                       "natural": 0.8, "本色": 0.8}.get(surface, 1.0)
        angle = float(self.conditions.get("angle_deg", 0))
        return reflectance * max(0.08, math.cos(math.radians(angle)))

    def ADC_Get_All_Channel(self):
        distance = self._distance()
        reflectance = self._reflectance()
        kind = self.conditions.get("sensor_kind", "distance")
        if kind == "grayscale":
            gray = max(0, min(1, float(self.conditions.get("gray_level", 0.5))))
            base = 100 + 3600 * gray * math.exp(-abs(distance - 1) / 2.5)
            base += 100 * float(self.conditions.get("light", 1))
        else:
            base = 150 + 27000 / (distance + 2) * reflectance
        noise = abs(float(self.conditions.get("noise_adc", 4)))
        for channel in range(10):
            self.adc[channel] = int(max(0, min(4095, base * (1 + channel * .003)
                                             + self.random.gauss(0, noise))))
        return self.adc

    def ADC_IO_GetAllInputLevel(self):
        distance = self._distance()
        limit = 30 * self._reflectance()
        if not self.detected and distance <= limit:
            self.detected = True
        elif self.detected and distance >= limit + 5:
            self.detected = False
        self.io[:] = [0 if self.detected else 1] * 8
        return self.io


def real_hardware_factory(conditions=None):
    """延迟导入厂商库；模拟与普通导入均不加载 libuptech.so。"""
    from uptech import UpTech
    return UpTech()


class Acquisition:
    """单个试次。采样线程独占硬件；网络线程负责发送 output 中的数据。"""

    def __init__(self, request, hardware_factory, simulated=False, queue_size=8192):
        self.request = validate_start(request)
        self.hardware_factory = hardware_factory
        self.simulated = simulated
        self.output = queue.Queue(maxsize=queue_size)
        self.commands = queue.Queue(maxsize=128)
        self.stop_event = threading.Event()
        self.wake_event = threading.Event()
        self.done = threading.Event()
        self.lock = threading.Lock()
        self.thread = threading.Thread(target=self._run, name="sensor-sampling", daemon=True)
        self.last_seq = 0
        self.created_ns = time.monotonic_ns()
        self.started_ns = None
        self.last_read_ns = None
        self.last_success_ns = None
        self.terminal = []
        self.stop_request_id = None
        self.incomplete_reason = None

    def start(self):
        self.thread.start()

    def stop(self, request_id=None):
        self.stop_request_id = request_id
        self.stop_event.set()
        self.wake_event.set()

    def mark(self, packet):
        name, data = packet.get("name"), packet.get("data", {})
        if not isinstance(name, str) or not name.strip() or len(name) > 200:
            raise ValueError("事件 name 必须是非空字符串")
        if not isinstance(data, dict):
            raise ValueError("事件 data 必须是对象")
        if self.stop_event.is_set() or self.done.is_set():
            raise ValueError("当前试次已停止")
        try:
            self.commands.put_nowait(dict(packet, data=dict(data)))
            self.wake_event.set()
        except queue.Full:
            raise ValueError("事件队列已满，请降低事件频率")

    def status(self):
        with self.lock:
            elapsed = 0 if self.started_ns is None or self.last_read_ns is None else (
                self.last_read_ns - self.started_ns) / 1e9
            rate = max(0, self.last_seq - 1) / elapsed if elapsed > 0 else 0
            return dict(active=not self.done.is_set(), trial_id=self.request["trial_id"],
                        last_seq=self.last_seq, reading_rate_hz=rate,
                        requested_rate_hz=self.request["rate_hz"],
                        incomplete=self.incomplete_reason is not None)

    def stalled(self, timeout_seconds):
        """覆盖打开模块、首次读取、后续读取和关闭模块的阻塞。"""
        with self.lock:
            heartbeat = self.last_success_ns or self.started_ns or self.created_ns
            return not self.done.is_set() and (time.monotonic_ns() - heartbeat) / 1e9 > timeout_seconds

    def _emit(self, packet):
        try:
            self.output.put_nowait(packet)
        except queue.Full:
            raise RuntimeError("采样发送队列溢出，本次记录不完整")

    def _events(self, hardware):
        while True:
            try:
                packet = self.commands.get_nowait()
            except queue.Empty:
                return
            now_ns = time.monotonic_ns()
            if self.simulated:
                try:
                    hardware.mark(packet["name"], packet["data"], now_ns)
                except ValueError as error:
                    self._emit(dict(type="error", request_id=packet.get("request_id"),
                                    trial_id=self.request["trial_id"], message=str(error), fatal=False))
                    continue
            self._emit(dict(type="event", request_id=packet.get("request_id"),
                            trial_id=self.request["trial_id"], name=packet["name"],
                            data=packet["data"], t_ns=now_ns))

    def _run(self):
        req, hardware, open_attempted = self.request, None, False
        try:
            hardware = self.hardware_factory(req["simulation"])
            open_attempted = True
            hardware.ADC_IO_Open()
            for channel in req["io_channels"]:
                hardware.ADC_IO_SetIOMode(channel, 0)
            now_ns = time.monotonic_ns()
            with self.lock:
                self.started_ns = now_ns
            self._emit(dict(type="started", request_id=req.get("request_id"),
                            trial_id=req["trial_id"], t_ns=now_ns, rate_hz=req["rate_hz"]))
            interval_ns = int(1e9 / req["rate_hz"])
            deadline = now_ns
            while not self.stop_event.is_set():
                self._events(hardware)
                wait_seconds = (deadline - time.monotonic_ns()) / 1e9
                if wait_seconds > 0:
                    self.wake_event.wait(wait_seconds)
                    self.wake_event.clear()
                    continue
                t_start = time.monotonic_ns()
                # 厂商接口复用内部列表，必须立即复制；每类每帧只调用一次批量接口。
                adc = list(hardware.ADC_Get_All_Channel()) if req["adc_channels"] else []
                io = list(hardware.ADC_IO_GetAllInputLevel()) if req["io_channels"] else []
                t_end = time.monotonic_ns()
                frame = dict(type="sample", trial_id=req["trial_id"], seq=self.last_seq + 1,
                             t_start_ns=t_start, t_end_ns=t_end, simulated=self.simulated,
                             io={str(ch): int(io[ch]) for ch in req["io_channels"]},
                             adc={str(ch): int(adc[ch]) for ch in req["adc_channels"]})
                if any(value not in (0, 1) for value in frame["io"].values()):
                    raise ValueError("控制器返回了无效 IO 电平")
                self._emit(frame)
                with self.lock:
                    self.last_seq = frame["seq"]
                    self.last_read_ns = t_start
                    self.last_success_ns = t_end
                # 跟不上时不补发密集读取；实际速度由每帧时间戳和状态统计体现。
                deadline = max(deadline + interval_ns, t_end)
            self._events(hardware)
        except Exception as error:
            self.incomplete_reason = str(error)
        finally:
            if hardware is not None and open_attempted:
                try:
                    hardware.ADC_IO_Close()
                except Exception as error:
                    self.incomplete_reason = self.incomplete_reason or "关闭 ADC/IO 失败: " + str(error)
            if self.incomplete_reason:
                self.terminal.append(dict(type="error", request_id=self.stop_request_id or req.get("request_id"),
                                          trial_id=req["trial_id"], message=self.incomplete_reason,
                                          fatal=True, incomplete=True))
            self.terminal.append(dict(type="stopped", request_id=self.stop_request_id,
                                      trial_id=req["trial_id"], t_ns=time.monotonic_ns(),
                                      last_seq=self.last_seq, complete=self.incomplete_reason is None,
                                      reason=self.incomplete_reason))
            self.done.set()


def _send(client, packet):
    client.sendall((json.dumps(packet, ensure_ascii=False, allow_nan=False) + "\n").encode("utf-8"))


def serve_client(client, hardware_factory=None, simulated=False, shutdown_event=None, queue_size=8192,
                 acquisition_timeout=ACQUISITION_TIMEOUT, cleanup_timeout=3.0):
    """处理单个连接，返回时停止采样并关闭 ADC/IO；不关闭调用方 socket。"""
    factory = hardware_factory or (SimulatedHardware if simulated else real_hardware_factory)
    shutdown_event = shutdown_event or threading.Event()
    acquisition, buffer = None, b""
    client.settimeout(0.5)
    try:
        _send(client, dict(type="hello", protocol=PROTOCOL, simulated=simulated,
                           io_channels=list(IO_CHANNELS), adc_channels=list(ADC_CHANNELS)))
        while not shutdown_event.is_set():
            if acquisition is not None:
                if acquisition.stalled(acquisition_timeout):
                    # ctypes 厂商调用无法安全强制中断。明确通知上位机并断线；
                    # finally 若清理仍挂住会抛异常退出主进程，不接受另一硬件试次。
                    _send(client, dict(type="error", trial_id=acquisition.request["trial_id"],
                                       message="ADC/IO 打开、采样或关闭超过 {} 秒未响应".format(acquisition_timeout),
                                       fatal=True, incomplete=True))
                    break
                # 限制一次发送批量，确保高频采集时仍能及时处理 stop。
                for unused in range(128):
                    try:
                        packet = acquisition.output.get_nowait()
                    except queue.Empty:
                        break
                    _send(client, packet)
                if acquisition.done.is_set() and acquisition.output.empty():
                    for packet in acquisition.terminal:
                        _send(client, packet)
                    acquisition = None
            ready, unused_w, unused_x = select.select([client], [], [], 0.005)
            if not ready:
                continue
            data = client.recv(16384)
            if not data:
                break
            buffer += data
            if len(buffer) > MAX_LINE_BYTES and b"\n" not in buffer:
                raise ValueError("请求超过长度限制")
            while b"\n" in buffer:
                line, buffer = buffer.split(b"\n", 1)
                packet = {}
                try:
                    if len(line) > MAX_LINE_BYTES:
                        raise ValueError("请求超过长度限制")
                    packet = json.loads(line.decode("utf-8"))
                    if not isinstance(packet, dict):
                        packet = {}
                        raise ValueError("请求必须是 JSON 对象")
                    if packet.get("protocol", PROTOCOL) != PROTOCOL:
                        raise ValueError("不支持该协议版本")
                    kind = packet.get("type")
                    if kind == "start":
                        if acquisition is not None:
                            raise ValueError("已有试次运行，请先停止")
                        acquisition = Acquisition(packet, factory, simulated, queue_size)
                        acquisition.start()
                    elif kind == "status":
                        status = acquisition.status() if acquisition else dict(active=False, last_seq=0,
                                                                               reading_rate_hz=0)
                        _send(client, dict(status, type="status", request_id=packet.get("request_id"),
                                           protocol=PROTOCOL, simulated=simulated))
                    elif kind in ("stop", "mark"):
                        if acquisition is None:
                            raise ValueError("没有正在采集的试次")
                        if packet.get("trial_id") != acquisition.request["trial_id"]:
                            raise ValueError("trial_id 与当前试次不匹配")
                        if kind == "stop":
                            acquisition.stop(packet.get("request_id"))
                        else:
                            acquisition.mark(packet)
                    else:
                        raise ValueError("未知请求 type")
                except (ValueError, UnicodeError) as error:
                    _send(client, dict(type="error", request_id=packet.get("request_id"),
                                       trial_id=packet.get("trial_id"), message=str(error), fatal=False))
    except (ConnectionError, OSError):
        # 断线记录由上位机标记不完整；这里保证采样线程退出并清理 ADC/IO。
        pass
    finally:
        if acquisition is not None:
            acquisition.stop()
            acquisition.thread.join(timeout=cleanup_timeout)
            if acquisition.thread.is_alive():
                # 厂商调用若阻塞，Python 无法安全中断线程；明确报告并终止服务，
                # 不再接受新试次并发操作同一个控制器。
                raise RuntimeError("厂商 ADC/IO 调用超过 {} 秒未退出，请终止服务并检查控制器".format(cleanup_timeout))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8766)
    parser.add_argument("--simulate", action="store_true", help="使用合成 ADC/IO 数据，不加载厂商库")
    args = parser.parse_args(argv)
    if not 1 <= args.port <= 65535:
        parser.error("端口必须为 1～65535")
    shutdown = threading.Event()

    def interrupted(signum, frame):
        shutdown.set()

    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, interrupted)
    if hasattr(signal, "SIGHUP"):
        signal.signal(signal.SIGHUP, interrupted)
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        listener.bind((args.host, args.port))
        listener.listen(1)
        listener.settimeout(0.2)
        print("传感器服务 {}:{}，{}".format(args.host, args.port,
                                         "模拟数据" if args.simulate else "实物 ADC/IO；未操作电机"), flush=True)
        while not shutdown.is_set():
            try:
                client, address = listener.accept()
            except socket.timeout:
                continue
            with client:
                try:
                    serve_client(client, simulated=args.simulate, shutdown_event=shutdown)
                except ValueError as error:
                    print("连接请求错误：" + str(error), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
