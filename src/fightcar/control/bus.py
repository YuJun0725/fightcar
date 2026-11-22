"""单线程总线调度：每轮至多一条，不在发送间隔内 sleep。"""

from collections import OrderedDict, deque
import time

from board.motor_control import COMMAND_GAP


class BusScheduler:
    def __init__(self, up, gap_s=COMMAND_GAP, clock=time.monotonic):
        self.up, self.clock = up, clock
        self.gap_s = max(COMMAND_GAP, gap_s)
        self.next_send_at = float("-inf")
        self.stops = deque()
        self.pending = {"support": OrderedDict(), "drive": OrderedDict()}
        self.sent = {}  # 仅软件调用完成的记录，不是硬件执行应答
        self.sent_at = {}

    @staticmethod
    def key(command):
        method, args = command
        return method, args[0]

    def matches(self, command):
        return self.sent.get(self.key(command)) == command[1]

    def replace(self, group, commands):
        """同一设备只保留最新目标，保留未发送设备的先后顺序。"""
        wanted = OrderedDict((self.key(command), command) for command in commands)
        pending = self.pending[group]
        for key in list(pending):
            if key not in wanted:
                del pending[key]
        pending.update(wanted)

    def request_stop(self, ids):
        self.pending["drive"].clear()
        if not self.stops:
            self.stops.extend(("CDS_SetSpeed", (motor_id, 0))
                              for _ in range(2) for motor_id in ids)

    def clear(self):
        self.stops.clear()
        for pending in self.pending.values():
            pending.clear()

    def pump(self):
        if self.clock() < self.next_send_at:
            return
        if self.stops:
            command = self.stops.popleft()
        else:
            command = None
            for group in ("support", "drive"):
                if self.pending[group]:
                    _, command = self.pending[group].popitem(last=False)
                    break
            if command is None:
                return
        method, args = command
        try:
            getattr(self.up, method)(*args)
        finally:
            # 以调用结束为基准，异常后也为退出停车保留最小间隔。
            self.next_send_at = self.clock() + self.gap_s
        key = self.key(command)
        self.sent[key], self.sent_at[key] = args, self.clock()
