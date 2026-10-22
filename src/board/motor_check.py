#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""分别测试已确认的底盘驱动器 ID 1 或 2；运行前架空四个车轮。"""

import argparse
import signal
import sys
import time


def stop_all(up):
    errors = []
    for motor_id in (1, 2):
        try:
            up.CDS_SetSpeed(motor_id, 0)
            time.sleep(0.02)
        except Exception as exc:
            errors.append("ID {}: {}".format(motor_id, exc))
    if errors:
        raise RuntimeError("停车发送失败：" + "; ".join(errors))


def test_driver(up, motor_id, speed, seconds):
    stop_all(up)
    up.CDS_SetMode(motor_id, 1)
    time.sleep(0.5)
    for value in (speed, -speed):
        print("向 ID {} 发送速度 {}，持续 {} 秒；观察哪几个轮子转。".format(
            motor_id, value, seconds), flush=True)
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            up.CDS_SetSpeed(motor_id, value)
            time.sleep(0.1)
        stop_all(up)
        time.sleep(0.5)


def interrupt(signum, frame):
    raise KeyboardInterrupt


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--id", type=int, required=True, choices=(1, 2), help="本次测试的驱动器ID")
    parser.add_argument("--speed", type=int, default=300, help="速度控制值，1~512，默认300")
    parser.add_argument("--seconds", type=float, default=1.0, help="每个方向持续时间，0.1~3秒")
    args = parser.parse_args()
    if not 1 <= args.speed <= 512:
        parser.error("测试速度必须为1~512")
    if not 0.1 <= args.seconds <= 3:
        parser.error("测试时间必须为0.1~3秒")
    if not sys.platform.startswith("linux"):
        print("请在小车的Ubuntu/Linux控制器上运行。", file=sys.stderr)
        return 1
    try:
        from uptech import UpTech
    except (ImportError, OSError) as exc:
        print("加载失败：{}；请检查同目录的uptech.py及控制器libuptech.so。".format(exc), file=sys.stderr)
        return 1

    for sig in (signal.SIGTERM, signal.SIGHUP):
        signal.signal(sig, interrupt)
    up = UpTech()
    result = 0
    try:
        up.CDS_Open()
        time.sleep(0.5)
        test_driver(up, args.id, args.speed, args.seconds)
    except KeyboardInterrupt:
        print("测试已中断。")
    except Exception as exc:
        print("测试异常：{}".format(exc), file=sys.stderr)
        result = 1
    finally:
        try:
            try:
                stop_all(up)
            finally:
                up.CDS_Close()
        except Exception as exc:
            print("退出清理异常：{}".format(exc), file=sys.stderr)
            result = 1
    print("测试结束；命令发送完成不代表驱动器已应答，请以轮子实际转动为准。")
    return result


if __name__ == "__main__":
    sys.exit(main())
