import cv2  
import numpy as np  
  
# 读取图片  
img = cv2.imread('cat.jpeg')  
  
# 将图片转换为灰度图  
gray_img = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)  
   
# Laplace锐化  
laplacian = cv2.Laplacian(gray_img, cv2.CV_64F)  
laplace_sharpened_img = cv2.convertScaleAbs(laplacian) + gray_img  
  
# 显示锐化后的图像（可选）  
cv2.imshow('Original Image', gray_img)  
cv2.imshow('Laplace Sharpened Image', laplace_sharpened_img)  
  
# 等待用户操作，然后关闭所有窗口  
cv2.waitKey(0)  
cv2.destroyAllWindows()