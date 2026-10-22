import time
import sys

sys.path.append("..")

from uptech import UpTech


def get_cpu_usage():
    # 读取 /proc/stat 文件获取 CPU 使用情况
    with open("/proc/stat", "r") as f:
        lines = f.readlines()
    for line in lines:
        if line.startswith("cpu "):
            parts = line.split()
            # CPU 时间统计（user, nice, system, idle, iowait, irq, softirq, steal, guest, guest_nice）
            total_time = sum(map(int, parts[1:]))
            idle_time = int(parts[4])
            return total_time, idle_time


def calculate_cpu_percent(prev_total, prev_idle, curr_total, curr_idle):
    # 计算 CPU 使用率
    total_diff = curr_total - prev_total
    idle_diff = curr_idle - prev_idle
    if total_diff == 0:
        return 0.0
    cpu_percent = 100.0 * (total_diff - idle_diff) / total_diff
    return cpu_percent


def get_ram_usage():
    # 读取 /proc/meminfo 文件获取内存使用情况
    meminfo = {}
    with open("/proc/meminfo", "r") as f:
        for line in f:
            key, value = line.split(":", 1)
            meminfo[key] = value.strip().split()[0]

    # 计算内存使用率
    total = int(meminfo["MemTotal"])  # KB
    available = int(meminfo["MemAvailable"])  # KB
    used = total - available
    percent = (used / total) * 100
    return total, used, percent


if __name__ == "__main__":
    uptech = UpTech()

    try:
        uptech.ADC_IO_Open()

        # 第一次读取 CPU 时间（用于计算初始差值）
        prev_total, prev_idle = get_cpu_usage()
        time.sleep(1)  # 等待 1 秒

        while True:
            # 获取当前 CPU 时间
            curr_total, curr_idle = get_cpu_usage()
            # 计算 CPU 使用率
            cpu_percent = calculate_cpu_percent(prev_total, prev_idle, curr_total, curr_idle)
            prev_total, prev_idle = curr_total, curr_idle

            # 获取 RAM 使用情况
            ram_total_kb, ram_used_kb, ram_percent = get_ram_usage()
            ram_total_gb = ram_total_kb / (1024 * 1024)  # KB → GB
            ram_used_gb = ram_used_kb / (1024 * 1024)  # KB → GB

            # 获取引脚数据
            adc_data = uptech.ADC_Get_All_Channel()
            io_data = uptech.ADC_IO_GetAllInputLevel()

            # 打印结果
            print(f"CPU 使用率: {cpu_percent:.1f}%")
            print(f"RAM 使用情况: {ram_used_gb:.2f}GB / {ram_total_gb:.2f}GB ({ram_percent:.1f}%)")
            print(f"ADC 数据: {adc_data}")
            print(f"IO 数据: {io_data}")
            print("-" * 40)

            # 每隔2秒更新一次
            time.sleep(2)

    except KeyboardInterrupt:
        uptech.ADC_IO_Close()
        print("\n程序已停止")
