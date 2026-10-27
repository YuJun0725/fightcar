#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""按电机日志的世界时间对齐 IR 原始数据；只换算距离，不滤波或删点。"""

import csv
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import re

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager
from matplotlib.ticker import MultipleLocator

HERE = Path(__file__).resolve().parent
INPUT = HERE.parent
ZONE = timezone(timedelta(hours=8))
START_CM, END_CM = 80.0, 10.0
COLORS = {25: "#2563eb", 50: "#0f9188", 100: "#d97706", 200: "#b33563"}
STAMP = re.compile(r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\.\d+)\s+([+-]\d{2}:\d{2})\s+(.*)$")
RUN = re.compile(r"^(正转|反转) (\d+) 圈/分.*指令已确认")


def motor_intervals():
    active, intervals = None, []
    for line_number, line in enumerate((INPUT / "motor_log.txt").read_text(encoding="utf-8-sig").splitlines(), 1):
        match = STAMP.match(line)
        if not match:
            continue
        stamp, offset, message = match.groups()
        timestamp = datetime.fromisoformat(stamp.replace(" ", "T") + offset)
        motion = RUN.match(message)
        if motion:
            if active is not None:
                raise ValueError("运行区间未结束就收到新的运行确认")
            active = dict(start=timestamp, rpm=int(motion.group(2)), direction=motion.group(1),
                          start_line=line_number, start_message=message)
        elif active is not None and (message.startswith("RX  01 06 00 03 00 01") or message == "暂停指令已确认。"):
            active.update(end=timestamp, end_line=line_number, end_message=message)
            intervals.append(active)
            active = None
    return intervals


def read_run(path, intervals):
    rpm = int(path.stem.rsplit("_", 1)[1])
    with path.open(encoding="utf-8-sig", newline="") as source:
        raw = list(csv.DictReader(source))
    timestamps = [datetime.fromisoformat(row["timestamp"]) for row in raw]
    timestamps = [t.replace(tzinfo=ZONE) if t.tzinfo is None else t.astimezone(ZONE) for t in timestamps]
    if not all(a < b for a, b in zip(timestamps, timestamps[1:])):
        raise ValueError("传感器时间不是严格递增：" + path.name)
    matches = [event for event in intervals if event["rpm"] == rpm
               and timestamps[0] <= event["start"] < event["end"] <= timestamps[-1]]
    if len(matches) != 1:
        raise ValueError("不能唯一匹配运动区间：" + path.name)
    event = matches[0]
    duration = (event["end"] - event["start"]).total_seconds()
    aligned = []
    for line, (row, timestamp) in enumerate(zip(raw, timestamps), 2):
        seconds = (timestamp - event["start"]).total_seconds()
        phase = "before_motion" if seconds < 0 else "after_motion" if seconds > duration else "motion"
        # 起停前后的原始采样同样保留，距离分别置于 80 和 10 cm，并另行标注。
        distance = START_CM + (END_CM - START_CM) * min(1.0, max(0.0, seconds / duration))
        aligned.append(dict(**row, source_csv_line=line, timestamp_utc08=timestamp.isoformat(timespec="milliseconds"),
                            motor_rpm=rpm, time_from_motor_start_s=f"{seconds:.6f}", phase=phase,
                            estimated_distance_cm=f"{distance:.9f}"))
    motion = [row for row in aligned if row["phase"] == "motion"]
    metadata = dict(source_file=path.name, rpm=rpm, adc_channels=sorted({r["adc_channel"] for r in raw}),
                    start_time=event["start"].isoformat(timespec="milliseconds"),
                    end_time=event["end"].isoformat(timespec="milliseconds"), duration_s=duration,
                    start_log_line=event["start_line"], end_log_line=event["end_line"],
                    start_log_message=event["start_message"], end_log_message=event["end_message"],
                    raw_rows=len(raw), motion_rows=len(motion), before_rows=sum(r["phase"] == "before_motion" for r in aligned),
                    after_rows=sum(r["phase"] == "after_motion" for r in aligned),
                    endpoint_based_speed_cm_s=(START_CM - END_CM) / duration,
                    approximate_nominal_speed_cm_s=25.0 * rpm / 200.0,
                    csv_first_time=timestamps[0].isoformat(), csv_last_time=timestamps[-1].isoformat())
    return dict(rpm=rpm, rows=aligned, motion=motion, metadata=metadata)


