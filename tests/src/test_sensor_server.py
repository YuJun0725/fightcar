"""仅用模拟与拒绝电机接口的假硬件验证传感器服务。"""

import importlib.util
import json
from pathlib import Path
import queue
import socket
import threading
import time
import unittest


SERVER_PATH = Path(__file__).resolve().parents[2] / "src" / "board" / "sensor_server.py"
SPEC = importlib.util.spec_from_file_location("sensor_server_under_test", SERVER_PATH)
server = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(server)


def request(**changes):
    packet = dict(type="start", request_id="start-1", trial_id="trial-1", rate_hz=100,
                  io_channels=[0, 7], adc_channels=[0, 8])
    packet.update(changes)
    return packet


class FakeHardware:
    """IO读取还会修改ADC缓存，用来验证采样时及时复制厂商共享数组。"""

    def __init__(self, fail_after=None):
        self.opens = self.closes = self.adc_reads = self.io_reads = 0
        self.modes = []
        self.adc = [0] * 10
        self.io = [1] * 8
        self.fail_after = fail_after

    def __getattr__(self, name):
        if name.startswith("CDS"):
            raise AssertionError("绝不允许调用电机/舵机接口：" + name)
        raise AttributeError(name)

    def ADC_IO_Open(self):
        self.opens += 1

    def ADC_IO_Close(self):
        self.closes += 1

    def ADC_IO_SetIOMode(self, channel, mode):
        self.modes.append((channel, mode))

    def ADC_Get_All_Channel(self):
        self.adc_reads += 1
        if self.fail_after is not None and self.adc_reads > self.fail_after:
            raise OSError("测试 ADC 读取异常")
        self.adc[:] = [100 * self.adc_reads + channel for channel in range(10)]
        return self.adc

    def ADC_IO_GetAllInputLevel(self):
        self.io_reads += 1
        self.adc[:] = [9999] * 10
        self.io[:] = [self.io_reads % 2] * 8
        return self.io


class Connection:
    def __init__(self, hardware=None, simulated=False, **options):
        self.server_socket, self.socket = socket.socketpair()
        self.socket.settimeout(3)
        self.buffer = b""
        self.hardware = hardware or FakeHardware()
        self.errors = []

        def run():
            try:
                server.serve_client(self.server_socket, lambda conditions: self.hardware,
                                    simulated=simulated, **options)
            except Exception as error:
                self.errors.append(error)
            finally:
                self.server_socket.close()

        self.thread = threading.Thread(target=run, daemon=True)
        self.thread.start()
        self.hello = self.read()

    def send(self, packet):
        self.socket.sendall((json.dumps(packet) + "\n").encode("utf-8"))

    def read(self):
        while b"\n" not in self.buffer:
            chunk = self.socket.recv(65536)
            if not chunk:
                raise EOFError("server closed")
            self.buffer += chunk
        line, self.buffer = self.buffer.split(b"\n", 1)
        return json.loads(line)

    def until(self, kind):
        records = []
        for unused in range(10000):
            item = self.read()
            records.append(item)
            if item["type"] == kind:
                return records
        raise AssertionError("没有收到 " + kind)

    def close(self):
        self.socket.close()
        self.thread.join(4)
        if self.thread.is_alive():
            raise AssertionError("断线后服务线程未退出")
        if self.errors:
            raise self.errors[0]


class ValidationTests(unittest.TestCase):
    def test_valid_defaults_and_channels(self):
        packet = server.validate_start(dict(type="start", trial_id="a", adc_channels=[8]))
        self.assertEqual(packet["rate_hz"], 50)
        self.assertEqual(packet["io_channels"], [])

    def test_reject_invalid_parameters(self):
        for changes in (dict(rate_hz=0), dict(rate_hz=1001), dict(rate_hz=True),
                        dict(rate_hz=10 ** 400),
                        dict(rate_hz=float("nan")), dict(io_channels=[8]),
                        dict(adc_channels=[9]), dict(io_channels=[0, 0]),
                        dict(adc_channels=[], io_channels=[]), dict(trial_id=""),
                        dict(simulation={"distance_cm": float("inf")})):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                server.validate_start(request(**changes))


