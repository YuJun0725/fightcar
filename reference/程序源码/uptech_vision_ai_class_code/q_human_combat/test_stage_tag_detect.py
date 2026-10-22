from sdk.api import UpAPIBuilder
from sdk.logic import PIDController

"""
阶段测试：攻击 April Tag

退出：Ctrl + Z
"""


if __name__ == "__main__":
    base_speed = 200

    Kp = 0.5
    Ki = 0.0
    Kd = 0.1

    api = UpAPIBuilder().build()
    pid = PIDController(Kp, Ki, Kd)

    counter_no_target = 0
    counter_no_target_max = 20

    while True:

        find_apriltag, tag_id, offset_x = api.detect_apriltag()

        if find_apriltag:
            
            if counter_no_target != 0:
                counter_no_target = 0
            
            api.action_attack()

            control_output = pid.compute(offset_x)

            # 计算基础速度
            left_speed = base_speed + control_output
            right_speed = base_speed - control_output

            # 速度限幅（0-255）
            left_speed = int(max(0, min(255, left_speed)))
            right_speed = int(max(0, min(255, right_speed)))

            print(f"left_speed: {left_speed}, right_speed: {right_speed}")

            # 执行移动
            api.move(left_speed, right_speed)

        else:

            if counter_no_target > counter_no_target_max:
                api.stop()
                api.action_standby()

            else:
                counter_no_target += 1
                api.move_forward(base_speed)
