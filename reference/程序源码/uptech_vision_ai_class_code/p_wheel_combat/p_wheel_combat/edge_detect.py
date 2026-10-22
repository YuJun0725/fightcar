import sys
sys.path.append("..")

from uptech import UpTech
from motion_controller import MotionController

import apriltag
import threading
import time
import cv2

"""
本程序用于实现机器人在台上，巡逻不掉台，识别到对方和中立能量块推下去，识别到对方机器推下去，识别到自己能量块绕开
上方四个红外光电检测擂台边缘
底部四个红外光电检测能量块与对方机器
前方测距用于测量前方的物体的近度
"""

"""
机器人上方向下看的四个红外光电传感器，用于检测擂台边缘
左前方：IO通道4
右前方：IO通道5
右后方：IO通道6
左后方：IO通道7
在擂台上IO为0代表红外光电没有检测到边缘（前方有障碍物，低电平）
在擂台上IO为1代表红外光电检测到了边缘（前方没有障碍物，高电平）
"""

"""
机器人底部的四个红外光电传感器，用于在台上检测对方是否靠近
前方：IO通道0
右方：IO通道1
后方：IO通道2
左方：IO通道3
在擂台上IO为0代表红外光电检测到了敌人（前方有障碍物，低电平）
在擂台上IO为1代表红外光电没有检测到敌人（前方没有障碍物，高电平）
"""

