import cv2  
import numpy as np  
  
# 读取图片  
img = cv2.imread('cat.jpeg')  
  
# 将图片转换为灰度图  
gray_img = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)  
  
# Shi-Tomasi角点检测，这里使用cv2.goodFeaturesToTrack函数  
corners = cv2.goodFeaturesToTrack(gray_img, maxCorners=100, qualityLevel=0.3, minDistance=7)  
  
# 在原图像上绘制检测到的角点  
for corner in corners:  
    x, y = corner.ravel()  
    cv2.circle(img, (int(x), int(y)), 3, (0, 255, 0), -1)  
  
# 显示图像  
cv2.imshow('Shi-Tomasi Corners', img)  
cv2.waitKey(0)  
cv2.destroyAllWindows()