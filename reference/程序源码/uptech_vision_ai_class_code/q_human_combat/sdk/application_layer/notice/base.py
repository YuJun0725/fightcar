from abc import ABC, abstractmethod
from .bus import SignalBus
import atexit


class NoticeBase(ABC):
    def __init__(self):
        self.cleaned = False
        SignalBus().register(self)
        atexit.register(self.__exit)

    def __exit(self):
        if not self.cleaned:
            self.clean_up()
            self.cleaned = True

    def handle_interruption(self):
        self.__exit()

    @abstractmethod
    def clean_up(self):
        pass
