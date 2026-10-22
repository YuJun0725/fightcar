import cv2  
  
# 读取图像  
img = cv2.imread("cat.jpeg")  
  
# 显示原始图像  
cv2.imshow('Original Image', img)  
  
# 分离颜色通道  
blue, green, red = cv2.split(img)  
  
# 显示分离后的颜色通道  
cv2.imshow('Blue Channel', blue)  
cv2.imshow('Green Channel', green)  
cv2.imshow('Red Channel', red)  
  
# 合并颜色通道  
merged = cv2.merge([blue, green, red])  
  
# 显示合并后的图像  
cv2.imshow('Merged Image', merged)  
  
# 等待用户按下任意键退出  
cv2.waitKey(0)  
  
# 销毁所有窗口  
cv2.destroyAllWindows()