"""真实 TCP + 模拟采集服务；临时文件不进入实验数据目录。"""
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src" / "desktop"))


class CollectorProcess:
    def __enter__(self):
        with socket.socket() as reserve:
            reserve.bind(("127.0.0.1", 0))
            self.port = reserve.getsockname()[1]
        self.process = subprocess.Popen(
            [sys.executable, "-X", "utf8", str(ROOT / "src/board/sensor_server.py"),
             "--simulate", "--port", str(self.port)],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, encoding="utf-8",
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        deadline = time.monotonic() + 8
        while time.monotonic() < deadline:
            if self.process.poll() is not None:
                raise RuntimeError(self.process.communicate()[1])
            try:
                self.sock = socket.create_connection(("127.0.0.1", self.port), timeout=0.3)
                break
            except OSError:
                time.sleep(0.05)
        else:
            self.process.terminate()
            self.process.communicate(timeout=5)
            raise RuntimeError("模拟服务未就绪")
        self.sock.settimeout(5)
        self.reader = self.sock.makefile("r", encoding="utf-8")
        self.hello = self.receive()
        return self

    def send(self, packet):
        self.sock.sendall((json.dumps(packet) + "\n").encode("utf-8"))

    def receive(self):
        line = self.reader.readline()
        if not line:
            raise ConnectionError("采集服务意外断开")
        return json.loads(line)

    def __exit__(self, *args):
        self.reader.close()
        self.sock.close()
        self.process.terminate()
        try:
            self.process.communicate(timeout=5)
        except subprocess.TimeoutExpired:
            self.process.kill()
            self.process.communicate(timeout=5)


class IntegrationTests(unittest.TestCase):
    def test_tcp_capture_events_and_csv_reopen(self):
        from sensor_analysis import SessionStore, load_session
        with tempfile.TemporaryDirectory() as temp, CollectorProcess() as server:
            self.assertEqual(server.hello["protocol"], 1)
            self.assertTrue(server.hello["simulated"])
            store = SessionStore(temp, "D2", {"sensor_id": "sim-0"})
            trial = store.start_trial({"primary": "adc_0", "distance_cm": 45,
                                       "experiment": "D2"})
            server.send(dict(type="start", request_id="start-test", trial_id=trial,
                             rate_hz=100, io_channels=[0, 2], adc_channels=[0, 4],
                             simulation={"distance_cm": 45, "sensor_kind": "distance"}))
            samples, events, marked, stop_requested = [], [], False, False
            while True:
                packet = server.receive()
                if packet["type"] == "sample":
                    self.assertEqual(packet["trial_id"], trial)
                    self.assertEqual(packet["seq"], len(samples) + 1)
                    self.assertLessEqual(packet["t_start_ns"], packet["t_end_ns"])
                    self.assertEqual(set(packet["io"]), {"0", "2"})
                    self.assertEqual(set(packet["adc"]), {"0", "4"})
                    store.append_sample(packet)
                    samples.append(packet)
                    if len(samples) >= 20 and not marked:
                        server.send(dict(type="mark", request_id="move", trial_id=trial,
                                         name="motion_start", data=dict(start_distance_cm=45,
                                         speed_cm_s=5, direction="approach")))
                        marked = True
                    if len(samples) >= 150 and not stop_requested:
                        server.send(dict(type="stop", request_id="stop-test", trial_id=trial))
                        stop_requested = True
                elif packet["type"] == "event":
                    events.append(packet)
                    store.append_event(packet)
                elif packet["type"] == "stopped":
                    self.assertTrue(packet.get("complete", True), packet)
                    self.assertEqual(packet["last_seq"], len(samples))
                    break
                elif packet["type"] == "error":
                    self.fail(str(packet))
            store.finish_trial()
            store.close()
            restored = load_session(store.path)
            self.assertEqual(len(restored["samples"]), len(samples))
            self.assertEqual(len(events), 1)
            self.assertEqual(len(restored["events"]), 1)
            self.assertGreaterEqual(len(samples), 150)


if __name__ == "__main__":
    unittest.main()
