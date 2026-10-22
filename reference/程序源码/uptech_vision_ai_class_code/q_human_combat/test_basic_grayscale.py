from sdk.api import UpAPIBuilder

"""
基础测试：灰度传感器
"""

if __name__ == "__main__":
    grayscale_pins = {
        "front": 1,  # 前方灰度传感器引脚号
        "back": 2,  # 后方灰度传感器引脚号
        "left": 3,  # 左侧灰度传感器引脚号
        "right": 4  # 右侧灰度传感器引脚号
    }

    api_builder = UpAPIBuilder()
    api_builder.set_grayscale_pins(
        front=grayscale_pins["front"],
        back=grayscale_pins["back"],
        left=grayscale_pins["left"],
        right=grayscale_pins["right"]
    )
    api = api_builder.build()

    while True:

        front, back, left, right = api.get_grayscale_data()

        print(f"灰度传感器 前：{front}，后：{back}， 左：{left}，右：{right}")
