import cv2

# 读取图像和模板
img = cv2.imread('cat.jpeg', 0)
template = cv2.imread('template.jpeg', 0)

# 计算SAD值
result = cv2.matchTemplate(img, template, cv2.TM_SQDIFF_NORMED)

# 获取最小值和最大值的位置
min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(result)

# 在原始图像中绘制矩形
w, h = template.shape[::-1]
top_left = min_loc
bottom_right = (top_left[0] + w, top_left[1] + h)
cv2.rectangle(img, top_left, bottom_right, 255, 2)

# 显示结果
cv2.imshow('image', img)
cv2.waitKey(0)
cv2.destroyAllWindows()
