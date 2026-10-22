import cv2  
  
# 读取图片  
img = cv2.imread('cat.jpeg')  
  
# 将图片转换为灰度图  
gray_img = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)  
  
# 使用Canny算法进行边缘检测  
edges = cv2.Canny(gray_img, threshold1=30, threshold2=100)  
  
# 显示原图和处理后的图像  
cv2.imshow('Original Image', img)  
cv2.imshow('Edge Image', edges)  
  
cv2.waitKey(0)  
cv2.destroyAllWindows()