import dlib                     #人脸识别的库dlib
import numpy as np              #数据处理的库numpy
import cv2                      #图像处理的库Opencv
import sys
sys.path.append("..")

import time
from uptech import UpTech


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

class Face_Emotion():

    def __init__(self):
        # 使用特征提取器get_frontal_face_detector
        self.detector = dlib.get_frontal_face_detector()
        
        # dlib的68点模型，使用作者训练好的特征预测器
        modelPath = sys.path[0] + "/shape_predictor_68_face_landmarks.dat"
        
        self.predictor = dlib.shape_predictor(modelPath)

        self.movement = FourWhellMove()

        # 打开摄像头，使用默认摄像头（索引为0）
        self.cap = cv2.VideoCapture(0)

        # 设置一个窗口来显示图像  
        self.result_name = "Emotion Detect Image" 
        
        cv2.namedWindow(self.result_name, cv2.WINDOW_NORMAL) 
        
        if not self.cap.isOpened():
            self.isOpen = False
            print("无法打开摄像头,请检查线路连接!!!")
        else:
            self.isOpen = True
            print("成功打开摄像头")

        if(self.isOpen):
            
            while(True):
                
                ret, frame = self.cap.read()
                frame = cv2.resize(frame, (640, 480))
                
                if (ret):
                
                    result = self.update_frame(frame)
                    cv2.imshow(self.result_name, result)

                key = cv2.waitKey(30) & 0xFF  # 等待1ms，并获取按键信息  
                if key == ord('q'):  # 如果按下'q'键，则退出循环  
                    self.cleanup()
                    break
   

    def update_frame(self, frame):

        result = frame.copy()

        # 取灰度
        img_gray = cv2.cvtColor(frame, cv2.COLOR_RGB2GRAY)

        # 使用人脸检测器检测每一帧图像中的人脸。并返回人脸数rects
        faces = self.detector(img_gray, 0)

        # 待会要显示在屏幕上的字体
        font = cv2.FONT_HERSHEY_SIMPLEX

        # 眉毛直线拟合数据缓冲
        line_brow_x = []
        line_brow_y = []

        # 如果检测到1人脸
        if len(faces) == 1:
            # 对每个人脸都标出68个特征点
            for i in range(len(faces)):
                # enumerate方法同时返回数据对象的索引和数据，k为索引，d为faces中的对象
                for k, d in enumerate(faces):
                    # 用红色矩形框出人脸
                    cv2.rectangle(result, (d.left(), d.top()), (d.right(), d.bottom()), (0, 0, 255))
                    # 计算人脸框边长
                    self.face_width = d.right() - d.left()

                    # 使用预测器得到68点数据的坐标
                    shape = self.predictor(result, d)
                    # 圆圈显示每个特征点
                    for i in range(68):
                        cv2.circle(result, (shape.part(i).x, shape.part(i).y), 2, (0, 255, 0), -1, 8)
                        # 分析任意n点的位置关系来作为表情识别的依据
                        mouth_width = (shape.part(54).x - shape.part(48).x) / self.face_width  # 嘴巴咧开程度
                        mouth_higth = (shape.part(66).y - shape.part(62).y) / self.face_width  # 嘴巴张开程度
                        # print("嘴巴宽度与识别框宽度之比：",mouth_width_arv)
                        # print("嘴巴高度与识别框高度之比：",mouth_higth_arv)

                        # 通过两个眉毛上的10个特征点，分析挑眉程度和皱眉程度
                        brow_sum = 0  # 高度之和
                        frown_sum = 0  # 两边眉毛距离之和
                        for j in range(17, 21):
                            brow_sum += (shape.part(j).y - d.top()) + (shape.part(j + 5).y - d.top())
                            frown_sum += shape.part(j + 5).x - shape.part(j).x
                            line_brow_x.append(shape.part(j).x)
                            line_brow_y.append(shape.part(j).y)

                        # 计算眉毛的倾斜程度
                        tempx = np.array(line_brow_x)
                        tempy = np.array(line_brow_y)
                        z1 = np.polyfit(tempx, tempy, 1)  # 拟合成一次直线
                        self.brow_k = -round(z1[0], 3)  # 拟合出曲线的斜率和实际眉毛的倾斜方向是相反的

                        brow_hight = (brow_sum / 10) / self.face_width  # 眉毛高度占比
                        brow_width = (frown_sum / 5) / self.face_width  # 眉毛距离占比
                        # print("眉毛高度与识别框高度之比：",round(brow_arv/self.face_width,3))
                        # print("眉毛间距与识别框高度之比：",round(frown_arv/self.face_width,3))

                        # 眼睛睁开程度
                        eye_sum = (shape.part(41).y - shape.part(37).y + shape.part(40).y - shape.part(38).y +
                                   shape.part(47).y - shape.part(43).y + shape.part(46).y - shape.part(44).y)
                        eye_hight = (eye_sum / 4) / self.face_width
                        # print("眼睛睁开距离与识别框高度之比：",round(eye_open/self.face_width,3))

                        # 分情况讨论
                        # 张嘴，可能是开心或者惊讶
                        if round(mouth_higth >= 0.03):
                            if eye_hight >= 0.056:
                                cv2.putText(result, "amazing", (d.left(), d.bottom() + 20), cv2.FONT_HERSHEY_SIMPLEX, 0.8,
                                            (0, 0, 255), 2, 4)
                                # 机器人右转
                                self.movement.turn_right(256)
                            else:
                                cv2.putText(result, "happy", (d.left(), d.bottom() + 20), cv2.FONT_HERSHEY_SIMPLEX, 0.8,
                                            (0, 0, 255), 2, 4)
                                # 机器人走向使用者
                                self.movement.move_forward(256)

                        # 没有张嘴，可能是正常和生气
                        else:
                            if self.brow_k <= -0.3:
                                cv2.putText(result, "angry", (d.left(), d.bottom() + 20), cv2.FONT_HERSHEY_SIMPLEX, 0.8,
                                            (0, 0, 255), 2, 4)
                                # 机器人远离使用者
                                self.movement.move_backward(256)
                            else:
                                cv2.putText(result, "nature", (d.left(), d.bottom() + 20), cv2.FONT_HERSHEY_SIMPLEX, 0.8,
                                            (0, 0, 255), 2, 4)
        else:
            # 没有检测到1人脸
            cv2.putText(result, "Not 1 Face", (20, 50), font, 1, (0, 0, 255), 1, cv2.LINE_AA)

        return result


    def cleanup(self):  
        # 关闭OpenCV窗口  
        cv2.destroyAllWindows() 


if __name__ == "__main__":
    my_face = Face_Emotion()
