import sys 
sys.path.append("..") 
import cv2  

from PyQt5.QtWidgets import QApplication, QWidget, QLabel , QSlider,QVBoxLayout, QHBoxLayout, QPushButton
from PyQt5.QtGui import QImage, QPixmap  
from PyQt5.QtCore import QTimer, Qt  

import numpy as np

import time

from uptech import UpTech

class RobotControl:
    def __init__(self):
        self.up = UpTech()
        time.sleep(0.01)
        self.up.CDS_Open()
        time.sleep(0.2)
        self.up.CDS_SetMode(1,1) #0舵机，1电机
        self.up.CDS_SetMode(2,1)
        self.up.CDS_SetMode(3,1)
        self.up.CDS_SetMode(4,1)

        self.up.CDS_SetMode(5,0) #0舵机，1电机
        self.up.CDS_SetMode(6,0)
        self.up.CDS_SetMode(7,0)
        self.up.CDS_SetMode(8,0)
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
    
    # 捡球动作
    def pick_ball(self):
        self.up.CDS_SetAngle(5,512,256)
        time.sleep(2)
        self.up.CDS_SetAngle(6,580,256)
        self.up.CDS_SetAngle(7,450,256)
        time.sleep(2)
        self.up.CDS_SetAngle(5,921,256)
        time.sleep(2)
        self.up.CDS_SetAngle(6,495,256)
        self.up.CDS_SetAngle(7,530,256)
    
    def close(self):
        self.up.CDS_Close()  
  
