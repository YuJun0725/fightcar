from ctypes import cdll
import ctypes, time, threading


class SoManager:
    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        # 双重检查锁定提高性能
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    instance = super(SoManager, cls).__new__(cls)
                    instance.__load_so_file()
                    cls._instance = instance
        return cls._instance

    def __load_so_file(self):
        """
        加载 so 文件
        """
        self.__api_io = cdll.LoadLibrary("libuptech.so")

    def get_api_io(self):
        return self.__api_io