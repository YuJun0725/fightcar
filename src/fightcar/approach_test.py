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
from fightcar.edge_stop import (
    PERIOD_S, STOP, SensorReadError, arm_on_platform, gray_inputs, interrupt,
    load as load_edge_config, rear_photo_input, sample_pair, stop_and_drain,
)
from fightcar.models import WheelCommand


MAX_FRAME_AGE_S = 0.30
SETTLE_S = 0.12


@dataclass(frozen=True)
class View:
    timestamp: float
    seen: bool
    distance_m: Optional[float] = None
    angle_deg: float = 0.0


def load_config(path, *, speed_override=None):
    cfg = json.loads(path.read_text(encoding="utf-8-sig"))
    if speed_override is not None:
        cfg["forward_speed"] = speed_override
    for key, low, high in (
        ("target_tag_id", 0, 586), ("search_speed", 1, 512), ("turn_speed", 1, 512),
        ("forward_speed", 1, 512),
    ):
        if type(cfg[key]) is not int or not low <= cfg[key] <= high:
            raise ValueError(f"{key} 须为 {low}～{high} 的整数")
    for key, low, high in (
        ("stop_distance_m", 0.20, 3.0), ("align_deg", 1.0, 20.0),
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
        return View(stamp, bool(matches) or any(tag["id"] == tag_id for tag in record["tags"]))
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


def run_trial(cfg, edge, latest, read_gray, read_photo, apply, *,
              clock=time.monotonic, sleep=time.sleep, log=print):
    check_edge = read_gray is not None or read_photo is not None

    def rear_edge():
        levels = sample_pair(read_photo, clock, "后光电 IO", 1)
        photo = edge["rear_photo"]
        if photo["active_level"] in levels:
            return f"后光电触边（左后 {levels[0]}，右后 {levels[1]}）"
        return None

    active_phase = None
    settling, accept_after = False, None
    last_seen, last_log = None, None
    got_vision = False
    try:
        if check_edge:
            arm_on_platform(read_gray, edge, clock, sleep, rear_edge)
        started = clock()
        while clock() - started < cfg["timeout_s"]:
            cycle = clock()
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
            got_vision |= view is not None
            phase, wheels = movement(view, last_seen, cfg)
            if view is not None and view.distance_m is not None:
                last_seen = view.timestamp
                if view.distance_m <= cfg["stop_distance_m"]:
                    return True, f"到达设定距离（测得 {view.distance_m * 100:.1f} cm）"
            if last_seen is not None and now - last_seen >= cfg["lost_timeout_s"]:
                return False, "目标丢失超时"

            if active_phase is not None and phase != active_phase:
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


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=Path("config/approach_test.json"))
    parser.add_argument("--edge-config", type=Path, default=Path("config/edge_stop.json"))
    parser.add_argument("--speed", type=int, help="本次直行靠近的控制值（1～512）")
    parser.add_argument("--no-edge", action="store_true", help="平地专项：跳过灰度、光电和台面起步检查")
    parser.add_argument("--vision-port", type=int, default=8080, help="板端相机预览的回环端口")
    parser.add_argument("--hardware", action="store_true", help="控制实车；默认模拟")
    args = parser.parse_args()
    if not 1 <= args.vision_port <= 65535:
        parser.error("视觉端口须在 1～65535 之间")
    try:
        cfg = load_config(args.config, speed_override=args.speed)
        edge = load_edge_config(args.edge_config, backward=not args.no_edge)
        mode = " · 平地测试，触边检测关闭" if args.no_edge else ""
        print(f"直行靠近控制值 {cfg['forward_speed']}{mode}", flush=True)
        if args.hardware:
            from uptech import UpTech
            for sig in (signal.SIGTERM, signal.SIGHUP):
                signal.signal(sig, interrupt)
            up = UpTech()
            sensors = nullcontext() if args.no_edge else gray_inputs(up, edge)
            with TargetReader(args.vision_port, cfg["target_tag_id"]) as reader, sensors as read_gray:
                read_photo = None if args.no_edge else rear_photo_input(up, edge["rear_photo"])
                with drive_output(up, edge) as apply:
                    reached, reason = run_trial(cfg, edge, lambda: reader.view, read_gray, read_photo,
                                                apply, log=lambda line: print(line, flush=True))
        else:
            reached, reason = simulate(cfg, edge, no_edge=args.no_edge)
        print(f"停车指令已发完 · {reason}")
        return 0 if reached else 1
    except KeyboardInterrupt:
        print("已退出")
        return 130
    except (OSError, RuntimeError, ValueError, TypeError, KeyError, ImportError) as error:
        print(f"靠近测试结束 · {error}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
