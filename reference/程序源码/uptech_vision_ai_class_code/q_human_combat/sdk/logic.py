from .utils.type_util import Number
from .mode import NavigateDirection
from typing import Optional, Tuple, List
import math, time


class PIDController:
    """
    PID 控制类
    """

    def __init__(self,
                 Kp: float = 0.5,
                 Ki: float = 0.0,
                 Kd: float = 0.1,
                 output_limits: Tuple[Number, Number] = (-55, 55),
                 integral_limit: int = 100
                 ):
        """
        初始化函数

        : param Kp: 比例因子
        : param Ki: 积分因子
        : param Kd: 微分因子
        : param output_limits: 输出限幅
        : param integral_limit: 积分限幅
        """

        self.Kp = Kp
        self.Ki = Ki
        self.Kd = Kd
        self.output_limits = output_limits
        self.integral_limit = integral_limit

        self.previous_error = 0
        self.integral = 0
        self.last_time = time.time()

    def compute(self, error: Number) -> Number:
        """
        计算 PID 输出

        :param error: 原始偏移量
        :return: 计算后偏移量
        """

        current_time = time.time()
        dt = current_time - self.last_time
        self.last_time = current_time

        # 计算积分项并限幅
        self.integral += error * dt
        self.integral = max(-self.integral_limit, min(self.integral, self.integral_limit))

        # 计算微分项
        derivative = (error - self.previous_error) / dt if dt > 0 else 0

        # PID计算
        output = self.Kp * error + self.Ki * self.integral + self.Kd * derivative

        # 输出限幅
        output = max(self.output_limits[0], min(output, self.output_limits[1]))
        self.previous_error = error

        return output


class GrayscaleNavigator:
    def __init__(self,
                 left_grayscale_sample: int,
                 right_grayscale_sample: int,
                 sample_edge: Optional[List[int]] = None,
                 red_zone_variance_threshold: int = 20000,
                 distance_edge_threshold: int = 200,
                 debug:bool = False
                 ):
        """
        初始化函数

        :param left_grayscale_sample: 左侧灰度传感器数据
        :param right_grayscale_sample: 右侧灰度传感器数据
        :param sample_edge: 灰度传感器边缘采样数据（列表类型，依次为前、后、左、右），默认 [3245, 2940, 2455, 2590]
        :param red_zone_variance_threshold: 中心武字红色区域方差阈值，默认 20000
        :param distance_edge_threshold: 边缘处匹配阈值，默认 600
        :param debug: 调试标志，默认 False
        """

        # 采样数据
        self.left = left_grayscale_sample
        self.right = right_grayscale_sample
        self.dt = self.__init_dt()

        # 环境参数
        self.red_zone_variance_threshold = red_zone_variance_threshold  # 红色区域方差阈值
        self.distance_edge_threshold = distance_edge_threshold  # 边缘处匹配阈值
        self.sample_edge = self.__init_sample_edge(sample_edge)  # 边缘处传感器数据样本

        # 调试标志
        self.debug = debug

    def __init_dt(self) -> int:
        """
        初始化左右灰度传感器的平均值

        :return: 左右灰度传感器的平均值
        """
        avg = abs(self.left + self.right) // 2
        dt = abs(self.left - avg) - 8
        return dt

    def __init_sample_edge(self, edge) -> List[int]:
        """
        初始化边缘位置的左右灰度传感器数据

        :return: 边缘位置的左右灰度传感器数据
        """
        if edge is None:
            return [3245, 2940, 2455, 2590]

        else:
            if len(edge) != 4:
                raise RuntimeError("sample_edge 长度不为 4")

            return edge

    def calculate_variance(self, data) -> float:
        """
        计算传感器数据方差

        :param data: 灰度传感器数据
        :return: 传感器数据方差
        """
        mean = sum(data) / len(data)
        return sum((x - mean) ** 2 for x in data) / len(data)

    def euclidean_distance(self, data):
        """
        计算与边缘处样本的欧氏距离

        :param data: 灰度传感器数据
        :return: 当前位置与边缘处样本的欧氏距离
        """
        return math.sqrt(sum((s - sample) ** 2 for s, sample in zip(data, self.sample_edge)))

    def control_strategy(self, sensor_data) -> NavigateDirection:
        """
        核心控制策略

        :param sensor_data: 灰度传感器数据
        :return: 移动方向
        """
        front, back, left, right = sensor_data

        if self.debug:
            print(f"dt: {self.dt}")

        if self.left < self.right:
            left += self.dt
            right -= self.dt
        else:
            left -= self.dt
            right += self.dt

        # 方向控制参数
        lr_diff = right - left  # 左右传感器差值
        fb_diff = front - back  # 前后传感器差值

        if self.debug:
            print(f"左右差值：{lr_diff}，前后差值：{fb_diff}")

        # 转向控制
        if abs(lr_diff) > 100:
            return NavigateDirection.RIGHT if lr_diff > 0 else NavigateDirection.LEFT

        # 前进控制
        if fb_diff > 50:
            return NavigateDirection.FORWARD
        elif fb_diff < -50:
            return NavigateDirection.BACKWARD

        return NavigateDirection.STOP


class Timer:
    """
    计时器
    """

    def __init__(self, target_time: int):
        """
        初始化函数

        :param target_time: 计时时间，单位毫秒
        """
        self.target_time = target_time
        self.last_time = self.__get_time_ms()
        self.in_progress = False

    def start(self) -> None:
        """
        启动计时器
        """
        self.last_time = self.__get_time_ms()
        self.in_progress = True

    def complete(self) -> bool:
        """
        计时器是否到时间

        :return: 是否到时间
        """
        if self.__get_time_ms() - self.last_time >= self.target_time:
            self.in_progress = False
            return True
        return False

    def __get_time_ms(self) -> int:
        """
        获取当前时间的毫秒值

        :return: 当前时间的毫秒值
        """
        return int(time.time() * 1000)
