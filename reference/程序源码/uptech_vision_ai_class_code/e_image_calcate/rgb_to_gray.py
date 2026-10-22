import cv2  
  
# 读取图片  
img = cv2.imread('cat.jpeg')  
  
# 将图片转换为灰度图  
gray_img = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)  
  
# 显示灰度图  
cv2.imshow('Grayscale Image', gray_img)  
  
# 等待用户按键，然后关闭窗口  
cv2.waitKey(0)  
cv2.destroyAllWindows()