class CameraWidget(QWidget):  
    def __init__(self):  
        super().__init__()  
        
        self.initUI()  
  
        # 创建定时器，用于定时读取摄像头图像  
        self.timer = QTimer(self)  
        self.timer.timeout.connect(self.update_frame)  
        self.timer.start(30)  # 设置定时器间隔为30ms  
  
        # 创建OpenCV视频捕获对象  
        self.cap = cv2.VideoCapture(0)  
        self.movement = RobotControl()

        # 初始化点击位置变量  
        self.click_pos = None  
        self.enable_move = False

        # 初始化HSV范围变量  
        self.hmin = 0  
        self.hmax = 180  
        self.smin = 0  
        self.smax = 255  
        self.vmin = 0  
        self.vmax = 255  
  
        # 创建滑动条并设置初始值  
        self.slider_hmin.setValue(self.hmin)  
        self.slider_hmax.setValue(self.hmax)  
        self.slider_smin.setValue(self.smin)  
        self.slider_smax.setValue(self.smax)  
        self.slider_vmin.setValue(self.vmin)  
        self.slider_vmax.setValue(self.vmax)  

        # 创建是否已经捡球标志位
        self.isPick = False
  
    def initUI(self):  
        # 设置窗口标题和大小  
        self.setWindowTitle('Camera View with HSV')  
        self.setGeometry(100, 100, 640, 480)  
  
        # 创建一个标签用于显示图像  
        self.label = QLabel(self)  
        self.label.resize(640, 480)  
        self.label.mousePressEvent = self.image_clicked  
        
        self.mask_label = QLabel(self)
        self.mask_label.resize(640,480)
        
        # 创建滑动条  
        self.slider_hmin = QSlider(Qt.Horizontal, self)  
        self.slider_hmin.setRange(0, 180)  
        self.slider_hmin.valueChanged.connect(self.update_hmin)  
        self.hmin_label = QLabel("HMIN_Value: 0 | Range: 0 - 180", self) 
        hmin_layout = QHBoxLayout()  
        hmin_layout.addWidget(self.slider_hmin)  
        hmin_layout.addWidget(self.hmin_label) 
  
        self.slider_hmax = QSlider(Qt.Horizontal, self)  
        self.slider_hmax.setRange(0, 180)  
        self.slider_hmax.valueChanged.connect(self.update_hmax)  
        self.hmax_label = QLabel("HMAX_Value: 180 | Range: 0 - 180", self)
        hmax_layout = QHBoxLayout()  
        hmax_layout.addWidget(self.slider_hmax)  
        hmax_layout.addWidget(self.hmax_label)  
  
        self.slider_smin = QSlider(Qt.Horizontal, self)  
        self.slider_smin.setRange(0, 255)  
        self.slider_smin.valueChanged.connect(self.update_smin)  
        self.smin_label = QLabel("SMIN_Value: 0 | Range: 0 - 255", self) 
        smin_layout = QHBoxLayout()  
        smin_layout.addWidget(self.slider_smin)  
        smin_layout.addWidget(self.smin_label) 
  
        self.slider_smax = QSlider(Qt.Horizontal, self)  
        self.slider_smax.setRange(0, 255)  
        self.slider_smax.valueChanged.connect(self.update_smax) 
        self.smax_label = QLabel("SMAX_Value: 255 | Range: 0 - 255", self)  
        smax_layout = QHBoxLayout()  
        smax_layout.addWidget(self.slider_smax)  
        smax_layout.addWidget(self.smax_label)  
  
        self.slider_vmin = QSlider(Qt.Horizontal, self)  
        self.slider_vmin.setRange(0, 255)  
        self.slider_vmin.valueChanged.connect(self.update_vmin)  
        self.vmin_label = QLabel("VMIN_Value: 0 | Range: 0 - 255", self) 
        vmin_layout = QHBoxLayout()  
        vmin_layout.addWidget(self.slider_vmin)  
        vmin_layout.addWidget(self.vmin_label) 
  
        self.slider_vmax = QSlider(Qt.Horizontal, self)  
        self.slider_vmax.setRange(0, 255)  
        self.slider_vmax.valueChanged.connect(self.update_vmax)  
        self.vmax_label = QLabel("VMAX_Value: 255 | Range: 0 - 255", self) 
        vmax_layout = QHBoxLayout()  
        vmax_layout.addWidget(self.slider_vmax)  
        vmax_layout.addWidget(self.vmax_label)  

        self.move_button = QPushButton('Start Move', self)
        self.move_button.clicked.connect(self.toggleButton)
  
        # 创建布局并添加控件  
        layout = QVBoxLayout()  
        slider_layout = QVBoxLayout()  
        slider_layout.addLayout(hmin_layout)  
        slider_layout.addLayout(hmax_layout)  
        slider_layout.addLayout(smin_layout)  
        slider_layout.addLayout(smax_layout)  
        slider_layout.addLayout(vmin_layout)  
        slider_layout.addLayout(vmax_layout)  

        img_layout = QHBoxLayout() 
        img_layout.addWidget(self.label)  
        img_layout.addWidget(self.mask_label) 
        layout.addLayout(img_layout) 
        layout.addLayout(slider_layout)  
        layout.addWidget(self.move_button)
        self.setLayout(layout)  
  
    def update_frame(self):  
        # 读取摄像头的一帧图像  
        ret, frame = self.cap.read()
        frame = cv2.flip(frame, 0)    
        if ret:  
            # 求解颜色识别
            result = self.calcate_color(frame)
            # 将图像转换为QImage，然后转换为QPixmap在标签中显示  
            rgb_image = cv2.cvtColor(result, cv2.COLOR_BGR2RGB)  
            mask_image = cv2.cvtColor(self.mask_color, cv2.COLOR_GRAY2RGB)
            h, w, ch = rgb_image.shape  
            bytes_per_line = ch * w  
            
            convert_to_Qt_format = QImage(rgb_image.data, w, h, bytes_per_line, QImage.Format_RGB888)  
            p = convert_to_Qt_format.scaled(640, 480, Qt.KeepAspectRatio) 

            convert_to_Qt_format = QImage(mask_image.data, w, h, bytes_per_line, QImage.Format_RGB888)  
            mask_p = convert_to_Qt_format.scaled(640, 480, Qt.KeepAspectRatio)   
            
            self.label.setPixmap(QPixmap.fromImage(p))  
            self.mask_label.setPixmap(QPixmap.fromImage(mask_p))

    #根据颜色输出坐标
    def calcate_color(self, img):
        src = img.copy()
        result = src.copy()
        #颜色空间转换
        hsv_frame = cv2.cvtColor(src, cv2.COLOR_BGR2HSV)
        #二值化
        low_color = np.array([self.hmin, self.smin, self.vmin])
        high_color = np.array([self.hmax, self.smax, self.vmax])
        mask_color = cv2.inRange(hsv_frame, low_color, high_color)
        #滤波
        mask_color = cv2.medianBlur(mask_color, 7)
        s = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
        opened = cv2.morphologyEx(mask_color, cv2.MORPH_OPEN, s, iterations=2)
        closed = cv2.morphologyEx(opened, cv2.MORPH_CLOSE, s, iterations=2)
        edges = cv2.Canny(closed, 50, 100)

        self.mask_color = edges
       #提取联通域
        cnts, _ = cv2.findContours(mask_color, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
        
        c_list = []
        
        for cnt in cnts:
            num_points = len(cnt)
            (x, y, w, h) = cv2.boundingRect(cnt)
            if w < 100 or h < 100 :
                continue  # 排除宽和高不符合要求的轮廓
            if w*h < 6000:
                continue #排除面积不符合要求的轮廓
            if num_points < 268:
                continue #排除像素点个数不满足要求的轮廓
            #将每个满足条件的颜色矩形存入cnt_list
            c_list.append((x, y, w, h))

        if len(c_list) == 1:
            (x, y, w, h) = c_list[0]
            cv2.rectangle(result, (x, y), (x + w, y + h), (0, 0, 255), 2)  
            self.target_x = x + w/2
            self.target_y = y + h/2
            #计算颜色中心相对于图像中心的像素距离
            offset_x = self.target_x - img.shape[1] / 2
            if(offset_x >= 10 and self.enable_move):
                self.movement.move_left(190)
            elif(offset_x <= -10 and self.enable_move):
                self.movement.move_right(190)
            else:
                if(self.enable_move and not self.isPick):
                    self.movement.stop()
                    self.movement.pick_ball()
                    self.isPick = True
        return result

    # 更新HSV范围的方法  
    def update_hmin(self, value):  
        self.hmin = value  
        self.hmin_label.setText(f"HMIN_Value: {value} | Range: 0 - 180") 
        self.update_frame()  
  
    def update_hmax(self, value):  
        self.hmax = value 
        self.hmax_label.setText(f"HMAX_Value: {value} | Range: 0 - 180")  
        self.update_frame()  
  
    def update_smin(self, value):  
        self.smin = value  
        self.smin_label.setText(f"SMIN_Value: {value} | Range: 0 - 255") 
        self.update_frame()  
  
    def update_smax(self, value):  
        self.smax = value  
        self.smax_label.setText(f"SMAX_Value: {value} | Range: 0 - 255") 
        self.update_frame()  
  
    def update_vmin(self, value):  
        self.vmin = value  
        self.vmin_label.setText(f"VMIN_Value: {value} | Range: 0 - 255") 
        self.update_frame()  
  
    def update_vmax(self, value):  
        self.vmax = value  
        self.vmax_label.setText(f"VMAX_Value: {value} | Range: 0 - 255") 
        self.update_frame() 
  
    def image_clicked(self, event):  
        # 获取点击位置  
        self.click_pos = event.pos()  
        print(f"Clicked position: {self.click_pos}")  
  
        # 读取当前帧的HSV值  
        ret, frame = self.cap.read()  
        if ret:  
            # 将QPoint转换为对应的图像坐标  
            x = int(self.click_pos.x() * frame.shape[1] / self.label.width())  
            y = int(self.click_pos.y() * frame.shape[0] / self.label.height())  
            hsv_value = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)[y, x]  
            print(f"HSV value at clicked position: {hsv_value}")  

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
          
    def closeEvent(self, event):  
        # 释放摄像头资源  
        self.cap.release()  
        event.accept()  
    
    def toggleButton(self):
        if(self.move_button.text() == 'Start Move'):
            self.enable_move = True
            self.isPick = False
            self.move_button.setText('Stop Move')
        else:
            self.enable_move = False
            self.isPick = True
            self.move_button.setText('Start Move')
            self.movement.stop()

  
if __name__ == '__main__':  
    app = QApplication(sys.argv)  
    ex = CameraWidget()  
    ex.show()  
    sys.exit(app.exec_())
