import sys
sys.path.append("..")

import apriltag
import threading
import cv2
import time

"""
本程序用于实现 apriltag 检测敌、我、中立能量块
"""


class TagDetector:
    
    # 前搁浅计时
    nd = 0
    # 后搁浅计时
    ne = 0
    
    def __init__(self):

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
    

if __name__ == '__main__':
    tag_detector = TagDetector()
    while True:
            time.sleep(1.0)
