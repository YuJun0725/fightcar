# main.py
import cv2
from face_reid import FaceDetector


debug = True


# 初始化检测器
face_detector = FaceDetector()

# 启动摄像头
cap = cv2.VideoCapture(0)

try:
    while True:
        ret, frame = cap.read()

        if not ret:
            print("没有图像,检查摄像头,程序将会退出")
            break

        frame = cv2.flip(frame,-1)

        # 进行识别, 并打印识别结果
        detections = face_detector.detect_faces_in_image(frame, sim_threshold=0.4)
    
        for name, box, center in detections:
            print(f"检测到 {name}; 其边框坐标 {box}; 中心点坐标 {center}")
    
        if debug:
            image =  face_detector.draw_bounding_boxes(frame, detections)
            cv2.imshow('Face', image)
            if cv2.waitKey(1) & 0xFF == ord("q"):
                break

except KeyboardInterrupt:
    cap.release()
