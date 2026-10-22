import sys
sys.path.append("..")

from uptech import UpTech
import time

class RobotControl:
    def __init__(self):
        self.up = UpTech()
        time.sleep(0.01)
        self.up.CDS_Open()
        time.sleep(0.2)
        self.up.ADC_IO_Open()
        time.sleep(1)
        self.up.CDS_SetMode(1,1) #0舵机，1电机
        self.up.CDS_SetMode(2,1)
        self.up.CDS_SetMode(3,1)
        self.up.CDS_SetMode(4,1)

        # 设置为舵机模式
        self.up.CDS_SetMode(5,0)
        self.up.CDS_SetMode(6,0)
        time.sleep(2.0)
        self.up.CDS_SetAngle(5, 512, 512)
        self.up.CDS_SetAngle(6, 512, 512)

        self.move_forward(250)

    def move_forward(self, speed):
        self.up.CDS_SetSpeed(1,speed)
        self.up.CDS_SetSpeed(3,speed)
        self.up.CDS_SetSpeed(2,-speed)
        self.up.CDS_SetSpeed(4,-speed) 

    def move_backward(self, speed):
        self.up.CDS_SetSpeed(1,-speed)
        self.up.CDS_SetSpeed(3,-speed)
        self.up.CDS_SetSpeed(2,speed)
        self.up.CDS_SetSpeed(4,speed)    

    def move_left(self, speed):
        self.up.CDS_SetSpeed(1,-speed)
        self.up.CDS_SetSpeed(3,speed)
        self.up.CDS_SetSpeed(2,-speed)
        self.up.CDS_SetSpeed(4,speed)  

    def move_right(self, speed):
        self.up.CDS_SetSpeed(1,speed)
        self.up.CDS_SetSpeed(3,-speed)
        self.up.CDS_SetSpeed(2,speed)
        self.up.CDS_SetSpeed(4,-speed)  

    def turn_left(self, speed):
        self.up.CDS_SetSpeed(1,-speed)
        self.up.CDS_SetSpeed(3,-speed)
        self.up.CDS_SetSpeed(2,-speed)
        self.up.CDS_SetSpeed(4,-speed)  

    def turn_right(self, speed):
        self.up.CDS_SetSpeed(1,speed)
        self.up.CDS_SetSpeed(3,speed)
        self.up.CDS_SetSpeed(2,speed)
        self.up.CDS_SetSpeed(4,speed)  

    def stop(self):
        self.up.CDS_SetSpeed(1,0)
        self.up.CDS_SetSpeed(2,0)
        self.up.CDS_SetSpeed(3,0)
        self.up.CDS_SetSpeed(4,0)  
    
    def close(self):
        self.up.CDS_Close()

    def pop_ballonns(self):
        self.up.CDS_SetAngle(5, 300, 800)
        time.sleep(0.7)
        self.up.CDS_SetAngle(5, 512, 800)
        time.sleep(0.7)

# 扎气球
class PopBallonns:

    def __init__(self):
        self.movement = RobotControl()

    def start(self):
        while True:
            io_channel_0 = self.movement.up.ADC_IO_GetInputLevel(0)
            io_channel_1 = self.movement.up.ADC_IO_GetInputLevel(1)
            io_channel_2 = self.movement.up.ADC_IO_GetInputLevel(2)

            print("io0 = {},io1 = {}, io2 = {}".format(io_channel_0,io_channel_1,io_channel_2))

            if io_channel_0 == 1 and io_channel_1 == 1 and io_channel_2 == 1:
                self.movement.move_forward(256)
                time.sleep(0.2)
            if io_channel_0 == 0 and io_channel_1 == 0 and io_channel_2 == 0:
                self.movement.move_backward(256)
                time.sleep(0.2)
            if io_channel_0 == 0 and io_channel_1 == 1 and io_channel_2 == 1:
                self.movement.move_left(256)
                time.sleep(0.2)
            if io_channel_0 == 1 and io_channel_1 == 1 and io_channel_2 == 0:
                self.movement.move_right(256)
                time.sleep(0.2)
            if io_channel_0 == 1 and io_channel_1 == 0 and io_channel_2 == 1:
                self.movement.stop()
                self.movement.pop_ballonns()
            time.sleep(0.1)
                


if __name__ == '__main__':
    pop = PopBallonns()
    # pop.start()

    




