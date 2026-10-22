import signal, sys, threading


class SignalBus:
    _instance = None
    _lock = threading.Lock()
    _notice_lock = threading.Lock()  # 单独的通知列表锁

    def __new__(cls, *args, **kwargs):
        # 第一次无锁检查提升性能
        if cls._instance is None:
            with cls._lock:
                # 第二次加锁检查确保单例
                if cls._instance is None:
                    instance = super(SignalBus, cls).__new__(cls)
                    instance.__notices = []
                    instance.__setup_signal_handlers()
                    cls._instance = instance
        return cls._instance

    def __setup_signal_handlers(self):
        """ 原子化信号处理器注册 """
        signal.signal(signal.SIGINT, self.__capture_signal)
        signal.signal(signal.SIGTSTP, self.__capture_signal)
        # 设置忽略信号时的恢复策略
        signal.signal(signal.SIGTERM, signal.SIG_DFL)

    def __capture_signal(self, sig, frame):
        """ 线程安全的信号处理 """
        with self._notice_lock:  # 加锁遍历通知列表
            for notice in self.__notices.copy():  # 使用副本避免迭代时修改
                try:
                    notice.handle_interruption()
                except Exception as e:
                    sys.stderr.write(f"Signal处理异常: {str(e)}\n")
        sys.exit(0)

    def register(self, notice):
        """ 线程安全的注册方法 """
        with self._notice_lock:
            if notice not in self.__notices:
                self.__notices.append(notice)

    def unregister(self, notice):
        """ 线程安全的注销方法 """
        with self._notice_lock:
            if notice in self.__notices:
                self.__notices.remove(notice)

    def clear_all(self):
        """ 清空通知列表 """
        with self._notice_lock:
            self.__notices.clear()
