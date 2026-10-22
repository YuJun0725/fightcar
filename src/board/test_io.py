
import time
from uptech import UpTech

up = UpTech()
up.ADC_IO_Open()

print("读取 IO0~IO7，请交替遮挡和放开传感器")

try:
    while True:
        values = []

        for i in range(8):
            value = up.ADC_IO_GetInputLevel(i)
            values.append(value)

        print("  ".join(
            "IO{}={}".format(i, values[i])
            for i in range(8)
        ))

        time.sleep(0.2)

except KeyboardInterrupt:
    print("\n测试结束")
