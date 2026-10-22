import cv2, threading


class CameraManager:
    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        # 双重检查锁定提高性能
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    instance = super(CameraManager, cls).__new__(cls)
                    instance.__initialize_camera()
                    cls._instance = instance
        return cls._instance

    def __initialize_camera(self):
        """ 初始化摄像头设备 """
        self.__cap_font = cv2.VideoCapture(0)

        if not self.__cap_font.isOpened():
            # 初始化失败时自动清除实例
            CameraManager._instance = None
            raise IOError('Cannot open front camera')

    def __getattr__(self, name):
        """ 属性访问委托 """
        return getattr(self.__class__._instance, name)

    def get_cap_font(self):
        return self.__cap_font
