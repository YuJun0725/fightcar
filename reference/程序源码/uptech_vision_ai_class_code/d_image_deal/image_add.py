import cv2  
  
# 读取两张图片  
img1 = cv2.imread("cat.jpeg")  
img2 = cv2.imread("dog.jpeg")  
  
# 获取两张图片的尺寸  
height1, width1 = img1.shape[:2]  
height2, width2 = img2.shape[:2]  
  
# 判断两张图片的尺寸是否一致，如果不一致，调整img2的尺寸  
if height1 != height2 or width1 != width2:  
    img2 = cv2.resize(img2, (width1, height1))  
  
# 进行图像的加法操作  
add1 = cv2.add(img1, img2)  
  
# 进行加权加法操作  
add2 = cv2.addWeighted(img1, 0.5, img2, 0.5, 3)  
  
# 显示结果  
cv2.imshow("add1", add1)  
cv2.imshow("add2", add2)  
  
cv2.waitKey()