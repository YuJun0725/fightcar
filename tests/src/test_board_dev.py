"""用临时目录执行远端脚本，检查同步边界；不连接板端。"""
import base64
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("board_dev", ROOT / "tools" / "board_dev.py")
board_dev = importlib.util.module_from_spec(spec)
spec.loader.exec_module(board_dev)


class DeploymentTests(unittest.TestCase):
    def remote(self, directory, command, files=None, target="sensor"):
        request = dict(remote_dir=str(directory), command=command, target=target)
        if files is not None:
            request["files"] = {name: base64.b64encode(value).decode("ascii")
                                for name, value in files.items()}
        result = subprocess.run([sys.executable, "-c", board_dev.REMOTE_SCRIPT],
                                input=json.dumps(request), text=True, encoding="utf-8",
                                capture_output=True, timeout=10)
        return result

    def result(self, process):
        self.assertEqual(process.returncode, 0, process.stderr)
        return json.loads(process.stdout.split("__BOARD_DEV_RESULT__", 1)[1])

    def test_sensor_preserves_vendor_and_backs_up_server(self):
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp)
            vendor = b"# board-specific vendor\n"
            previous = b"# old collector\n"
            (directory / "uptech.py").write_bytes(vendor)
            (directory / "sensor_server.py").write_bytes(previous)
            payload = {"sensor_server.py": b"# new collector\n", "uptech.py": b"# local vendor\n"}
            result = self.result(self.remote(directory, "deploy", payload))
            self.assertEqual((directory / "uptech.py").read_bytes(), vendor)
            self.assertEqual(result["preserved"], ["uptech.py"])
            self.assertEqual((Path(result["backup_dir"]) / "sensor_server.py").read_bytes(), previous)
            again = self.result(self.remote(directory, "deploy", payload))
            self.assertEqual(again["unchanged"], ["sensor_server.py"])

    def test_sensor_check_and_pull_exclude_motor_files(self):
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp)
            (directory / "sensor_server.py").write_text("# collector\n", encoding="utf-8")
            (directory / "motor_server.py").write_text("# motor\n", encoding="utf-8")
            result = self.result(self.remote(directory, "check"))
            self.assertEqual(result["files"], ["sensor_server.py"])
            pulled = self.result(self.remote(directory, "pull"))
            self.assertEqual(list(pulled["files"]), ["sensor_server.py"])

    def test_rejects_wrong_group_and_invalid_python_before_writes(self):
        for payload in ({"motor_server.py": b"pass\n"},
                        {"sensor_server.py": b"if broken syntax\n"}):
            with tempfile.TemporaryDirectory() as temp:
                result = self.remote(Path(temp) / "new", "deploy", payload)
                self.assertNotEqual(result.returncode, 0)
                self.assertFalse((Path(temp) / "new").exists())

    def test_default_target_still_motor(self):
        process = subprocess.run([sys.executable, str(ROOT / "tools/board_dev.py"),
                                  "deploy", "--dry-run"], text=True, encoding="utf-8",
                                 capture_output=True, timeout=10)
        self.assertEqual(process.returncode, 0, process.stderr)
        result = json.loads(process.stdout)
        self.assertEqual(result["source_group"], "motor")
        self.assertEqual(result["files"], list(board_dev.SOURCE_NAMES["motor"]))
        self.assertFalse(result["network_access"])


if __name__ == "__main__":
    unittest.main()
