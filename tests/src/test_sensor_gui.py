"""真实 Tk 窗口 + 模拟 TCP 服务烟测；不访问硬件，数据仅写临时目录。"""

import argparse
import csv
import importlib.util
import math
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

from test_sensor_integration import CollectorProcess


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src" / "desktop"))


@unittest.skipUnless(importlib.util.find_spec("matplotlib"), "需要 Matplotlib 才能验证绘图界面")
class SensorGuiTests(unittest.TestCase):
    def setUp(self):
        import tkinter as tk
        try:
            self.root = tk.Tk()
        except tk.TclError as exc:
            self.skipTest("当前环境不能创建 Tk 窗口：{}".format(exc))
        self.root.withdraw()
        self.callback_errors = []
        self.dialog_errors = []
        self.root.report_callback_exception = lambda *exc: self.callback_errors.append(str(exc[1]))
        self.addCleanup(self.destroy_root)
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.server = CollectorProcess().__enter__()
        self.addCleanup(self.server.__exit__, None, None, None)
        # CollectorProcess 首次连接用于探活；释放后让真实 GUI 占用采集服务。
        self.server.reader.close()
        self.server.sock.close()
        import tkinter.messagebox as messagebox
        self.addCleanup(mock.patch.stopall)
        mock.patch.object(messagebox, "showerror", side_effect=lambda *a, **k:
                          self.dialog_errors.append(a)).start()
        mock.patch.object(messagebox, "showinfo", return_value=None).start()
        mock.patch.object(messagebox, "showwarning", return_value=None).start()
        mock.patch.object(messagebox, "askyesno", return_value=True).start()
        import sensor_client
        self.app = sensor_client.SensorWindow(self.root, argparse.Namespace(
            host="127.0.0.1", port=self.server.port, simulate=False))
        self.addCleanup(self.close_app)
        self.app.vars["output"].set(self.directory.name)
        self.app.vars["duration"].set("0.2")
        self.app.vars["rate"].set("100")
        self.app.connect()
        self.pump_until(lambda: self.app.worker.connected, "GUI 未连接模拟服务")

    def destroy_root(self):
        try:
            self.root.destroy()
        except Exception:
            pass

    def close_app(self):
        self.app.close()
        deadline = time.monotonic() + 6
        while time.monotonic() < deadline:
            try:
                if not self.root.winfo_exists():
                    break
                self.root.update()
            except Exception:
                break
            time.sleep(0.01)
        self.app.worker._thread.join(timeout=0.5)
        self.assertFalse(self.app.worker._thread.is_alive(), "窗口关闭后后台线程未退出")

    def pump_until(self, predicate, message, timeout=8):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            self.root.update()
            self.assertEqual(self.callback_errors, [], "Tk 回调异常")
            if predicate():
                return
            time.sleep(0.01)
        self.fail(message)

    def pump_for(self, seconds):
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            self.root.update()
            self.assertEqual(self.callback_errors, [], "Tk 回调异常")
            time.sleep(0.01)

    def capture_point(self, distance, phase="接近"):
        self.app.vars["distance"].set(str(distance))
        self.app.vars["phase"].set(phase)
        self.app.start_capture(point=True)
        self.assertTrue(self.app.capture, self.app.status.get())
        self.pump_until(lambda: not self.app.capture and self.app.worker.trial_id is None,
                        "静态点采样未完成：" + self.app.status.get())
        self.assertTrue(self.app.worker.path)

    def assert_plot_has_samples(self, axis, minimum=2):
        lines = [line for line in axis.lines if len(line.get_xdata()) >= minimum
                 and any(value is not None and math.isfinite(float(value))
                         for value in line.get_ydata())]
        self.assertTrue(lines, "曲线轴中缺少带有效数据的绘图线")

    def test_static_capture_is_saved_while_tk_is_paused(self):
        from sensor_analysis import load_session
        self.app.vars["experiment"].set("D1")
        self.app.vars["distance"].set("20")
        self.app.vars["duration"].set("0.3")
        self.app.start_capture(point=True)
        self.pump_until(lambda: self.app.worker.latest is not None,
                        "后台采集未开始")
        # 故意暂停 Tk；点采样截止与写盘必须由后台继续执行。
        time.sleep(0.9)
        self.assertIsNone(self.app.worker.trial_id, "Tk 阻塞延长了采样过程")
        data = load_session(self.app.worker.path)
        trial = data["metadata"]["trials"][0]
        self.assertEqual(trial["status"], "complete")
        self.assertGreater(len(data["samples"]), 10)
        duration = (data["samples"][-1]["t_end_ns"] - data["samples"][0]["t_start_ns"]) / 1e9
        self.assertLess(duration, 0.6)
        self.pump_until(lambda: not self.app.capture, "界面未消费完成通知")
        self.assertEqual(self.callback_errors, [])

    def test_connection_failure_preserves_incomplete_samples(self):
        from sensor_analysis import load_session
        self.app.vars["experiment"].set("D2")
        self.app.start_capture()
        self.pump_until(lambda: self.app.worker.sample_count >= 8,
                        "连续采样未收到足够数据")
        path = self.app.worker.path
        self.server.process.terminate()
        self.server.process.communicate(timeout=5)
        self.pump_until(lambda: not self.app.capture and not self.app.worker.connected,
                        "服务退出后界面未结束采样")
        data = load_session(path)
        self.assertGreaterEqual(len(data["samples"]), 8)
        self.assertEqual(data["metadata"]["trials"][0]["status"], "incomplete")
        self.assertTrue(data["metadata"]["trials"][0]["reason"])

    def test_static_photoelectric_conditions_are_recorded(self):
        from sensor_analysis import load_session, photoelectric_summary
        self.app.vars["experiment"].set("P1")
        self.app.vars["sensor_id"].set("photo_1")
        for distance, phase in [(40, "接近"), (30, "接近"), (25, "接近"),
                                (25, "释放"), (32, "释放"), (35, "释放")]:
            self.capture_point(distance, phase)
        data = load_session(self.app.worker.path)
        points = []
        for trial in data["metadata"]["trials"]:
            metadata = trial["metadata"]
            points.append(dict(phase=metadata["phase"], distance_cm=metadata["distance_cm"],
                io_values=[sample["io"]["0"] for sample in data["samples"]
                           if sample["trial_id"] == trial["trial_id"]]))
        result = photoelectric_summary(points)
        self.assertEqual(result["trigger_distance_cm"], 30)
        self.assertEqual(result["release_distance_cm"], 35)
        self.assertEqual(result["hysteresis_cm"], 5)
        self.assertTrue(all(trial["status"] == "complete"
                            for trial in data["metadata"]["trials"]))
        self.app.plot_history()
        self.assert_plot_has_samples(self.app.io_ax)

    def test_distance_calibration_independent_validation_export_and_reopen(self):
        import sensor_client
        from sensor_analysis import load_session, validate_calibration
        self.app.vars["experiment"].set("D1")
        self.app.vars["sensor_id"].set("distance_1")
        for distance in (10, 20, 30):
            self.capture_point(distance)
        self.app.make_calibration()
        self.assertIsNotNone(self.app.calibration, self.app.status.get())
        self.assertEqual(len(self.app.calibration["points"]), 3)
        self.assertEqual(self.app.calibration["sensor_id"], "distance_1")
        self.assert_plot_has_samples(self.app.ax, minimum=3)
        self.app.vars["experiment"].set("D5")
        self.assertEqual(self.app.vars["validation"].get(), "是")
        self.capture_point(25)
        results = []

        def run_validation(*args, **kwargs):
            value = validate_calibration(*args, **kwargs)
            results.append(value)
            return value

        with mock.patch.object(sensor_client, "validate_calibration", side_effect=run_validation):
            self.app.validate()
        self.assertTrue(results, self.app.status.get())
        self.assertEqual(len(results[-1]["rows"]), 1)
        self.assertEqual(results[-1]["rows"][0]["distance_cm"], 25)
        self.assertLess(results[-1]["mae"], 2)
        self.assertTrue(all(point["distance_cm"] != 25 for point in self.app.calibration["points"]))
        path = self.app.worker.path
        image = Path(self.directory.name) / "curve.png"
        calibration_file = Path(self.directory.name) / "calibration.json"
        self.app.export_png(str(image))
        self.app.export_calibration(str(calibration_file))
        self.assertEqual(image.read_bytes()[:8], b"\x89PNG\r\n\x1a\n")
        self.assertTrue(calibration_file.exists())
        raw_export = Path(self.directory.name) / "raw_export.csv"
        summary_export = Path(self.directory.name) / "summary_export.csv"
        self.app.export_csv(str(raw_export), raw=True)
        self.app.export_csv(str(summary_export))
        self.assertEqual(raw_export.read_bytes(), (path / "samples.csv").read_bytes())
        self.assertTrue(summary_export.read_bytes().startswith(b"\xef\xbb\xbf"))
        with summary_export.open(encoding="utf-8-sig", newline="") as handle:
            exported_rows = list(csv.DictReader(handle))
        self.assertTrue(any(row["experiment"] == "D5" and row.get("error_cm")
                            for row in exported_rows))
        self.pump_for(0.15)
        restored = load_session(path)
        self.assertEqual(len(restored["metadata"]["trials"]), 4)
        self.assertTrue(restored["summaries"])
        self.app.new_session()
        self.pump_until(lambda: self.app.worker.path is None, "新会话未关闭旧记录")
        self.app.open_history(str(path))
        self.assertIsNotNone(self.app.dataset)
        self.assertEqual(len(self.app.dataset["samples"]), len(restored["samples"]))
        self.assertTrue(self.app.table.get_children())
        self.app.vars["filter"].set("滑动平均")
        self.app.plot_history()
        self.assert_plot_has_samples(self.app.ax)
        self.assertGreaterEqual(len(self.app.ax.lines), 2, "历史图缺少滤波对比线")
        self.assert_plot_has_samples(self.app.distance_ax)
        self.app.plot_groups()
        self.assert_plot_has_samples(self.app.ax)
        self.root.update()
        self.assertEqual(self.callback_errors, [])

    def test_photoelectric_dynamic_motion_and_analysis(self):
        from sensor_analysis import dynamic_photoelectric, load_session
        self.app.vars["experiment"].set("P4")
        self.app.vars["distance"].set("40")
        self.app.vars["speed"].set("20")
        self.app.start_capture()
        self.pump_until(lambda: self.app.worker.sample_count >= 5,
                        "动态光电采样未开始")
        self.assertEqual(self.app.worker.latest["io"]["0"], 1)
        self.app.mark_motion("motion_start")
        self.pump_until(lambda: self.app.worker.latest["io"]["0"] == 0,
                        "模拟目标经过边界后未触发")
        self.pump_for(0.08)  # 留足连续稳定帧，避免在第一帧触发时立刻停止。
        self.app.mark_motion("motion_end")
        self.app.stop_capture()
        self.pump_until(lambda: not self.app.capture and self.app.worker.trial_id is None,
                        "动态采样未停止")
        data = load_session(self.app.worker.path)
        self.assertEqual([event["name"] for event in data["events"]],
                         ["motion_start", "motion_end"])
        result = dynamic_photoelectric(data["samples"], data["events"])
        self.assertEqual(result["miss_status"], "detected")
        self.assertAlmostEqual(result["trigger_distance_cm"], 30, delta=2)
        self.assertEqual(result["position_source"], "estimated")
        self.assertTrue(any(row.get("experiment") == "P4" for row in self.app.summaries),
                        "GUI 未生成动态实验统计")
        self.app.plot_history()
        self.assert_plot_has_samples(self.app.io_ax)
        self.assert_plot_has_samples(self.app.distance_ax)

    def test_all_templates_defaults_and_grayscale_condition_snapshots(self):
        from sensor_analysis import EXPERIMENTS, load_session
        for code in EXPERIMENTS:
            with self.subTest(template=code):
                self.app.vars["experiment"].set(code)
                self.assertEqual([value.get() for value in self.app.io_vars],
                                 [code.startswith("P")] + [False] * 7)
                self.assertEqual([value.get() for value in self.app.adc_vars],
                                 [not code.startswith("P")] + [False] * 8)
                self.assertEqual(self.app.vars["main_channel"].get(),
                                 "IO0" if code.startswith("P") else "ADC0")
                self.assertEqual(self.app.vars["validation"].get(), "是" if code == "D5" else "否")
        for index, code in enumerate(("G1", "G2", "G3"), 1):
            self.app.vars["experiment"].set(code)
            self.app.vars["unit"].set("mm")
            self.app.vars["gray"].set(str(index / 4))
            self.app.vars["light"].set("光照条件{}".format(index))
            self.app.vars["light_factor"].set(str(index / 2))
            self.capture_point(index * 10)
        data = load_session(self.app.worker.path)
        self.assertEqual(len(data["metadata"]["trials"]), 3)
        for index, trial in enumerate(data["metadata"]["trials"], 1):
            metadata = trial["metadata"]
            self.assertEqual(metadata["experiment"], "G{}".format(index))
            self.assertEqual(metadata["unit"], "mm")
            self.assertEqual(metadata["distance_cm"], index)
            self.assertEqual(metadata["gray_level"], index / 4)
            self.assertEqual(metadata["light"], "光照条件{}".format(index))
            self.assertEqual(float(metadata["light_factor"]), index / 2)
            samples = [sample for sample in data["samples"] if sample["trial_id"] == trial["trial_id"]]
            self.assertGreater(len(samples), 3)
            self.assertTrue(all("0" in sample["adc"] and not sample["io"] for sample in samples))
        self.app.plot_groups()
        self.assert_plot_has_samples(self.app.ax)

    def test_history_analysis_cannot_overwrite_current_session(self):
        from sensor_analysis import SessionStore, load_session
        self.app.vars["experiment"].set("D1")
        self.app.vars["sensor_id"].set("live_sensor")
        for distance in (10, 20, 30):
            self.capture_point(distance)
        self.assertIsNotNone(self.app.make_calibration())
        live_path = self.app.worker.path
        self.pump_until(lambda: (live_path / "summary.csv").exists()
                        and (live_path / "calibration.json").exists(), "当前会话文件未保存")
        self.pump_for(0.15)
        original_summary = (live_path / "summary.csv").read_bytes()
        original_calibration = (live_path / "calibration.json").read_bytes()
        template = dict(load_session(live_path)["metadata"]["trials"][0]["metadata"])
        template["sensor_id"] = "historical_sensor"
        history = SessionStore(Path(self.directory.name) / "history_fixture", "D1", template)
        try:
            for index, (distance, adc) in enumerate(((12, 2800), (24, 1700), (36, 1100)), 1):
                metadata = dict(template, distance_cm=distance)
                trial = history.start_trial(metadata)
                for seq in range(1, 6):
                    stamp = index * 1_000_000 + seq * 1000
                    history.append_sample(dict(type="sample", trial_id=trial, seq=seq,
                        t_start_ns=stamp, t_end_ns=stamp + 1, io={}, adc={"0": adc}, simulated=True))
                history.finish_trial()
        finally:
            history.close()
        self.app.vars["sensor_id"].set("historical_sensor")
        self.app.open_history(str(history.path))
        self.app.analyze()
        model = self.app.make_calibration()
        self.assertIsNotNone(model, self.app.status.get())
        self.assertEqual(model["sensor_id"], "historical_sensor")
        self.assertEqual(model["points"][0]["distance_cm"], 12)
        self.pump_for(0.2)
        self.assertEqual(self.app.worker.path, live_path)
        self.assertEqual((live_path / "summary.csv").read_bytes(), original_summary)
        self.assertEqual((live_path / "calibration.json").read_bytes(), original_calibration)


if __name__ == "__main__":
    unittest.main()
