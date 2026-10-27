"""传感器实验的统计、标定和 CSV 会话记录（仅使用 Python 标准库）。

时间一律为板端 monotonic_ns；它只能用于同一采集时间轴，不能当作墙上时间。
ADC 保留厂商接口返回的原始码值，本模块不假设 ADC 位数或满量程电压。
"""

import csv
import json
import math
import os
import re
import statistics
import threading
import time
from bisect import bisect_left
from collections import deque
from datetime import datetime
from pathlib import Path


EXPERIMENTS = {
    "P1": "光电：静态接近与释放", "P2": "光电：不同表面",
    "P3": "光电：不同角度", "P4": "光电：动态接近",
    "D1": "距离：静态多点", "D2": "距离：动态靠近",
    "D3": "距离：不同表面", "D4": "距离：不同夹角",
    "D5": "距离：标定与验证", "G1": "灰度：不同距离",
    "G2": "灰度：不同灰度", "G3": "灰度：不同光照",
}


def _number(value, label="数值"):
    if isinstance(value, bool):
        raise ValueError("{}必须是有限数值".format(label))
    try:
        result = float(value)
    except (TypeError, ValueError):
        raise ValueError("{}必须是有限数值".format(label))
    if not math.isfinite(result):
        raise ValueError("{}必须是有限数值".format(label))
    return result


def _snapshot(value):
    """同时检查 JSON 可保存性，避免条件后来被调用者改写。"""
    return json.loads(json.dumps(value, ensure_ascii=False, allow_nan=False))


def summarize(values):
    values = [_number(value) for value in values if value is not None]
    return {
        "count": len(values),
        "mean": statistics.mean(values) if values else None,
        "std": statistics.stdev(values) if len(values) > 1 else None,
        "minimum": min(values) if values else None,
        "maximum": max(values) if values else None,
    }


def filter_values(values, method="raw", window=5):
    """因果滤波；None 表示数据中断并重置窗口。每个试次须独立调用。"""
    if method not in ("raw", "mean", "median"):
        raise ValueError("未知滤波方法：{}".format(method))
    if isinstance(window, bool) or not isinstance(window, int) or window < 1:
        raise ValueError("滤波窗口必须是正整数")
    result = []
    recent = deque(maxlen=window)
    for value in values:
        if value is None:
            recent.clear()
            result.append(None)
            continue
        value = _number(value)
        if method == "raw":
            result.append(value)
            continue
        recent.append(value)
        if len(recent) < window:
            result.append(None)
        else:
            function = statistics.mean if method == "mean" else statistics.median
            result.append(function(recent))
    return result


def build_calibration(points, method="piecewise", sensor_id="", conditions=None):
    """在可逆的工作区间建立 ADC -> cm 标定。重复距离先求各次均值的均值。"""
    if method not in ("piecewise", "linear"):
        raise ValueError("标定方法必须为 piecewise 或 linear")
    source_points = []
    grouped = {}
    for point in points:
        distance = _number(point["distance_cm"], "距离")
        adc = _number(point["adc_mean"], "ADC 均值")
        if distance < 0:
            raise ValueError("距离不能为负")
        source_points.append({"distance_cm": distance, "adc_mean": adc})
        grouped.setdefault(distance, []).append(adc)
    if len(grouped) < 3:
        raise ValueError("至少需要 3 个不同距离的标定点")
    averaged = [
        {"distance_cm": distance, "adc_mean": statistics.mean(grouped[distance]),
         "repeats": len(grouped[distance])}
        for distance in sorted(grouped)
    ]
    deltas = [b["adc_mean"] - a["adc_mean"]
              for a, b in zip(averaged, averaged[1:])]
    if not (all(value > 0 for value in deltas) or all(value < 0 for value in deltas)):
        raise ValueError("ADC 均值必须随距离严格单调；请选择无歧义的工作区间")
    model = {
        "version": 1, "method": method, "sensor_id": str(sensor_id),
        "conditions": _snapshot(conditions or {}), "input": "raw_adc_mean",
        "distance_unit": "cm", "points": averaged, "source_points": source_points,
        "distance_range_cm": [averaged[0]["distance_cm"], averaged[-1]["distance_cm"]],
        "adc_range": [min(p["adc_mean"] for p in averaged),
                      max(p["adc_mean"] for p in averaged)],
    }
    if method == "linear":
        x_mean = statistics.mean(p["adc_mean"] for p in averaged)
        y_mean = statistics.mean(p["distance_cm"] for p in averaged)
        denominator = sum((p["adc_mean"] - x_mean) ** 2 for p in averaged)
        slope = sum((p["adc_mean"] - x_mean) * (p["distance_cm"] - y_mean)
                    for p in averaged) / denominator
        model.update(slope=slope, intercept=y_mean - slope * x_mean)
    return model


