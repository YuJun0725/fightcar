import cv2  
import numpy as np  
  
# 读取图片  
img = cv2.imread('cat.jpeg')  
  
# 将图片转换为灰度图  
gray_img = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)  
  
# Harris角点检测  
corner_harris = cv2.cornerHarris(gray_img, 2, 3, 0.04)  
  
# 对Harris检测的结果进行膨胀，以便更好地标记角点位置  
corner_harris = cv2.dilate(corner_harris, None)  
  
# 阈值处理，将角点和非角点分开（可调整阈值进行更细致地控制）  
corner_harris[corner_harris > 0.01 * corner_harris.max()] = 255  
corner_harris = np.uint8(corner_harris)  
  
# 找到Harris角点，并标记出来  
img[corner_harris > 0] = [0, 0, 255]  
  
# 显示图像  
cv2.imshow('Harris Corners', img)  
cv2.waitKey(0)  
cv2.destroyAllWindows()