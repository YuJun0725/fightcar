import cv2  
import numpy as np  
  
# 生成一张纯白色的图片  
width, height = 500, 500  # 定义图片的宽和高  
white_image = np.ones((height, width, 3), dtype=np.uint8) * 255  # 生成一张纯白色的图片  
black_image = np.ones((height, width, 3), dtype=np.uint8) * 0  # 生成一张纯黑色的图片   

  
# 显示图像  
cv2.imshow('Image White', white_image) 
cv2.imshow('Image Black', black_image)   
cv2.waitKey(0)  
cv2.destroyAllWindows()