def setup_style():
    for name in ("Microsoft YaHei", "SimHei", "Noto Sans CJK SC"):
        if any(font.name == name for font in font_manager.fontManager.ttflist):
            plt.rcParams["font.family"] = name
            break
    plt.rcParams.update({"axes.unicode_minus": False, "font.size": 10, "axes.spines.top": False,
                         "axes.spines.right": False, "svg.fonttype": "none", "savefig.facecolor": "white"})


def plot_distance(axis, run):
    rows = run["motion"]
    x = [float(row["estimated_distance_cm"]) for row in rows]
    y = [int(row["adc_value"]) for row in rows]
    color = COLORS[run["rpm"]]
    axis.plot(x, y, color=color, linewidth=.75, marker="o", markersize=2.7, markeredgewidth=0)
    stationary = [row for row in run["rows"] if row["phase"] != "motion"]
    axis.scatter([float(row["estimated_distance_cm"]) for row in stationary],
                 [int(row["adc_value"]) for row in stationary], s=8, color="#94a3b8", alpha=.6, zorder=1)
    nominal = run["metadata"]["approximate_nominal_speed_cm_s"]
    axis.set_title(f'{run["rpm"]} 圈/分（标称约 {nominal:g} cm/s）', loc="left", fontweight="bold")
    axis.text(.98, .95, f'运动区间 {run["metadata"]["duration_s"]:.3f} s\n运动采样 {len(rows)} 点',
              transform=axis.transAxes, ha="right", va="top", fontsize=9, color="#475569")
    axis.set_xlim(8, 82)
    axis.set_ylim(0, 2850)
    axis.xaxis.set_major_locator(MultipleLocator(10))
    axis.yaxis.set_major_locator(MultipleLocator(500))
    axis.set_xlabel("估算距离（cm；运动方向 80 → 10）")
    axis.set_ylabel("原始 ADC 值（通道 8）")
    axis.grid(True, color="#e2e8f0", linewidth=.7)
    axis.set_axisbelow(True)


