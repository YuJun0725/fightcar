import cv2  
import numpy as np  
  
def flood_fill(img, seed_point, new_val, lo_diff=2, up_diff=2, conn=8):  
    """  
    泛洪填充算法实现  
  
    参数:  
    img: 需要处理的图像  
    seed_point: 泛洪填充的起始点  
    new_val: 新的颜色值  
    lo_diff: 最大值与最小值之差的下限  
    up_diff: 最大值与最小值之差的上限  
    conn: 连接方式，4代表四连接，8代表八连接  
    """  
    height, width = img.shape[:2]  
    seed_y, seed_x = seed_point  
    cv2.floodFill(img, None, seed_point, new_val, loDiff=lo_diff, upDiff=up_diff, flags=conn)  
  
# 读取图片  
img = cv2.imread('cat.jpeg')  

cv2.imshow('Raw Image', img)  
  
# 确保图片读取正确  
if img is not None:  
    # 转换为灰度图像  
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)  
  
    # 显示填充后的图片  
    cv2.imshow('Filled Image', gray)  
  
    # 选择一个起始点进行泛洪填充  
    seed_point = (50, 450)  
  
    # 新的颜色  
    new_color = 128  # BGR format  
  
    # 进行泛洪填充  
    flood_fill(gray, seed_point, new_color)  
  
    # 显示填充后的图片  
    cv2.imshow('Filled Image', gray)  
  
    # 等待用户按键，然后关闭窗口  
    cv2.waitKey(0)  
    cv2.destroyAllWindows()  
else:  
    print("Error: Unable to read the image.")