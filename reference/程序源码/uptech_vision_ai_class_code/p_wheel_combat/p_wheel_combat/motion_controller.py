import sys
sys.path.append("..")

from uptech import UpTech
import time

class MotionController:
    def __init__(self):
        self.uptech = UpTech()

        self.uptech.CDS_Open()
        time.sleep(0.5)
        self.servo_speed = 600
        self.uptech.CDS_SetMode(3, 0)
        self.uptech.CDS_SetMode(4, 0)
        self.uptech.CDS_SetMode(5, 0)
        self.uptech.CDS_SetMode(6, 0)
        self.uptech.CDS_SetMode(7, 0)  
        self.uptech.CDS_SetMode(8, 0)     
        self.uptech.CDS_SetMode(11, 0)     
        self.uptech.CDS_SetMode(12, 0)  

    # 速度指令,参数分别为左速度和右速度，自由控制-开环控制器
    def move_cmd(self, left_speed, right_speed):
        self.uptech.CDS_SetSpeed(1, left_speed)
        self.uptech.CDS_SetSpeed(2, -right_speed)

    # 默认为前后爪都收起的状态
    def default_platform(self):
        self.uptech.CDS_SetAngle(5, 424, self.servo_speed)
        self.uptech.CDS_SetAngle(6, 600, self.servo_speed)
        self.uptech.CDS_SetAngle(7, 600, self.servo_speed)
        self.uptech.CDS_SetAngle(8, 424, self.servo_speed)

    # 支撑前爪,发两遍确认发送成功
    def pack_up_ahead(self):
        self.uptech.CDS_SetAngle(5, 980, self.servo_speed)
        self.uptech.CDS_SetAngle(6, 44, self.servo_speed)
        time.sleep(0.01)
        self.uptech.CDS_SetAngle(5, 980, self.servo_speed)
        self.uptech.CDS_SetAngle(6, 44, self.servo_speed)

    # 支撑后爪，发两遍确认发送成功
    def pack_up_behind(self):
        self.uptech.CDS_SetAngle(7, 44, self.servo_speed)
        self.uptech.CDS_SetAngle(8, 980, self.servo_speed)
        time.sleep(0.01)
        self.uptech.CDS_SetAngle(7, 44, self.servo_speed)
        self.uptech.CDS_SetAngle(8, 980, self.servo_speed)

    # 前上台动作
    def go_up_ahead_platform(self):
        self.move_cmd(0, 0)
        time.sleep(0.1)
        # 前后支撑爪抬起
        self.default_platform()
        time.sleep(0.4)
        #前进0.7s，这时前方已经顶住擂台边缘
        self.move_cmd(500, 500)
        time.sleep(0.7)
        # 支前爪,把前半身撑起来
        self.pack_up_ahead()
        time.sleep(1)
        # 收起前爪
        self.default_platform()
        time.sleep(0.3)
        # 支后爪，把后半身撑起来
        self.pack_up_behind()
        time.sleep(1)
        # 恢复成默认上台动作
        self.default_platform()
        time.sleep(1)
        self.move_cmd(0, 0)
        time.sleep(0.5)

    # 后上台动作
    def go_up_behind_platform(self):
        self.move_cmd(0, 0)
        time.sleep(0.1)
        # 前后支撑爪抬起
        self.default_platform()
        time.sleep(0.4)
        # 后退0.7s，这时后方已经顶住擂台边缘
        self.move_cmd(-500, -500)
        time.sleep(0.7)
        # 支后爪，把后半身撑起来
        self.pack_up_behind()
        time.sleep(1)
        # 收起前爪
        self.default_platform()
        # 支前爪，把前半身撑起来
        time.sleep(0.5)
        self.pack_up_ahead()
        time.sleep(1)
        # 默认上台
        self.default_platform()
        time.sleep(1)
        self.move_cmd(0, 0)
        time.sleep(0.5)