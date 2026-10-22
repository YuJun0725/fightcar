from .application_layer.io import IO
from .application_layer.camera import Camera
from .logic_layer.tag_detector import ApriltagDetector
from .logic_layer.fall_detector import FallDetector
from .mode import ServoMode, TiltState
from .utils.type_util import Number
from dataclasses import dataclass
from typing import Tuple
import time, cv2


@dataclass
class HardwareConfig:
    """
    硬件系统配置类
    """
    # 底盘电机默认ID
    id_left_motor: int = 2
    id_right_motor: int = 1

    # 舵机默认ID
    id_left_hand: int = 8
    id_left_elbow: int = 7
    id_left_shoulder: int = 6
    id_left_hip: int = 11
    id_right_hand: int = 5
    id_right_elbow: int = 4
    id_right_shoulder: int = 3
    id_right_hip: int = 12

    # 传感器默认引脚
    pin_tilt_sensor: int = 8
    pin_grayscale_front: int = 1
    pin_grayscale_back: int = 2
    pin_grayscale_left: int = 3
    pin_grayscale_right: int = 4


class UpAPIBuilder:
    """
    UpAPI构建器类
    """

    def __init__(self):
        self.__config = HardwareConfig()

    def set_motors(self, left: int, right: int) -> 'UpAPIBuilder':
        """
        设置底盘电机 ID

        :param left: 左侧电机 ID
        :param right: 右侧电机 ID
        :return: UpAPIBuilder 实例
        """
        self.__config.id_left_motor = left
        self.__config.id_right_motor = right
        return self

    def set_left_servos(self, hand: int, elbow: int, shoulder: int, hip: int) -> 'UpAPIBuilder':
        """
        设置左侧舵机 ID

        :param hand: 手部舵机 ID
        :param elbow: 肘部舵机 ID
        :param shoulder: 肩部舵机 ID
        :param hip: 胯部舵机 ID
        :return: UpAPIBuilder 实例
        """
        self.__config.id_left_hand = hand
        self.__config.id_left_elbow = elbow
        self.__config.id_left_shoulder = shoulder
        self.__config.id_left_hip = hip
        return self

    def set_right_servos(self, hand: int, elbow: int, shoulder: int, hip: int) -> 'UpAPIBuilder':
        """
        设置右侧舵机 ID

        :param hand: 手部舵机 ID
        :param elbow: 肘部舵机 ID
        :param shoulder: 肩部舵机 ID
        :param hip: 胯部舵机 ID
        :return: UpAPIBuilder 实例
        """
        self.__config.id_right_hand = hand
        self.__config.id_right_elbow = elbow
        self.__config.id_right_shoulder = shoulder
        self.__config.id_right_hip = hip
        return self

    def set_tilt_pin(self, tilt: int) -> 'UpAPIBuilder':
        """
        设置倾角传感器引脚

        :param tilt: 倾角传感器引脚
        :return: UpAPIBuilder 实例
        """
        self.__config.pin_tilt_sensor = tilt
        return self

    def set_grayscale_pins(self, front: int, back: int, left: int, right: int) -> 'UpAPIBuilder':
        """
        设置灰度传感器引脚

        :param front: 前方灰度传感器引脚
        :param back: 后方灰度传感器引脚
        :param left: 左侧灰度传感器引脚
        :param right: 有侧灰度传感器引脚
        :return: UpAPIBuilder 实例
        """
        self.__config.pin_grayscale_front = front
        self.__config.pin_grayscale_back = back
        self.__config.pin_grayscale_left = left
        self.__config.pin_grayscale_right = right
        return self

    def build(self) -> 'UpAPI':
        """
        创建 UpAPI 实例

        :return: UpAPI 实例
        """
        return UpAPI._UpAPI__create(self.__config)


