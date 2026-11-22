"""防掉台专项：低速前进或倒车，触边时锁存停车。"""

import argparse
from contextlib import contextmanager
import json
import math
from pathlib import Path
import signal
import sys
import time

from fightcar.control.drive import drive_output
from fightcar.models import WheelCommand


PERIOD_S = 0.02
MAX_SAMPLE_S = 0.20
STOP_TIMEOUT_S = 1.0
STOP = WheelCommand()


class SensorReadError(RuntimeError):
    """读数无法用于判断台面。"""


def load(path, *, speed_override=None, backward=False):
    cfg = json.loads(path.read_text(encoding="utf-8-sig"))
    if speed_override is not None:
        cfg["speed"] = speed_override
    for key, lo, hi in (("speed", 1, 512), ("front_adc", 0, 9), ("rear_adc", 0, 9),
                        ("edge_threshold", 0, 65534), ("arm_threshold", 1, 65535)):
        if type(cfg[key]) is not int or not lo <= cfg[key] <= hi:
            raise ValueError(f"{key} 须为 {lo}～{hi} 的整数")
    if cfg["front_adc"] == cfg["rear_adc"]:
        raise ValueError("前后灰度通道须不同")
    if cfg["edge_threshold"] >= cfg["arm_threshold"]:
        raise ValueError("触边阈值须低于起步阈值")
    drive = cfg["drive"]
    ids = (drive["left_id"], drive["right_id"])
    if ids[0] == ids[1] or any(type(i) is not int or not 1 <= i <= 253 for i in ids):
        raise ValueError("左右驱动器 ID 须为不同的 1～253 整数")
    if type(drive["reverse"]) is not bool:
        raise ValueError("drive.reverse 须为 true 或 false")
    for value, label, low, high in ((drive["refresh_s"], "drive.refresh_s", 0.05, 1),
                                    (cfg["arm_confirm_s"], "arm_confirm_s", 0.05, 3)):
        if type(value) not in (int, float) or not math.isfinite(value) or not low <= value <= high:
            raise ValueError(f"{label} 须在 {low}～{high} 秒之间")
    if backward:
        photo = cfg.get("rear_photo")
        if not isinstance(photo, dict):
            raise ValueError("倒车模式需要配置 rear_photo")
        left, right = photo.get("left_io"), photo.get("right_io")
        if any(type(channel) is not int or not 0 <= channel <= 7 for channel in (left, right)) or left == right:
            raise ValueError("左后和右后光电须使用不同的 IO 0～7")
        active = photo.get("active_level")
        if type(active) is not int or active not in (0, 1):
            raise ValueError("后光电触边电平须为 0 或 1")
    return cfg


@contextmanager
def gray_inputs(up, cfg):
    try:
        status = up.ADC_IO_Open()
        if isinstance(status, int) and status < 0:
            raise OSError("打开 ADC 失败")

        def read():
            adc = up.ADC_Get_All_Channel()
            return adc[cfg["front_adc"]], adc[cfg["rear_adc"]]

        yield read
    finally:
        up.ADC_IO_Close()


def rear_photo_input(up, photo):
    left, right = photo["left_io"], photo["right_io"]
    for channel in (left, right):
        status = up.ADC_IO_SetIOMode(channel, 0)
        if isinstance(status, int) and status < 0:
            raise OSError(f"设置 IO{channel} 输入失败")

    def read():
        return up.ADC_IO_GetInputLevel(left), up.ADC_IO_GetInputLevel(right)

    return read


def sample_pair(read, clock, label, maximum):
    started = clock()
    try:
        first, second = read()
    except Exception as error:
        raise SensorReadError(f"{label}读取失败：{error}") from error
    if any(type(value) is not int or not 0 <= value <= maximum for value in (first, second)):
        raise SensorReadError(f"{label}数据无效")
    elapsed = clock() - started
    if elapsed > MAX_SAMPLE_S:
        raise SensorReadError(f"{label}采样耗时 {elapsed:.3f} 秒，超过 {MAX_SAMPLE_S:g} 秒")
    return first, second


def arm_on_platform(read, cfg, clock, sleep, check_rear=None):
    started = clock()
    while True:
        cycle = clock()
        front, rear = sample_pair(read, clock, "灰度 ADC", 65535)
        if min(front, rear) < cfg["arm_threshold"]:
            raise SensorReadError(f"起步需两路灰度都达到 {cfg['arm_threshold']}，当前前 {front}、后 {rear}")
        if check_rear is not None:
            reason = check_rear()
            if reason is not None:
                raise SensorReadError(f"无法倒车起步 · {reason}")
        if clock() - started >= cfg["arm_confirm_s"]:
            return
        sleep(max(0, PERIOD_S - (clock() - cycle)))


def stop_and_drain(apply, clock, sleep):
    deadline = clock() + STOP_TIMEOUT_S
    while not apply(STOP):
        if clock() >= deadline:
            raise TimeoutError("停车指令未能在时限内发完")
        sleep(PERIOD_S)


