"""记录运动目标轮速和底盘 SDK 调用。"""

from collections import Counter
from datetime import datetime
import logging
from pathlib import Path
import sys
import time


class MotionLog:
    def __init__(self, name, label):
        self.logger = logging.Logger(f"fightcar.{name}", logging.DEBUG)
        formatter = logging.Formatter("%(asctime)s.%(msecs)03d %(message)s", datefmt="%H:%M:%S")
        console = logging.StreamHandler(sys.stdout)
        console.setLevel(logging.INFO)
        console.setFormatter(formatter)
        self.logger.addHandler(console)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        path = Path("measurements") / name / f"{name}_{stamp}.log"
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            file = logging.FileHandler(path, mode="x", encoding="utf-8")
        except OSError as error:
            self.logger.warning("无法写入%s日志文件 · %s", label, error)
        else:
            file.setFormatter(formatter)
            self.logger.addHandler(file)
            self.logger.info("%s日志 · %s", label, path.resolve())

    def close(self):
        for handler in self.logger.handlers[:]:
            self.logger.removeHandler(handler)
            handler.close()


class MotorTrace:
    """统计厂商接口已返回的调用，供现场区分轮速请求和 SDK 调用。"""

    def __init__(self, up, drive, logger, *, clock=time.monotonic):
        self.up, self.logger, self.clock = up, logger, clock
        self.ids = (drive["left_id"], drive["right_id"])
        self.last = {}
        self.counts = Counter()
        self.next_report = clock() + 1.0

    def _call(self, method, *args):
        self.logger.debug("调用 %s%r", method, args)
        started = self.clock()
        try:
            result = getattr(self.up, method)(*args)
        except Exception:
            self.logger.exception("%s%r 调用失败", method, args)
            raise
        self.logger.debug("返回 %s%r · %r · %.1f ms", method, args, result,
                          (self.clock() - started) * 1000)
        return result

    def CDS_Open(self):
        return self._call("CDS_Open")

    def CDS_Close(self):
        return self._call("CDS_Close")

    def CDS_SetMode(self, motor_id, mode):
        return self._call("CDS_SetMode", motor_id, mode)

    def CDS_SetSpeed(self, motor_id, speed):
        result = self._call("CDS_SetSpeed", motor_id, speed)
        self.last[motor_id] = speed, self.clock()
        self.counts[motor_id, speed != 0] += 1
        return result

    def wrap_apply(self, apply):
        def traced_apply(wheels):
            ready = apply(wheels)
            now = self.clock()
            if now >= self.next_report:
                details = []
                for motor_id in self.ids:
                    count, zeros = self.counts[motor_id, True], self.counts[motor_id, False]
                    if motor_id in self.last:
                        speed, stamp = self.last[motor_id]
                        last = f"最近 {speed:+d}（{now - stamp:.2f} 秒前）"
                    else:
                        last = "尚无返回"
                    details.append(f"ID{motor_id} 非零 {count} 次、零速 {zeros} 次，{last}")
                self.logger.info("轮速请求 左%+d 右%+d · SDK 调用返回 · %s",
                                 wheels.left, wheels.right, " | ".join(details))
                self.counts.clear()
                self.next_report = now + 1.0
            return ready

        return traced_apply
