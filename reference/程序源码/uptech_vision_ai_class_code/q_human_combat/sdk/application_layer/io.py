from .notice.base import NoticeBase
from ..hardware_layer.so_manager import SoManager
from ..utils.os_util import check_root
import ctypes, time


class IO(NoticeBase):

    def __init__(self):
        super().__init__()

        if check_root():
            raise RuntimeError("没有 ROOT 权限，请使用 sudo 命令启动")

        self.__io_so = SoManager().get_api_io()

        # ADC 数据存储
        self.__adc_length = 10
        self.__adc_data_ctype = (ctypes.c_uint16 * self.__adc_length)()
        self.__adc_data = [0] * self.__adc_length

        # IO 数据存储
        self.__io_length = 8
        self.__io_data_ctype = (ctypes.c_uint16 * self.__io_length)()
        self.__io_data = [0] * self.__io_length

        # 打开通讯
        time.sleep(0.2)
        self.open_io_and_adc()
        time.sleep(0.2)
        self.open_servo()
        time.sleep(0.2)

    def clean_up(self):
        print("关闭 IO 和舵机...")

        self.set_servo_speed(1, 0)
        self.set_servo_speed(2, 0)
        time.sleep(0.2)

        self.close_io_and_adc()
        time.sleep(0.2)
        self.close_servo()
        time.sleep(0.2)

    # -------------------- 舵机控制 --------------------

    def open_servo(self):
        """
        打开舵机
        """
        self.__io_so.cds_servo_open()

    def close_servo(self):
        """
        关闭舵机
        """
        self.__io_so.cds_servo_close()

    def set_servo_mode(self, servo_id, mode):
        """
        设置舵机工作模式

        :param servo_id: 舵机 ID
        :param mode: 舵机工作模式
        """
        self.__io_so.cds_servo_SetMode(servo_id, mode)

    def set_servo_angle(self, servo_id, angle, speed):
        """
        设置舵机以指定速度旋转到指定角度

        :param servo_id: 舵机 ID
        :param angle: 旋转角度
        :param speed: 旋转速度
        """
        self.__io_so.cds_servo_SetAngle(servo_id, angle, speed)

    def set_servo_speed(self, servo_id, speed):
        """
        设置舵机以指定速度旋转

        :param servo_id: 舵机 ID
        :param speed: 旋转速度
        """
        self.__io_so.cds_servo_SetSpeed(servo_id, speed)

    def get_servo_angle(self, servo_id):
        """
        获取舵机当前角度

        :param servo_id: 舵机 ID
        :return: 当前角度
        """
        angle = self.__io_so.cds_servo_GetPos(servo_id)
        return angle

    # -------------------- ADC IO 控制 --------------------

    def open_io_and_adc(self):
        """
        打开 IO 和 ADC
        """
        self.__io_so.adc_io_open()

    def close_io_and_adc(self):
        """
        关闭 IO 和 ADC
        """
        self.__io_so.adc_io_open()

    def get_all_adc_data(self):
        """
        获取所有引脚通道的模拟量数据

        :return: 所有引脚通道的 ADC 数据
        """
        self.__io_so.ADC_GetAll(self.__adc_data_ctype)
        for i in range(self.__adc_length):
            self.__adc_data[i] = self.__adc_data_ctype[i]
        return self.__adc_data

    def get_adc_data_from_channel(self, channel):
        """
        获取指定引脚通道的模拟量数据

        :param channel: 引脚通道号
        :return: 指定引脚通道的模拟量数据
        """
        self.__io_so.ADC_GetAll(self.__adc_data_ctype)
        adc_data = self.__adc_data_ctype[channel]
        return adc_data

    def set_pin_output_level(self, index, level):
        """
        设置指定引脚的输出电平

        :param index: 引脚通道号
        :param level: 引脚输出电平
        """
        self.__io_so.adc_io_SetLevelAll(level)

    def set_pin_mode(self, index, mode):
        """
        设置指定引脚的工作模式

        :param index: 引脚通道号
        :param mode: 引脚工作模式（输入、输出）
        """
        self.__io_so.adc_io_ModeSet(index, mode)

    def set_all_pin_mode(self, mode):
        """
        设置全部引脚的工作模式

        :param mode: 引脚工作模式（输入、输出）
        """
        self.__io_so.adc_io_ModeSetAll(mode)

    def get_all_pin_input_level(self):
        """
        获取所有引脚的输入电平

        :return: 所有引脚的输入电平
        """
        self.__io_so.adc_io_InputGetAll(self.__io_data_ctype)
        for i in range(self.__io_length):
            self.__io_data[i] = self.__io_data_ctype
        return self.__io_data

    def get_pin_input_level_from_channel(self, index):
        """
        获取指定引脚的输入电平

        :param index: 引脚索引
        :return: 引脚的输入电平
        """
        level = self.__io_so.adc_io_InputGet(index)
        return level