class EdgeDetector:
    
    # 前搁浅计时
    nd = 0
    # 后搁浅计时
    ne = 0
    
    def __init__(self):
        self.uptech = UpTech()
        self.uptech.ADC_IO_Open()
        self.motion_controller = MotionController()

        options = apriltag.DetectorOptions(families='tag36h11')
        self.tag_detector = apriltag.Detector(options) 
        
        #开启Tag识别这里用了多线程
        self.apriltag_width = 0
        self.tag_id = -1
        apriltag_detect = threading.Thread(target = self.apriltag_detect_thread)
        apriltag_detect.setDaemon(True)
        apriltag_detect.start()

    def apriltag_detect_thread(self):
        print("detect start")
        self.camera_activate = True
        while self.camera_activate:
            try:
                cap = cv2.VideoCapture(0)
                if not cap.isOpened():
                    raise RuntimeError ("attempt to connect camera")
                else:
                    self.camera_activate = True 
                    print("camera connected succesfully")
            except RuntimeError as e:
                print("cannot connect camera")

            while True:

                weight = 320
                height = 240
                # x坐标为40  
                cup_w = (int)((640 - weight) / 2) -120 
                # y坐标为80
                cup_h = (int)((480 - height) / 2) -40 

                try:             
                    ret, frame = cap.read()
                    if not ret:
                        raise RuntimeError("frame read failed")
                    else:
                        frame= cv2.resize(frame, (640, 480))
                        #进行截取，截取图像左上角坐标为（40,80），视频宽440，高500
                        frame1 = frame[cup_h:cup_h +440,cup_w:cup_w + 500]
                        result = frame1.copy()

                        gray = cv2.cvtColor(result, cv2.COLOR_BGR2GRAY) 
                        
                        # 识别的主函数
                        apriltag_detect_results = self.tag_detector.detect(gray) 
                        
                        # 没识别到tag,id设定为-1
                        if(len(apriltag_detect_results) == 0):
                            self.tag_id = -1
                        
                        # 画出识别结果
                        for tag in apriltag_detect_results:
                            # 将识别到的 tag 的 id 赋值给类做判断
                            self.tag_id = tag.tag_id
                            print("tag_id = {}".format(tag.tag_id))
                            #test_output
                            if self.tag_id != 2 :
                                # 前方有敌人且不是己方物块需要推，返回1
                                print("前方有敌人且不是己方物块需要推，返回1") 
                            else:
                                #自家物块，需要绕
                                print("自家物块，需要绕") 
                            cv2.circle(result, tuple(tag.corners[0].astype(int)), 4, (255, 0, 0), 2) # left-top
                            cv2.circle(result, tuple(tag.corners[1].astype(int)), 4, (255, 0, 0), 2) # right-top
                            cv2.circle(result, tuple(tag.corners[2].astype(int)), 4, (255, 0, 0), 2) # right-bottom
                            cv2.circle(result, tuple(tag.corners[3].astype(int)), 4, (255, 0, 0), 2) # left-bottom
                        cv2.imshow("result", result)
                        #cv2.imshow("frame", frame)   
                        if cv2.waitKey(1) & 0xff == ord('q'):
                            self.camera_activate=False
                            break
                                
                except Exception as e:
                    print("camera error,try to connect camera...")                    
                    cap.release()
                    break  
            
        cap.release()
        cv2.destroyAllWindows()

    # 边缘检测
    def edge_detect(self):
        io_4 =self.uptech.ADC_IO_GetInputLevel(4) #左前
        io_5 =self.uptech.ADC_IO_GetInputLevel(5) #右前
        io_6 =self.uptech.ADC_IO_GetInputLevel(6) #右后
        io_7 =self.uptech.ADC_IO_GetInputLevel(7) #左后
        
        ad_0 = self.uptech.ADC_Get_Channel(0) #前方测距值
        ad_2 = self.uptech.ADC_Get_Channel(2) #后方测距值
        
        if io_4 == 0 and io_5 == 0 and io_6 == 0 and io_7 == 0:
            # 四个红外光电都没有检测到边缘,离擂台边缘都很远
            return 0
        elif io_4 == 1 and io_5 == 0 and io_6 == 0 and io_7 == 0:
            # 左前检测到边缘
            return 1
        elif io_4 == 0 and io_5 == 1 and io_6 == 0 and io_7 == 0:
            # 右前检测到边缘
            return 2
        elif io_4 == 0 and io_5 == 0 and io_6 == 1 and io_7 == 0:
            # 右后检测到边缘
            return 3
        elif io_4 == 0 and io_5 == 0 and io_6 == 0 and io_7 == 1:
            # 左后检测到边缘
            return 4
        elif io_4 == 1 and io_5 == 1 and io_6 == 0 and io_7 == 0:
            # 前方两个检测到边缘
            return 5
        elif io_4 == 0 and io_5 == 0 and io_6 == 1 and io_7 == 1:
            # 后方两个检测到边缘
            return 6
        elif io_4 == 1 and io_5 == 0 and io_6 == 0 and io_7 == 1:
            # 左侧两个检测到边缘
            return 7
        elif io_4 == 0 and io_5 == 1 and io_6 == 1 and io_7 == 0:
            # 右侧两个检测到边缘
            return 8  
        elif io_4 == 1 and io_5 == 1 and io_6 == 1 and io_7 == 1 and ad_0 > 1000:
            # 卡台搁浅在擂台边缘，其中前方在擂台下，后方在擂台上
            return 9
        elif io_4 == 1 and io_5 == 1 and io_6 == 1 and io_7 == 1 and ad_2 > 1000:
            # 卡台搁浅在擂台边缘，其中前方在擂台上，后方在擂台下
            return 10
        else:
            return 102        
          
        
    # 敌人检测
    def enemy_detect(self):
        # 底部前方红外光电
        io_0 = self.uptech.ADC_IO_GetInputLevel(0)
        # 底部右侧红外光电
        io_1 = self.uptech.ADC_IO_GetInputLevel(1)
        # 底部后方红外光电
        io_2 = self.uptech.ADC_IO_GetInputLevel(2)
        # 底部左侧红外光电
        io_3 = self.uptech.ADC_IO_GetInputLevel(3)
        
        # 前方测距
        ad_0 = self.uptech.ADC_Get_Channel(0)
        
        # 四路红外光电都是空的，没有检测到敌人
        if io_0==1 and io_1==1 and io_2==1 and io_3==1:
            # 无敌人
            return 0
        
        # 前方红外光电感应，其他方向没感应
        elif io_0==0 :
            #默认己方物块信息为2，若为其他物块修改下方tag_id
            if self.tag_id != 2 :                    
                if ad_0 < 1000:
                      # 前方有敌人且不是己方物块需要推，返回1
                    print("前方有敌人且不是己方物块需要推，返回11111")
                    return 1               
                else:
                 # 已经非常接近目标，加速撞击，将对方推下擂台
                    return 11 
            else:
                #自家物块，需要绕
                print("自家物块，需要绕")
                return 5
                           
        elif  io_1==0 :
            # 右侧有敌人或能量块
            return 2
        
        elif  io_2==0 :
            # 后方有敌人或能量块
            return 3
        
        elif  io_3==0:
            # 左侧有敌人或能量块
            return 4
        
        else:
            # 其他情况
            return 103
    
    def start_move(self):
        freeSpeed = 400 #漫游擂台、旋转速度 
        enemySpeed = 800 #检测到敌人撞击速度
        turn = 0.6   #左右有物块/敌人旋转90度时间延迟为0.5s
        turn_180 = 1.3 #后方有物块/敌人旋转180度时间延迟为1s
        
        self.nd = 0
        self.ne = 0
        while(1):     
            # 检测边缘
            edge = self.edge_detect()
                    
            # 四个边缘检测的红外光电都没有检测到擂台边缘
            if edge == 0:
                enemy = self.enemy_detect()
                # 无敌人，巡航速度前进
                if enemy == 0:
                    self.motion_controller.move_cmd(freeSpeed, freeSpeed)
                    time.sleep(0.01)
                    
                # 正前有敌人或对方或中立能量块，巡航加速前进，靠近敌方物块
                if enemy == 1:
                    self.motion_controller.move_cmd(700, 700)
                    time.sleep(0.02)
                
                # 右侧有敌人，先后退然后右转朝向敌人
                if enemy == 2:
                    self.motion_controller.move_cmd(-freeSpeed, -freeSpeed)
                    time.sleep(0.1)
                    self.motion_controller.move_cmd(freeSpeed, -freeSpeed)
                    time.sleep(turn)
                    
                # 后方有敌人，左转
                if enemy == 3:
                    self.motion_controller.move_cmd(-freeSpeed, freeSpeed)
                    time.sleep(turn_180)
                    
                # 左侧有敌人，先后退然后右转
                if enemy == 4:
                    self.motion_controller.move_cmd(-freeSpeed, -freeSpeed)
                    time.sleep(0.2)
                    self.motion_controller.move_cmd(-freeSpeed, freeSpeed)
                    time.sleep(turn)
                    
                # 自家物块，绕着走
                if enemy == 5:
                    self.motion_controller.move_cmd(-freeSpeed, -freeSpeed)
                    time.sleep(0.2)
                    self.motion_controller.move_cmd(-freeSpeed, freeSpeed)
                    time.sleep(turn_180)
                    self.motion_controller.move_cmd(freeSpeed, freeSpeed)
                    time.sleep(0.5)
                            
                # 接近待推下台的物体，加速
                if enemy == 11:
                    self.motion_controller.move_cmd(enemySpeed, enemySpeed)
                    time.sleep(0.02)
                            
            # 左前检测到边缘，先后退，然后右转一点
            if edge == 1:
                    self.motion_controller.move_cmd(-freeSpeed, -freeSpeed)
                    time.sleep(0.4)
                    self.motion_controller.move_cmd(freeSpeed, -freeSpeed)
                    time.sleep(turn)
                        
            # 右前检测到边缘，先后退，然后左转一点
            if edge == 2:
                    self.motion_controller.move_cmd(-freeSpeed, -freeSpeed)
                    time.sleep(0.4)
                    self.motion_controller.move_cmd(-freeSpeed, freeSpeed)
                    time.sleep(0.3)
                        
            # 右后检测到边缘，先前进，然后左转一点
            if edge == 3:
                self.motion_controller.move_cmd(freeSpeed, freeSpeed)
                time.sleep(0.5)
                self.motion_controller.move_cmd(-freeSpeed, freeSpeed)
                time.sleep(turn)
                        
            # 左后检测到边缘，先前进，然后右转一点
            if edge == 4:
                self.motion_controller.move_cmd(freeSpeed, freeSpeed)
                time.sleep(0.5)
                self.motion_controller.move_cmd(freeSpeed, -freeSpeed)
                time.sleep(turn)
                        
            # 前方两个检测到边缘，后退，然后右转
            if edge == 5:
                self.motion_controller.move_cmd(-500, -500)
                time.sleep(0.7)
                self.motion_controller.move_cmd(500, -500)
                time.sleep(0.3)
                        
            # 后方两个检测到边缘，前进
            if edge == 6:
                self.motion_controller.move_cmd(500, 500)
                time.sleep(0.5)
                        
            # 左侧两个检测到边缘，先右转再前进
            if edge == 7:
                self.motion_controller.move_cmd(500, -freeSpeed)
                time.sleep(0.5)
                self.motion_controller.move_cmd(freeSpeed, freeSpeed)
                time.sleep(0.3)
                        
            # 右侧两个检测到边缘，先左转再前进
            if edge == 8:
                self.motion_controller.move_cmd(-freeSpeed, 500)
                time.sleep(0.5)
                self.motion_controller.move_cmd(freeSpeed, freeSpeed)
                time.sleep(0.3)
                        
            # 搁浅卡台了，头朝下，后退上台动作
            if edge == 9:
                self.nd += 1
                if self.nd > 80:
                    self.nd = 0
                    self.motion_controller.move_cmd(0, 0)
                    time.sleep(0.01)
                    self.motion_controller.move_cmd(-500, -500)
                    time.sleep(0.2)
                    self.motion_controller.go_up_behind_platform()
                    self.motion_controller.move_cmd(-500, -500)
                    time.sleep(0.8)
                    self.motion_controller.default_platform()
                    self.motion_controller.move_cmd(-500, -500)
                    time.sleep(0.5)
                    self.motion_controller.move_cmd(500, -500)
                    time.sleep(0.3)
                    self.motion_controller.move_cmd(0, 0)
                    time.sleep(0.1)
                else:
                    time.sleep(0.02)
                    
            # 搁浅卡台了，头朝上，前进上台动作      
            if edge == 10:
                self.ne += 1
                if self.ne > 80:
                    self.ne = 0
                    self.motion_controller.move_cmd(0, 0)
                    time.sleep(0.01)
                    self.motion_controller.move_cmd(500, 500)
                    time.sleep(0.2)
                    self.motion_controller.go_up_ahead_platform()
                    self.motion_controller.move_cmd(500, 500)
                    time.sleep(0.8)
                    self.motion_controller.default_platform()
                    self.motion_controller.move_cmd(500, 500)
                    time.sleep(0.4)
                    self.motion_controller.move_cmd(0, 0)
                    time.sleep(0.1)
                else:
                    time.sleep(0.02)
            
            # 其他情况，默认前进，直到进入别的状态                
            if edge == 102:
                self.motion_controller.move_cmd(freeSpeed, freeSpeed)
                time.sleep(0.01)       
        

if __name__ == '__main__':
    edge_detector = EdgeDetector()
    edge_detector.start_move()