def estimate_distance(model, adc):
    if adc is None:
        return None
    adc = _number(adc, "ADC")
    lower, upper = model["adc_range"]
    if adc < lower or adc > upper:
        return None
    if model["method"] == "linear":
        return model["slope"] * adc + model["intercept"]
    if model["method"] != "piecewise":
        raise ValueError("未知标定方法")
    points = sorted(model["points"], key=lambda point: point["adc_mean"])
    index = bisect_left([point["adc_mean"] for point in points], adc)
    if index < len(points) and points[index]["adc_mean"] == adc:
        return points[index]["distance_cm"]
    if index == 0 or index == len(points):
        return None
    left, right = points[index - 1:index + 1]
    weight = (adc - left["adc_mean"]) / (right["adc_mean"] - left["adc_mean"])
    return left["distance_cm"] + weight * (right["distance_cm"] - left["distance_cm"])


def validate_calibration(model, points):
    rows = []
    for point in points:
        distance = _number(point["distance_cm"], "验证距离")
        adc = _number(point["adc_mean"], "验证 ADC")
        if distance < 0:
            raise ValueError("距离不能为负")
        estimate = estimate_distance(model, adc)
        row = dict(point)
        row.update(distance_cm=distance, adc_mean=adc, estimated_distance_cm=estimate,
                   error_cm=None if estimate is None else estimate - distance,
                   in_range=estimate is not None)
        rows.append(row)
    errors = [abs(row["error_cm"]) for row in rows if row["error_cm"] is not None]
    return {"rows": rows, "mae": statistics.mean(errors) if errors else None,
            "max_abs_error": max(errors) if errors else None}


def _io_level(value):
    if value in (0, 1, "0", "1"):
        return int(value)
    if value is None or value == "":
        return None
    raise ValueError("IO 状态只能是 0 或 1")


def _validate_stable(active_level, stable_count):
    if active_level not in (0, 1):
        raise ValueError("有效电平只能是 0 或 1")
    if isinstance(stable_count, bool) or not isinstance(stable_count, int) or stable_count < 1:
        raise ValueError("稳定帧数必须是正整数")


def _settled_level(values, stable_count):
    last, run, settled = None, 0, None
    for value in values:
        value = _io_level(value)
        run = run + 1 if value is not None and value == last else 1
        last = value
        if value is None:
            run, settled = 0, None
        elif run >= stable_count:
            settled = value
    return settled


def photoelectric_summary(points, active_level=0, stable_count=3):
    """点位按实际测量顺序输入。保留离散测点确定的边界区间，而非精确边界。"""
    _validate_stable(active_level, stable_count)
    rows = []
    for point in points:
        if point.get("phase") not in ("approach", "release"):
            raise ValueError("光电静态点必须说明 approach 或 release")
        distance = _number(point["distance_cm"], "距离")
        if distance < 0:
            raise ValueError("距离不能为负")
        level = _settled_level(point.get("io_values", []), stable_count)
        rows.append({"phase": point["phase"], "distance_cm": distance,
                     "level": level, "stable": level is not None})
    result = {"points": rows, "trigger_distance_cm": None, "release_distance_cm": None,
              "hysteresis_cm": None, "approach_interval_cm": None,
              "release_interval_cm": None, "reliable_interval_cm": None}
    for phase, target, field in (("approach", active_level, "trigger_distance_cm"),
                                  ("release", 1 - active_level, "release_distance_cm")):
        previous = None
        for point in (row for row in rows if row["phase"] == phase):
            if point["level"] is None:
                previous = None
                continue
            if point["level"] == target:
                result[field] = point["distance_cm"]
                if previous is not None and previous["level"] != target:
                    result[phase + "_interval_cm"] = sorted(
                        [previous["distance_cm"], point["distance_cm"]])
                break
            previous = point
    trigger, release = result["trigger_distance_cm"], result["release_distance_cm"]
    if trigger is not None and release is not None:
        result["hysteresis_cm"] = abs(release - trigger)
    # 至少两个已确认的触发点才定义可靠区间，不能由一个阈值推出所有更近距离。
    detected = sorted(set(row["distance_cm"] for row in rows
                          if row["phase"] == "approach" and row["level"] == active_level))
    # 不能把中间出现未触发或不稳定读数的两个点包成可靠区间。
    interior_unreliable = bool(detected) and any(
        row["phase"] == "approach" and detected[0] <= row["distance_cm"] <= detected[-1]
        and row["level"] != active_level for row in rows)
    if len(detected) > 1 and not interior_unreliable:
        result["reliable_interval_cm"] = [detected[0], detected[-1]]
    return result


