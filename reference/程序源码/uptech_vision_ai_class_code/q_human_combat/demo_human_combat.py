from sdk.api import UpAPIBuilder
from sdk.logic import PIDController, GrayscaleNavigator, Timer
from sdk.mode import TiltState, NavigateDirection
from enum import Enum, auto

"""
仿人散打

主状态机切换：
上台 ----- 上台完成 ------> 巡台
巡台 -- 发现 April Tag --> 攻击
攻击 ---- 到达地图边缘 ----> 巡台
巡台 ------- 倒下 -------> 起身
起身 ----- 起身完成 ------> 巡台
"""


class MainState(Enum):
    """
    机器人主状态
    """
    ARENA = auto()  # 上台
    PATROL = auto()  # 巡台
    ATTACK = auto()  # 攻击（识别到并攻击 April Tag）
    STAND = auto()  # 起身


class PatrolState(Enum):
    """
    巡台状态
    """
    MOVE_TO_CENTER = auto()  # 前进到地图中心
    TURN_BACK = auto()  # 向后转
    SPIN = auto()  # 自旋


class RobotController:
    def __init__(self):
        # 硬件设置
        self.motor_ids = {
            "left": 2,  # 左侧电机 ID
            "right": 1  # 右侧电机 ID
        }
        self.servo_ids = {
            "left_hand": 8,  # 左侧手部舵机 ID
            "left_elbow": 7,  # 左侧肘部舵机 ID
            "left_shoulder": 6,  # 左侧肩部舵机 ID
            "left_hip": 11,  # 左侧胯舵机 ID
            "right_hand": 5,  # 右侧手部舵机 ID
            "right_elbow": 4,  # 右侧肘部舵机 ID
            "right_shoulder": 3,  # 右侧肩部舵机 ID
            "right_hip": 12  # 右侧胯部舵机 ID
        }
        self.sensor_pins = {
            "tilt": 8,  # 倾角传感器引脚号
            "grayscale_front": 1,  # 前方灰度传感器引脚号
            "grayscale_back": 2,  # 后方灰度传感器引脚号
            "grayscale_left": 3,  # 左侧灰度传感器引脚号
            "grayscale_right": 4  # 右侧灰度传感器引脚号
        }

        # 灰度传感器采样参数
        grayscale_data_samples = {
            "left": 1960,  # 左侧灰度传感器在地图中取样点的数据
            "right": 2090  # 右侧灰度传感器在地图中取样点的数据
        }

        # 灰度传感器检测到地图边缘时的数据（前、后、左、右）
        grayscale_data_edge = [3245, 2940, 2455, 2590]

        # 速度参数
        self.speed_move = 200  # 移动速度
        self.speed_move_max = 255  # 最大移动速度
        self.speed_turn = 200  # 旋转速度

        # 时间参数
        self.time_turn_back = 2000  # 向后转的时间，单位毫秒
        self.time_arena = 3600  # 登台的时间，单位毫秒

        # PID 控制参数
        self.Kp = 0.5  # 比例参数
        self.Ki = 0.0  # 积分参数
        self.Kd = 0.1  # 微分参数

        # April Tag ID 参数
        self.tag_id_friendly = 5  # 友方能量块 ID

        # 状态机
        self.state_main = MainState.ARENA
        self.state_patrol = PatrolState.MOVE_TO_CENTER

        # 接口
        self.api = self.__build_api()

        # 逻辑控制
        self.pid = PIDController(Kp=self.Kp, Ki=self.Ki, Kd=self.Kd)
        self.navigator = GrayscaleNavigator(
            left_grayscale_sample=grayscale_data_samples["left"],
            right_grayscale_sample=grayscale_data_samples["right"],
            sample_edge=grayscale_data_edge
        )

        # 计时器
        self.timer_turn_back = Timer(self.time_turn_back)  # 向后转
        self.timer_arena = Timer(self.time_arena)  # 登台

        # 计数器
        self.counter_fall_down = 0  # 倒地计数器
        self.counter_fall_down_max = 5  # 最大倒地计数

        self.counter_no_target = 0  # 视野中没有 April Tag
        self.counter_no_target_max = 20

        self.arm_attack = True

    def run(self):

        while True:
            # 传感器数据
            find_apriltag, tag_id, offset_x = self.api.detect_apriltag(self.tag_id_friendly)
            tilt_state = self.api.detect_tilt_state()
            grayscale_data = self.api.get_grayscale_data()

            # 数据处理
            action = self.navigator.control_strategy(grayscale_data)  # 灰度导航

            # 倾倒检测
            if tilt_state == TiltState.FALL_FORWARD or tilt_state == TiltState.FALL_BACKWARD:

                if self.counter_fall_down > self.counter_fall_down_max:
                    print("倒下了")

                    self.counter_fall_down = 0
                    self.state_main = MainState.STAND

                else:
                    self.counter_fall_down += 1

            elif tilt_state == TiltState.STAND:
                self.counter_fall_down = 0

            # 状态控制与动作执行
            if self.state_main == MainState.ARENA:

                if self.timer_arena.complete():
                    print("上台完成")

                    self.state_main = MainState.PATROL
                    self.state_patrol = PatrolState.MOVE_TO_CENTER

                else:
                    print("上台中")

                    self.api.move_forward(self.speed_move)

                    if self.arm_attack:
                        self.api.action_standby()
                        self.arm_attack = False

            elif self.state_main == MainState.PATROL:

                if self.state_patrol == PatrolState.MOVE_TO_CENTER:
                    print(f"向中心移动：{action}")

                    if action == NavigateDirection.LEFT:
                        self.api.turn_left()

                    elif action == NavigateDirection.RIGHT:
                        self.api.turn_right()

                    elif action == NavigateDirection.FORWARD:
                        self.api.move_forward()

                    elif action == NavigateDirection.BACKWARD:
                        self.api.move_backward()

                    else:
                        self.api.stop()

                        print("开始旋转寻找 April Tag")

                        self.state_main = MainState.PATROL
                        self.state_patrol = PatrolState.SPIN

                elif self.state_patrol == PatrolState.TURN_BACK:

                    if not self.timer_turn_back.in_progress:
                        print("开始向后转")

                        self.timer_turn_back.start()

                    if self.timer_turn_back.complete():
                        print("向后转完成，向中心巡台")

                        self.state_main = MainState.PATROL
                        self.state_patrol = PatrolState.MOVE_TO_CENTER

                    else:
                        self.api.turn_left(self.speed_turn)

                        if self.arm_attack:
                            self.api.action_standby()
                            self.arm_attack = False

                elif self.state_patrol == PatrolState.SPIN:

                    if find_apriltag:
                        print("找到 April Tag，开始攻击")

                        self.state_main = MainState.ATTACK

                    else:
                        print("向右转，寻找 April Tag")
                        self.api.turn_right(self.speed_turn)

            elif self.state_main == MainState.ATTACK:

                if find_apriltag:
                    self.__move_to_tag(offset_x)

                    if not self.arm_attack:
                        self.api.action_attack()
                        self.arm_attack = True

                else:
                    if self.counter_no_target > self.counter_no_target_max:
                        print("攻击完成，开始向后转")

                        self.counter_no_target = 0

                        self.state_main = MainState.PATROL
                        self.state_patrol = PatrolState.TURN_BACK

                    else:
                        self.counter_no_target += 1
                        self.api.move_forward(self.speed_move)

            elif self.state_main == MainState.STAND:

                if tilt_state == TiltState.FALL_FORWARD:

                    print("开始从向前倒下的姿态起身")
                    self.api.action_stand_up_from_fall_forward()
                    print("从向前倒下的姿态起身完成")

                    print("开始向中心移动")
                    self.state_main = MainState.PATROL
                    self.state_patrol = PatrolState.MOVE_TO_CENTER

                elif tilt_state == TiltState.FALL_BACKWARD:

                    print("开始从向后倒下的姿态起身")
                    self.api.action_stand_up_from_fall_backward()
                    print("从向后倒下的姿态起身完成")

                    print("开始向中心移动")
                    self.state_main = MainState.PATROL
                    self.state_patrol = PatrolState.MOVE_TO_CENTER
                else:
                    print(f"tilt_state: {tilt_state}")

    def __build_api(self):
        api_builder = UpAPIBuilder()
        api_builder.set_motors(
            left=self.motor_ids["left"],
            right=self.motor_ids["right"]
        ).set_left_servos(
            hand=self.servo_ids["left_hand"],
            elbow=self.servo_ids["left_elbow"],
            shoulder=self.servo_ids["left_shoulder"],
            hip=self.servo_ids["left_hip"]
        ).set_right_servos(
            hand=self.servo_ids["right_hand"],
            elbow=self.servo_ids["right_elbow"],
            shoulder=self.servo_ids["right_shoulder"],
            hip=self.servo_ids["right_hip"]
        ).set_tilt_pin(
            tilt=self.sensor_pins["tilt"]
        ).set_grayscale_pins(
            front=self.sensor_pins["grayscale_front"],
            back=self.sensor_pins["grayscale_back"],
            left=self.sensor_pins["grayscale_left"],
            right=self.sensor_pins["grayscale_right"]
        )
        return api_builder.build()

    def __move_to_tag(self, offset_x):
        control_output = self.pid.compute(offset_x)

        # 计算基础速度
        base_speed = self.speed_move
        left_speed = base_speed + control_output
        right_speed = base_speed - control_output

        # 速度限幅
        left_speed = int(max(0, min(self.speed_move_max, left_speed)))
        right_speed = int(max(0, min(self.speed_move_max, right_speed)))

        print(f"left_speed: {left_speed}, right_speed: {right_speed}")

        # 执行移动
        self.api.move(left_speed, right_speed)


if __name__ == "__main__":
    controller = RobotController()
    controller.run()
