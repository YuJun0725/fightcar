"""台下低速转动测试。停车复核距离和，并记录车尾光电。"""

import argparse
from bisect import bisect_left
from collections import deque
from contextlib import contextmanager
from datetime import datetime
import json
import math
from pathlib import Path
import signal
from statistics import median
import time
from typing import NamedTuple, Optional

from fightcar.control.drive import drive_output
from fightcar.models import WheelCommand


PERIOD_S = 0.02
CONFIRM_FRAMES = 3
SETTLE_S = 0.30
MAX_READ_S = 0.50
SURVEY_S = 3.0
CURVE_WINDOW = 5
MAX_SPIN_SPEED = 512
STOP = WheelCommand()


def number(value, label, lower, upper):
    if (type(value) not in (int, float) or not math.isfinite(value)
            or not lower <= value <= upper):
        raise ValueError(f"{label} 必须在 {lower}～{upper} 之间")
    return value


def limits(values, label, lower, upper):
    if not isinstance(values, (list, tuple)) or len(values) != 2:
        raise ValueError(f"{label} 需要最小值和最大值")
    lo, hi = [number(v, label, lower, upper) for v in values]
    if lo >= hi:
        raise ValueError(f"{label} 的最大值必须大于最小值")
    return lo, hi


def piecewise(points):
    xs, ys = zip(*points)

    def interpolate(x):
        if not xs[0] <= x <= xs[-1]:
            return None
        i = bisect_left(xs, x)
        if x == xs[i]:
            return ys[i]
        return ys[i - 1] + (ys[i] - ys[i - 1]) * (x - xs[i - 1]) / (xs[i] - xs[i - 1])

    return interpolate


def converter(calibration, label):
    if calibration is None:
        return None
    if not isinstance(calibration, dict):
        raise ValueError(f"{label} 需要填写标定对象")
    if "points" in calibration:
        points = calibration["points"]  # [ADC, 实测厘米]
        if not isinstance(points, list) or len(points) < 3:
            raise ValueError(f"{label} 至少需要 3 个标定点")
        pairs = sorted((number(x, label + " ADC", 1, 65535),
                        number(y, label + " cm", 0.1, 500)) for x, y in points)
        xs, ys = zip(*pairs)
        if not all(a < b for a, b in zip(xs, xs[1:])):
            raise ValueError(f"{label} 的 ADC 点不能重复")
        if not (all(a < b for a, b in zip(ys, ys[1:])) or all(a > b for a, b in zip(ys, ys[1:]))):
            raise ValueError(f"{label} 的标定点须在同一单调区间")

        return piecewise(pairs)
    a = number(calibration["a"], label + ".a", 0.01, 10**8)
    b = number(calibration["b"], label + ".b", -500, 500)
    lo, hi = limits(calibration["adc_range"], label + ".adc_range", 1, 65535)
    for adc in (lo, hi):
        number(a / adc + b, label + " cm", 0.1, 500)
    return lambda adc: a / adc + b if lo <= adc <= hi else None


def load(path):
    config = json.loads(path.read_text(encoding="utf-8-sig"))
    for key, lo, hi in (("front_adc", 0, 9), ("rear_adc", 0, 9), ("rear_photo_io", 0, 7),
                        ("spin_speed", 1, MAX_SPIN_SPEED)):
        if type(config[key]) is not int:
            raise ValueError(f"{key} 必须为整数")
        number(config[key], key, lo, hi)
    if config["front_adc"] == config["rear_adc"]:
        raise ValueError("前后测距须使用不同 ADC")
    drive = config["drive"]
    ids = (drive["left_id"], drive["right_id"])
    if ids[0] == ids[1] or any(type(i) is not int or not 1 <= i <= 253 for i in ids):
        raise ValueError("左右驱动器 ID 须不同且在 1～253 之间")
    if type(drive["reverse"]) is not bool:
        raise ValueError("drive.reverse 必须是 true 或 false")
    number(drive["refresh_s"], "drive.refresh_s", 0.05, 1)
    number(config["timeout_s"], "timeout_s", 2, 60)
    number(config["reference_tolerance_cm"], "reference_tolerance_cm", 0.1, 20)
    return config


