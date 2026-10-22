from .notice.base import NoticeBase
from ..hardware_layer.camera_manager import CameraManager
import cv2


class Camera(NoticeBase):

    def __init__(self):
        super().__init__()

        # 硬件管理单例
        self.__cameras = CameraManager()  # 相机

    def clean_up(self):
        print("释放摄像头和窗口资源...")
        if self.__cameras.get_cap_font().isOpened():
            self.__cameras.get_cap_font().release()
        cv2.destroyAllWindows()

    def get_camera(self):
        return self.__cameras.get_cap_font()