def position_at(t_ns, events):
    """单试次人工运动标记的匀速估计；调用者需先按 trial_id 选取 events。"""
    t_ns = int(t_ns)
    active = None
    for event in sorted(events, key=lambda value: int(value["t_ns"])):
        event_time = int(event["t_ns"])
        name = event.get("name", "")
        if event_time > t_ns:
            break
        if name == "motion_start":
            active = event
        elif name == "motion_end":
            if event_time == t_ns and active is not None:
                break
            active = None
    if active is None:
        return {"distance_cm": None, "position_source": ""}
    data = active.get("data", {})
    try:
        start = _number(data["start_distance_cm"], "起始距离")
        speed = _number(data["speed_cm_s"], "速度")
        direction = data["direction"]
    except (KeyError, ValueError, TypeError):
        return {"distance_cm": None, "position_source": ""}
    if start < 0 or speed < 0 or direction not in ("approach", "release"):
        return {"distance_cm": None, "position_source": ""}
    elapsed = (t_ns - int(active["t_ns"])) / 1e9
    distance = start + (-1 if direction == "approach" else 1) * speed * elapsed
    if distance < 0:
        return {"distance_cm": None, "position_source": ""}
    return {"distance_cm": distance, "position_source": "estimated"}


def dynamic_photoelectric(samples, events, baseline=None, active_level=0,
                          stable_count=3, io_channel=0):
    """从 IO 边沿计算动态触发。无可靠静态区间或位置覆盖时不自动判为漏检。"""
    _validate_stable(active_level, stable_count)
    edges, stable_edges = [], []
    previous_level, candidate, settled = None, None, None
    count, candidate_time = 0, None
    previous_trial, previous_seq = None, None
    positions, stable_active = [], False
    events_by_trial = {}
    for sample in samples:
        trial, seq = sample.get("trial_id"), sample.get("seq")
        if trial not in events_by_trial:
            events_by_trial[trial] = [event for event in events
                                     if trial is None or event.get("trial_id") in (None, trial)]
        trial_events = events_by_trial[trial]
        gap = ((previous_trial is not None and trial != previous_trial) or
               (previous_seq is not None and seq is not None and seq != previous_seq + 1))
        if gap:
            previous_level, candidate, settled, count = None, None, None, 0
        previous_trial, previous_seq = trial, seq
        stamp = sample.get("t_ns")
        if stamp is None:
            stamp = (int(sample["t_start_ns"]) + int(sample["t_end_ns"])) // 2
        stamp = int(stamp)
        channel_values = sample.get("io", {})
        value = sample.get("io_value", channel_values.get(str(io_channel),
                                                         channel_values.get(io_channel)))
        level = _io_level(value)
        if level is None:
            previous_level, candidate, settled, count = None, None, None, 0
            continue
        position = position_at(stamp, trial_events)
        if position["distance_cm"] is not None:
            positions.append(position["distance_cm"])
        if previous_level is not None and level != previous_level:
            edges.append({"from": previous_level, "to": level, "t_ns": stamp,
                          **position})
        previous_level = level
        if level != candidate:
            candidate, count, candidate_time = level, 1, stamp
        else:
            count += 1
        if count >= stable_count and level != settled:
            if settled is not None:
                stable_edges.append({"from": settled, "to": level,
                                     "t_ns": candidate_time, "confirmed_t_ns": stamp,
                                     **position_at(candidate_time, trial_events)})
            settled = level
            stable_active = stable_active or level == active_level
    triggers = [edge for edge in stable_edges if edge["to"] == active_level]
    trigger = triggers[0] if triggers else None
    distance = trigger["distance_cm"] if trigger else None
    reference = baseline.get("trigger_distance_cm") if baseline else None
    interval = baseline.get("reliable_interval_cm") if baseline else None
    covered = bool(interval and any(min(interval) <= p <= max(interval) for p in positions))
    if trigger is not None:
        miss_status, reason = "detected", "已记录未触发到触发的稳定跳变"
    elif stable_active:
        miss_status, reason = "undetermined", "已读到触发状态，但未记录完整的进入边沿"
    elif not baseline:
        miss_status, reason = "undetermined", "缺少同条件静态基准"
    elif not interval:
        miss_status, reason = "undetermined", "静态基准未提供已确认的可靠检测区间"
    elif not covered:
        miss_status, reason = "undetermined", "位置记录未确认进入可靠检测区间"
    else:
        miss_status, reason = "missed", "估计位置进入可靠区间，采样中未读到稳定触发"
    return {
        "edges": edges, "stable_edges": stable_edges,
        "trigger_distance_cm": distance,
        "trigger_t_ns": trigger["t_ns"] if trigger else None,
        "confirmed_t_ns": trigger["confirmed_t_ns"] if trigger else None,
        "position_source": "estimated" if distance is not None else "",
        "baseline_trigger_distance_cm": reference,
        "trigger_difference_cm": distance - reference if distance is not None
        and reference is not None else None,
        "miss_status": miss_status, "reason": reason,
        "raw_edge_count": len(edges), "stable_edge_count": len(stable_edges),
        "entered_reliable_region": covered,
    }


