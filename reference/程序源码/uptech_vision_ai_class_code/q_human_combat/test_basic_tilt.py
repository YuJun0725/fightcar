from sdk.api import UpAPIBuilder
from sdk.mode import TiltState

"""
基础测试：倾角传感器

显示倾角传感器数据和机器人状态

退出：Ctrl + Z
"""

if __name__ == "__main__":
    tilt_pin = 8  # 倾角传感器引脚号

    api_builder = UpAPIBuilder()
    api_builder.set_tilt_pin(tilt_pin)
    api = api_builder.build()

    while True:

        tilt_state = api.detect_tilt_state(debug=True)

        if tilt_state == TiltState.STAND:
            print("站立")

        elif tilt_state == TiltState.FALL_FORWARD:
            print("向前倾倒")

        elif tilt_state == TiltState.FALL_BACKWARD:
            print("向后倾倒")

        elif tilt_state == TiltState.EDGE:
            print("边缘状态")
