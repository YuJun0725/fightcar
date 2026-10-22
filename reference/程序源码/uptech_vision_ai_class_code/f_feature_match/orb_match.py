import cv2
import numpy as np

# 读取图像并提取特征，并以灰度模式加载。
img = cv2.imread("cat.jpeg", cv2.IMREAD_GRAYSCALE)
template = cv2.imread("template.jpeg", cv2.IMREAD_GRAYSCALE)
# 预览显示
cv2.imshow("cat image", img)
cv2.imshow("template image", template)
cv2.waitKey(0)

# 特征描述子，创建了一个 ORB（Oriented FAST and Rotated BRIEF）特征提取器。
orb = cv2.ORB_create()
# 使用 ORB 提取器检测图像中的特征点和特征描述子。
keypoints_img, descriptors_img = orb.detectAndCompute(img, None)
keypoints_template, descriptors_template = orb.detectAndCompute(template, None)

# 创建BFMatcher对象，基于暴力匹配的匹配器。
bf = cv2.BFMatcher()
# 使用匹配器在两个图像的特征描述子之间进行了 K 近邻匹配，得到了每个特征点的最佳两个匹配。
# 这个参数定义了我们希望得到的最佳匹配项的数量。通常情况下，设置为2，这样每个特征点会有两个最佳匹配项，然后可以通过 Lowe's ratio 测试来筛选这些匹配，只保留最可靠的匹配。
matches = bf.knnMatch(descriptors_img, descriptors_template, k=2)

# 过滤
matches = [match for match in matches if match]
# 排序
matches = sorted(matches, key=lambda x: x[0].distance) if matches else []

# 画出距离最短的前15个点
result = cv2.drawMatchesKnn(img, keypoints_img, template, keypoints_template, matches[0:15], None,
                            matchColor=(0, 255, 0), singlePointColor=(255, 0, 255))
cv2.imshow("orb-match", result)
cv2.imwrite("orb-match-1.jpg", result)
cv2.waitKey(0)

# 应用Lowe's ratio测试剔除不良匹配
good = []
for m, n in matches:
    if m.distance < 0.99 * n.distance:
        good.append([m])

if len(good) >= 4:  # 至少需要4个匹配点来计算单应性矩阵

    # keypoints_img[m[0].queryIdx].pt for m in good：这是一个列表推导式，它遍历了列表 good 中的每个元素 m，然后使用索引 m[0].queryIdx 来获取关键点 keypoints_img 中对应索引的位置信息.pt。这样就创建了一个包含关键点位置信息的列表。
    # np.float32(...)：这将列表中的数据转换为 NumPy 的浮点数类型。
    # .reshape(-1, 1, 2)：这个操作用于调整数组的形状。在这里，它将数组重新组织为一个三维数组，第一维度是自动确定的（根据数组的长度），第二维度是1（每个点有1个坐标），第三维度是2（x 和 y 坐标）。
    src_pts = np.float32([keypoints_img[m[0].queryIdx].pt for m in good]).reshape(-1, 1, 2)
    dst_pts = np.float32([keypoints_template[m[0].trainIdx].pt for m in good]).reshape(-1, 1, 2)

    # 使用 RANSAC 算法计算了图像之间的单应性矩阵。这个矩阵可以用来对图像进行透视变换，使它们更好地对齐。
    H, mask = cv2.findHomography(src_pts, dst_pts, cv2.RANSAC, 5.0)

    # 使用得到的单应性矩阵H将原图像做透视变换
    height, width = img.shape
    warped_img = cv2.warpPerspective(img, H, (width, height))

    # 将匹配结果绘制在图像上
    # cv2.addWeighted(img, 0.5, warped_img, 0.5, 0): 这行代码创建了一个融合图像，通过将原图像 img 与经过透视变换后的图像 warped_img 进行融合。
    # 参数 0.5 表示两个图像的权重相同，最后一个参数 0 表示融合时没有gamma值的加权。融合后的图像展示了原图像和变换后的图像的叠加，以便直观地比较它们之间的对应关系。
    result = cv2.addWeighted(img, 0.5, warped_img, 0.5, 0)

    cv2.imshow("warped image", warped_img)
    cv2.imshow("addWeighted", result)
    cv2.waitKey(0)


    for i in range(len(good[0: 15])):
        pt1 = tuple(map(int, keypoints_img[good[i][0].queryIdx].pt))  # 获取第一个图像的匹配点坐标
        pt2 = tuple(map(int, keypoints_template[good[i][0].trainIdx].pt))  # 获取第二个图像的匹配点坐标
        cv2.line(result, pt1, pt2, (0, 255, 0), 1)  # 绘制匹配点之间的连线

    cv2.imshow("Matching Result", result)
    cv2.waitKey(0)
    cv2.destroyAllWindows()
else:
    print("匹配点数不足，无法计算单应性矩阵。")