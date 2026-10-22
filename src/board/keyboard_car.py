#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Ubuntu/SSH键盘控制：W/S前后，A/D原地旋转，J/L半径转弯，空格停，Q退出。"""

import argparse
import math
import signal
import time

VERSION = "3.1"
COMMAND_GAP = 0.05     # 总线指令间隔，避免两路连续发送过密
REFRESH_INTERVAL = 0.1
KEY_TIMEOUT = 0.6     # 终端没有松键事件，使用按键超时停车


def wheel_speeds(action, speed, spin_speed, width, radius):
    """直行/弧线使用speed，原地旋转单独使用spin_speed。"""
    inner = round(speed * (radius - width / 2) / (radius + width / 2))
    return {
        "w": (speed, speed), "s": (-speed, -speed),
        "a": (-spin_speed, spin_speed), "d": (spin_speed, -spin_speed),
        "j": (inner, speed), "l": (speed, inner),
    }.get(action, (0, 0))


def send(up, ids, wheels, reverse=False):
    """右电机安装方向相反，只在这里把右轮速度取反。"""
    sign = -1 if reverse else 1
    for motor_id, speed in zip(ids, (wheels[0], -wheels[1])):
        up.CDS_SetSpeed(motor_id, sign * speed)
        time.sleep(COMMAND_GAP)


def stop(up, ids):
    # 两路各停两次；某一路出错仍继续尝试另一路。
    for _ in range(2):
        for motor_id in ids:
            try:
                up.CDS_SetSpeed(motor_id, 0)
            except Exception as error:
                print(f"Stop ID {motor_id} failed: {error}")
            time.sleep(COMMAND_GAP)


def control(screen, up, args):
    import curses
    ids = (args.left_id, args.right_id)
    arrows = {curses.KEY_UP: "w", curses.KEY_DOWN: "s",
              curses.KEY_LEFT: "a", curses.KEY_RIGHT: "d"}
    screen.keypad(True)
    screen.timeout(20)
    action, previous = "", (0, 0)
    last_key, last_send = 0.0, float("-inf")

    while True:
        raw = screen.getch()
        key = arrows.get(raw, chr(raw).lower() if 0 <= raw < 256 else "")
        now = time.monotonic()
        if key in ("q", "\x03"):
            return
        if key and key in "wsadjl":
            action, last_key = key, now
        elif key == " ":
            action = ""
        elif key in ("+", "="):
            args.speed = min(1023, args.speed + 50)
        elif key == "-":
            args.speed = max(1, args.speed - 50)
        elif key == "r":
            args.spin_speed = min(1023, args.spin_speed + 50)
        elif key == "f":
            args.spin_speed = max(1, args.spin_speed - 50)
        elif key == "[":
            args.radius = max(0.01, round(args.radius - 0.1, 2))
        elif key == "]":
            args.radius = round(args.radius + 0.1, 2)
        if now - last_key >= KEY_TIMEOUT:
            action = ""

        wheels = wheel_speeds(action, args.speed, args.spin_speed, args.track_width, args.radius)
        if wheels != previous:
            if wheels == (0, 0) or any(a * b < 0 for a, b in zip(previous, wheels)):
                stop(up, ids)  # 停车或任一侧换向时，先让两侧停车
            previous, last_send = wheels, float("-inf")
        if wheels != (0, 0) and time.monotonic() - last_send >= REFRESH_INTERVAL:
            send(up, ids, wheels, args.reverse)
            last_send = time.monotonic()

        screen.erase()
        try:
            screen.addstr(0, 0,
                f"Keyboard car v{VERSION}\n"
                "Hold W/S: forward/back    A/D: spin left/right\n"
                "Hold J/L: arc left/right  SPACE: stop  Q: quit\n"
                "+/-: drive speed  R/F: spin speed +/-50  [ / ]: radius\n"
                f"Drive: {args.speed}  Spin: {args.spin_speed}\n"
                f"Track: {args.track_width:.3f} m  "
                f"Radius: {args.radius:.2f} m\n"
                f"Action: {action or 'STOP'}  Wheels L/R: {wheels}\n"
                "Release key: stop after about 0.6 s. Radius is an estimate.")
        except curses.error:
            pass  # 终端较小时允许部分文字显示不全
        screen.refresh()


def interrupt(signum, frame):
    raise KeyboardInterrupt


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--version", action="version", version="keyboard_car " + VERSION)
    parser.add_argument("--speed", type=int, default=200, help="前后/弧线速度1~1023，默认200")
    parser.add_argument("--spin-speed", type=int, default=150, help="原地旋转速度1~1023，默认150")
    parser.add_argument("--track-width", type=float, default=0.30, help="左右轮中心线距离，米；示例0.30")
    parser.add_argument("--radius", type=float, default=0.50, help="车身中心转弯半径，米；示例0.50")
    parser.add_argument("--left-id", type=int, default=1)
    parser.add_argument("--right-id", type=int, default=2)
    parser.add_argument("--reverse", action="store_true", help="反转电机安装方向映射")
    args = parser.parse_args()
    if not all(1 <= speed <= 1023 for speed in (args.speed, args.spin_speed)):
        parser.error("行驶速度和原地旋转速度必须在1~1023之间")
    if not all(math.isfinite(x) and x > 0 for x in (args.track_width, args.radius)):
        parser.error("轮距和半径必须是大于0的有限数值，单位为米")
    ids = (args.left_id, args.right_id)
    if args.left_id == args.right_id or not all(1 <= i <= 253 for i in ids):
        parser.error("左右驱动器ID须不同，且在1~253之间")

    import curses
    from uptech import UpTech
    for sig in (signal.SIGTERM, signal.SIGHUP):
        signal.signal(sig, interrupt)
    up = UpTech()
    try:
        up.CDS_Open()
        time.sleep(0.5)
        stop(up, ids)
        for motor_id in ids:
            up.CDS_SetMode(motor_id, 1)
            time.sleep(0.1)
        time.sleep(2.0)
        curses.wrapper(control, up, args)
    except KeyboardInterrupt:
        pass
    finally:
        try:
            stop(up, ids)
        finally:
            up.CDS_Close()


if __name__ == "__main__":
    main()