class CurveReading(NamedTuple):
    total: Optional[float]
    reference: Optional[float]
    difference: Optional[float]
    photo_level: int


class RearAlignmentCurve:
    """比较当前距离和与同前距下的正对参考，曲线范围外不判命中。"""

    def __init__(self, config):
        if not isinstance(config, dict):
            raise ValueError("请配置 rear_alignment_curve")
        points = config["points"]
        if not isinstance(points, list) or len(points) < 3:
            raise ValueError("正对参考曲线至少需要 3 个点")
        pairs = [(number(x, "曲线前距", 0.1, 500), number(y, "曲线距离和", 0.1, 1000))
                 for x, y in points]
        if not all(x < y for x, y in pairs) or not all(
                a[0] < b[0] and a[1] <= b[1] for a, b in zip(pairs, pairs[1:])):
            raise ValueError("曲线须按前距严格递增排列，距离和须不减且大于前距")
        self.reference = piecewise(pairs)
        self.tolerance = number(config["tolerance_cm"], "曲线容差 cm", 0.1, 20)
        frames = config["confirm_frames"]
        if type(frames) is not int:
            raise ValueError("曲线确认帧数须为整数")
        self.confirm_frames = number(frames, "曲线确认帧数", 1, 50)
        self.front = deque(maxlen=CURVE_WINDOW)
        self.rear = deque(maxlen=CURVE_WINDOW)

    def read(self, front_cm, rear_cm, level):
        if front_cm is None or rear_cm is None:
            self.front.clear()
            self.rear.clear()
            return CurveReading(None, None, None, level)
        self.front.append(front_cm)
        self.rear.append(rear_cm)
        if len(self.front) < CURVE_WINDOW:
            return CurveReading(None, None, None, level)
        front_cm, rear_cm = median(self.front), median(self.rear)
        total, expected = front_cm + rear_cm, self.reference(front_cm)
        return CurveReading(total, expected, None if expected is None else total - expected, level)


def within(total, band):
    return total is not None and band[0] <= total <= band[1]


def spin_until_aligned(read, apply, band, speed, timeout,
                       clock=time.monotonic, sleep=time.sleep, *, curve=None):
    """固定距离范围或曲线偏差范围。apply 返回当前指令是否已发送完。"""
    spin = WheelCommand(-speed, speed)
    confirm_frames = curve.confirm_frames if curve else CONFIRM_FRAMES
    startup_s = CURVE_WINDOW * PERIOD_S if curve else 0.0
    started = clock()
    in_band = count = 0
    settled_at = None
    stopping = False
    while clock() - started < timeout:
        cycle = clock()
        observation = read()
        value = observation.difference if curve else observation[0]
        now = clock()
        if now - cycle > MAX_READ_S:
            raise TimeoutError(f"单次采样过慢：{now - cycle:.3f} 秒，上限 {MAX_READ_S:g} 秒")
        if now - started >= timeout:
            break
        if not stopping:
            in_band = in_band + 1 if within(value, band) else 0
            stopping = in_band >= confirm_frames
        if not stopping:
            if curve and (in_band or now - started < startup_s):
                apply(STOP)
            else:
                apply(spin)
        elif apply(STOP):
            if settled_at is None:
                settled_at = now
            elif now - settled_at >= SETTLE_S:
                if not within(value, band):
                    stopping = False
                    in_band = count = 0
                    settled_at = None
                else:
                    count += 1
                    if count >= confirm_frames:
                        return observation
        sleep(max(0, PERIOD_S - (clock() - cycle)))
    raise TimeoutError(f"摆正搜索达到 {timeout:g} 秒，未通过停稳复核")