class AcquisitionTests(unittest.TestCase):
    def test_watchdog_uses_last_successful_end_not_read_start(self):
        acquisition = server.Acquisition(request(), lambda conditions: FakeHardware())
        now = time.monotonic_ns()
        acquisition.started_ns = now - 10_000_000_000
        acquisition.last_read_ns = now - 10_000_000_000
        acquisition.last_success_ns = now
        self.assertFalse(acquisition.stalled(.1))

    def test_batch_reads_are_once_per_frame_and_immediately_copied(self):
        hardware = FakeHardware()
        acquisition = server.Acquisition(request(rate_hz=200), lambda conditions: hardware)
        acquisition.start()
        rows = [acquisition.output.get(timeout=2) for unused in range(5)]
        acquisition.stop("stop")
        acquisition.thread.join(2)
        while not acquisition.output.empty():
            rows.append(acquisition.output.get_nowait())
        frames = [row for row in rows if row["type"] == "sample"]
        self.assertGreaterEqual(len(frames), 4)
        self.assertEqual([row["seq"] for row in frames], list(range(1, len(frames) + 1)))
        for row in frames:
            self.assertEqual(row["adc"], {"0": row["seq"] * 100, "8": row["seq"] * 100 + 8})
            self.assertLessEqual(row["t_start_ns"], row["t_end_ns"])
        self.assertEqual(hardware.adc_reads, len(frames))
        self.assertEqual(hardware.io_reads, len(frames))
        self.assertEqual(hardware.modes, [(0, 0), (7, 0)])
        self.assertEqual(hardware.opens, 1)
        self.assertEqual(hardware.closes, 1)
        self.assertTrue(acquisition.terminal[-1]["complete"])

    def test_queue_overflow_is_reported_as_incomplete(self):
        hardware = FakeHardware()
        acquisition = server.Acquisition(request(rate_hz=1000), lambda conditions: hardware,
                                         queue_size=2)
        acquisition.start()
        self.assertTrue(acquisition.done.wait(2))
        self.assertEqual(acquisition.output.qsize(), 2)
        self.assertEqual(acquisition.terminal[0]["type"], "error")
        self.assertIn("溢出", acquisition.terminal[0]["message"])
        self.assertFalse(acquisition.terminal[-1]["complete"])
        self.assertEqual(hardware.closes, 1)

    def test_unused_interface_is_not_read(self):
        hardware = FakeHardware()
        acquisition = server.Acquisition(request(io_channels=[], adc_channels=[8]),
                                         lambda conditions: hardware)
        acquisition.start()
        acquisition.output.get(timeout=2)
        acquisition.output.get(timeout=2)
        acquisition.stop()
        acquisition.thread.join(2)
        self.assertEqual(hardware.io_reads, 0)
        self.assertEqual(hardware.modes, [])


