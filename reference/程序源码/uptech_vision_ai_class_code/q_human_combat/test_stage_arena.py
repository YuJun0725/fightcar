from sdk.api import UpAPIBuilder
from sdk.logic import Timer

"""
阶段测试：上擂台
"""

if __name__ == "__main__":
    speed = 200  # 移动速度
    time_arena = 3000  # 上擂台的时间

    timer_arena = Timer(time_arena)

    api = UpAPIBuilder().build()

    while True:

        if not timer_arena.in_progress:
            timer_arena.start()

        if timer_arena.complete():
            print("上台完成，程序退出")
            api.stop()
            break

        else:
            api.move_forward(speed)

