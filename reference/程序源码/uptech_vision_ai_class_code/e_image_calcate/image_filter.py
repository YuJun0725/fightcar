import cv2  
import numpy as np  
  
# 读取图片  
img = cv2.imread('cat.jpeg')  
  
# 将图片转换为灰度图  
gray_img = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)  
  
# 均值滤波  
mean_filtered_img = cv2.blur(gray_img, (5, 5))  # 使用5x5的均值滤波器  
  
# 方框滤波  
box_filtered_img = cv2.boxFilter(gray_img, -1, (5, 5))  # 使用5x5的方框滤波器  
  
# 高斯滤波  
gaussian_filtered_img = cv2.GaussianBlur(gray_img, (5, 5), 0)  # 使用5x5的高斯滤波器，标准差为0  
  
# 中值滤波  
median_filtered_img = cv2.medianBlur(gray_img, 5)  # 使用5x5的中值滤波器  
  
# 显示各种滤波后的图像（可选）  
cv2.imshow('Mean Filtered Image', mean_filtered_img)  
cv2.imshow('Box Filtered Image', box_filtered_img)  
cv2.imshow('Gaussian Filtered Image', gaussian_filtered_img)  
cv2.imshow('Median Filtered Image', median_filtered_img)  
  
# 等待用户操作，然后关闭所有窗口  
cv2.waitKey(0)  
cv2.destroyAllWindows()