#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""原始 IR 运动数据的离线居中 5 点中值滤波，保留原值与原坐标。"""

import csv
import hashlib
import importlib.util
import json
from pathlib import Path
from statistics import median

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.ticker import MultipleLocator

HERE = Path(__file__).resolve().parent
SOURCE = HERE.parent
RAW = SOURCE / "raw_adc_distance"
WINDOW = 5
COLORS = {25: "#2563eb", 50: "#0f9188", 100: "#d97706", 200: "#b33563"}


def source_hashes():
    paths = list(RAW.glob("*")) + [SOURCE / "motor_log.txt"] + list(SOURCE.glob("ir_sensor_*.csv"))
    return {path.relative_to(SOURCE).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in paths if path.is_file()}


def median_filter(values, size=WINDOW):
    """居中奇数窗口；边界重复端点，不补零，不跨试次或启停阶段。"""
    if size <= 0 or size % 2 == 0:
        raise ValueError("中值窗口必须是正奇数")
    radius = size // 2
    return [median(values[min(len(values) - 1, max(0, j))]
                   for j in range(i - radius, i + radius + 1))
            for i in range(len(values))]


def load_runs():
    alignment = json.loads((RAW / "alignment.json").read_text(encoding="utf-8"))
    for filename, digest in alignment["source_sha256"].items():
        if hashlib.sha256((SOURCE / filename).read_bytes()).hexdigest() != digest:
            raise ValueError("原始输入已变化，请先核对时间对应关系：" + filename)
    with (RAW / "aligned_raw_samples.csv").open(encoding="utf-8-sig", newline="") as source:
        all_rows = list(csv.DictReader(source))
    runs = []
    for meta in alignment["runs"]:
        rpm = meta["rpm"]
        rows = [dict(row) for row in all_rows if int(row["motor_rpm"]) == rpm and row["phase"] == "motion"]
        if len(rows) != meta["motion_rows"] or {row["adc_channel"] for row in rows} != {"8"}:
            raise ValueError("运动样本数或通道与原图对应记录不一致")
        values = [int(row["adc_value"]) for row in rows]
        filtered = median_filter(values)
        for row, value in zip(rows, filtered):
            row["adc_median5"] = str(value)
        times = [float(row["time_from_motor_start_s"]) for row in rows]
        distances = [float(row["estimated_distance_cm"]) for row in rows]
        metadata = dict(rpm=rpm, nominal_speed_cm_s=meta["approximate_nominal_speed_cm_s"],
                        sample_count=len(rows), start_time=meta["start_time"], end_time=meta["end_time"],
                        changed_samples=sum(a != b for a, b in zip(values, filtered)),
                        median_abs_change_adc=median(abs(a - b) for a, b in zip(values, filtered)),
                        max_abs_change_adc=max(abs(a - b) for a, b in zip(values, filtered)),
                        median_full_window_time_span_s=median(times[i + 2] - times[i - 2] for i in range(2, len(times) - 2)),
                        median_full_window_distance_span_cm=median(abs(distances[i + 2] - distances[i - 2]) for i in range(2, len(times) - 2)))
        runs.append(dict(rows=rows, metadata=metadata))
    return runs


def draw_panel(axis, run):
    rows, meta = run["rows"], run["metadata"]
    x = [float(row["estimated_distance_cm"]) for row in rows]
    raw = [int(row["adc_value"]) for row in rows]
    filtered = [float(row["adc_median5"]) for row in rows]
    axis.plot(x, raw, color="#94a3b8", alpha=.7, linewidth=.8, label="原始 ADC", zorder=1)
    axis.plot(x, filtered, color=COLORS[meta["rpm"]], linewidth=1.6,
              marker="o", markersize=2.1, markeredgewidth=0, label="5 点中值滤波", zorder=2)
    axis.set_title(f'{meta["rpm"]} 圈/分（标称约 {meta["nominal_speed_cm_s"]:g} cm/s）', loc="left", fontweight="bold")
    axis.set(xlim=(8, 82), ylim=(0, 2850), xlabel="估算距离（cm；运动方向 80 → 10）", ylabel="ADC 值（通道 8）")
    axis.xaxis.set_major_locator(MultipleLocator(10))
    axis.yaxis.set_major_locator(MultipleLocator(500))
    axis.grid(True, color="#e2e8f0", linewidth=.7)
    axis.set_axisbelow(True)
    axis.text(.98, .96, f'{meta["sample_count"]} 点，样本数不变', transform=axis.transAxes,
              ha="right", va="top", color="#475569", fontsize=9)
    axis.legend(loc="upper right", bbox_to_anchor=(1, .89), frameon=False, fontsize=9)


