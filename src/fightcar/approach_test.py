"""实车专项：搜索、对准能量块，靠近至相机测得的中心距离后停车。"""

import argparse
from contextlib import nullcontext
from dataclasses import dataclass
import http.client
import json
import math
from pathlib import Path
import signal
import threading
import time
from typing import Optional

from fightcar.control.drive import drive_output
from fightcar.control.safety import MAX_WHEEL_SPEED
from fightcar.edge_stop import (
    PERIOD_S, STOP, SensorReadError, arm_on_platform, gray_inputs, interrupt,
    load as load_edge_config, rear_photo_input, sample_pair, stop_and_drain,
)
from fightcar.follow_log import MotionLog, MotorTrace
from fightcar.models import WheelCommand


MAX_FRAME_AGE_S = 0.30
SETTLE_S = 0.12
FOLLOW_MIN_WHEEL_SPEED = 450  # 本车实测的最低起转控制值。
FOLLOW_FULL_STEERING_DEG = 45.0
MAX_APPROACH_SPEED = 512


@dataclass(frozen=True)
class View:
    timestamp: float
    seen: bool
    distance_m: Optional[float] = None
    angle_deg: float = 0.0
    ambiguous: bool = False


def load_config(path, *, speed_override=None, target_tag_id=None, follow=False):
    cfg = json.loads(path.read_text(encoding="utf-8-sig"))
    if follow:
        cfg["forward_speed"] = cfg.get("follow_forward_speed", cfg["forward_speed"])
        cfg["turn_speed"] = cfg.get("follow_turn_speed", cfg["turn_speed"])
        cfg["stop_distance_m"] = cfg.get("follow_stop_distance_m", cfg["stop_distance_m"])
    if speed_override is not None:
        cfg["forward_speed"] = speed_override
    if target_tag_id is not None:
        cfg["target_tag_id"] = target_tag_id
    limit = MAX_WHEEL_SPEED if follow else MAX_APPROACH_SPEED
    for key, low, high in (("target_tag_id", 0, 586), ("search_speed", 1, MAX_APPROACH_SPEED),
                           ("turn_speed", 1, limit), ("forward_speed", 1, limit)):
        if type(cfg[key]) is not int or not low <= cfg[key] <= high:
            raise ValueError(f"{key} 须为 {low}～{high} 的整数")
    for key, low, high in (
        ("stop_distance_m", 0.10 if follow else 0.20, 3.0), ("align_deg", 1.0, 20.0),
        ("timeout_s", 1.0, 60.0), ("lost_timeout_s", MAX_FRAME_AGE_S, 10.0),
    ):
        value = cfg[key]
        if type(value) not in (int, float) or not math.isfinite(value) or not low <= value <= high:
            raise ValueError(f"{key} 须在 {low}～{high} 之间")
    return cfg


def parse_view(record, tag_id):
    if (record["state"] != "live" or record["pose_status"] != "ready"
            or not record["center_geometry"]):
        return None
    stamp = record["timestamp_s"]
    if type(stamp) not in (int, float) or not math.isfinite(stamp):
        return None
    matches = [p for p in record["blocks"] if tag_id in p["tag_ids"]]
    if len(matches) != 1:
        tags = [tag for tag in record["tags"] if tag["id"] == tag_id]
        return View(stamp, bool(matches or tags), ambiguous=len(matches) > 1 or len(tags) > 1)
    target = matches[0]
    x, y, z = target["xyz_m"]
    raw_distance = target["raw_distance_m"]
    if (not all(type(v) in (int, float) and math.isfinite(v) for v in (x, y, z, raw_distance))
            or z <= 0 or raw_distance <= 0):
        return View(stamp, True)
    return View(stamp, True, min(math.hypot(x, y, z), raw_distance), math.degrees(math.atan2(x, z)))


class TargetReader:
    """后台读取板端回环接口，控制循环只读取最近一次观测。"""

    def __init__(self, port, tag_id):
        self.port, self.tag_id = port, tag_id
        self.view = None
        self.stopping = threading.Event()
        self.worker = threading.Thread(target=self.poll, daemon=True)

    def poll(self):
        while not self.stopping.is_set():
            client = http.client.HTTPConnection("127.0.0.1", self.port, timeout=0.20)
            try:
                client.request("GET", "/api/targets")
                response = client.getresponse()
                self.view = parse_view(json.loads(response.read(65536)), self.tag_id) if response.status == 200 else None
            except (OSError, http.client.HTTPException, ValueError, TypeError, KeyError):
                self.view = None
            finally:
                client.close()
            self.stopping.wait(0.05)

    def __enter__(self):
        self.worker.start()
        return self

    def __exit__(self, *exc):
        self.stopping.set()
        self.worker.join(0.3)


