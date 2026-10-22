from sdk.logic import Timer
from sdk.api import UpAPIBuilder
from enum import Enum, auto

"""
基础测试：底盘控制

前后移动，左右自旋
"""

class State(Enum):
    IDLE = auto()
    FORWARD = auto()
    BACKWARD = auto()
    LEFT = auto()
    RIGHT = auto()
    FINISH = auto()


class Controller:
    def __init__(self):
        self.state = State.IDLE
        self.time_interval = 2000
        self.timer = Timer(self.time_interval)

    def update_state(self):

        if self.state == State.IDLE:

            if self.timer.complete():
                self.state = State.FORWARD
                self.timer.start()

        elif self.state == State.FORWARD:

            if self.timer.complete():
                self.state = State.BACKWARD
                self.timer.start()

        elif self.state == State.BACKWARD:

            if self.timer.complete():
                self.state = State.LEFT
                self.timer.start()

        elif self.state == State.LEFT:
            if self.timer.complete():
                self.state = State.RIGHT
                self.timer.start()

        elif self.state == State.RIGHT:

            if self.timer.complete():
                self.state = State.FINISH

        elif self.state == State.FINISH:
            pass


if __name__ == "__main__":

    api = UpAPIBuilder().build()
    controller = Controller()

    while True:

        controller.update_state()

        if controller.state == State.IDLE:

            api.stop()

        elif controller.state == State.FORWARD:

            api.move_forward()

        elif controller.state == State.BACKWARD:

            api.move_backward()

        elif controller.state == State.LEFT:

            api.turn_left()

        elif controller.state == State.RIGHT:

            api.turn_right()

        elif controller.state == State.FINISH:

            api.stop()
            print("程序结束")
            break

