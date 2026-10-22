import sys
sys.path.append("..")

import cv2

from uptech import UpTech
import apriltag
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

class TagDetect:
    def __init__(self):
        options = apriltag.DetectorOptions(families='tag36h11')
        self.tag_detector = apriltag.Detector(options) 
        # 打开USB摄像头（通常0代表默认摄像头，如果有多个摄像头可以尝试1、2等）
        self.cap = cv2.VideoCapture(0)
        self.movement = FourWhellMove()
        self.target_tag_id = 3
        # 设置一个窗口来显示图像  
        self.result_name = "Apritag Detect Image"  
        
    #tag检测，输入图像，反馈tag的数组
    def update_frame(self):
        ret, frame = self.cap.read()
        result = frame.copy()
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY) 
        apriltag_detect_results = self.tag_detector.detect(gray) 
        for tag_result in apriltag_detect_results:
            tag_id = tag_result.tag_id
            if(tag_id == self.target_tag_id):
                top_left, top_right, bottom_right, bottom_left = tag_result.corners
                center_x = (top_left[0] + bottom_right[0]) / 2  
                center_y = (top_left[1] + bottom_right[1]) / 2 
                
                print(center_x, center_y)

                self.draw_rect(result, int(top_left[0]), int(top_left[1]), int(bottom_right[0]-top_left[0]), int(bottom_right[1]-top_left[1]))
                self.draw_cross(result, (int(center_x), int(center_y)), 20)


                #计算tag中心相对于图像中心的像素距离
                offset_x = center_x - frame.shape[1] / 2
                if(offset_x >= 40):
                    self.movement.turn_right(256)
                elif(offset_x <= -40):
                    self.movement.turn_left(256)
                else:
                    self.movement.stop()
        return result 

    def run(self):
        while True:
            result = self.update_frame()
      
            cv2.imshow(self.result_name, result)
            
            key = cv2.waitKey(1) & 0xFF  # 等待1ms，并获取按键信息
            if key == ord('q'):  # 如果按下'q'键，则退出循环
                break
        self.cleanup()

    def cleanup(self):  
        # 关闭OpenCV窗口  
        cv2.destroyAllWindows()  
        self.movement.stop()
        time.sleep(1.0)
        self.movement.close()

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


if __name__ == '__main__':
    apriltag_detect = TagDetect()
    apriltag_detect.run()
            