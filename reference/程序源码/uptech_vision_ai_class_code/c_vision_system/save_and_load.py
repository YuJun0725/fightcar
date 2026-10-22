import cv2
import numpy as np

# 生成一张纯白色的图片
width, height = 500, 500  # 定义图片的宽和高
white_image = np.ones((height, width, 3), dtype=np.uint8) * 255  # 生成一张纯白色的图片

# 在图像左上方画一个红色的圆形
center_coordinates = (int(width * 0.1), int(height * 0.1))  # 圆心坐标，位于图像的左上方
radius = 50  # 圆的半径
color = (0, 0, 255)  # 圆的颜色，红色
thickness = 2  # 圆的线条粗细

# 使用cv2.circle()方法在图像上画一个圆
white_image = cv2.circle(white_image, center_coordinates, radius, color, thickness)

# 保存图像到本地
cv2.imwrite('image_with_circle.jpg', white_image)

# 加载图像
loaded_image = cv2.imread('image_with_circle.jpg')

# 显示图像
cv2.imshow('Image with Red Circle', loaded_image)
cv2.waitKey(0)
cv2.destroyAllWindows()