@contextmanager
def sensor_inputs(up, config):
    try:
        status = up.ADC_IO_Open()
        if isinstance(status, int) and status < 0:
            raise OSError("打开 ADC/IO 失败")
        up.ADC_IO_SetIOMode(config["rear_photo_io"], 0)

        def read_raw():
            adc = up.ADC_Get_All_Channel()
            a, b = adc[config["front_adc"]], adc[config["rear_adc"]]
            level = up.ADC_IO_GetInputLevel(config["rear_photo_io"])
            if any(type(v) is not int or not 0 <= v <= 65535 for v in (a, b)) or level not in (0, 1):
                raise ValueError("ADC 或 IO 数据无效")
            return a, b, level

        yield read_raw
    finally:
        up.ADC_IO_Close()


def sensor_reader(read_raw, front, rear, photo_channel, curve=None):
    next_log = 0.0

    def text(value):
        return "未换算" if value is None else f"{value:.1f}"

    def read():
        nonlocal next_log
        front_adc, rear_adc, level = read_raw()
        forward = front(front_adc) if front else None
        backward = rear(rear_adc) if rear else None
        total = None if forward is None or backward is None else forward + backward
        reading = curve.read(forward, backward, level) if curve else (total, level)
        now = time.monotonic()
        if now >= next_log:
            line = (f"前 ADC={front_adc:4} {text(forward)} cm  后 ADC={rear_adc:4} {text(backward)} cm  "
                    f"距离和={text(total)} cm  IO {photo_channel}={level}")
            if curve:
                error = reading.difference
                verdict = ("参考范围外或采样尚不足" if error is None else
                           "本帧符合" if abs(error) <= curve.tolerance else "本帧不符")
                line += (f"  中值和={text(reading.total)} cm  参考={text(reading.reference)} cm"
                         f"  偏差={text(error)} cm  {verdict}")
            print(line, flush=True)
            next_log = now + 0.25
        return reading

    return read


def distance_summary(samples, key):
    values = [sample[key] for sample in samples if sample[key] is not None]
    if not values:
        return {"valid": 0, "median_cm": None, "min_cm": None, "max_cm": None}
    return {"valid": len(values), "median_cm": median(values),
            "min_cm": min(values), "max_cm": max(values)}


def survey_samples(read_raw, front, rear, clock=time.monotonic, sleep=time.sleep):
    started = clock()
    samples = []
    while clock() - started < SURVEY_S:
        cycle = clock()
        front_adc, rear_adc, level = read_raw()
        ended = clock()
        if ended - cycle > MAX_READ_S:
            raise TimeoutError("静止采样过慢，请重测本组")
        front_cm, rear_cm = front(front_adc), rear(rear_adc)
        total = None if front_cm is None or rear_cm is None else front_cm + rear_cm
        samples.append({"elapsed_s": ended - started, "front_adc": front_adc, "rear_adc": rear_adc,
                        "rear_photo_level": level, "front_cm": front_cm, "rear_cm": rear_cm,
                        "sum_cm": total})
        sleep(max(0, PERIOD_S - (clock() - cycle)))
    return samples


