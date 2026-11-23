"""轮速目标合并、刷新与换向停车；由共用调度器逐条发送。"""

from contextlib import contextmanager
import time

from board.motor_control import motor_commands, stop
from fightcar.models import Command, WheelCommand
from fightcar.control.bus import BusScheduler
from fightcar.control.safety import validate_command


class DriveController:
    def __init__(self, up, config, bus):
        self.up, self.bus = up, bus
        self.ids = (config["left_id"], config["right_id"])
        self.reverse = config["reverse"]
        self.refresh_s = config["refresh_s"]
        self.target = WheelCommand()

    def commands(self, wheels):
        return tuple(("CDS_SetSpeed", args) for args in motor_commands(
            self.ids, (wheels.left, wheels.right), self.reverse))

    def request(self, wheels):
        validate_command(Command(wheels=wheels))
        commands = self.commands(wheels)
        self.target = wheels
        if wheels == WheelCommand():
            self.bus.replace("drive", ())
            if not all(self.bus.matches(command) for command in commands):
                self.bus.request_stop(self.ids)
            return
        # 按真正发出的各路指令判断换向，涵盖只发了一路就改变方向的情况。
        if any(self.bus.sent.get(self.bus.key(cmd), (0, 0))[1] * cmd[1][1] < 0 for cmd in commands):
            self.bus.request_stop(self.ids)
        # 左右轮独立刷新，避免一侧频繁调速挤掉另一侧的持续输出。
        now = self.bus.clock()
        due = tuple(cmd for cmd in commands if not self.bus.matches(cmd)
                    or now - self.bus.sent_at.get(self.bus.key(cmd), float("-inf")) >= self.refresh_s)
        self.bus.replace("drive", due)

    @property
    def ready(self):
        return (not self.bus.stops and not self.bus.pending["drive"]
                and all(self.bus.matches(cmd) for cmd in self.commands(self.target)))

    def stop(self):
        """初始化/异常/退出时的同步清理；不在正常主循环中调用。"""
        self.bus.clear()
        wait = self.bus.next_send_at - self.bus.clock()
        if wait > 0:
            time.sleep(wait)
        stop(self.up, self.ids, self.bus.gap_s)
        self.target = WheelCommand()
        for command in self.commands(self.target):
            key = self.bus.key(command)
            self.bus.sent[key] = command[1]
            self.bus.sent_at[key] = self.bus.clock()
        self.bus.next_send_at = self.bus.clock()


@contextmanager
def drive_output(up, config):
    """为独立实车测试打开两路底盘输出，退出时停车并释放接口。"""
    bus = BusScheduler(up)
    drive = DriveController(up, config["drive"], bus)
    try:
        up.CDS_Open()
        drive.stop()
        for motor_id in drive.ids:
            up.CDS_SetMode(motor_id, 1)
            time.sleep(0.1)

        def apply(wheels):
            drive.request(wheels)
            bus.pump()
            return drive.ready

        yield apply
    finally:
        try:
            drive.stop()
        finally:
            up.CDS_Close()
