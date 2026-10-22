from sdk.api import UpAPIBuilder
from sdk.logic import GrayscaleNavigator
from sdk.mode import NavigateDirection

"""
阶段测试：巡台

退出：Ctrl + Z
"""


if __name__ == "__main__":
    grayscale_pins = {
        "front": 1,  # 前方灰度传感器引脚号
        "back": 2,  # 后方灰度传感器引脚号
        "left": 3,  # 左侧灰度传感器引脚号
        "right": 4  # 右侧灰度传感器引脚号
    }

    grayscale_data_samples = {
        "left": 1960,  # 左侧灰度传感器在地图中取样点的数据
        "right": 2090  # 右侧灰度传感器在地图中取样点的数据
    }

    api_builder = UpAPIBuilder()
    api_builder.set_grayscale_pins(
        front=grayscale_pins["front"],
        back=grayscale_pins["back"],
        left=grayscale_pins["left"],
        right=grayscale_pins["right"]
    )
    api = api_builder.build()

    navigator = GrayscaleNavigator(grayscale_data_samples["left"], grayscale_data_samples["right"])

    while True:

        front, back, left, right = api.get_grayscale_data()
        grayscale = (front, back, left, right)
        print(f"front: {front}, back: {back}, left: {left}, right: {right}")

        # 40cm位置检测
        print(f"threshold: {navigator.euclidean_distance(grayscale)}")
        if navigator.euclidean_distance(grayscale) < navigator.distance_edge_threshold:
            print("检测到40cm位置，启动返回程序")

        # 执行控制策略
        action = navigator.control_strategy(grayscale)

        print(f"action: {action}")

        if action == NavigateDirection.LEFT:
            api.turn_left()
        
        elif action == NavigateDirection.RIGHT:
            api.turn_right()
        
        elif action == NavigateDirection.FORWARD:
            api.move_forward()
        
        elif action == NavigateDirection.BACKWARD:
            api.move_backward()
        
        else:
            api.stop()