def main():
    protected = source_hashes()
    spec = importlib.util.spec_from_file_location("ir_plot_style", RAW / "plot_raw.py")
    style = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(style)
    style.setup_style()
    runs = load_runs()

    fields = list(runs[0]["rows"][0])
    with (HERE / "filtered_motion_samples.csv").open("w", encoding="utf-8-sig", newline="") as output:
        writer = csv.DictWriter(output, fieldnames=fields)
        writer.writeheader()
        for run in runs:
            writer.writerows(run["rows"])
    details = dict(method="centered rolling median", window_samples=WINDOW,
                   edge_rule="repeat endpoint values", scope="motion phase only, separately for each speed and trial",
                   offline_only=True, additional_smoothing=False, time_shift_s=0,
                   coordinate_changes=False, sample_deletion=False, resampling=False,
                   distance_method="Unchanged: 80-to-10 cm linear mapping using existing motor acknowledgement timestamps",
                   note="Filters ADC only; does not correct sensor response, clock offset or estimated distance error. Median filtering is not ground truth.",
                   source_sha256=protected, runs=[run["metadata"] for run in runs])
    (HERE / "filter_settings.json").write_text(json.dumps(details, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    fig, axes = plt.subplots(2, 2, figsize=(13.6, 9.6), sharex=True, sharey=True)
    for axis, run in zip(axes.flat, runs):
        draw_panel(axis, run)
        axis.tick_params(labelbottom=True, labelleft=True)
    fig.suptitle("红外测距传感器：5 点中值滤波前后对照", fontsize=17, fontweight="bold", y=.98)
    fig.text(.5, .925, "四组采用相同居中窗口；灰色为原始值，彩色为滤波值；保留原时间、距离和运动样本数", ha="center", color="#475569")
    fig.text(.5, .018, "仅对原图的运动区间离线滤波；80 → 10 cm 为日志时间换算距离。未进行时间偏移、距离标定或响应延迟补偿。", ha="center", fontsize=9, color="#475569")
    fig.tight_layout(rect=(0, .04, 1, .91))
    for suffix in ("png", "svg"):
        fig.savefig(HERE / ("filtered_adc_distance_4speeds." + suffix), dpi=200)
    plt.close(fig)

    for run in runs:
        fig, axis = plt.subplots(figsize=(9.5, 6))
        draw_panel(axis, run)
        fig.text(.5, .02, "离线居中 5 点中值滤波；原始值、时间与距离保留；没有额外平滑或延迟补偿。", ha="center", fontsize=9)
        fig.tight_layout(rect=(0, .05, 1, 1))
        fig.savefig(HERE / f'filtered_adc_distance_{run["metadata"]["rpm"]}rpm.png', dpi=200)
        plt.close(fig)

    fig, axis = plt.subplots(figsize=(11, 6.8))
    for run in runs:
        meta = run["metadata"]
        axis.plot([float(row["estimated_distance_cm"]) for row in run["rows"]],
                  [float(row["adc_median5"]) for row in run["rows"]],
                  color=COLORS[meta["rpm"]], linewidth=1.6, label=f'{meta["rpm"]} 圈/分')
    axis.set(xlim=(10, 80), ylim=(0, 2850), xlabel="估算距离（cm；运动方向 80 → 10）", ylabel="5 点中值滤波 ADC（通道 8）",
             title="四种速度的滤波曲线对比")
    axis.grid(True, color="#e2e8f0");axis.legend(frameon=False)
    fig.text(.5, .02, "相同 5 点窗口对应不同距离跨度；曲线差异不等于已测得的传感器动态误差。", ha="center", fontsize=9)
    fig.tight_layout(rect=(0, .05, 1, 1))
    fig.savefig(HERE / "filtered_adc_distance_overlay.png", dpi=200)
    plt.close(fig)

    assert source_hashes() == protected, "原始数据或原图发生意外修改"
    for run in runs:
        print(json.dumps(run["metadata"], ensure_ascii=True))
    print("Verified: original data and plots unchanged; all 817 motion samples retained")


if __name__ == "__main__":
    main()
