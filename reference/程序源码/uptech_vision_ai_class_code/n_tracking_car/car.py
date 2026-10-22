import sys
import time

sys.path.append("..")
from uptech import UpTech


# 参数
SPEED = 240
OFFSET_LIMIT = 40


class Car:
    def __init__(self):
        self.up = UpTech()
        time.sleep(0.01)
        self.up.CDS_Open()
        time.sleep(0.2)
        self.up.CDS_SetMode(1, 1)  # 0舵机，1电机
        self.up.CDS_SetMode(2, 1)
        self.up.CDS_SetMode(3, 1)
        self.up.CDS_SetMode(4, 1)
        time.sleep(2.0)

    def move_forward(self, speed):
        self.up.CDS_SetSpeed(1, speed)
        self.up.CDS_SetSpeed(3, speed)
        self.up.CDS_SetSpeed(2, -speed)
        self.up.CDS_SetSpeed(4, -speed)

    def move_backward(self, speed):
        self.up.CDS_SetSpeed(1, -speed)
        self.up.CDS_SetSpeed(3, -speed)
        self.up.CDS_SetSpeed(2, speed)
        self.up.CDS_SetSpeed(4, speed)

    def move_left(self, speed):
        self.up.CDS_SetSpeed(1, -speed)
        self.up.CDS_SetSpeed(3, speed)
        self.up.CDS_SetSpeed(2, -speed)
        self.up.CDS_SetSpeed(4, speed)

    def move_right(self, speed):
        self.up.CDS_SetSpeed(1, speed)
        self.up.CDS_SetSpeed(3, -speed)
        self.up.CDS_SetSpeed(2, speed)
        self.up.CDS_SetSpeed(4, -speed)

    def turn_left(self, speed):
        self.up.CDS_SetSpeed(1, -speed)
        self.up.CDS_SetSpeed(3, -speed)
        self.up.CDS_SetSpeed(2, -speed)
        self.up.CDS_SetSpeed(4, -speed)

    def turn_right(self, speed):
        self.up.CDS_SetSpeed(1, speed)
        self.up.CDS_SetSpeed(3, speed)
        self.up.CDS_SetSpeed(2, speed)
        self.up.CDS_SetSpeed(4, speed)

    def stop(self):
        self.up.CDS_SetSpeed(1, 0)
        self.up.CDS_SetSpeed(2, 0)
        self.up.CDS_SetSpeed(3, 0)
        self.up.CDS_SetSpeed(4, 0)

    def close(self):
        self.up.CDS_Close()


def main():
    # 初始化底盘控制
    car = Car()

    try:

        # 开始跟踪
        while True:
            car.turn_left(SPEED)

    except (KeyboardInterrupt, Exception) as e:
        print(e)

    finally:
        car.stop()
        time.sleep(1.0)
        car.close()
        time.sleep(1.0)


# 程序入口
if __name__ == '__main__':
    main()