def survey(up, config, front, rear, log=None):
    if log is None:
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        log = Path("measurements") / "alignment" / f"rear_step_survey_{stamp}.jsonl"
    group = 0
    if log.exists():
        with log.open(encoding="utf-8") as previous:
            for line in previous:
                item = json.loads(line)
                if item.get("scene") != "rear_facing_step" or item.get("group") != group + 1:
                    raise ValueError("原文件不是连续的车尾对台测量记录")
                group += 1
    print("车尾正对台阶 · 只读测量 · 每组 3 秒")
    print(f"记录文件：{log.resolve()}", flush=True)
    while True:
        answer = input("停稳后输入尺量后距，可再填前距（厘米，用空格分隔；q 结束）> ").strip()
        if answer.lower() == "q":
            return 0
        fields = answer.replace(",", " ").replace("，", " ").split()
        try:
            if len(fields) not in (1, 2):
                raise ValueError("需要后距，可选填前距")
            measured = number(float(fields[0]), "尺量后距 cm", 0, 500)
            front_tape = number(float(fields[1]), "尺量前距 cm", 0, 500) if len(fields) == 2 else None
        except ValueError:
            print("请输入 0～500 之间的厘米数，如 31 或 31 25。")
            continue
        measured_at = datetime.now().astimezone().isoformat(timespec="seconds")
        print("采样中，保持小车静止……", flush=True)
        with sensor_inputs(up, config) as read_raw:
            samples = survey_samples(read_raw, front, rear)
        group += 1
        record = {
            "schema_version": 1, "group": group, "scene": "rear_facing_step",
            "measured_at": measured_at, "rear_tape_cm": measured,
            "front_tape_cm": front_tape,
            "sum_tape_cm": None if front_tape is None else front_tape + measured,
            "front_adc_channel": config["front_adc"], "rear_adc_channel": config["rear_adc"],
            "rear_photo_io": config["rear_photo_io"], "sample_count": len(samples),
            "front_calibration": config["front_calibration"],
            "rear_calibration": config["rear_calibration"],
            "summary": {key: distance_summary(samples, key) for key in ("front_cm", "rear_cm", "sum_cm")},
            "samples": samples,
        }
        log.parent.mkdir(parents=True, exist_ok=True)
        with log.open("a", encoding="utf-8") as output:
            output.write(json.dumps(record, ensure_ascii=False, allow_nan=False) + "\n")
        print(f"第 {group} 组已保存 · 尺量后距 {measured:g} cm · 共 {len(samples)} 帧", flush=True)
        if front_tape is not None:
            print(f"尺量前距 {front_tape:g} cm，尺量和 {record['sum_tape_cm']:g} cm")
        for title, key in (("前距", "front_cm"), ("后距", "rear_cm"), ("逐帧距离和", "sum_cm")):
            sm = record["summary"][key]
            if not sm["valid"]:
                print(f"{title}：无有效换算")
            else:
                print(f"{title}：中位数 {sm['median_cm']:.1f} cm，"
                      f"范围 {sm['min_cm']:.1f}～{sm['max_cm']:.1f} cm，"
                      f"有效 {sm['valid']}/{len(samples)} 帧")


def teach(read, tolerance):
    input("手动把车在台下摆正，保持静止，按回车测参考距离和：")
    measured = []
    for _ in range(25):
        started = time.monotonic()
        total, _ = read()
        if time.monotonic() - started > MAX_READ_S:
            raise TimeoutError("参考采样过慢")
        if total is not None:
            measured.append(total)
        time.sleep(PERIOD_S)
    if len(measured) < 20:
        raise ValueError("参考位置的前后测距超出标定范围，请检查现场位置和曲线")
    result = median(measured)
    if max(measured) - min(measured) > 2 * tolerance:
        raise ValueError("参考距离和不稳定，请保持车静止后重测")
    band = result - tolerance, result + tolerance
    print(f"参考 {result:.1f} cm，允许范围 {band[0]:.1f}～{band[1]:.1f} cm")
    input("把车手动转成斜对台阶并留足原地旋转空间，按回车开始低速摆正：")
    return band


def report(result, photo_channel):
    total, level = result
    print(f"停止转动 · 距离和在参考范围内：{total:.1f} cm · IO {photo_channel}={level} · 朝向请现场确认")


def report_curve(result, photo_channel):
    print(f"已停稳 · 符合车尾正对参考 · 中值和 {result.total:.1f} cm · 参考 {result.reference:.1f} cm"
          f" · 偏差 {result.difference:+.1f} cm · IO {photo_channel}={result.photo_level} · 请核对朝向")


