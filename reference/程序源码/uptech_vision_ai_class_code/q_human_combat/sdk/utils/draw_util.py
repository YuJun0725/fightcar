import cv2


def draw_cross(frame, x, y, size):
    """
    绘制十字
    :param frame: 待处理图像
    :param x: 十字 x 坐标
    :param y: 十字 y 坐标
    :param size: 十字长度
    """

    thickness = 2  # 线条粗度
    color = (0, 0, 255)  # 红色，BGR格式

    # 计算十字的四个端点坐标
    center_x, center_y = int(x), int(y)
    p1 = (center_x - size, center_y)
    p2 = (center_x + size, center_y)
    p3 = (center_x, center_y - size)
    p4 = (center_x, center_y + size)

    # 在图像上绘制十字
    cv2.line(frame, p1, p2, color, thickness)
    cv2.line(frame, p3, p4, color, thickness)


def draw_rect(frame, x, y, width, height):
    """
    绘制矩形
    :param frame: 待处理图像
    :param x: 矩形左上角 x 坐标
    :param y: 矩形左上角 y 坐标
    :param width: 矩形宽度
    :param height: 矩形高度
    """
    cv2.rectangle(frame, (x, y), (x + width, y + height), (0, 0, 255), 2)


def draw_circle(frame, x, y, radius):
    """
    绘制圆形
    :param frame: 待处理图像
    :param x: 圆中心 x 坐标
    :param y: 圆中心 y 坐标
    :param radius: 圆形半径
    """
    cv2.circle(frame, (x, y), radius, (255, 0, 0), -1)
