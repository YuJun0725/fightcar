import cv2
import numpy as np
import sys
import os


class FaceRecognition:
    def __init__(self):
        
        # 人脸阈值参数
        self.confidence = 90

        # 加载一个人脸检测模型
        current_path = sys.path[0]
        modelPath = current_path + "/haarcascade_frontalface_alt.xml"
        self.face_cascade = cv2.CascadeClassifier(modelPath)

        # 要识别的人脸名称
        self.face_name = ""
        self.dirname = current_path + "/data"
        if not os.path.isdir(self.dirname):
            os.makedirs(self.dirname)

        # 读取人脸图片，训练一个人脸识别模型
        [names, X, Y] = self.read_images(self.dirname)
        Y = np.asarray(Y, dtype=np.int32)
        self.model = cv2.face.LBPHFaceRecognizer_create()
        self.model.train(np.asarray(X), np.asarray(Y))
        self.names = names
        print("Train Finish!!!!")

        # 打开USB摄像头（通常0代表默认摄像头，如果有多个摄像头可以尝试1、2等）
        self.cap = cv2.VideoCapture(0)

        # 设置一个窗口来显示图像  
        self.result_name = "Face Recognize Image" 
        
        cv2.namedWindow(self.result_name, cv2.WINDOW_NORMAL) 

        self.forward_speed = 0.3
        self.turn_speed = 1.0

    def read_images(self, path, sz=None):
        c = 0
        X, Y = [], []
        names = []
        for dirname, dirnames, filenames in os.walk(path):
            for subdirname in dirnames:
                subject_path = os.path.join(dirname, subdirname)
                for filename in os.listdir(subject_path):
                    try:
                        if filename == ".directory":
                            continue
                        filepath = os.path.join(subject_path, filename)
                        im = cv2.imread(os.path.join(subject_path, filename), cv2.IMREAD_GRAYSCALE)
                        if im is None:
                            print("image" + filepath + "is None")
                        if sz is not None:
                            im = cv2.resize(im, sz)
                        X.append(np.asarray(im, dtype=np.uint8))
                        Y.append(c)
                    except:
                        print("unexpected error")
                        raise
                c = c + 1
                names.append(subdirname)
        return [names, X, Y]

    def update_cmd(self, linear_speed, angular_speed):
        # 这里可以根据实际情况处理速度控制相关逻辑，比如控制机器人（如果有的话）
        print(f"Linear speed: {linear_speed}, Angular speed: {angular_speed}")

    def process_image(self):
        
        ret, cv_image = self.cap.read()
        cv_image = cv2.resize(cv_image, (640, 480))
        
        if not ret:
            print("无法获取摄像头图像")
            return

        result = cv_image.copy()
       
        # 转化为灰度图
        gray = cv2.cvtColor(cv_image, cv2.COLOR_BGR2GRAY)
       
        # 人脸检测函数
        faces = self.face_cascade.detectMultiScale(gray, 1.3, 5)
        
        # 如果没有识别到人脸，直接忽略
        if len(faces) == 0:
            self.update_cmd(0, 0)
            print("No Person, Ignore!!!")
            return
        
        # 如果不是只有一张脸，直接忽略
        if len(faces)!= 1:
            self.update_cmd(0, 0)
            print("More than one face or no face detected, Ignore!!!")
            return
        
        for (x, y, w, h) in faces:
            result = cv2.rectangle(result, (x, y), (x + w, y + h), (255, 0, 0), 2)
            roi = gray[x:x + w, y:y + h]
            try:
                
                # 人脸归一化，统一200x200大小
                roi = cv2.resize(roi, (200, 200), interpolation=cv2.INTER_LINEAR)
                
                # 人脸预测
                [p_label, p_confidence] = self.model.predict(roi)
                
                # 画出名字的结果和置信度
                cv2.putText(result, self.names[p_label], (x, y - 50), cv2.FONT_HERSHEY_SIMPLEX, 1, 255, 2)
                cv2.putText(result, str(p_confidence), (x, y - 20), cv2.FONT_HERSHEY_SIMPLEX, 1, 255, 2)
                
                if p_confidence > self.confidence and self.names[p_label] == self.face_name:
                    offset_x = ((x + w) / 2 - cv_image.shape[1] / 2)
                    target_area = w * h
                    linear_vel = 0
                    angular_vel = 0
                    if target_area < 100:
                        linear_vel = 0.0
                    elif target_area > 110:
                        linear_vel = 0.1
                    else:
                        linear_vel = 0.0
                    if offset_x > 0:
                        angular_vel = 0.1
                    if offset_x < 0:
                        angular_vel = -0.1
                    self.update_cmd(linear_vel, angular_vel)
            except:
                return
            
        cv2.imshow(self.result_name, result)
        
        if cv2.waitKey(1) & 0xFF == ord('q'):
            self.cleanup()

    def run(self):
        while True:
            self.process_image()

    def cleanup(self):
        # 关闭OpenCV窗口和释放摄像头资源
        cv2.destroyAllWindows()
        self.cap.release()


if __name__ == '__main__':
    face_recognition = FaceRecognition()
    face_recognition.run()