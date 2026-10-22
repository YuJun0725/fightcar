import cv2
import sys
import time

from rknn_func.rknnpool import rknnPoolExecutor
from rknn_func.func import myFunc

class YoloDetect:
    def __init__(self):
        
        # 打开摄像头，使用默认摄像头（索引为0）
        self.cap = cv2.VideoCapture(0)
        
        modelPath = sys.path[0] + "/rknnModel/yolov5s_relu_tk2_RK3588_i8.rknn"
        #modelPath = sys.path[0] + "/rknnModel/shooting_quantized_mmse.rknn"
        
        # 线程数, 增大可提高帧率
        TPEs = 4
        # 初始化rknn池
        self.pool = rknnPoolExecutor(rknnModel=modelPath, TPEs=TPEs, func=myFunc)

        # 设置一个窗口来显示图像  
        self.result_name = "Yolo Detect Image"  
        cv2.namedWindow(self.result_name, cv2.WINDOW_NORMAL) 
        
        if not self.cap.isOpened():
            self.isOpen = False
            print("无法打开摄像头,请检查线路连接!!!")
        else:
            self.isOpen = True
            print("成功打开摄像头")

        if(self.isOpen):
            
            #初始化异步所需要的帧
            for i in range(TPEs + 1):
                ret, frame = self.cap.read()
                frame = cv2.resize(frame, (640, 480))
                self.pool.put(frame)

            frames, loopTime, initTime = 0, time.time(), time.time()

            while(True):
                
                ret, frame = self.cap.read()
                frame = cv2.resize(frame, (640, 480))
                result = self.update_frame(frame)
                
                cv2.imshow(self.result_name, result)

                key = cv2.waitKey(30) & 0xFF  # 等待1ms，并获取按键信息 
                 
                if key == ord('q'):  # 如果按下'q'键，则退出循环 
                    self.cleanup() 
                    break

    #yolo检测，输入图像
    def update_frame(self, frame):
        self.pool.put(frame)
        (frame, center), flag = self.pool.get()
        result = frame.copy()
        return result 

    def cleanup(self):  
        # 关闭OpenCV窗口  
        cv2.destroyAllWindows()  
        self.pool.release()


if __name__ == '__main__':
    yolo_detect = YoloDetect()
