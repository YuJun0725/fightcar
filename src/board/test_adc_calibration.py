#这里用的是输入口ADC8


import time
from uptech import UpTech

up = UpTech()
up.ADC_IO_Open()

# 最后一个 ADC 通道
ADC_CHANNEL = 8

# 标定距离，单位 cm
DISTANCES = range(10, 81, 10)

# 每个距离采集 20 次
SAMPLES = 20

results = []

print("红外距离传感器标定")
print("读取通道：ADC{}".format(ADC_CHANNEL))
print("请依次将目标放在 10~80 cm 处\n")

try:
    for distance in DISTANCES:
        input("将目标放在 {} cm 处，稳定后按回车...".format(distance))

        time.sleep(0.5)
        values = []

        for _ in range(SAMPLES):
            value = up.ADC_Get_Channel(ADC_CHANNEL)
            values.append(float(value))
            time.sleep(0.05)

        avg = sum(values) / len(values)

        print("距离: {} cm | ADC平均值: {:.3f} | 波动范围: {:.3f}~{:.3f}\n".format(
            distance, avg, min(values), max(values)
        ))

        results.append((distance, avg))

    print("\n===== 最终标定数据 =====")
    print("距离(cm)\tADC平均值")

    for distance, avg in results:
        print("{}\t\t{:.3f}".format(distance, avg))

except KeyboardInterrupt:
    print("\n标定中断")

print("程序结束")