def interrupt(unused_signum, unused_frame):
    raise KeyboardInterrupt


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=Path("config/align_test.json"))
    parser.add_argument("--hardware", action="store_true", help="打开实车 ADC/IO；扫描模式会转动")
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument("--measure", action="store_true", help="静止显示传感器，按 Ctrl+C 退出")
    modes.add_argument("--survey", action="store_true", help="按尺量后距逐组采样，保存每组的距离和")
    modes.add_argument("--teach", action="store_true", help="先手动摆正采参考范围，再放斜启动")
    modes.add_argument("--sum-range", type=float, nargs=2, metavar=("MIN_CM", "MAX_CM"))
    parser.add_argument("--survey-log", type=Path, help="续写已有的多点静止测量记录")
    parser.add_argument("--curve", action="store_true", help="用实测曲线判断车尾对台；可与 --measure 同用")
    parser.add_argument("--speed", type=int, help="原地旋转控制值，覆盖配置")
    args = parser.parse_args()
    if args.survey_log is not None and not args.survey:
        parser.error("--survey-log 需要与 --survey 同用")
    if args.curve and (args.survey or args.teach or args.sum_range is not None):
        parser.error("--curve 可与 --measure 同用，需单独于 --survey、--teach、--sum-range 运行")
    try:
        config = load(args.config)
        curve = RearAlignmentCurve(config.get("rear_alignment_curve")) if args.curve else None
        speed = (config["spin_speed"] if args.speed is None
                 else number(args.speed, "--speed", 1, MAX_SPIN_SPEED))
        photo_channel = config["rear_photo_io"]
        band = (-curve.tolerance, curve.tolerance) if curve else args.sum_range or config["sum_range_cm"]
        if band is not None and not curve:
            band = limits(band, "前后距离和", 0.1, 1000)
        if not args.hardware:
            if args.measure or args.survey or args.teach:
                parser.error("--measure、--survey 和 --teach 需要 --hardware")
            print("模拟输入")
            if curve:
                demo_front = config["rear_alignment_curve"]["points"][1][0]
                demo_rear = curve.reference(demo_front) - demo_front
                offsets = iter([curve.tolerance + 4] * 12)
                result = spin_until_aligned(
                    lambda: curve.read(demo_front, demo_rear + next(offsets, 0), 1),
                    lambda _: True, band, speed, config["timeout_s"], curve=curve)
                report_curve(result, photo_channel)
            else:
                band = band or (40.0, 46.0)
                middle = sum(band) / 2
                samples = iter([None] * 2 + [band[1] + 10] * 6)
                result = spin_until_aligned(lambda: (next(samples, middle), 1), lambda _: True,
                                            band, speed, config["timeout_s"])
                report(result, photo_channel)
            return 0
        front = converter(config["front_calibration"], "前测距")
        rear = converter(config["rear_calibration"], "后测距")
        if (curve or not args.measure) and (front is None or rear is None):
            parser.error("测量厘米数前须配置前后两只探头的标定，可用 --hardware --measure 看原始值")
        if not (args.measure or args.survey or args.teach) and band is None:
            parser.error("请填写 sum_range_cm，或指定 --sum-range / --teach")
        from uptech import UpTech

        for sig in (signal.SIGTERM, signal.SIGHUP):
            signal.signal(sig, interrupt)
        up = UpTech()
        if args.survey:
            return survey(up, config, front, rear, args.survey_log)
        with sensor_inputs(up, config) as read_raw:
            read = sensor_reader(read_raw, front, rear, photo_channel, curve)
            if args.measure:
                while True:
                    read()
                    time.sleep(PERIOD_S)
            if args.teach:
                band = teach(read, config["reference_tolerance_cm"])
            print(f"开始逆时针搜索参考距离和，轮速控制值 {speed}，Ctrl+C 退出", flush=True)
            with drive_output(up, config) as apply:
                result = spin_until_aligned(read, apply, band, speed, config["timeout_s"], curve=curve)
            if curve:
                report_curve(result, photo_channel)
            else:
                report(result, photo_channel)
        return 0
    except KeyboardInterrupt:
        print("已中断")
        return 130
    except (OSError, ValueError, KeyError, TypeError, IndexError, RuntimeError, ImportError, EOFError) as error:
        print(f"摆正测试结束 · {error}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
