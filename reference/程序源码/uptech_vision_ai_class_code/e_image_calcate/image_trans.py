import cv2  
import numpy as np  
  
# 读取图片  
img = cv2.imread('cat.jpeg')  
  
# 将图片转换为灰度图  
gray_img = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)  
  
# --- 平移操作 ---  
# 定义平移矩阵，将图像向右平移50像素，向下平移100像素  
M_translation = np.float32([[1, 0, 50], [0, 1, 100]])  
# 使用warpAffine函数实现平移  
translated_img = cv2.warpAffine(gray_img, M_translation, (gray_img.shape[1], gray_img.shape[0]))  
  
# --- 旋转操作 ---  
# 获取图像的尺寸  
(h, w) = gray_img.shape[:2]  
# 定义旋转中心点，这里选择图像中心  
center = (w / 2, h / 2)  
# 计算旋转矩阵，逆时针旋转45度  
M_rotation = cv2.getRotationMatrix2D(center, -45, 1.0)  
# 使用warpAffine函数实现旋转  
rotated_img = cv2.warpAffine(gray_img, M_rotation, (w, h))  
  
# --- 缩放操作 ---  
# 使用resize函数实现缩放，将图像的尺寸缩小为原来的一半  
resized_img = cv2.resize(gray_img, None, fx=0.5, fy=0.5, interpolation=cv2.INTER_LINEAR)  
  
# 显示处理后的图像（可选）  
cv2.imshow('Original Image', gray_img)  
cv2.imshow('Translated Image', translated_img)  
cv2.imshow('Rotated Image', rotated_img)  
cv2.imshow('Resized Image', resized_img)  
  
# 等待用户操作，然后关闭所有窗口  
cv2.waitKey(0)  
cv2.destroyAllWindows()