class ProtocolTests(unittest.TestCase):
    def test_disconnect_before_hello_does_not_crash_service(self):
        peer, client = socket.socketpair()
        client.close()
        created = []
        try:
            server.serve_client(peer, lambda conditions: created.append(conditions))
        finally:
            peer.close()
        self.assertEqual(created, [])

    def test_oversized_integer_request_returns_error_and_connection_stays_usable(self):
        connection = Connection()
        try:
            connection.send(request(rate_hz=10 ** 400))
            error = connection.until("error")[-1]
            self.assertFalse(error["fatal"])
            self.assertEqual(connection.hardware.opens, 0)
            connection.send(dict(type="status"))
            self.assertFalse(connection.until("status")[-1]["active"])
        finally:
            connection.close()

    def test_blocked_read_reports_incomplete_then_exits_without_stopped(self):
        unblock = threading.Event()

        class BlockedHardware(FakeHardware):
            def ADC_Get_All_Channel(self):
                unblock.wait(2)
                return super().ADC_Get_All_Channel()

        hardware = BlockedHardware()
        connection = Connection(hardware, acquisition_timeout=.04, cleanup_timeout=.02)
        try:
            connection.send(request())
            records = connection.until("error")
            self.assertTrue(records[-1]["fatal"])
            self.assertTrue(records[-1]["incomplete"])
            self.assertNotIn("stopped", [row["type"] for row in records])
            connection.thread.join(1)
            self.assertFalse(connection.thread.is_alive())
            self.assertEqual(len(connection.errors), 1)
            self.assertIsInstance(connection.errors[0], RuntimeError)
            self.assertEqual(connection.socket.recv(1024), b"")
        finally:
            unblock.set()
            connection.errors.clear()
            connection.close()
        deadline = time.monotonic() + 1
        while not hardware.closes and time.monotonic() < deadline:
            time.sleep(.005)
        self.assertEqual(hardware.closes, 1)

    def test_blocked_open_is_also_timed_out(self):
        unblock = threading.Event()

        class BlockedOpen(FakeHardware):
            def ADC_IO_Open(self):
                super().ADC_IO_Open()
                unblock.wait(2)

        connection = Connection(BlockedOpen(), acquisition_timeout=.04, cleanup_timeout=.02)
        try:
            connection.send(request())
            error = connection.until("error")[-1]
            self.assertTrue(error["fatal"])
            connection.thread.join(1)
            self.assertFalse(connection.thread.is_alive())
            self.assertEqual(len(connection.errors), 1)
            self.assertIsInstance(connection.errors[0], RuntimeError)
        finally:
            unblock.set()
            connection.errors.clear()
            connection.close()

    def test_start_mark_status_stop_and_reuse_connection(self):
        connection = Connection()
        try:
            self.assertEqual(connection.hello["protocol"], 1)
            self.assertFalse(connection.hello["simulated"])
            connection.send(request())
            self.assertEqual(connection.until("started")[-1]["trial_id"], "trial-1")
            connection.send(dict(type="mark", request_id="mark-1", trial_id="trial-1",
                                 name="motion_start", data={"start_distance_cm": 40}))
            marked = connection.until("event")
            self.assertEqual(marked[-1]["request_id"], "mark-1")
            self.assertEqual(marked[-1]["data"], {"start_distance_cm": 40})
            connection.send(dict(type="status", request_id="status-1"))
            self.assertTrue(connection.until("status")[-1]["active"])
            connection.send(dict(type="stop", request_id="stop-1", trial_id="trial-1"))
            records = connection.until("stopped")
            self.assertTrue(records[-1]["complete"])
            self.assertEqual(records[-1]["request_id"], "stop-1")
            self.assertEqual(connection.hardware.closes, 1)
            connection.send(request(trial_id="trial-2"))
            restarted = connection.until("started")[-1]
            self.assertEqual(restarted["trial_id"], "trial-2")
            self.assertEqual(connection.until("sample")[-1]["seq"], 1)
        finally:
            connection.close()
        self.assertEqual(connection.hardware.closes, 2)

    def test_errors_preserve_frames_before_terminal_packets(self):
        connection = Connection(FakeHardware(fail_after=3))
        try:
            connection.send(request())
            records = connection.until("stopped")
            self.assertEqual([row["seq"] for row in records if row["type"] == "sample"], [1, 2, 3])
            self.assertEqual(records[-2]["type"], "error")
            self.assertTrue(records[-2]["fatal"])
            self.assertFalse(records[-1]["complete"])
            self.assertEqual(records[-1]["last_seq"], 3)
            self.assertEqual(connection.hardware.closes, 1)
        finally:
            connection.close()

    def test_stop_frame_order_and_no_frames_after_stopped(self):
        connection = Connection()
        try:
            connection.send(request(rate_hz=1000))
            records = connection.until("sample")
            connection.send(dict(type="stop", trial_id="trial-1", request_id="s"))
            records.extend(connection.until("stopped"))
            frames = [row for row in records if row["type"] == "sample"]
            self.assertEqual([row["seq"] for row in frames], list(range(1, len(frames) + 1)))
            self.assertEqual(records[-1]["last_seq"], len(frames))
            connection.send(dict(type="status"))
            after = connection.until("status")
            self.assertEqual(len(after), 1)
            self.assertFalse(after[-1]["active"])
        finally:
            connection.close()

    def test_invalid_request_does_not_open_hardware(self):
        connection = Connection()
        try:
            connection.send(request(rate_hz=1001))
            self.assertFalse(connection.until("error")[-1]["fatal"])
            self.assertEqual(connection.hardware.opens, 0)
            connection.send(request())
            connection.until("started")
            connection.send(dict(type="stop", trial_id="wrong"))
            self.assertIn("不匹配", connection.until("error")[-1]["message"])
        finally:
            connection.close()

    def test_disconnect_closes_adc_io(self):
        connection = Connection()
        connection.send(request())
        connection.until("sample")
        connection.close()
        self.assertEqual(connection.hardware.closes, 1)


