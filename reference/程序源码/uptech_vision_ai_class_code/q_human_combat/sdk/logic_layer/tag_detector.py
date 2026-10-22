from ..utils.draw_util import draw_rect, draw_cross, draw_circle
import cv2, apriltag, numpy as np


class ApriltagDetector:
    def __init__(self, show=True, aspect_ratio=0.8):
        # 检测器设置
        options = apriltag.DetectorOptions(families='tag36h11')
        self.tag_detector = apriltag.Detector(options)

        self.window_name = "apriltag detector frame"

        self.show = show
        self.aspect_ratio = aspect_ratio  # 高宽比

    def process_frame(self, frame, ignore_id):
        """
        计算 x 轴上 Apriltag 距离中心距离
        :return: 是否找到 Apriltag, Apriltag 中心相对于图像中心的像素距离
        """

        # 定义处理结果
        find_apriltag = False  # 视野中是否有 Apriltag
        offset_x = 0  # Apriltag 中心相对于图像中心的像素距离（大于0，Apriltag 在屏幕右侧；小于0，Apriltag 在屏幕左侧）
        tag_id = -1  # Apriltag 的 ID

        # 预处理
        frame = cv2.resize(frame, (640, 480))

        # 转灰度
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

        # 检测视野中的 Apriltag
        tags = self.tag_detector.detect(gray)

        # 过滤掉需要忽略的靶子
        self.__filter_ignore_id(tags, ignore_id)

        # 过滤出立起来的靶子
        risen_tags = self.__filter_risen_tags(tags)

        # 寻找最近的 Apriltag
        closest_tag = self.__find_closest_tag(risen_tags)

        if closest_tag is not None:
            screen_width = frame.shape[1] / 2
            tag_id, offset_x = self.__get_tag_info(closest_tag, screen_width)
            find_apriltag = True

            if self.show:
                # 绘制结果
                self.__draw_result(frame, closest_tag)

        if self.show:
            # 显示结果
            self.__display(frame)

        return find_apriltag, tag_id, offset_x

    def __filter_ignore_id(self, tags, ignore_id):
        if tags is None or len(tags) <= 0:
            return None

        if ignore_id is None:
            return tags

        filter_tags = []
        for tag in tags:
            if tag.tag_id != ignore_id:
                filter_tags.append(tag)
        return filter_tags

    def __filter_risen_tags(self, tags):
        if tags is None or len(tags) <= 0:
            return None

        risen_tags = []
        for tag in tags:
            width, height = self.__get_width_height(tag)
            if height / width >= self.aspect_ratio:
                risen_tags.append(tag)

        return risen_tags

    def __find_closest_tag(self, tags):
        if tags is None or len(tags) <= 0:
            return None

        # 使用列表推导式获取所有 tag 的 corners
        corners_list = [tag.corners for tag in tags]

        # 将 corners_list 转换为 numpy 数组
        corners_array = np.array(corners_list)

        # 计算每个 tag 的高度
        heights = corners_array[:, 1, 1] - corners_array[:, 3, 1]

        # 找到高度最大的 tag 的索引
        max_index = np.argmax(heights)

        return tags[max_index]

    def __get_tag_info(self, tag, screen_width):
        # 计算中心点
        [center_x, center_y] = tag.center

        # 计算 tag 中心相对于图像中心的像素距离
        offset_x = center_x - screen_width

        return tag.tag_id, offset_x

    def __get_width_height(self, tag):
        # 获取 Apriltag 四个顶点
        top_left, top_right, bottom_right, bottom_left = tag.corners

        # 计算宽度和高度
        width = int(bottom_right[0] - top_left[0])
        height = int(bottom_right[1] - top_left[1])

        return width, height

    def __draw_result(self, frame, tag):
        # 获取 Apriltag 四个顶点
        top_left, top_right, bottom_right, bottom_left = tag.corners

        # 获取 Apriltag 中心点
        [center_x, center_y] = tag.center

        # 用矩形框住 apriltag
        x = int(top_left[0])
        y = int(top_left[1])
        width, height = self.__get_width_height(tag)
        draw_rect(frame, x, y, width, height)

        # 绘制 apriltag 中心点
        draw_cross(frame, int(center_x), int(center_y), 20)

    def __display(self, frame):
        x = frame.shape[1] // 2
        y = frame.shape[0] // 2
        draw_circle(frame, x, y, 5)

        cv2.imshow(self.window_name, frame)
        cv2.waitKey(1)