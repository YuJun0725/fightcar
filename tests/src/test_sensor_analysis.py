"""传感器分析和持久化的离线测试，不加载真实硬件。"""

import csv
import json
import math
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src" / "desktop"))
import sensor_analysis as analysis


class AnalysisTests(unittest.TestCase):
    def setUp(self):
        self.points = [dict(distance_cm=10, adc_mean=3000),
                       dict(distance_cm=20, adc_mean=1800),
                       dict(distance_cm=30, adc_mean=1300)]

    def test_statistics_and_filter_gaps(self):
        stats = analysis.summarize([1, 2, 3])
        self.assertEqual(stats["count"], 3)
        self.assertEqual(stats["mean"], 2)
        self.assertEqual(stats["std"], 1)
        self.assertIsNone(analysis.summarize([1])["std"])
        self.assertIsNone(analysis.summarize([])["mean"])
        self.assertEqual(analysis.filter_values([1, 2, 3, None, 4, 5, 6], "mean", 3),
                         [None, None, 2, None, None, None, 5])
        self.assertEqual(analysis.filter_values([1, 100, 2, 3], "median", 3),
                         [None, None, 2, 3])
        self.assertEqual(analysis.filter_values([1, None, 2]), [1, None, 2])
        with self.assertRaises(ValueError):
            analysis.filter_values([1], "mean", 0)
        with self.assertRaises(ValueError):
            analysis.summarize([math.nan])

    def test_nonlinear_piecewise_calibration_and_validation(self):
        model = analysis.build_calibration(self.points, sensor_id="距离1", conditions={"color": "白"})
        self.assertEqual(analysis.estimate_distance(model, 3000), 10)
        self.assertEqual(analysis.estimate_distance(model, 1550), 25)
        self.assertIsNone(analysis.estimate_distance(model, 1000))
        self.assertIsNone(analysis.estimate_distance(model, 4000))
        result = analysis.validate_calibration(model, [dict(distance_cm=24, adc_mean=1550),
                                                       dict(distance_cm=12, adc_mean=2760),
                                                       dict(distance_cm=50, adc_mean=500)])
        self.assertEqual(result["rows"][0]["error_cm"], 1)
        self.assertAlmostEqual(result["mae"], 0.5)
        self.assertEqual(result["max_abs_error"], 1)
        self.assertFalse(result["rows"][2]["in_range"])
        self.assertEqual(json.loads(json.dumps(model))["sensor_id"], "距离1")

    def test_repeats_linear_and_ambiguous_calibration(self):
        model = analysis.build_calibration(self.points + [self.points[1]])
        self.assertEqual(model["points"][1]["repeats"], 2)
        linear = analysis.build_calibration([dict(distance_cm=d, adc_mean=4000 - d * 10)
                                              for d in (10, 20, 30)], method="linear")
        self.assertAlmostEqual(analysis.estimate_distance(linear, 3750), 25)
        self.assertIsNone(analysis.estimate_distance(linear, 100))
        for points in ([self.points[0], self.points[0], self.points[1]],
                       [self.points[0], self.points[1], dict(distance_cm=30, adc_mean=1800)],
                       [self.points[0], self.points[1], dict(distance_cm=30, adc_mean=2000)]):
            with self.assertRaises(ValueError):
                analysis.build_calibration(points)

    def test_photoelectric_static_boundary_intervals(self):
        points = [dict(phase="approach", distance_cm=d, io_values=[v] * 4)
                  for d, v in ((25, 1), (20, 1), (19, 0), (15, 0))]
        points += [dict(phase="release", distance_cm=d, io_values=[v] * 4)
                   for d, v in ((15, 0), (20, 0), (21, 1))]
        result = analysis.photoelectric_summary(points)
        self.assertEqual(result["trigger_distance_cm"], 19)
        self.assertEqual(result["release_distance_cm"], 21)
        self.assertEqual(result["hysteresis_cm"], 2)
        self.assertEqual(result["approach_interval_cm"], [19, 20])
        self.assertEqual(result["release_interval_cm"], [20, 21])
        self.assertEqual(result["reliable_interval_cm"], [15, 19])
        # 两个状态样本不足三帧，不伪造边界。
        result = analysis.photoelectric_summary([dict(phase="approach", distance_cm=10,
                                                       io_values=[0, 0])])
        self.assertIsNone(result["trigger_distance_cm"])

    def test_position_only_during_motion_and_no_negative(self):
        events = [dict(name="motion_start", t_ns=1_000_000_000,
                       data=dict(start_distance_cm=50, speed_cm_s=10, direction="approach")),
                  dict(name="motion_end", t_ns=3_000_000_000, data={})]
        self.assertIsNone(analysis.position_at(0, events)["distance_cm"])
        self.assertEqual(analysis.position_at(2_000_000_000, events),
                         dict(distance_cm=40, position_source="estimated"))
        self.assertEqual(analysis.position_at(3_000_000_000, events)["distance_cm"], 30)
        self.assertIsNone(analysis.position_at(3_000_000_001, events)["distance_cm"])
        self.assertIsNone(analysis.position_at(7_000_000_000, events[:1])["distance_cm"])

    def test_dynamic_edges_and_missing_baseline(self):
        events = [dict(name="motion_start", t_ns=0,
                       data=dict(start_distance_cm=50, speed_cm_s=10, direction="approach")),
                  dict(name="motion_end", t_ns=4_000_000_000, data={})]
        samples = [dict(seq=i, trial_id="T1", t_ns=i * 500_000_000,
                        io={"2": value}) for i, value in enumerate([1, 1, 1, 0, 0, 0, 0, 0])]
        baseline = dict(trigger_distance_cm=36, reliable_interval_cm=[15, 20])
        result = analysis.dynamic_photoelectric(samples, events, baseline, io_channel=2)
        self.assertEqual(result["miss_status"], "detected")
        self.assertEqual(result["trigger_distance_cm"], 35)
        self.assertEqual(result["trigger_difference_cm"], -1)
        self.assertEqual(result["confirmed_t_ns"], 2_500_000_000)
        self.assertEqual(result["raw_edge_count"], 1)
        inactive = [dict(s, io={"2": 1}) for s in samples]
        self.assertEqual(analysis.dynamic_photoelectric(inactive, events, io_channel=2)["miss_status"],
                         "undetermined")
        self.assertEqual(analysis.dynamic_photoelectric(inactive, events, baseline,
                                                        io_channel=2)["miss_status"], "missed")
        self.assertEqual(analysis.dynamic_photoelectric(inactive, [], baseline,
                                                        io_channel=2)["miss_status"], "undetermined")
        # 序号中断两侧的状态不能被拼成稳定边沿。
        samples[3]["seq"] = 9
        result = analysis.dynamic_photoelectric(samples, events, baseline, io_channel=2)
        self.assertEqual(result["miss_status"], "undetermined")

    def test_non_contiguous_detected_points_are_not_reliable_region(self):
        for middle_values in ([1, 1, 1], [0, 1]):
            points = [dict(phase="approach", distance_cm=40, io_values=[1] * 3),
                      dict(phase="approach", distance_cm=30, io_values=[0] * 3),
                      dict(phase="approach", distance_cm=25, io_values=middle_values),
                      dict(phase="approach", distance_cm=20, io_values=[0] * 3)]
            baseline = analysis.photoelectric_summary(points)
            self.assertIsNone(baseline["reliable_interval_cm"])
            events = [dict(name="motion_start", t_ns=0,
                           data=dict(start_distance_cm=25, speed_cm_s=0, direction="approach"))]
            samples = [dict(t_ns=i, seq=i, io_value=1) for i in range(4)]
            self.assertEqual(analysis.dynamic_photoelectric(samples, events, baseline)["miss_status"],
                             "undetermined")

    def test_dynamic_does_not_reuse_previous_trials_unclosed_motion(self):
        events = [dict(name="motion_start", trial_id="old", t_ns=0,
                       data=dict(start_distance_cm=30, speed_cm_s=5, direction="approach"))]
        samples = [dict(trial_id="new", seq=i, t_ns=i * 100_000_000, io_value=1)
                   for i in range(4)]
        baseline = dict(trigger_distance_cm=31, reliable_interval_cm=[20, 30])
        result = analysis.dynamic_photoelectric(samples, events, baseline)
        self.assertEqual(result["miss_status"], "undetermined")
        self.assertFalse(result["entered_reliable_region"])
        samples = [dict(sample, io_value=1 if i < 3 else 0) for i, sample in enumerate(
            [dict(trial_id="new", seq=i, t_ns=i * 100_000_000) for i in range(6)])]
        result = analysis.dynamic_photoelectric(samples, events, baseline)
        self.assertEqual(result["miss_status"], "detected")
        self.assertIsNone(result["trigger_distance_cm"])


class SessionTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)

    def packet(self, trial_id, seq=0):
        return dict(type="sample", trial_id=trial_id, seq=seq, t_start_ns=100 + seq * 10,
                    t_end_ns=105 + seq * 10, io={"0": 0, "7": 1},
                    adc={"0": 3245, "8": 5000}, simulated=True)

    def test_round_trip_snapshots_channels_events_and_summary_schema(self):
        metadata = dict(experiment_id="实验一", color="白")
        store = analysis.SessionStore(self.directory.name, "D1", metadata)
        self.addCleanup(store.close)
        trial_conditions = dict(distance_cm=25, primary="adc_0", experiment="D1")
        trial = store.start_trial(trial_conditions)
        trial_conditions["distance_cm"] = 999
        metadata["color"] = "黑"
        store.append_sample(self.packet(trial))
        store.append_event(dict(name="point", trial_id=trial, t_ns=100,
                                data=dict(distance_cm=25)))
        store.finish_trial()
        store.save_summary([dict(trial_id=trial, mean=3245),
                            dict(trial_id=trial, error_cm=0.5, conditions={"颜色": "白"})])
        store.save_calibration(analysis.build_calibration([
            dict(distance_cm=10, adc_mean=3000), dict(distance_cm=20, adc_mean=2000),
            dict(distance_cm=30, adc_mean=1500)]))
        store.close()
        restored = analysis.load_session(store.path)
        self.assertEqual(restored["metadata"]["metadata"]["color"], "白")
        saved_trial = restored["metadata"]["trials"][0]
        self.assertEqual(saved_trial["metadata"]["distance_cm"], 25)
        self.assertEqual(saved_trial["status"], "complete")
        self.assertEqual(saved_trial["sample_count"], 1)
        self.assertEqual(restored["samples"][0], self.packet(trial))
        self.assertEqual(restored["events"][0]["data"]["distance_cm"], 25)
        self.assertEqual(restored["summaries"][0]["mean"], 3245)
        self.assertIsNone(restored["summaries"][0]["error_cm"])
        self.assertEqual(restored["summaries"][1]["conditions"], {"颜色": "白"})
        self.assertIsNotNone(restored["calibration"])
        self.assertTrue((store.path / "samples.csv").read_bytes().startswith(b"\xef\xbb\xbf"))
        with (store.path / "samples.csv").open(encoding="utf-8-sig", newline="") as handle:
            fields = csv.DictReader(handle).fieldnames
        self.assertIn("adc_8", fields)
        self.assertIn("io_7", fields)
        self.assertEqual(restored["warnings"], [])

    def test_close_incomplete_and_reopen_crashed_record(self):
        store = analysis.SessionStore(self.directory.name, "P4", {})
        trial = store.start_trial(dict(phase="approach"))
        store.append_sample(self.packet(trial))
        store.flush()
        restored = analysis.load_session(store.path)
        self.assertEqual(restored["metadata"]["trials"][0]["status"], "incomplete")
        self.assertTrue(restored["warnings"])
        store.close()
        restored = analysis.SessionStore.load_session(store.path)
        self.assertEqual(restored["metadata"]["trials"][0]["status"], "incomplete")
        self.assertEqual(len(restored["samples"]), 1)
        with (store.path / "samples.csv").open("a", encoding="utf-8") as handle:
            handle.write("T0001,1,12")
        restored = analysis.load_session(store.path)
        self.assertEqual(len(restored["samples"]), 1)
        self.assertTrue(any("不完整" in warning for warning in restored["warnings"]))

    def test_io_failures_propagate_and_partial_record_survives(self):
        store = analysis.SessionStore(self.directory.name, "D1", {})
        self.addCleanup(store.close)
        trial = store.start_trial({})
        store.append_sample(self.packet(trial))
        with mock.patch.object(store._sample_writer, "writerow", side_effect=OSError("磁盘已满")):
            with self.assertRaisesRegex(OSError, "磁盘已满"):
                store.append_sample(self.packet(trial, 1))
        store.finish_trial("incomplete", "磁盘已满")
        store.close()
        restored = analysis.load_session(store.path)
        self.assertEqual(len(restored["samples"]), 1)
        self.assertEqual(restored["metadata"]["trials"][0]["reason"], "磁盘已满")

    def test_trial_mismatch_and_unique_directories(self):
        first = analysis.SessionStore(self.directory.name, "G1", {})
        second = analysis.SessionStore(self.directory.name, "G1", {})
        self.addCleanup(first.close)
        self.addCleanup(second.close)
        self.assertNotEqual(first.path, second.path)
        trial = first.start_trial({})
        with self.assertRaises(RuntimeError):
            first.start_trial({})
        with self.assertRaises(ValueError):
            first.append_sample(self.packet("WRONG"))
        first.finish_trial()
        next_trial = first.start_trial({})
        self.assertNotEqual(trial, next_trial)

    def test_reopen_detects_sample_sequence_gaps(self):
        store = analysis.SessionStore(self.directory.name, "D2", {})
        trial = store.start_trial({})
        store.append_sample(self.packet(trial, 1))
        store.append_sample(self.packet(trial, 3))
        store.finish_trial()
        store.close()
        restored = analysis.load_session(store.path)
        self.assertEqual(restored["metadata"]["trials"][0]["status"], "incomplete")
        self.assertTrue(any("序号不连续" in warning for warning in restored["warnings"]))

    def test_reopen_recovers_after_partial_utf8_character(self):
        store = analysis.SessionStore(self.directory.name, "P4", {})
        trial = store.start_trial({})
        store.append_sample(self.packet(trial))
        store.finish_trial()
        store.close()
        with (store.path / "samples.csv").open("ab") as handle:
            handle.write(b"T0001,2,200,205,1,\xe4\xb8")
        restored = analysis.load_session(store.path)
        self.assertEqual(len(restored["samples"]), 1)
        self.assertEqual(restored["metadata"]["trials"][0]["status"], "incomplete")
        self.assertTrue(any("UTF-8" in warning for warning in restored["warnings"]))


if __name__ == "__main__":
    unittest.main()
