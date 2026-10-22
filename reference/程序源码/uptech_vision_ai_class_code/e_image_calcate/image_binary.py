import cv2  
  
# 读取图片  
img = cv2.imread('cat.jpeg')  
  
# 将图片转换为灰度图  
gray_img = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)  
  
# 二值化处理  
ret, binary_img = cv2.threshold(gray_img, 0, 255, cv2.THRESH_BINARY | cv2.THRESH_OTSU)  
  
# 显示二值化后的图像（可选）  
cv2.imshow('Binary Image', binary_img)  
  
# 等待用户操作，然后关闭所有窗口  
cv2.waitKey(0)  
cv2.destroyAllWindows()