class UpAPI:
    """
    实现防直接实例化的单例类
    """

    class __ConstructionToken:  # 私有控制令牌
        def __init__(self):
            assert __class__.__name__.startswith("__"), "Token class access violation"

    _instance = None

    def __init__(self, config: HardwareConfig, token: __ConstructionToken):
        """
        通过私有令牌控制构造函数访问
        """
        if not isinstance(token, self.__ConstructionToken):
            raise RuntimeError("不可直接实例化 UpApi，请使用 UpAPIBuilder.build()")

        # 硬件系统配置
        self.__init_hardware_config(config)

        # 子系统初始化
        self.__io = IO()
        self.__camera = Camera()

        # 初始化舵机模式
        self.__init_servo_mode()

        # 逻辑处理器
        self.__apriltag_detector = ApriltagDetector()
        self.__fall_detector = FallDetector()

    def __init_hardware_config(self, config: HardwareConfig) -> None:
        """
        初始化硬件参数
        """
        self.__id_left_motor = config.id_left_motor
        self.__id_right_motor = config.id_right_motor

        self.__id_left_hand = config.id_left_hand
        self.__id_left_elbow = config.id_left_elbow
        self.__id_left_shoulder = config.id_left_shoulder
        self.__id_left_hip = config.id_left_hip

        self.__id_right_hand = config.id_right_hand
        self.__id_right_elbow = config.id_right_elbow
        self.__id_right_shoulder = config.id_right_shoulder
        self.__id_right_hip = config.id_right_hip

        self.__pin_tilt_sensor = config.pin_tilt_sensor
        self.__pin_grayscale_front = config.pin_grayscale_front
        self.__pin_grayscale_back = config.pin_grayscale_back
        self.__pin_grayscale_left = config.pin_grayscale_left
        self.__pin_grayscale_right = config.pin_grayscale_right

    def __init_servo_mode(self):
        """
        初始化手臂舵机
        """
        servo_mode = ServoMode.SERVO.value

        self.__io.set_servo_mode(self.__id_left_hand, servo_mode)
        self.__io.set_servo_mode(self.__id_left_elbow, servo_mode)
        self.__io.set_servo_mode(self.__id_left_shoulder, servo_mode)
        self.__io.set_servo_mode(self.__id_left_hip, servo_mode)

        self.__io.set_servo_mode(self.__id_right_hand, servo_mode)
        self.__io.set_servo_mode(self.__id_right_elbow, servo_mode)
        self.__io.set_servo_mode(self.__id_right_shoulder, servo_mode)
        self.__io.set_servo_mode(self.__id_right_hip, servo_mode)

    @classmethod
    def __create(cls, config) -> 'UpAPI':
        """
        仅限构建器调用的创建方法
        """
        if cls._instance is not None:
            raise RuntimeError("硬件系统已初始化，禁止重复操作")
        cls._instance = cls(config, cls.__ConstructionToken())
        return cls._instance

    # -------------------- 移动控制 --------------------

    def move(self, left_speed: int = 200, right_speed: int = 200) -> None:
        """
        移动

        :param left_speed: 左轮速度（默认 200）
        :param right_speed: 右轮速度（默认 200）
        """
        self.__io.set_servo_speed(self.__id_left_motor, left_speed)
        self.__io.set_servo_speed(self.__id_right_motor, -right_speed)

    def stop(self) -> None:
        """
        停止
        """
        self.move(0, 0)

    def move_forward(self, speed: int = 200) -> None:
        """
        前进

        :param speed: 移动速度（默认 200）
        """
        self.move(speed, speed)

    def move_backward(self, speed: int = 200) -> None:
        """
        后退

        :param speed: 移动速度（默认 200）
        """
        self.move(-speed, -speed)

    def turn_left(self, speed: int = 200) -> None:
        """
        左旋

        :param speed: 自旋速度（默认 200）
        """
        self.move(-speed, speed)

    def turn_right(self, speed: int = 200) -> None:
        """
        左旋

        :param speed: 自旋速度（默认 200）
        """
        self.move(speed, -speed)

    # -------------------- 硬件数据 --------------------

    def get_camera_frame(self) -> cv2.typing.MatLike:
        """
        从帧图像队列获取相机数据

        :return: 相机图像数据
        """
        ret, frame = self.__camera.get_camera().read()
        if ret:
            return frame
        raise RuntimeError("从相机获取数据失败")

    def get_adc_data_from_channel(self, channel: int) -> Number:
        """
        获取指定引脚通道的模拟量数据

        :param channel: 引脚通道号
        :return: 指定引脚通道的模拟量数据
        """
        channel_adc_data = self.__io.get_adc_data_from_channel(channel)
        return channel_adc_data

    # -------------------- 逻辑处理 --------------------

    def display_camera_frame(self) -> None:
        """
        显示图像
        """
        frame = self.get_camera_frame()
        if frame is not None:
            cv2.imshow("camera", frame)
            cv2.waitKey(1)

    def detect_apriltag(self, ignore_id: int = None) -> Tuple[bool, int, int]:
        """
        检测 Apriltag

        :param ignore_id: 忽略的 ID
        :return: 是否找到 Apriltag，Apriltag 的 ID，水平方向偏移量
        """
        frame = self.get_camera_frame()

        if frame is not None:
            find_apriltag, tag_id, offset_x = self.__apriltag_detector.process_frame(frame, ignore_id)
            return find_apriltag, tag_id, offset_x

        return False, -1, 0

    def detect_tilt_state(self, debug: bool = False) -> TiltState:
        """
        检测倾角状态

        :param debug: 是否调试
        :return: 倾角状态
        """
        tilt_data = self.get_adc_data_from_channel(self.__pin_tilt_sensor)

        if debug:
            print(f"倾角传感器数据：{tilt_data}")

        tilt_state = self.__fall_detector.detect_angle(tilt_data)
        if tilt_state == 1:  # 没有倒
            return TiltState.STAND

        elif tilt_state == 2:  # 前倾
            return TiltState.FALL_FORWARD

        elif tilt_state == 3:  # 后倾
            return TiltState.FALL_BACKWARD

        else:  # 边缘状态
            return TiltState.EDGE

    def get_grayscale_data(self) -> Tuple[int, int, int, int]:
        """
        灰度传感器数据

        :return: 前部灰度传感器数据，后部灰度传感器数据，左侧灰度传感器数据，右侧灰度传感器数据
        """
        front = self.get_adc_data_from_channel(self.__pin_grayscale_front)
        back = self.get_adc_data_from_channel(self.__pin_grayscale_back)
        left = self.get_adc_data_from_channel(self.__pin_grayscale_left)
        right = self.get_adc_data_from_channel(self.__pin_grayscale_right)
        return front, back, left, right

    # -------------------- 手臂控制 --------------------

    def set_servo_angle(self, servo_id, angle, speed) -> None:
        """
        设置舵机以指定速度旋转到指定角度

        :param servo_id: 舵机 ID
        :param angle: 旋转角度
        :param speed: 旋转速度
        """
        self.__io.set_servo_angle(servo_id, angle, speed)

    def set_servo_speed(self, servo_id, speed) -> None:
        """
        设置舵机以指定速度旋转

        :param servo_id: 舵机 ID
        :param speed: 旋转速度
        """
        self.__io.set_servo_speed(servo_id, speed)

    def get_servo_angle(self, servo_id) -> Number:
        """
        获取舵机当前角度

        :param servo_id: 舵机 ID
        :return: 当前角度
        """
        angle = self.__io.get_servo_angle(servo_id)
        return angle

    def action_standby(self) -> None:
        """
        在台上待机默认动作
        """

        # 左侧
        self.set_servo_angle(self.__id_left_hand, 717, 1000)
        self.set_servo_angle(self.__id_left_elbow, 949, 1000)
        self.set_servo_angle(self.__id_left_shoulder, 512, 1000)
        self.set_servo_angle(self.__id_left_hip, 512, 1000)

        # 右侧
        self.set_servo_angle(self.__id_right_hand, 307, 1000)
        self.set_servo_angle(self.__id_right_elbow, 75, 1000)
        self.set_servo_angle(self.__id_right_shoulder, 512, 1000)
        self.set_servo_angle(self.__id_right_hip, 512, 1000)

    def action_stand_up_from_fall_forward(self) -> None:
        """
        从向前倒下的姿态站起
        """
        self.set_servo_angle(self.__id_left_hand, 717, 512)
        self.set_servo_angle(self.__id_left_elbow, 949, 512)
        self.set_servo_angle(self.__id_left_shoulder, 512, 512)
        self.set_servo_angle(self.__id_left_hip, 512, 512)
        self.set_servo_angle(self.__id_right_hand, 307, 512)
        self.set_servo_angle(self.__id_right_elbow, 75, 512)
        self.set_servo_angle(self.__id_right_shoulder, 512, 512)
        self.set_servo_angle(self.__id_right_hip, 512, 512)
        time.sleep(1.5)
        self.set_servo_angle(self.__id_left_shoulder, 82, 812)
        self.set_servo_angle(self.__id_left_hip, 562, 512)
        self.set_servo_angle(self.__id_right_shoulder, 942, 812)
        self.set_servo_angle(self.__id_right_hip, 462, 512)
        time.sleep(2)
        self.set_servo_angle(self.__id_left_elbow, 649, 512)
        self.set_servo_angle(self.__id_right_elbow, 375, 512)
        time.sleep(0.5)
        self.set_servo_angle(self.__id_left_hand, 512, 512)
        self.set_servo_angle(self.__id_left_elbow, 512, 512)
        self.set_servo_angle(self.__id_left_shoulder, 112, 812)
        self.set_servo_angle(self.__id_left_hip, 512, 512)
        self.set_servo_angle(self.__id_right_hand, 512, 512)
        self.set_servo_angle(self.__id_right_elbow, 512, 512)
        self.set_servo_angle(self.__id_right_shoulder, 912, 812)
        self.set_servo_angle(self.__id_right_hip, 512, 512)
        time.sleep(2)
        self.set_servo_angle(self.__id_left_shoulder, 262, 812)
        self.set_servo_angle(self.__id_left_hip, 362, 512)
        self.set_servo_angle(self.__id_right_shoulder, 762, 812)
        self.set_servo_angle(self.__id_right_hip, 662, 512)
        time.sleep(1.5)
        self.set_servo_angle(self.__id_left_hand, 712, 812)
        self.set_servo_angle(self.__id_right_hand, 312, 812)
        time.sleep(0.5)
        self.set_servo_angle(self.__id_left_hand, 717, 512)
        self.set_servo_angle(self.__id_left_elbow, 949, 512)
        self.set_servo_angle(self.__id_left_shoulder, 512, 512)
        self.set_servo_angle(self.__id_left_hip, 512, 512)
        self.set_servo_angle(self.__id_right_hand, 307, 512)
        self.set_servo_angle(self.__id_right_elbow, 75, 512)
        self.set_servo_angle(self.__id_right_shoulder, 512, 512)
        self.set_servo_angle(self.__id_right_hip, 512, 512)
        self.move_backward(500)
        time.sleep(0.3)
        self.stop()
        time.sleep(0.01)

    def action_stand_up_from_fall_backward(self) -> None:
        """
        从向后倒下的姿态站起
        """
        self.set_servo_angle(self.__id_left_hand, 717, 512)
        self.set_servo_angle(self.__id_left_elbow, 949, 512)
        self.set_servo_angle(self.__id_left_shoulder, 512, 512)
        self.set_servo_angle(self.__id_left_hip, 512, 512)
        self.set_servo_angle(self.__id_right_hand, 307, 512)
        self.set_servo_angle(self.__id_right_elbow, 75, 512)
        self.set_servo_angle(self.__id_right_shoulder, 512, 512)
        self.set_servo_angle(self.__id_right_hip, 512, 512)
        time.sleep(1.5)
        self.set_servo_angle(self.__id_left_shoulder, 942, 812)
        self.set_servo_angle(self.__id_left_hip, 462, 512)
        self.set_servo_angle(self.__id_right_shoulder, 82, 812)
        self.set_servo_angle(self.__id_right_hip, 562, 512)
        time.sleep(2)
        self.set_servo_angle(self.__id_left_elbow, 649, 512)
        self.set_servo_angle(self.__id_right_elbow, 375, 512)
        time.sleep(0.5)
        self.set_servo_angle(self.__id_left_hand, 512, 512)
        self.set_servo_angle(self.__id_left_elbow, 512, 512)
        self.set_servo_angle(self.__id_left_shoulder, 912, 812)
        self.set_servo_angle(self.__id_left_hip, 512, 512)
        self.set_servo_angle(self.__id_right_hand, 512, 512)
        self.set_servo_angle(self.__id_right_elbow, 512, 512)
        self.set_servo_angle(self.__id_right_shoulder, 112, 812)
        self.set_servo_angle(self.__id_right_hip, 512, 512)
        time.sleep(2)
        self.set_servo_angle(self.__id_left_shoulder, 762, 812)
        self.set_servo_angle(self.__id_left_hip, 712, 512)
        self.set_servo_angle(self.__id_right_shoulder, 262, 812)
        self.set_servo_angle(self.__id_right_hip, 312, 512)
        time.sleep(1.5)
        self.set_servo_angle(self.__id_left_hand, 712, 812)
        self.set_servo_angle(self.__id_right_hand, 312, 812)
        time.sleep(0.5)
        self.set_servo_angle(self.__id_left_hand, 717, 512)
        self.set_servo_angle(self.__id_left_elbow, 949, 512)
        self.set_servo_angle(self.__id_left_shoulder, 512, 512)
        self.set_servo_angle(self.__id_left_hip, 512, 512)
        self.set_servo_angle(self.__id_right_hand, 307, 512)
        self.set_servo_angle(self.__id_right_elbow, 75, 512)
        self.set_servo_angle(self.__id_right_shoulder, 512, 512)
        self.set_servo_angle(self.__id_right_hip, 512, 512)

    def action_attack(self) -> None:
        """
        攻击
        """
        self.set_servo_angle(self.__id_left_hand, 686, 1000)
        self.set_servo_angle(self.__id_left_elbow, 315, 1000)
        self.set_servo_angle(self.__id_left_shoulder, 200, 1000)
        self.set_servo_angle(self.__id_left_hip, 512, 1000)
        self.set_servo_angle(self.__id_right_hand, 305, 1000)
        self.set_servo_angle(self.__id_right_elbow, 715, 1000)
        self.set_servo_angle(self.__id_right_shoulder, 815, 1000)
        self.set_servo_angle(self.__id_right_hip, 512, 1000)
