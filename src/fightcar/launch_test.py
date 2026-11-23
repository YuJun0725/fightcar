"""固定出发位上台试车。触发后全速直行 1.5 秒，然后停车退出。"""

import argparse
from contextlib import contextmanager, nullcontext
from pathlib import Path
import signal
import time

from fightcar.control.drive import drive_output
from fightcar.control.safety import MAX_WHEEL_SPEED
from fightcar.edge_stop import (
    MAX_SAMPLE_S, PERIOD_S, clear_pending_keys, interrupt, load as load_edge_config,
    sample_pair, stop_and_drain,
)
from fightcar.follow_log import MotionLog, MotorTrace
from fightcar.models import WheelCommand


START_CHANNELS = (3, 7)
BLOCKED_LEVELS = (0, 0)
HOLD_S = 1.0
RUN_S = 1.5
# 上台沿与全局逻辑前进相反的方向执行。
LAUNCH_WHEELS = WheelCommand(-MAX_WHEEL_SPEED, -MAX_WHEEL_SPEED)


@contextmanager
def start_inputs(up):
    status = up.ADC_IO_Open()
    if isinstance(status, int) and status < 0:
        raise OSError("打开起跑光电的 ADC/IO 接口失败")
    try:
        for channel in START_CHANNELS:
            status = up.ADC_IO_SetIOMode(channel, 0)
            if isinstance(status, int) and status < 0:
                raise OSError(f"设置 IO{channel} 为输入失败")

        def read():
            return tuple(up.ADC_IO_GetInputLevel(channel) for channel in START_CHANNELS)

        yield read
    finally:
        up.ADC_IO_Close()


def wait_for_trigger(read, *, clock=time.monotonic, sleep=time.sleep):
    covered_since = last_sample_at = None
    while True:
        cycle = clock()
        levels = sample_pair(read, clock, "起跑光电 IO3/IO7", 1)
        now = clock()
        if last_sample_at is not None and now - last_sample_at > MAX_SAMPLE_S:
            covered_since = None
        if levels != BLOCKED_LEVELS:
            covered_since = None
        elif covered_since is None:
            covered_since = now
        elif now - covered_since >= HOLD_S:
            return
        last_sample_at = now
        sleep(max(0, PERIOD_S - (clock() - cycle)))


def run_launch(apply, *, clock=time.monotonic, sleep=time.sleep):
    deadline = clock() + RUN_S
    try:
        while clock() < deadline:
            apply(LAUNCH_WHEELS)
            sleep(max(0, min(PERIOD_S, deadline - clock())))
    finally:
        stop_and_drain(apply, clock, sleep)


def wait_for_enter():
    clear_pending_keys()
    while True:
        answer = input("将起跑方向对准台阶并停稳后，按回车起步；输入 q 退出 > ")
        if answer.strip().lower() == "q":
            return False
        if answer == "":
            return True


def uart_counters():
    """在鲁班猫上读取厂商驱动使用的 ttyS0 内核收发计数。"""
    try:
        for line in Path("/proc/tty/driver/serial").read_text().splitlines():
            if line.lstrip().startswith("0:"):
                fields = dict(word.split(":", 1) for word in line.split() if word.startswith(("tx:", "rx:")))
                return int(fields["tx"]), int(fields["rx"])
    except (OSError, ValueError, KeyError):
        pass
    return None


def wait_and_launch(apply, read=None, *, log=print, track_uart=False):
    if read is not None:
        log(f"等待 IO3 和 IO7 同时遮挡 {HOLD_S:.1f} 秒 · Ctrl+C 退出")
        wait_for_trigger(read)
    elif not wait_for_enter():
        return
    log(f"开始直行 · 双轮控制值 {MAX_WHEEL_SPEED} · {RUN_S:.1f} 秒")
    before = uart_counters() if track_uart else None
    try:
        run_launch(apply)
    finally:
        if before is not None:
            after = uart_counters()
            if after is not None:
                log(f"ttyS0 本次计时及停车 · 发送 {after[0] - before[0]:+d} 字节"
                    f" · 接收 {after[1] - before[1]:+d} 字节")
    log(f"{RUN_S:.1f} 秒计时结束，停车指令已发完")


def main(*, trigger="sensor", default_hardware=False):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path,
                        help="使用指定配置的底盘映射；省略时使用本车已核对的起跑方向")
    if default_hardware:
        parser.add_argument("--simulate", dest="hardware", action="store_false", help="模拟运行")
    else:
        parser.add_argument("--hardware", action="store_true", help="控制实车；默认模拟")
    args = parser.parse_args()
    use_sensor = trigger == "sensor"
    trace = MotionLog("launch", "上台") if args.hardware else None

    def log(line):
        if trace is None:
            print(line, flush=True)
        else:
            trace.logger.info(line)

    try:
        if args.hardware:
            cfg = load_edge_config(args.config or Path("config/edge_stop.json"))
            if args.config is None:
                # 实车反馈表明防掉台配置的方向映射会让起跑朝车尾走。
                cfg["drive"]["reverse"] = False
            from uptech import UpTech

            for sig in (signal.SIGTERM, signal.SIGHUP):
                signal.signal(sig, interrupt)
            up = UpTech()
            motor = MotorTrace(up, cfg["drive"], trace.logger)
            inputs = start_inputs(up) if use_sensor else nullcontext()
            with inputs as read, drive_output(motor, cfg) as apply:
                wait_and_launch(motor.wrap_apply(apply), read, log=log, track_uart=True)
        else:
            log("模拟模式")
            starts_at = time.monotonic() + 0.25

            def simulate_inputs():
                return (1, 1) if time.monotonic() < starts_at else BLOCKED_LEVELS

            wait_and_launch(lambda _: True, simulate_inputs if use_sensor else None, log=log)
        return 0
    except (KeyboardInterrupt, EOFError):
        log("已退出")
        return 130
    except (OSError, RuntimeError, ValueError, TypeError, KeyError, ImportError) as error:
        log(f"上台试车结束 · {error}")
        return 1
    finally:
        if trace is not None:
            trace.close()


if __name__ == "__main__":
    raise SystemExit(main())
