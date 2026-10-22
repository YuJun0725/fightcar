import cv2

# 打开摄像头，使用默认摄像头（索引为0）
cap = cv2.VideoCapture(0)

cv2.namedWindow("Camera Feed", cv2.WINDOW_NORMAL) 

# 检查摄像头是否成功打开
if not cap.isOpened():
    print("无法打开摄像头")
    exit()

# 循环读取摄像头的每一帧图像
while True:
    # 读取一帧图像
    ret, frame = cap.read()

    # 检查是否成功读取图像
    if not ret:
        print("无法获取摄像头帧")
        break

    # 显示图像
    cv2.imshow("Camera Feed", frame)

    # 按下'q'键退出循环
    if cv2.waitKey(1) & 0xFF == ord('q'):
        break

# 释放摄像头资源
cap.release()

# 关闭所有OpenCV窗口
cv2.destroyAllWindows()