def drive_until_stop(read, apply, cfg, *, read_photo=None, clock=time.monotonic, sleep=time.sleep, log=print):
    """每次人工授权只行驶一趟，返回前完成停车发送。"""
    speed = cfg["speed"]
    if read_photo is None:
        def check_edge():
            front, _ = sample_pair(read, clock, "灰度 ADC", 65535)
            return f"前灰度 {front} 触边" if front <= cfg["edge_threshold"] else None

        description = f"开始直行 · 控制值 {speed} · 前 ADC{cfg['front_adc']} ≤ {cfg['edge_threshold']} 触边停车"
        check_rear = None
    else:
        photo = cfg["rear_photo"]
        left_io, right_io = photo["left_io"], photo["right_io"]
        active = photo["active_level"]

        def check_edge():
            left, right = sample_pair(read_photo, clock, "后光电 IO", 1)
            hits = [f"{side} IO{channel}={level}" for side, channel, level in
                    (("左后", left_io, left), ("右后", right_io, right)) if level == active]
            return f"{'、'.join(hits)} 触边" if hits else None

        description = f"开始倒车 · 控制值 {speed} · 后光电 IO{left_io}/IO{right_io} 任一路={active} 停车"
        speed = -speed
        check_rear = check_edge

    wheels = WheelCommand(speed, speed)
    try:
        arm_on_platform(read, cfg, clock, sleep, check_rear)
        log(description)
        while True:
            cycle = clock()
            reason = check_edge()
            if reason is not None:
                return reason
            apply(wheels)
            sleep(max(0, PERIOD_S - (clock() - cycle)))
    except SensorReadError as error:
        return str(error)
    finally:
        stop_and_drain(apply, clock, sleep)


def clear_pending_keys():
    if sys.stdin.isatty():
        import termios
        termios.tcflush(sys.stdin.fileno(), termios.TCIFLUSH)


def run_hardware(up, cfg, measure=False, *, backward=False):
    with gray_inputs(up, cfg) as read:
        photo = cfg["rear_photo"] if backward else None
        read_photo = rear_photo_input(up, photo) if photo is not None else None
        if measure:
            while True:
                front, rear = sample_pair(read, time.monotonic, "灰度 ADC", 65535)
                line = f"前 ADC{cfg['front_adc']}={front}  后 ADC{cfg['rear_adc']}={rear}"
                if read_photo is not None:
                    left, right = sample_pair(read_photo, time.monotonic, "后光电 IO", 1)
                    line += f"  左后 IO{photo['left_io']}={left}  右后 IO{photo['right_io']}={right}"
                print(line, flush=True)
                time.sleep(0.25)

        with drive_output(up, cfg) as apply:
            reset = ""
            while True:
                prompt = ("将车放在台面安全位置，停稳后按回车起步；输入 q 退出 > " if not reset else
                          "放回台面安全位置，输入 r 回车手动复位；输入 q 退出 > ")
                answer = input(prompt).strip().lower()
                if answer == "q":
                    return
                if answer != reset:
                    continue
                reason = drive_until_stop(read, apply, cfg, read_photo=read_photo,
                                          log=lambda line: print(line, flush=True))
                clear_pending_keys()
                print(f"停车指令已发完 · {reason} · 已锁存", flush=True)
                reset = "r"


def simulate(cfg, *, backward=False):
    edge_at = time.monotonic() + cfg["arm_confirm_s"] + 0.4

    def read_gray():
        front = cfg["edge_threshold"] if time.monotonic() >= edge_at else cfg["arm_threshold"]
        return front, cfg["arm_threshold"]

    def read_photo():
        active = cfg["rear_photo"]["active_level"]
        safe = 1 - active
        return (active if time.monotonic() >= edge_at else safe), safe

    print("模拟输入")
    reason = drive_until_stop(read_gray, lambda _: True, cfg, read_photo=read_photo if backward else None)
    print(f"停车指令已发完 · {reason} · 已锁存，等待人工复位")


def interrupt(unused_signum, unused_frame):
    raise KeyboardInterrupt


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=Path("config/edge_stop.json"))
    parser.add_argument("--hardware", action="store_true", help="使用实车传感器和底盘")
    parser.add_argument("--speed", type=int, help="直行控制值（1～512），覆盖本次运行的配置")
    parser.add_argument("--reverse", dest="backward", action="store_true", help="倒车，使用左右后光电触边停车")
    parser.add_argument("--measure", action="store_true", help="只读传感器，倒车模式加读两只后光电")
    args = parser.parse_args()
    if args.measure and not args.hardware:
        parser.error("--measure 需要 --hardware")
    try:
        cfg = load(args.config, speed_override=args.speed, backward=args.backward)
        if not args.hardware:
            simulate(cfg, backward=args.backward)
        else:
            from uptech import UpTech
            for sig in (signal.SIGTERM, signal.SIGHUP):
                signal.signal(sig, interrupt)
            run_hardware(UpTech(), cfg, args.measure, backward=args.backward)
        return 0
    except (KeyboardInterrupt, EOFError):
        print("已退出")
        return 130
    except (OSError, RuntimeError, ValueError, TypeError, KeyError, ImportError) as error:
        print(f"防掉台测试结束 · {error}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
