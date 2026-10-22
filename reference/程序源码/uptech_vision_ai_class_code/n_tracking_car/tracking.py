import sys
import cv2
import time

sys.path.append("..")
from uptech import UpTech


# 参数
SPEED = 240
OFFSET_LIMIT = 40


class Car:
    def __init__(self):
        self.up = UpTech()
        time.sleep(0.01)
        self.up.CDS_Open()
        time.sleep(0.2)
        self.up.CDS_SetMode(1, 1)  # 0舵机，1电机
        self.up.CDS_SetMode(2, 1)
        self.up.CDS_SetMode(3, 1)
        self.up.CDS_SetMode(4, 1)
        time.sleep(2.0)

    def move_forward(self, speed):
        self.up.CDS_SetSpeed(1, speed)
        self.up.CDS_SetSpeed(3, speed)
        self.up.CDS_SetSpeed(2, -speed)
        self.up.CDS_SetSpeed(4, -speed)

    def move_backward(self, speed):
        self.up.CDS_SetSpeed(1, -speed)
        self.up.CDS_SetSpeed(3, -speed)
        self.up.CDS_SetSpeed(2, speed)
        self.up.CDS_SetSpeed(4, speed)

    def move_left(self, speed):
        self.up.CDS_SetSpeed(1, -speed)
        self.up.CDS_SetSpeed(3, speed)
        self.up.CDS_SetSpeed(2, -speed)
        self.up.CDS_SetSpeed(4, speed)

    def move_right(self, speed):
        self.up.CDS_SetSpeed(1, speed)
        self.up.CDS_SetSpeed(3, -speed)
        self.up.CDS_SetSpeed(2, speed)
        self.up.CDS_SetSpeed(4, -speed)

    def turn_left(self, speed):
        self.up.CDS_SetSpeed(1, -speed)
        self.up.CDS_SetSpeed(3, -speed)
        self.up.CDS_SetSpeed(2, -speed)
        self.up.CDS_SetSpeed(4, -speed)

    def turn_right(self, speed):
        self.up.CDS_SetSpeed(1, speed)
        self.up.CDS_SetSpeed(3, speed)
        self.up.CDS_SetSpeed(2, speed)
        self.up.CDS_SetSpeed(4, speed)

    def stop(self):
        self.up.CDS_SetSpeed(1, 0)
        self.up.CDS_SetSpeed(2, 0)
        self.up.CDS_SetSpeed(3, 0)
        self.up.CDS_SetSpeed(4, 0)

    def close(self):
        self.up.CDS_Close()


def create_kcf_tracker():
    """
    创建一个 KCF 跟踪器实例
    返回:
        tracker (cv2.legacy.TrackerKCF): 一个 KCF 跟踪器实例
    """
    return cv2.legacy.TrackerKCF_create()


def initialize_tracker(tracker, frame, bbox):
    """
    使用第一帧和边界框初始化 KCF 跟踪器
    参数:
        tracker (cv2.legacy.TrackerKCF): KCF 跟踪器实例
        frame (numpy.ndarray): 包含目标的初始帧
        bbox (tuple): 目标的边界框 (x, y, width, height)
    返回:
        bool: 初始化成功返回 True，否则返回 False
    """
    return tracker.init(frame, bbox)


def update_tracker(tracker, frame):
    """
    更新 KCF 跟踪器，传入当前帧
    参数:
        tracker (cv2.legacy.TrackerKCF): KCF 跟踪器实例
        frame (numpy.ndarray): 当前帧，用于更新跟踪
    返回:
        success (bool): 跟踪成功返回 True，否则返回 False
        bbox (tuple): 更新后的边界框 (x, y, width, height)
    """
    success, bbox = tracker.update(frame)
    return success, bbox


def follow(car, screen_center_x, p1, p2):
    """
    跟踪
    参数:
        car (Car): Car 底盘控制实例
        screen_center_x (float): 屏幕中心 x 坐标
        p1 (tuple(int, int)): 跟踪区域左上角顶点坐标
        p2 (tuple(int, int)): 跟踪区域左上角顶点坐标宽高
    """
    target_left_x = p1[0]
    target_width = p2[0]
    target_center_x = target_left_x + target_width / 2

    offset = screen_center_x - target_center_x
    if offset > OFFSET_LIMIT:
        car.turn_left(SPEED)
    elif offset < -OFFSET_LIMIT:
        car.turn_right(SPEED)
    else:
        car.stop()


def main():
    # 初始化底盘控制
    car = Car()

    # 打开视频或摄像头
    cap = cv2.VideoCapture(0)  # 使用摄像头，也可以替换为视频文件路径

    try:

        # 读取初始帧
        ret, frame = cap.read()
        if not ret:
            print("无法读取视频")
            cap.release()
            exit()

        # 选择初始跟踪对象的区域
        cv2.namedWindow("Select ROI")
        bbox = cv2.selectROI("Select ROI", frame, fromCenter=False, showCrosshair=False)
        cv2.destroyWindow("Select ROI")

        # 创建并初始化 KCF 跟踪器
        tracker = create_kcf_tracker()
        initialize_tracker(tracker, frame, bbox)

        # 开始跟踪
        while True:
            ret, frame = cap.read()
            if not ret:
                break

            # 更新跟踪状态
            success, bbox = update_tracker(tracker, frame)

            if success:
                # 如果跟踪成功，绘制跟踪框
                p1 = (int(bbox[0]), int(bbox[1]))
                p2 = (int(bbox[0] + bbox[2]), int(bbox[1] + bbox[3]))
                cv2.rectangle(frame, p1, p2, (255, 0, 0), 2, 1)

                # 计算屏幕中心并跟踪
                screen_center_x = frame.shape[1] / 2
                follow(car, screen_center_x, p1, p2)
            else:
                # 跟踪失败
                cv2.putText(frame, "Failed", (50, 80),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.75, (0, 0, 255), 2)

                # 停车
                car.stop()

            # 显示跟踪结果
            cv2.imshow("KCF", frame)

            # 按 ESC 键退出
            if cv2.waitKey(1) & 0xFF == 27:
                break

    except (KeyboardInterrupt, Exception) as e:
        print(e)

    finally:
        # 释放硬件资源
        cap.release()
        cv2.destroyAllWindows()
        car.stop()
        time.sleep(1.0)
        car.close()
        time.sleep(1.0)


# 程序入口
if __name__ == '__main__':
    main()
