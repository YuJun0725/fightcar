import cv2
import numpy as np

# 读取图像
image = cv2.imread('cat.jpeg')

# 获取图像的高度、宽度和通道数
height, width, channels = image.shape

# 选择要操作的像素位置（这里以(100, 100)为例）
x = 100
y = 100

# 加法操作
pixel_addition = image.copy()
pixel_addition[y, x] = np.clip(pixel_addition[y, x]+np.array([50, 50, 50]), 0, 255).astype(np.uint8) # 对像素值增加[50,50,50]

# 减法操作
pixel_subtraction = image.copy()
pixel_addition[y, x] = np.clip(pixel_addition[y, x] - np.array([30, 30, 30]), 0, 255).astype(np.uint8) # 对像素值减小[50,50,50]

# 乘法操作
pixel_multiplication = image.copy()
pixel_addition[y, x] = np.clip(pixel_addition[y, x] * np.array([2, 2, 2]), 0, 255).astype(np.uint8) # 对像素值乘以2

# 除法操作
pixel_division = image.copy()
pixel_addition[y, x] = np.clip(pixel_addition[y, x] / np.array([2, 2, 2]), 0, 255).astype(np.uint8) # 对像素值除以2（注意这里像素值会取整）

# 显示原始图像和操作后的图像（这里简单显示，你可以根据需要进一步处理显示效果）
cv2.imshow('Original Image', image)
cv2.imshow('Pixel Addition', pixel_addition)
cv2.imshow('Pixel Subtraction', pixel_subtraction)
cv2.imshow('Pixel Multiplication', pixel_multiplication)
cv2.imshow('Pixel Division', pixel_division)
cv2.waitKey(0)
cv2.destroyAllWindows()