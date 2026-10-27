"""回归：停止确认不能掩盖本地写盘失败。无需窗口、网络或真实硬件。"""

from pathlib import Path
import json
import queue
import sys
import tempfile
import unittest
from unittest import mock


DESKTOP = Path(__file__).resolve().parents[2] / "src" / "desktop"
if str(DESKTOP) not in sys.path:
    sys.path.insert(0, str(DESKTOP))

from sensor_client import SensorWorker
from sensor_analysis import SessionStore


class FailingStore:
    """一次性故障允许清理代码重新写入不完整状态，模拟可恢复的写入错误。"""

    def __init__(self, failure=None):
        self.failure = failure
        self.failed = False
        self.metadata = {"status": "recording", "reason": ""}
        self.flush_count = 0

    def finish_trial(self, status="complete", reason=""):
        if self.failure == "finish" and not self.failed:
            self.failed = True
            raise OSError("模拟磁盘已满：结束试次失败")
        self.metadata.update(status=status, reason=reason)

    def flush(self):
        self.flush_count += 1
        if self.failure == "flush" and not self.failed:
            self.failed = True
            raise OSError("模拟磁盘已满：刷新记录失败")


def worker_without_thread(store):
    worker = SensorWorker.__new__(SensorWorker)
    worker.trial_id = "T0001"
    worker._reason = ""
    worker.path = Path("unused-regression-session")
    worker.store = store
    worker.events = queue.Queue()
    worker._deadline = None
    worker._start_wait = None
    return worker


def pending_events(worker):
    rows = []
    while True:
        try:
            rows.append(worker.events.get_nowait())
        except queue.Empty:
            return rows


class FinishPersistenceTests(unittest.TestCase):
    def test_real_metadata_file_does_not_claim_complete_after_flush_failure(self):
        with tempfile.TemporaryDirectory() as temporary:
            store = SessionStore(temporary, "D1", {"sensor_id": "regression"})
            trial_id = store.start_trial({"sensor_id": "regression"})
            worker = worker_without_thread(store)
            worker.trial_id = trial_id
            worker.path = store.path
            original_flush = store.flush
            failed = [False]

            def fail_first_flush():
                if not failed[0]:
                    failed[0] = True
                    raise OSError("模拟磁盘已满：刷新记录失败")
                return original_flush()

            try:
                with mock.patch.object(store, "flush", side_effect=fail_first_flush):
                    try:
                        worker._finish(True)
                    except OSError:
                        pass
                metadata = json.loads((store.path / "metadata.json").read_text(encoding="utf-8"))
                self.assertNotEqual(metadata["trials"][0]["status"], "complete",
                                    "磁盘故障后重新打开 metadata.json 不应看到完整状态")
                for kind, payload in pending_events(worker):
                    if kind == "finished":
                        self.assertFalse(payload["complete"])
                        self.assertIn("磁盘", payload["reason"])
            finally:
                store.close()

    def test_successful_persistence_can_report_complete(self):
        store = FailingStore()
        worker = worker_without_thread(store)
        worker._finish(True)
        finished = [payload for kind, payload in pending_events(worker) if kind == "finished"]
        self.assertEqual(len(finished), 1)
        self.assertTrue(finished[0]["complete"])
        self.assertEqual(finished[0]["reason"], "")
        self.assertEqual(store.metadata["status"], "complete")
        self.assertGreaterEqual(store.flush_count, 1)

    def test_finish_or_flush_failure_never_reports_or_leaves_complete(self):
        for failure in ("finish", "flush"):
            with self.subTest(failure=failure):
                store = FailingStore(failure)
                worker = worker_without_thread(store)
                caught = None
                try:
                    worker._finish(True)
                except OSError as error:
                    # 调用方可以统一处理异常，也可以在 _finish 内处理。
                    caught = error
                events = pending_events(worker)
                finished = [payload for kind, payload in events if kind == "finished"]
                for payload in finished:
                    self.assertFalse(payload["complete"], "写盘失败不能报告采集完整")
                    self.assertIn("磁盘", payload["reason"], "必须保留写盘故障原因")
                if not finished:
                    # 无 finished 时，异常或错误事件仍必须让故障可见。
                    messages = [str(payload) for kind, payload in events if kind == "error"]
                    self.assertTrue(caught is not None or messages, "写盘失败不可静默吞掉")
                self.assertNotEqual(store.metadata["status"], "complete",
                                    "记录元数据不能在写盘失败后保留 complete")
                if store.metadata["status"] == "incomplete":
                    self.assertIn("磁盘", store.metadata["reason"])

    def test_prior_capture_failure_is_not_erased_by_stop_confirmation(self):
        store = FailingStore()
        worker = worker_without_thread(store)
        worker._reason = "采样序号缺失：7 → 9"
        worker._finish(True)
        finished = [payload for kind, payload in pending_events(worker) if kind == "finished"]
        self.assertEqual(len(finished), 1)
        self.assertFalse(finished[0]["complete"])
        self.assertIn("序号缺失", finished[0]["reason"])
        self.assertEqual(store.metadata["status"], "incomplete")


if __name__ == "__main__":
    unittest.main()
