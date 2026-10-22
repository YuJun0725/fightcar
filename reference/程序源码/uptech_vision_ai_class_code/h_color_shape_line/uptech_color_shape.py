import sys
sys.path.append("..")

import cv2
import numpy as np

from uptech import UpTech
import time

class FourWhellMove:
    def __init__(self):
        self.up = UpTech()
        time.sleep(0.01)
        self.up.CDS_Open()
        time.sleep(0.2)
        self.up.CDS_SetMode(1,1) #0舵机，1电机
        self.up.CDS_SetMode(2,1)
        self.up.CDS_SetMode(3,1)
        self.up.CDS_SetMode(4,1)
        time.sleep(2.0)
    
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


class ImageProcessing:
    
    def __init__(self):
        # 初始化颜色参数
        self.gray_frame = None
        self.hsv_frame = None
        self.target_x = None
        self.target_y = None
        self.is_detect = False

        # 设置一个窗口来显示图像
        self.window_name = "USB Camera Image"
        
        cv2.namedWindow(self.window_name,  cv2.WINDOW_NORMAL)
        cv2.namedWindow('result', cv2.WINDOW_NORMAL)
        
        cv2.createTrackbar("H_MIN", "USB Camera Image", 17, 180, self.nothing)
        cv2.createTrackbar("H_MAX", "USB Camera Image", 45, 180, self.nothing)
        cv2.createTrackbar("S_MIN", "USB Camera Image", 160, 255, self.nothing)
        cv2.createTrackbar("S_MAX", "USB Camera Image", 212, 255, self.nothing)
        cv2.createTrackbar("V_MIN", "USB Camera Image", 115, 255, self.nothing)
        cv2.createTrackbar("V_MAX", "USB Camera Image", 197, 255, self.nothing)
        
        cv2.setMouseCallback("USB Camera Image", self.mouse_click)
        
        self.movement = FourWhellMove()
        
        self.enable_move = True

        # 打开USB摄像头（通常0代表默认摄像头，如果有多个摄像头可以尝试1、2等）
        self.cap = cv2.VideoCapture(0)

    def update_frame(self):
        
        ret, src_frame = self.cap.read()
        
        src_frame =  cv2.resize(src_frame, (640, 480))
        
        cv2.imshow(self.window_name, src_frame)
        
        if not ret:
            print("无法获取摄像头图像")
            return

        result = src_frame.copy()
        # 获取HSV的阈值
        h_min = cv2.getTrackbarPos("H_MIN", "USB Camera Image")
        h_max = cv2.getTrackbarPos("H_MAX", "USB Camera Image")
        s_min = cv2.getTrackbarPos("S_MIN", "USB Camera Image")
        s_max = cv2.getTrackbarPos("S_MAX", "USB Camera Image")
        v_min = cv2.getTrackbarPos("V_MIN", "USB Camera Image")
        v_max = cv2.getTrackbarPos("V_MAX", "USB Camera Image")

        # 颜色空间转换
        self.gray_frame = cv2.cvtColor(src_frame, cv2.COLOR_BGR2GRAY)
        self.hsv_frame = cv2.cvtColor(src_frame, cv2.COLOR_BGR2HSV)
        # 二值化
        low_color = np.array([h_min, s_min, v_min])
        high_color = np.array([h_max, s_max, v_max])
        mask_color = cv2.inRange(self.hsv_frame, low_color, high_color)
        
        #滤波
        mask_color = cv2.medianBlur(mask_color, 7)

        s = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
        opened = cv2.morphologyEx(mask_color, cv2.MORPH_OPEN, s, iterations=2)
        closed = cv2.morphologyEx(opened, cv2.MORPH_CLOSE, s, iterations=2)
        edges = cv2.Canny(closed, 50, 100)

        self.mask_color = edges

        minDist = 100
        circles = cv2.HoughCircles(edges, cv2.HOUGH_GRADIENT, 1, minDist, param1=100, param2=10, minRadius=10, maxRadius=500)

        if circles is not None:  # 如果识别出圆
            for circle in circles[0]:
                
                #  获取圆的坐标与半径
                x = int(circle[0])
                y = int(circle[1])
                r = int(circle[2])
                
                cv2.circle(result, (x, y), r, (0, 0, 255), 3)  # 标记圆
                self.draw_cross(result, (x, y), 10)
                
                offset_x = x - src_frame.shape[1] / 2
                
                if(offset_x >= 20):
                    if(self.enable_move):
                        self.movement.turn_right(128)
                elif(offset_x <= -20):
                    if(self.enable_move):
                        self.movement.turn_left(-128)
                else:
                    self.movement.stop()

        cv2.imshow("result", result)

    # 鼠标点击回调
    def mouse_click(self, event, x, y, flags, para):
        if event == cv2.EVENT_LBUTTONDOWN:
            print('PIX: ', x, y)
            print('GRAY: ', self.gray_frame[y, x] if self.gray_frame is not None else None)
            print('HSV: ', self.hsv_frame[y, x] if self.hsv_frame is not None else None)

    def run(self):
        while True:
            self.update_frame()
            key = cv2.waitKey(1) & 0xFF  # 等待1ms，并获取按键信息
            if key == ord('q'):  # 如果按下'q'键，则退出循环
                break
        self.cleanup()

    def cleanup(self):
        # 关闭OpenCV窗口
        cv2.destroyAllWindows()
        self.cap.release()

    #在图像中画十字
    def draw_cross(self, frame, point, size):   
        thickness = 2  # 线条粗度  
        color = (0, 0, 255)  # 红色，BGR格式  
        # 计算十字的四个端点坐标  
        x, y = point
        x = int(x)
        y = int(y)  
        p1 = (x - size, y)  
        p2 = (x + size, y)  
        p3 = (x, y - size)  
        p4 = (x, y + size)  
        # 在图像上画十字  
        cv2.line(frame, p1, p2, color, thickness)  
        cv2.line(frame, p3, p4, color, thickness)

    #在图像中画方块
    def draw_rect(self, frame, x, y, w, h):
        cv2.rectangle(frame, (x, y), (x + w, y + h), (0, 0, 255), 2)    
    
    #在图像中画圆
    def draw_circle(self, frame, x, y, radius):
        cv2.circle(frame, (x, y), radius, (255, 0, 0), -1)

    def nothing(self):
        pass


if __name__ == '__main__':
    image_processing = ImageProcessing()
    image_processing.run()
    
    
    
    
    
    
    
    
    