class SimulatorTests(unittest.TestCase):
    def test_release_static_points_keep_hysteresis_when_restarting(self):
        for distance, expected in ((25, 0), (32, 0), (34, 0), (35, 1), (40, 1)):
            with self.subTest(distance=distance):
                acquisition = server.Acquisition(
                    request(io_channels=[0], adc_channels=[],
                            simulation={"phase": "release", "distance_cm": distance}),
                    server.SimulatedHardware, simulated=True)
                acquisition.start()
                self.assertEqual(acquisition.output.get(timeout=2)["type"], "started")
                frame = acquisition.output.get(timeout=2)
                self.assertEqual(frame["io"]["0"], expected)
                acquisition.stop()
                acquisition.thread.join(2)
                self.assertTrue(acquisition.done.is_set())

    def test_photoelectric_hysteresis_and_motion(self):
        hardware = server.SimulatedHardware({"distance_cm": 40})
        self.assertEqual(hardware.ADC_IO_GetAllInputLevel()[0], 1)
        hardware.distance = 29
        self.assertEqual(hardware.ADC_IO_GetAllInputLevel()[0], 0)
        hardware.distance = 34
        self.assertEqual(hardware.ADC_IO_GetAllInputLevel()[0], 0)
        hardware.distance = 35
        self.assertEqual(hardware.ADC_IO_GetAllInputLevel()[0], 1)
        stamp = time.monotonic_ns()
        hardware.mark("motion_start", dict(start_distance_cm=50, speed_cm_s=10,
                                           direction="approach"), stamp)
        self.assertAlmostEqual(hardware._distance(stamp + 1_000_000_000), 40)
        hardware.mark("motion_end", {}, stamp + 2_000_000_000)
        self.assertAlmostEqual(hardware._distance(), 30)

    def test_nonlinear_distance_adc_and_simulated_event(self):
        samples = []
        for distance in (10, 20, 30):
            hardware = server.SimulatedHardware(dict(distance_cm=distance, noise_adc=0))
            samples.append(hardware.ADC_Get_All_Channel()[0])
        self.assertGreater(samples[0], samples[1])
        self.assertGreater(samples[1], samples[2])
        self.assertNotEqual(samples[0] - samples[1], samples[1] - samples[2])
        hardware = server.SimulatedHardware(dict(distance_cm=50))
        connection = Connection(hardware, simulated=True)
        try:
            connection.send(request(rate_hz=1))
            connection.until("sample")
            begin = time.monotonic()
            connection.send(dict(type="mark", trial_id="trial-1", name="motion_start",
                                 data=dict(start_distance_cm=50, speed_cm_s=10,
                                           direction="approach")))
            event = connection.until("event")[-1]
            self.assertLess(time.monotonic() - begin, .5)
            self.assertIsNotNone(hardware.motion)
            self.assertEqual(hardware.motion[0], event["t_ns"])
        finally:
            connection.close()


if __name__ == "__main__":
    unittest.main()
