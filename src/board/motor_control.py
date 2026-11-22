"""板端共用电机控制：运动计算、安装方向映射和总线发送。

不导入键盘、网络、比赛状态机或厂商库；调用者提供已打开的硬件接口。
轮速以朝车头方向为正，单位是驱动控制值，不是 RPM。
"""

import time

COMMAND_GAP = 0.05  # 保留原总线发送间隔
REFRESH_INTERVAL = 0.1


def wheel_speeds(action, speed, spin_speed, width, radius):
    """直行/弧线使用 speed，原地旋转单独使用 spin_speed。"""
    inner = round(speed * (radius - width / 2) / (radius + width / 2))
    return {
        "w": (speed, speed), "s": (-speed, -speed),
        "a": (-spin_speed, spin_speed), "d": (spin_speed, -spin_speed),
        "j": (inner, speed), "l": (speed, inner),
    }.get(action, (0, 0))


def motor_commands(ids, wheels, reverse=False):
    """整车轮速映射为驱动器指令，供直接发送和定时调度共用。"""
    sign = -1 if reverse else 1
    return tuple((motor_id, sign * speed)
                 for motor_id, speed in zip(ids, (wheels[0], -wheels[1])))


def send(up, ids, wheels, reverse=False):
    """旧遥控入口的同步发送；比赛程序使用逐条调度。"""
    for motor_id, speed in motor_commands(ids, wheels, reverse):
        up.CDS_SetSpeed(motor_id, speed)
        time.sleep(COMMAND_GAP)


def stop(up, ids, command_gap=COMMAND_GAP):
    """每路停车两次；失败仍尝试所有驱动器，结束后统一报告错误。"""
    errors = []
    for _ in range(2):
        for motor_id in ids:
            try:
                up.CDS_SetSpeed(motor_id, 0)
            except Exception as error:
                errors.append("ID {}: {}".format(motor_id, error))
            time.sleep(command_gap)
    if errors:
        raise RuntimeError("停车指令发送失败；已尝试两侧: " + "; ".join(errors))
