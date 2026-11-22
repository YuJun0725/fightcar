"""软件输入检查；不能中断阻塞的厂商调用，也不替代物理急停。"""

import math


class SafetyError(ValueError):
    """输入失效时由运行循环统一停车并结束本次任务。"""


def validate_snapshot(snapshot, now, config):
    """批量读取时间超过有效期时拒绝该帧，不用旧值继续决策。"""
    if (type(snapshot.timestamp) not in (int, float)
            or not math.isfinite(snapshot.timestamp)
            or not math.isfinite(now)):
        raise SafetyError("传感器时间戳无效")
    age = now - snapshot.timestamp
    if age < 0 or age > config["runtime"]["max_sensor_age_s"]:
        raise SafetyError("传感器帧过期或时间戳超前: {:.3f} s".format(age))
    if len(snapshot.adc) != 10 or len(snapshot.io) != 8:
        raise SafetyError("传感器批量读取应返回 10 路 ADC 和 8 路 IO")
    # 这里只检查厂商 uint16 容器边界，不假定实际 ADC 为 12 位。
    if any(type(value) is not int or not 0 <= value <= 65535 for value in snapshot.adc):
        raise SafetyError("ADC 数据不在 uint16 容器范围内")
    if any(type(value) is not int or value not in (0, 1) for value in snapshot.io):
        raise SafetyError("IO 数据必须为 0 或 1")


def validate_command(command):
    if any(type(value) is not int or not -1023 <= value <= 1023
           for value in (command.wheels.left, command.wheels.right)):
        raise SafetyError("左右轮控制值必须是 -1023～1023 的整数")
    if command.support not in (None, "stowed", "front", "rear"):
        raise SafetyError("未知支撑爪姿态: {!r}".format(command.support))
