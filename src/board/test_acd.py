import time
from uptech import UpTech

# 创建控制器对象
up = UpTech()

# 初始化 ADC（和之前一样）
up.ADC_IO_Open()

print("开始读取 ADC0~ADC8")
print("请交替遮挡和放开红外传感器，按 Ctrl+C 退出")

try:
    while True:
        values = []

        for ch in range(9):      # ADC0 ~ ADC8
            value = up.ADC_Get_Channel(ch)
            values.append(value)

        print(" | ".join(
            "ADC{}={:.2f}".format(i, values[i])
            for i in range(9)
        ))

        time.sleep(0.2)

except KeyboardInterrupt:
    print("\n测试结束")