SAMPLE_FIELDS = ["trial_id", "seq", "t_start_ns", "t_end_ns", "simulated"] + [
    "io_{}".format(channel) for channel in range(8)
] + ["adc_{}".format(channel) for channel in range(9)]
EVENT_FIELDS = ["trial_id", "t_ns", "name", "data"]


def _now():
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _write_json(path, payload):
    temporary = path.with_name(path.name + ".tmp")
    with temporary.open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(payload, handle, ensure_ascii=False, allow_nan=False, indent=2)
        handle.write("\n")
    os.replace(str(temporary), str(path))


def _cell(value):
    if isinstance(value, (dict, list, tuple)):
        return json.dumps(value, ensure_ascii=False, allow_nan=False)
    return value


class SessionStore:
    """原始样本只写盘不缓存。建议由专用写入线程调用，方法内部锁防止交错。"""

    def __init__(self, root, experiment, metadata):
        if experiment not in EXPERIMENTS:
            raise ValueError("未知实验编号：{}".format(experiment))
        self._lock = threading.RLock()
        self._closed = False
        self._active_trial = None
        self._last_flush = time.monotonic()
        self._sample_file = self._event_file = None
        self._sample_writer = self._event_writer = None
        # 元数据先校验，不能留下一个条件不可保存的空会话。
        snapshot = _snapshot(metadata)
        root = Path(root)
        root.mkdir(parents=True, exist_ok=True)
        suffix = re.sub(r"[^\w\-]", "_", str(snapshot.get("experiment_id", experiment)))
        stem = datetime.now().strftime("%Y%m%d_%H%M%S_%f") + "_" + suffix[:60]
        self.path = root / stem
        collision = 0
        while True:
            try:
                self.path.mkdir()
                break
            except FileExistsError:
                collision += 1
                self.path = root / (stem + "_" + str(collision))
        self.metadata = {"schema_version": 1, "experiment": experiment,
                         "created_at": _now(), "metadata": snapshot, "trials": []}
        _write_json(self.path / "metadata.json", self.metadata)

    @property
    def current_trial_id(self):
        return self._active_trial["trial_id"] if self._active_trial else None

    def _check_open(self):
        if self._closed:
            raise RuntimeError("会话已关闭")

    def start_trial(self, metadata):
        with self._lock:
            self._check_open()
            if self._active_trial is not None:
                raise RuntimeError("请先结束当前试次")
            trial_id = "T{:04d}".format(len(self.metadata["trials"]) + 1)
            trial = {"trial_id": trial_id, "metadata": _snapshot(metadata),
                     "status": "recording", "reason": "", "sample_count": 0,
                     "started_at": _now(), "finished_at": None}
            self.metadata["trials"].append(trial)
            self._active_trial = trial
            try:
                _write_json(self.path / "metadata.json", self.metadata)
            except Exception:
                self._active_trial = None
                self.metadata["trials"].pop()
                raise
            return trial_id

    def _flush(self, force=False):
        if force or time.monotonic() - self._last_flush >= 1:
            for handle in (self._sample_file, self._event_file):
                if handle is not None:
                    handle.flush()
            self._last_flush = time.monotonic()

    def flush(self):
        with self._lock:
            self._check_open()
            self._flush(force=True)

    def append_sample(self, packet):
        with self._lock:
            self._check_open()
            if self._active_trial is None:
                raise RuntimeError("请先开始试次")
            trial_id = packet.get("trial_id", self.current_trial_id)
            if trial_id != self.current_trial_id:
                raise ValueError("采样的 trial_id 与当前试次不一致")
            start, end = int(packet["t_start_ns"]), int(packet["t_end_ns"])
            if end < start:
                raise ValueError("读取结束时间不能早于开始时间")
            row = {"trial_id": trial_id, "seq": int(packet["seq"]),
                   "t_start_ns": start, "t_end_ns": end,
                   "simulated": int(bool(packet.get("simulated", False)))}
            for family, limit in (("io", 8), ("adc", 9)):
                for channel, value in packet.get(family, {}).items():
                    if not 0 <= int(channel) < limit:
                        raise ValueError("{} 通道超出范围".format(family))
                    row["{}_{}".format(family, int(channel))] = int(value)
                    if family == "io" and int(value) not in (0, 1):
                        raise ValueError("IO 状态只能是 0 或 1")
            if self._sample_file is None:
                self._sample_file = (self.path / "samples.csv").open(
                    "w", encoding="utf-8-sig", newline="")
                self._sample_writer = csv.DictWriter(self._sample_file, SAMPLE_FIELDS)
                self._sample_writer.writeheader()
                self._sample_file.flush()
            self._sample_writer.writerow(row)
            self._active_trial["sample_count"] += 1
            self._flush()

    def append_event(self, event):
        with self._lock:
            self._check_open()
            trial_id = event.get("trial_id", self.current_trial_id)
            if trial_id is None or trial_id not in {t["trial_id"] for t in self.metadata["trials"]}:
                raise ValueError("事件必须关联一个已存在的试次")
            row = {"trial_id": trial_id, "t_ns": int(event["t_ns"]),
                   "name": str(event["name"]), "data": _cell(event.get("data", {}))}
            if self._event_file is None:
                self._event_file = (self.path / "events.csv").open(
                    "w", encoding="utf-8-sig", newline="")
                self._event_writer = csv.DictWriter(self._event_file, EVENT_FIELDS)
                self._event_writer.writeheader()
                self._event_file.flush()
            self._event_writer.writerow(row)
            self._flush()

    def finish_trial(self, status="complete", reason=""):
        with self._lock:
            self._check_open()
            if self._active_trial is None:
                return
            if status not in ("complete", "incomplete", "cancelled"):
                raise ValueError("试次状态必须为 complete、incomplete 或 cancelled")
            self._flush(force=True)
            self._active_trial.update(status=status, reason=str(reason), finished_at=_now())
            _write_json(self.path / "metadata.json", self.metadata)
            self._active_trial = None

    def save_summary(self, rows):
        """用传入的全部统计行替换 summary.csv；不同类型的列取并集。"""
        with self._lock:
            self._check_open()
            rows = _snapshot(list(rows))
            fields = list(dict.fromkeys(key for row in rows for key in row))
            if not fields:
                fields = ["trial_id"]
            target = self.path / "summary.csv"
            temporary = target.with_name(target.name + ".tmp")
            with temporary.open("w", encoding="utf-8-sig", newline="") as handle:
                writer = csv.DictWriter(handle, fields)
                writer.writeheader()
                for row in rows:
                    writer.writerow({key: _cell(value) for key, value in row.items()})
            os.replace(str(temporary), str(target))

    def save_calibration(self, model):
        with self._lock:
            self._check_open()
            _write_json(self.path / "calibration.json", _snapshot(model))

    def close(self):
        with self._lock:
            if self._closed:
                return
            error = None
            try:
                if self._active_trial is not None:
                    self.finish_trial("incomplete", "会话关闭前试次尚未正常结束")
                self._flush(force=True)
            except Exception as exc:
                error = exc
            finally:
                for handle in (self._sample_file, self._event_file):
                    if handle is not None:
                        try:
                            handle.close()
                        except Exception as exc:
                            if error is None:
                                error = exc
                self._closed = True
            if error is not None:
                raise error

    @classmethod
    def load_session(cls, path):
        return load_session(path)