def movement(view, last_seen, cfg):
    if view is None:
        return "等待新鲜视觉帧", STOP
    if view.distance_m is None:
        if view.seen or last_seen is not None:
            return "暂未得到目标中心，停车", STOP
        speed = cfg["search_speed"]
        # 实车上原先的负左、正右指令使车顺时针转。
        return "逆时针搜索", WheelCommand(speed, -speed)
    if view.distance_m <= cfg["stop_distance_m"]:
        return "达到目标距离", STOP
    if abs(view.angle_deg) > cfg["align_deg"]:
        turn = cfg["turn_speed"] if view.angle_deg > 0 else -cfg["turn_speed"]
        # 按实车反馈修正相机偏角到两侧轮速的符号。
        phase = "右转对准" if turn > 0 else "左转对准"
        return phase, WheelCommand(-turn, turn)
    speed = cfg["forward_speed"]
    return "直行靠近", WheelCommand(speed, speed)


def follow_movement(view, cfg):
    if view is None:
        return "等待新鲜视觉帧", STOP
    if view.distance_m is None:
        if view.ambiguous:
            return "同 ID 有多个候选，等待确定目标", STOP
        if view.seen:
            return "已识别指定目标，等待测距", STOP
        return "等待指定目标", STOP
    if view.distance_m <= cfg["stop_distance_m"]:
        return "达到目标距离", STOP

    base = cfg["forward_speed"]
    minimum = min(base, FOLLOW_MIN_WHEEL_SPEED)
    deadband = cfg["align_deg"]
    error = max(0.0, abs(view.angle_deg) - deadband)
    fraction = min(1.0, error / (FOLLOW_FULL_STEERING_DEG - deadband))
    difference = min(round(cfg["turn_speed"] * fraction), MAX_WHEEL_SPEED - minimum)
    # 保持两轮同向，优先保留差速，再将内轮和外轮限制在可用范围内。
    inner = min(max(minimum, base - difference // 2), MAX_WHEEL_SPEED - difference)
    outer = inner + difference
    wheels = WheelCommand(outer, inner) if view.angle_deg > 0 else WheelCommand(inner, outer)
    return "合成速度跟随", wheels


def platform_photo_input(up):
    for channel in (1, 2):
        status = up.ADC_IO_SetIOMode(channel, 0)
        if isinstance(status, int) and status < 0:
            raise OSError(f"设置 IO{channel} 输入失败")

    def read():
        levels = up.ADC_IO_GetAllInputLevel()
        return levels[1], levels[2]

    return read


def run_trial(cfg, edge, latest, read_gray, read_photo, apply, *,
              follow=False, read_platform_photo=None, clock=time.monotonic, sleep=time.sleep, log=print):
    check_edge = read_gray is not None or read_photo is not None

    def rear_edge():
        levels = sample_pair(read_photo, clock, "后光电 IO", 1)
        photo = edge["rear_photo"]
        if photo["active_level"] in levels:
            return (f"后光电触边（左后 IO{photo['left_io']}={levels[0]}，"
                    f"右后 IO{photo['right_io']}={levels[1]}）")
        return None

    active_phase = None
    settling, accept_after = False, None
    last_seen, last_log = None, None
    got_vision = False
    last_follow_view = None
    try:
        if check_edge:
            arm_on_platform(read_gray, edge, clock, sleep, rear_edge)
        started = clock()
        while follow or clock() - started < cfg["timeout_s"]:
            cycle = clock()
            if read_platform_photo is not None:
                levels = sample_pair(read_platform_photo, clock, "出台光电 IO1/IO2", 1)
                if levels == (1, 1):
                    return False, "出台 · IO1=1 且 IO2=1"
            if check_edge:
                front, rear = sample_pair(read_gray, clock, "灰度 ADC", 65535)
                if min(front, rear) <= edge["edge_threshold"]:
                    return False, f"灰度触边（前 {front}，后 {rear}）"
                reason = rear_edge()
                if reason:
                    return False, reason

            view = latest()
            now = clock()
            if view is not None and not 0 <= now - view.timestamp <= MAX_FRAME_AGE_S:
                view = None
            if follow:
                # 同一目标短时漏检或缺测距时沿用最后位置，时间戳保持为原始测量时间。
                if (active_phase is not None and view is not None
                        and view.distance_m is None and not view.ambiguous
                        and last_follow_view is not None
                        and 0 <= now - last_follow_view.timestamp <= MAX_FRAME_AGE_S):
                    view = last_follow_view
                last_follow_view = view if view is not None and view.distance_m is not None else None
                phase, wheels = follow_movement(view, cfg)
            else:
                got_vision |= view is not None
                phase, wheels = movement(view, last_seen, cfg)
                if view is not None and view.distance_m is not None:
                    last_seen = view.timestamp
                    if view.distance_m <= cfg["stop_distance_m"]:
                        return True, f"到达设定距离（测得 {view.distance_m * 100:.1f} cm）"
                if last_seen is not None and now - last_seen >= cfg["lost_timeout_s"]:
                    return False, "目标丢失超时"

            if not follow and active_phase is not None and phase != active_phase:
                # 停稳后使用新的相机帧，再决定下一段动作。
                settling, accept_after, active_phase = True, None, None
            if settling:
                phase = "停车确认"
                if apply(STOP):
                    if accept_after is None:
                        accept_after = clock() + SETTLE_S
                    if view is not None and view.timestamp >= accept_after:
                        settling = False
            else:
                apply(wheels)
                active_phase = phase if wheels != STOP else None
            if phase != last_log:
                detail = (f" · 距离 {view.distance_m * 100:.1f} cm · 偏角 {view.angle_deg:+.1f}°"
                          if view is not None and view.distance_m is not None else "")
                log(phase + detail)
                last_log = phase
            sleep(max(0, PERIOD_S - (clock() - cycle)))
        return False, "测试超时" if got_vision else "没有收到可测距的视觉帧，请检查相机预览"
    except SensorReadError as error:
        return False, str(error)
    finally:
        stop_and_drain(apply, clock, sleep)


def simulate(cfg, edge, *, no_edge=False):
    started = time.monotonic() + (0 if no_edge else edge["arm_confirm_s"])

    def latest():
        now = time.monotonic()
        elapsed = now - started
        if elapsed < 0.45:
            return View(now, False)
        angle = cfg["align_deg"] + 6 if elapsed < 1.2 else 0
        return View(now, True, cfg["stop_distance_m"] + max(0, 1.8 - elapsed) * 0.2, angle)

    if no_edge:
        return run_trial(cfg, edge, latest, None, None, lambda _: True)
    safe_photo = 1 - edge["rear_photo"]["active_level"]
    return run_trial(cfg, edge, latest, lambda: (65535, 65535),
                     lambda: (safe_photo, safe_photo), lambda _: True)


def main(*, follow=False):
    description = "持续跟随指定 AprilTag ID 的能量块。" if follow else __doc__
    parser = argparse.ArgumentParser(description=description)
    parser.add_argument("--config", type=Path, default=Path("config/approach_test.json"))
    parser.add_argument("--edge-config", type=Path, help="默认 config/edge_stop.json")
    limit = MAX_WHEEL_SPEED if follow else MAX_APPROACH_SPEED
    parser.add_argument("--speed", type=int, help=f"本次直行的控制值（1～{limit}）")
    parser.add_argument("--no-edge", action="store_true", help="平地专项：跳过灰度、光电和台面起步检查")
    parser.add_argument("--vision-port", type=int, default=8080, help="板端相机预览的回环端口")
    if follow:
        parser.add_argument("tag_id", type=int, help="跟随目标的 AprilTag ID")
    else:
        parser.add_argument("--hardware", action="store_true", help="控制实车；默认模拟")
    args = parser.parse_args()
    if not 1 <= args.vision_port <= 65535:
        parser.error("视觉端口须在 1～65535 之间")
    trace = MotionLog("follow", "跟随") if follow else None

    def log(line):
        if trace is None:
            print(line, flush=True)
        else:
            trace.logger.info(line)

    try:
        cfg = load_config(args.config, speed_override=args.speed,
                          target_tag_id=args.tag_id if follow else None, follow=follow)
        edge = load_edge_config(args.edge_config or Path("config/edge_stop.json"), backward=not args.no_edge)
        if follow and args.edge_config is None:
            edge["drive"]["reverse"] = False  # 与实车核对过的起跑方向一致。
        mode = " · 平地测试，触边检测关闭" if args.no_edge else ""
        if follow:
            stop_distance = cfg["stop_distance_m"]
            platform_stop = "" if args.no_edge else " · IO1 和 IO2 同为 1 时停车退出"
            log(f"持续跟随 AprilTag ID {cfg['target_tag_id']} · 基础轮速 {cfg['forward_speed']}"
                f" · 差速设定上限 {cfg['turn_speed']} · {stop_distance * 100:g} cm 停车"
                f"{platform_stop}{mode}")
        else:
            log(f"直行靠近控制值 {cfg['forward_speed']}{mode}")
        if follow or args.hardware:
            from uptech import UpTech
            for sig in (signal.SIGTERM, signal.SIGHUP):
                signal.signal(sig, interrupt)
            up = UpTech()
            motor = MotorTrace(up, edge["drive"], trace.logger) if trace is not None else up
            sensors = nullcontext() if args.no_edge else gray_inputs(up, edge)
            with TargetReader(args.vision_port, cfg["target_tag_id"]) as reader, sensors as read_gray:
                read_photo = None if args.no_edge else rear_photo_input(up, edge["rear_photo"])
                read_platform_photo = platform_photo_input(up) if follow and not args.no_edge else None
                with drive_output(motor, edge) as apply:
                    if trace is not None:
                        apply = motor.wrap_apply(apply)
                    reached, reason = run_trial(cfg, edge, lambda: reader.view, read_gray, read_photo,
                                                apply, follow=follow, read_platform_photo=read_platform_photo, log=log)
        else:
            reached, reason = simulate(cfg, edge, no_edge=args.no_edge)
        log(f"停车指令已发完 · {reason}")
        return 0 if reached else 1
    except KeyboardInterrupt:
        log("已退出")
        return 130
    except (OSError, RuntimeError, ValueError, TypeError, KeyError, ImportError) as error:
        mode = "跟随" if follow else "靠近"
        log(f"{mode}测试结束 · {error}")
        return 1
    finally:
        if trace is not None:
            trace.close()


if __name__ == "__main__":
    raise SystemExit(main())
