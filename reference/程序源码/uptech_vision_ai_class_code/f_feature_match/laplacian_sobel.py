import cv2  
import numpy as np  
import matplotlib.pyplot as plt  
  
# 读取图片  
img = cv2.imread('cat.jpeg')  
  
# 将图片转换为灰度图  
gray_img = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)  
  
# 使用Sobel算子进行边缘检测  
sobel_edges = cv2.Sobel(gray_img, cv2.CV_8U, 1, 1, ksize=3)  
  
  
# 使用Laplacian算子进行边缘检测  
laplacian_edges = cv2.Laplacian(gray_img, cv2.CV_8U)  
  
# 显示原始图像和处理后的图像（可选）  
plt.figure(figsize=(10,10))  
plt.subplot(1,3,1), plt.imshow(gray_img, cmap='gray'), plt.title('Original Image')  
plt.subplot(1,3,2), plt.imshow(sobel_edges, cmap='gray'), plt.title('Edges using Sobel Operator') 
plt.subplot(1,3,3), plt.imshow(laplacian_edges, cmap='gray'), plt.title('Edges using Laplacian Operator')   
plt.show()  
