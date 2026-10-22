import sys

sys.path.append("..")

from uptech import UpTech
from motion_controller import MotionController
import time

"""
本程序用于实现机器人在台下，检测自身所处的位置，调整姿态正对或者背对擂台，完成上台
上方四个红外测距检测围栏
底部四个红外光电检测擂台与围栏
倾斜传感器用于辨别卡台情况
"""

"""
机器人底部，平视的四个红外光电，用于在台下检测擂台与围栏
前方：IO通道0
右方：IO通道1
后方：IO通道2
左方：IO通道3
在擂台下IO为0代表红外光电检测到了擂台（前方有障碍物，低电平）
在擂台下IO为1代表红外光电没有检测到擂台（前方没有障碍物，高电平）
"""

"""
机器人上部，平视的四个红外测距，用于在台下检测围栏（高度高于擂台）
前方：ADC通道0
右方：ADC通道1
后方：ADC通道2
左方：ADC通道3
ADC读数越大，则前方障碍距离越小
"""

"""
倾斜传感器，用来检测卡台，ADC通道4
"""


class PlatformDetector:
    # 以下四个距离，为红外测距检测距离围栏的临界距离，用于判断是直接上台还是调整正位置
    FD = 150
    RD = 150
    BD = 150
    LD = 150



    def __init__(self):
        self.uptech = UpTech()
        self.uptech.ADC_IO_Open()
        self.servo_speed = 800
        self.motion_controller = MotionController()
    
     # 检测是否在台上-返回状态
    def paltform_detect(self):
        #前方灰度
        ad_4 = self.uptech.ADC_Get_Channel(4)
        #后方灰度
        ad_5 = self.uptech.ADC_Get_Channel(5)
        if ad_4 + ad_5 < 3000 :
            # 灰度值较小在台下
            return 0
        else:
            # 灰度值较大在台上
            return 1

    # 台下的位置检测判定，底部红外光电可以检测擂台和围栏，上方红外测距可以检测围栏
    # 红外测距读数越小，意味着距离越大    
    def fence_detect(self):
        # 底部前方红外光电
        io_0 = self.uptech.ADC_IO_GetInputLevel(0) 
        # 底部右侧红外光电
        io_1 = self.uptech.ADC_IO_GetInputLevel(1) 
        # 底部后方红外光电
        io_2 = self.uptech.ADC_IO_GetInputLevel(2) 
        # 底部左侧红外光电
        io_3 = self.uptech.ADC_IO_GetInputLevel(3) 

        # 前红外测距传感器
        ad_0 = self.uptech.ADC_Get_Channel(0)
        # 右红外测距传感器
        ad_1 = self.uptech.ADC_Get_Channel(1)
        # 后红外测距传感器
        ad_2 = self.uptech.ADC_Get_Channel(2)
        # 左红外测距传感器
        ad_3 = self.uptech.ADC_Get_Channel(3)


        # ----------------------对擂台，一个测距检测到--------------------
        if io_2 ==0 and io_1 ==1 and io_3 ==1 and ad_0 > self.FD and ad_1 < self.RD and ad_2 < self.BD and ad_3 < self.LD:
            # 在台下，后方对擂台
            return 1
        if io_3 ==0 and io_0 ==1 and io_2 ==1 and ad_0 < self.FD and ad_1 > self.RD and ad_2 < self.BD and ad_3 < self.LD:
            # 在台下，左侧对擂台
            return 2
        if io_0 ==0 and io_1 ==1 and io_3 ==1 and ad_0 < self.FD and ad_1 < self.RD and ad_2 > self.BD and ad_3 < self.LD:
            # 在台下，前方对擂台
            return 3
        if io_1 ==0 and io_0 ==1 and io_2 ==1 and ad_0 < self.FD and ad_1 < self.RD and ad_2 < self.BD and ad_3 > self.LD:
            # 在台下，右侧对擂台
            return 4

        # ------------------------对围栏，两个相邻测距检测到-------------
        if io_1 ==1 and io_2 ==1 and ad_0 > self.FD and ad_1 < self.RD and ad_2 < self.BD and ad_3 > self.LD:
            # 右和后的红外光电都没有检测到擂台，前左的红外测距检测到近度大于阈值，后右检测到近度小于阈值，前和左侧方向对围栏
            return 5

        if io_2 ==1 and io_3 ==1 and ad_0 > self.FD and ad_1 > self.RD and ad_2 < self.BD and ad_3 < self.LD:
            # 左和后的红外光电没有检测到擂台，前右的红外测距检测到近度大于阈值，左后检测到近度小于阈值，前侧和右侧方向对围栏
            return 6
        if io_0 ==1 and io_3 ==1 and ad_0 < self.FD and ad_1 > self.RD and ad_2 > self.BD and ad_3 < self.LD:
            # 后侧和右侧对围栏
            return 7
        if io_0 ==1 and io_1 ==1 and ad_0 < self.FD and ad_1 < self.RD and ad_2 > self.BD and ad_3 > self.LD:
            # 后侧和左侧对围栏
            return 8

        # --------------------------台上有敌人，两个相对测距检测到-----------
        if ad_0 > self.FD and ad_1 < self.RD and ad_2 > self.BD and ad_3 < self.LD:
            # 在台下，前方或后方有台上敌人
            return 9
        if ad_0 < self.FD and ad_1 > self.RD and ad_2 < self.BD and ad_3 > self.LD:
            # 在台下，左侧或右侧由台上敌人
            return 10

        # -------------------------三侧有障碍，三个测距检测到---------------
        if ad_0 > self.FD and ad_1 > self.RD and ad_2 < self.BD and ad_3 > self.LD:
            # 在台下，前方、左侧和右侧检测到围栏
            return 11
        if ad_0 > self.FD and ad_1 > self.RD and ad_2 > self.BD and ad_3 < self.LD:
            # 在台下，前方、右侧和后方检测到围栏
            return 12
        if ad_0 > self.FD and ad_1 < self.RD and ad_2 > self.BD and ad_3 > self.LD:
            # 在台下，前方、左侧和后方检测到围栏
            return 13
        if ad_0 < self.FD and ad_1 > self.RD and ad_2 > self.BD and ad_3 > self.LD:
            # 在台下，右侧、左侧和后方检测到围栏
            return 14

        # -----------------------斜对擂台，两个红外光电检测到----------------
        if io_0 ==0 and io_1 ==0 and ad_0 < self.FD and ad_1 < self.RD:
            # 在台下，前方和右侧对擂台其他传感器没检测到
            return 15
        if io_0 ==0 and io_3 ==0 and ad_0 < self.FD and ad_3 < self.LD:
            # 在台下，在台下，前方和左侧对擂台其他传感器没检测到
            return 16
        if io_1 ==0 and io_2 ==0 and ad_1 < self.FD and ad_2 < self.RD:
            # 在台下，后方和右侧对擂台其他传感器没检测到
            return 17
        if io_2 ==0 and io_3 ==0 and ad_2 < self.FD and ad_3 < self.LD:
            # 在台下，后方和左侧对擂台其他传感器没检测到
            return 18
        else:
            return 101
        
    def start_move(self):
        #选择角度与蓝色电池电量有关，可以根据实际情况进行修改选择时间
        freeSpeed = 400 #漫游擂台、旋转速度 
        turn = 0.6   #左右有物块/敌人旋转90度时间延迟为0.5

        self.motion_controller.default_platform()
        time.sleep(1)

        while True:

            # 首先，需要检测是否在台上
            stage = self.paltform_detect()
            time.sleep(0.01)

            # 检测上台了，先什么都不做
            if stage == 1:
                print("Now On Platform!!!!!")
                time.sleep(0.01)

            # 检测到在台下，要先上台，是冲着擂台的，按照前后上台，不是冲着擂台的，调整姿态到前后冲着擂台
            if stage == 0: 
                print("在台下")
                fence = self.fence_detect()
                #后方对擂台
                if fence == 1:
                    self.motion_controller.go_up_behind_platform()
                # 左侧对擂台
                if fence == 2:
                    self.motion_controller.move_cmd(0, 0)
                    time.sleep(0.1)
                    while 1:
                        # 底部前方红外光电
                        io_0 = self.uptech.ADC_IO_GetInputLevel(0)
                        # 底部左侧红外光电
                        i0_3 = self.uptech.ADC_IO_GetInputLevel(3)
                        # 中间右侧红外测距
                        ad_1 = self.uptech.ADC_Get_Channel(1)
                        # 前方触发，左侧没触发，右侧离得足够远,说明转过来了，前进
                        if io_0 ==0 and ad_1 < self.RD and i0_3 ==1:
                            time.sleep(0.2)
                            self.motion_controller.move_cmd(freeSpeed, freeSpeed)
                            time.sleep(0.3)
                            break
                        else:
                            # 否则一直左转
                            self.motion_controller.move_cmd(-freeSpeed, freeSpeed)
                            time.sleep(0.01)
                # 前方对擂台
                if fence == 3:
                    self.motion_controller.go_up_ahead_platform()
                # 右侧对擂台
                if fence == 4:
                    self.motion_controller.move_cmd(0, 0)
                    time.sleep(0.1)
                    while 1:
                        # 底部前方红外光电
                        io_0 = self.uptech.ADC_IO_GetInputLevel(0)
                        # 底部左侧红外光电
                        i0_3 = self.uptech.ADC_IO_GetInputLevel(3)
                        # 中间右侧红外测距
                        ad_1 = self.uptech.ADC_Get_Channel(1)
                        # 前方触发，右侧没触发，左侧离得足够远,说明转过来了，前进
                        if io_0 ==0 and ad_1 < self.RD and i0_3 ==1:
                            time.sleep(0.2)
                            self.motion_controller.move_cmd(freeSpeed, freeSpeed)
                            time.sleep(0.3)
                            break   
                        else:
                            # 否则一直右转
                            self.motion_controller.move_cmd(freeSpeed, -freeSpeed)
                            time.sleep(0.01)
                # 前左检测到围栏
                if fence == 5:
                    self.motion_controller.move_cmd(-freeSpeed, -freeSpeed)
                    time.sleep(0.4)
                # 前右检测到围栏
                if fence == 6:
                    self.motion_controller.move_cmd(-freeSpeed, -freeSpeed)
                    time.sleep(0.4)
                # 后右检测到围栏
                if fence == 7:
                    self.motion_controller.move_cmd(freeSpeed, freeSpeed)
                    time.sleep(0.4)
                # 后左检测到围栏
                if fence == 8:
                    self.motion_controller.move_cmd(freeSpeed, freeSpeed)
                    time.sleep(0.4)
                # 前方或后方有台上敌人
                if fence == 9:
                    self.motion_controller.move_cmd(freeSpeed, -freeSpeed)
                    time.sleep(turn)
                    self.motion_controller.move_cmd(freeSpeed, freeSpeed)
                    time.sleep(0.4)
                # 左侧或右侧有台上敌人
                if fence == 10:
                    self.motion_controller.move_cmd(freeSpeed, freeSpeed)
                    time.sleep(0.4)
                # 前方、左侧和右侧检测到围栏
                if fence == 11:
                    self.motion_controller.move_cmd(-freeSpeed, -freeSpeed)
                    time.sleep(0.5)
                    self.motion_controller.move_cmd(-freeSpeed, freeSpeed)
                    time.sleep(turn)
                # 前右后检测到围栏
                if fence == 12:
                    self.motion_controller.move_cmd(300, 600)
                    time.sleep(turn)
                # 前左后检测到围栏
                if fence == 13:
                    self.motion_controller.move_cmd(600, 300)
                    time.sleep(turn)
                # 右左后检测到围栏
                if fence == 14:
                    self.motion_controller.move_cmd(-freeSpeed, freeSpeed)
                    time.sleep(0.2)
                    self.motion_controller.move_cmd(freeSpeed, freeSpeed)
                    time.sleep(0.3)
                # 前右检测到擂台
                if fence == 15:
                    self.motion_controller.move_cmd(0, 0)
                    time.sleep(0.2)
                    while 1:
                        # 底部前方红外光电
                        io_0 = self.uptech.ADC_IO_GetInputLevel(0)
                        # 底部左侧红外光电
                        i0_3 = self.uptech.ADC_IO_GetInputLevel(3)
                        # 中间右侧红外测距
                        ad_1 = self.uptech.ADC_Get_Channel(1)
                         # 前方触发，右侧没触发，左侧离得足够远,说明转过来了，前进
                        if io_0 ==0 and ad_1 < self.RD and i0_3 ==1:
                            time.sleep(0.2)
                            self.motion_controller.move_cmd(freeSpeed, freeSpeed)
                            time.sleep(0.3)
                            break
                        # 否则一直右转
                        else:
                            self.motion_controller.move_cmd(freeSpeed, -freeSpeed)
                            time.sleep(0.01)
                #  前左检测到擂台
                if fence == 16:
                    self.motion_controller.move_cmd(0, 0)
                    time.sleep(0.2)
                    while 1:
                        # 底部前方红外光电
                        io_0 = self.uptech.ADC_IO_GetInputLevel(0)
                        # 底部左侧红外光电
                        i0_3 = self.uptech.ADC_IO_GetInputLevel(3)
                        # 中间右侧红外测距
                        ad_1 = self.uptech.ADC_Get_Channel(1)
                        # 前方触发，左侧没触发，右侧离得足够远,说明转过来了，前进
                        if io_0 ==0 and ad_1 < self.RD and i0_3 ==1:
                            time.sleep(0.2)
                            self.motion_controller.move_cmd(freeSpeed, freeSpeed)
                            time.sleep(0.3)
                            break
                        # 否则一直左转
                        else:
                            self.motion_controller.move_cmd(-freeSpeed, freeSpeed)
                            time.sleep(0.01)
                # 在台下，后方和右侧对擂台其他传感器没检测到
                if fence == 17:
                    self.motion_controller.move_cmd(0, 0)
                    time.sleep(0.2)
                    while 1:
                        # 底部前方红外光电
                        io_0 = self.uptech.ADC_IO_GetInputLevel(0)
                        # 底部左侧红外光电
                        i0_3 = self.uptech.ADC_IO_GetInputLevel(3)
                        # 中间右侧红外测距
                        ad_1 = self.uptech.ADC_Get_Channel(1)
                         # 前方触发，右侧没触发，左侧离得足够远,说明转过来了，前进
                        if io_0 ==0 and ad_1 < self.RD and i0_3 ==1:
                            time.sleep(0.2)
                            self.motion_controller.move_cmd(freeSpeed, freeSpeed)
                            time.sleep(0.3)
                            break
                        # 否则一直右转
                        else:
                            self.motion_controller.move_cmd(freeSpeed, -freeSpeed)
                            time.sleep(0.01)
                # 在台下，后方和左侧对擂台其他传感器没检测到
                if fence == 18:
                    self.motion_controller.move_cmd(0, 0)
                    time.sleep(0.2)
                    while 1:
                        # 底部前方红外光电
                        io_0 = self.uptech.ADC_IO_GetInputLevel(0)
                        # 底部左侧红外光电
                        i0_3 = self.uptech.ADC_IO_GetInputLevel(3)
                        # 中间右侧红外测距
                        ad_1 = self.uptech.ADC_Get_Channel(1)
                         # 前方触发，左侧没触发，右侧离得足够远,说明转过来了，前进
                        if io_0 ==0 and ad_1 < self.RD and i0_3 ==1:
                            time.sleep(0.2)
                            self.motion_controller.move_cmd(freeSpeed, freeSpeed)
                            time.sleep(0.3)
                            break
                        # 否则一直左转
                        else:
                            self.motion_controller.move_cmd(-freeSpeed, freeSpeed)
                            time.sleep(0.01)


if __name__ == '__main__':
    platform_detector = PlatformDetector()
    platform_detector.start_move()