def _read_rows(path, warnings):
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8-sig", errors="replace", newline="") as handle:
        result = []
        try:
            for line, row in enumerate(csv.DictReader(handle), 2):
                if any("\ufffd" in str(value) for value in row.values()):
                    warnings.append("{} 第 {} 行 UTF-8 编码损坏，已替换无法解码的字节".format(
                        path.name, line))
                if None in row or None in row.values():
                    warnings.append("{} 第 {} 行不完整，已跳过".format(path.name, line))
                    continue
                result.append(row)
        except csv.Error as exc:
            warnings.append("{} CSV 读取中断：{}".format(path.name, exc))
    return result


def _decode_cell(value):
    if value == "":
        return None
    try:
        return json.loads(value)
    except (ValueError, TypeError):
        return value


def load_session(path):
    """重开已保存记录；崩溃留下的 recording 状态仅在返回结果标为不完整。"""
    path = Path(path)
    with (path / "metadata.json").open("r", encoding="utf-8") as handle:
        metadata = json.load(handle)
    warnings, samples, events = [], [], []
    for trial in metadata.get("trials", []):
        if trial.get("status") == "recording":
            trial.update(status="incomplete", reason="上次记录未正常结束", recovered=True)
            warnings.append("{} 上次未正常结束".format(trial["trial_id"]))
    for row in _read_rows(path / "samples.csv", warnings):
        try:
            packet = {"type": "sample", "trial_id": row["trial_id"],
                      "seq": int(row["seq"]), "t_start_ns": int(row["t_start_ns"]),
                      "t_end_ns": int(row["t_end_ns"]),
                      "simulated": bool(int(row["simulated"])), "io": {}, "adc": {}}
            if packet["t_end_ns"] < packet["t_start_ns"]:
                raise ValueError("读取结束时间早于开始时间")
            for family, limit in (("io", 8), ("adc", 9)):
                for channel in range(limit):
                    value = row["{}_{}".format(family, channel)]
                    if value != "":
                        packet[family][str(channel)] = int(value)
            samples.append(packet)
        except (ValueError, TypeError, KeyError) as exc:
            warnings.append("samples.csv 记录无法解析，已跳过：{}".format(exc))
    # 崩溃、手动编辑或文件截断之后，不能仍向界面报告完整试次。
    counts, previous_sequences, damaged_trials = {}, {}, set()
    for sample in samples:
        trial_id = sample["trial_id"]
        counts[trial_id] = counts.get(trial_id, 0) + 1
        previous_seq = previous_sequences.get(trial_id)
        if previous_seq is not None and sample["seq"] != previous_seq + 1:
            damaged_trials.add(trial_id)
            warnings.append("{} 采样序号不连续".format(trial_id))
        previous_sequences[trial_id] = sample["seq"]
    parse_damage = any(warning.startswith("samples.csv") for warning in warnings)
    for trial in metadata.get("trials", []):
        trial_id = trial["trial_id"]
        count_mismatch = (trial.get("status") == "complete"
                          and trial.get("sample_count", 0) != counts.get(trial_id, 0))
        if count_mismatch:
            warnings.append("{} 保存的样本数与实际文件不一致".format(trial_id))
        if trial.get("status") == "complete" and (parse_damage or count_mismatch
                                                  or trial_id in damaged_trials):
            trial.update(status="incomplete", reason="原始数据完整性检查未通过", recovered=True)
    for row in _read_rows(path / "events.csv", warnings):
        try:
            events.append({"type": "event", "trial_id": row["trial_id"],
                           "t_ns": int(row["t_ns"]), "name": row["name"],
                           "data": json.loads(row["data"])})
        except (ValueError, TypeError, KeyError) as exc:
            warnings.append("events.csv 记录无法解析，已跳过：{}".format(exc))
    summaries = [{key: _decode_cell(value) for key, value in row.items()}
                 for row in _read_rows(path / "summary.csv", warnings)]
    calibration = None
    if (path / "calibration.json").exists():
        with (path / "calibration.json").open("r", encoding="utf-8") as handle:
            calibration = json.load(handle)
    return {"metadata": metadata, "samples": samples, "events": events,
            "summaries": summaries, "calibration": calibration, "warnings": warnings}
