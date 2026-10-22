from enum import Enum, auto


class ServoMode(Enum):
    """
    舵机模式
    """
    SERVO = 0
    MOTOR = 1


class PinMode(Enum):
    """
    引脚工作模式
    """
    INPUT = 0  # 输入
    OUTPUT = 1  # 输出


class PinOutputLevel(Enum):
    """
    引脚输出电平
    """
    LOW = 0
    HIGH = 1


class TiltState(Enum):
    """
    倾角传感器状态
    """
    FALL_FORWARD = auto()  # 前倾
    FALL_BACKWARD = auto()  # 后倾
    EDGE = auto()  # 边缘状态
    STAND = auto()  # 站立


class NavigateDirection(Enum):
    """
    灰度传感器导航方向
    """
    FORWARD = auto()
    BACKWARD = auto()
    LEFT = auto()
    RIGHT = auto()
    STOP = auto()