def write_outputs(runs):
    all_rows = [row for run in runs for row in run["rows"]]
    fields = list(all_rows[0])
    with (HERE / "aligned_raw_samples.csv").open("w", encoding="utf-8-sig", newline="") as output:
        writer = csv.DictWriter(output, fieldnames=fields)
        writer.writeheader()
        writer.writerows(all_rows)
    hashes = {path.name: hashlib.sha256(path.read_bytes()).hexdigest()
              for path in [INPUT / "motor_log.txt"] + sorted(INPUT.glob("ir_sensor_*.csv"))}
    metadata = dict(timezone="UTC+08:00; naive sensor timestamps assigned +08:00 without an additional shift",
                    start_distance_cm=START_CM, end_distance_cm=END_CM,
                    endpoints_confirmed_by_user=True,
                    distance_method="Linear 80-to-10 cm mapping over matched motor command acknowledgement interval",
                    nominal_speed_note="User estimates 200 rpm is about 25 cm/s; other nominal labels scale proportionally. Not independently measured.",
                    motor_timing_note="Start is confirmed motion message; end is RX acknowledgement of stop register. Not encoder-measured mechanical start/stop.",
                    adc_processing="None: no filtering, averaging, smoothing, outlier removal or resampling",
                    source_sha256=hashes, runs=[run["metadata"] for run in runs])
    (HERE / "alignment.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    fig, axes = plt.subplots(2, 2, figsize=(13.6, 9.6), sharex=True, sharey=True)
    for axis, run in zip(axes.flat, runs):
        plot_distance(axis, run)
        axis.tick_params(labelbottom=True, labelleft=True)
    fig.suptitle("红外测距传感器：四种速度下的原始 ADC—距离", fontsize=17, fontweight="bold", y=.98)
    fig.text(.5, .925, "按世界时间匹配电机运行区间；80 → 10 cm 匀速换算；ADC 不滤波、不删点", ha="center", color="#475569")
    fig.text(.5, .018, "彩色：运动中的逐点原始采样；灰色：启停前后的全部采样（置于端点）。距离为时间换算值，未读取滑台位置。", ha="center", fontsize=9, color="#475569")
    fig.tight_layout(rect=(0, .04, 1, .91))
    for suffix in ("png", "svg"):
        fig.savefig(HERE / ("raw_adc_distance_4speeds." + suffix), dpi=200)
    plt.close(fig)
    for run in runs:
        fig, axis = plt.subplots(figsize=(9.5, 6))
        plot_distance(axis, run)
        fig.text(.5, .02, "距离由 80→10 cm 与日志起停时间线性换算；彩色为运动原始采样，灰色为端点静止采样。", ha="center", fontsize=9)
        fig.tight_layout(rect=(0, .05, 1, 1))
        fig.savefig(HERE / f'raw_adc_distance_{run["rpm"]}rpm.png', dpi=200)
        plt.close(fig)

    fig, axis = plt.subplots(figsize=(11, 6.8))
    for run in runs:
        axis.plot([float(row["estimated_distance_cm"]) for row in run["motion"]],
                  [int(row["adc_value"]) for row in run["motion"]], color=COLORS[run["rpm"]],
                  linewidth=.8, marker="o", markersize=2.5, markeredgewidth=0,
                  label=f'{run["rpm"]} 圈/分')
    axis.set(xlim=(10, 80), ylim=(0, 2850), xlabel="估算距离（cm；运动方向 80 → 10）", ylabel="原始 ADC 值（通道 8）",
             title="四种速度的运动区间原始采样对比")
    axis.grid(True, color="#e2e8f0");axis.legend()
    fig.text(.5, .02, "仅展示已匹配的运动区间；逐点绘制，未平均、滤波、剔除或重采样。", ha="center", fontsize=9)
    fig.tight_layout(rect=(0, .05, 1, 1))
    fig.savefig(HERE / "raw_adc_distance_overlay.png", dpi=200)
    plt.close(fig)

    fig, axes = plt.subplots(2, 2, figsize=(13.6, 9), sharey=True)
    for axis, run in zip(axes.flat, runs):
        x = [float(row["time_from_motor_start_s"]) for row in run["rows"]]
        axis.plot(x, [int(row["adc_value"]) for row in run["rows"]], color=COLORS[run["rpm"]], linewidth=.75, marker="o", markersize=2)
        duration = run["metadata"]["duration_s"]
        axis.axvspan(0, duration, color=COLORS[run["rpm"]], alpha=.08)
        for position in (0, duration):
            axis.axvline(position, color="#475569", linestyle="--", linewidth=.8)
        axis.set(title=f'{run["rpm"]} 圈/分｜{len(run["rows"])} 个完整原始样本', xlabel="相对电机启动确认时间（s）", ylabel="原始 ADC 值", ylim=(0, 2850))
        axis.grid(True, color="#e2e8f0")
    fig.suptitle("完整采样时间轴：阴影为日志确认的运动区间", fontsize=16, fontweight="bold")
    fig.tight_layout(rect=(0, 0, 1, .95))
    fig.savefig(HERE / "raw_adc_time_alignment.png", dpi=200)
    plt.close(fig)
    return metadata


def main():
    setup_style()
    runs = [read_run(INPUT / f"ir_sensor_{rpm}.csv", motor_intervals()) for rpm in (25, 50, 100, 200)]
    metadata = write_outputs(runs)
    # 校验全部输入行和 ADC 字符串原样保留，输出距离只用于标注和绘图。
    for run in runs:
        with (INPUT / f'ir_sensor_{run["rpm"]}.csv').open(encoding="utf-8-sig", newline="") as source:
            original = list(csv.DictReader(source))
        assert len(original) == len(run["rows"])
        for before, after in zip(original, run["rows"]):
            assert all(before[key] == after[key] for key in before)
        print(json.dumps(run["metadata"], ensure_ascii=True))
    for name, digest in metadata["source_sha256"].items():
        assert hashlib.sha256((INPUT / name).read_bytes()).hexdigest() == digest
    print("Verified: source files unchanged; all ADC samples preserved")


if __name__ == "__main__":
    main()
