#!/usr/bin/env python3
import ctypes
from ctypes import cdll
import time
__version__="1.0"

so_up = cdll.LoadLibrary("libuptech.so")

class UpTech:
    
    CDS_MODE_SERVO = 0
    CDS_MODE_MOTOR = 1
    
    __adc_data = ctypes.c_uint16*10
    __ADC_DATA=__adc_data()
    ADC_DATA = [0]*10
    
    __io_data = ctypes.c_uint16*8
    __IO_DATA=__io_data()
    IO_DATA = [0]*8

    def __init__(self):
        self.cds_mode = self.CDS_MODE_SERVO

    def stop(self):
        pass

    #打开舵机通讯模块
    def CDS_Open(self):
        so_up.cds_servo_open()
        time.sleep(0.2)

    #关闭舵机通讯模块
    def CDS_Close(self):
        time.sleep(0.2)
        so_up.cds_servo_close()

    #设置舵机工作模式
    def CDS_SetMode(self,id,mode):
        so_up.cds_servo_SetMode(id,mode)

    #设置id编号的舵机的运动角度和运动速度，以speed的速度运动到angle角度
    def CDS_SetAngle(self,id,angle,speed):
        so_up.cds_servo_SetAngle(id,angle,speed)

    #设置id编号的舵机的运动速度
    def CDS_SetSpeed(self,id,speed):
        so_up.cds_servo_SetSpeed(id,speed)

    #获取当前舵机的角度
    def CDS_GetCurPos(self,id):
        return so_up.cds_servo_GetPos(id)

    def ADC_IO_Open(self):
        return so_up.adc_io_open()

    def ADC_IO_Close(self):
        so_up.adc_io_close()

    #获取全部AD口的模拟量输入
    def ADC_Get_All_Channel(self):
        so_up.ADC_GetAll(self.__ADC_DATA)
        for i in range(10):
            self.ADC_DATA[i] = self.__ADC_DATA[i]
        return self.ADC_DATA
    
    #获取指定channel的模拟量输入
    def ADC_Get_Channel(self, channel):
        so_up.ADC_GetAll(self.__ADC_DATA)
        adc_data = self.__ADC_DATA[channel]
        return adc_data
    
    ##设置index的IO的输出，level为0,1
    def ADC_IO_SetIOLevel(self,index,level):
        so_up.adc_io_Set(index,level)

    #设置全部index的IO的输出，level为0,1
    def ADC_IO_SetAllIOLevel(self,level):
        so_up.adc_io_SetLevelAll(level)        

    #设置指定index的IO的模式，mode为0，代表输入模式，mode为1代表输出模式
    def ADC_IO_SetIOMode(self,index,mode):
        so_up.adc_io_ModeSet(index,mode) 
        
    #设置全部index的IO的模式，mode为0，代表输入模式，mode为1代表输出模式
    def ADC_IO_SetAllIOMode(self,mode):
        so_up.adc_io_ModeSetAll(mode)   

    def ADC_IO_GetAllInputLevel(self):
        so_up.adc_io_InputGetAll(self.__IO_DATA)
        for i in range(8):
            self.IO_DATA[i] = self.__IO_DATA[i]
        return self.IO_DATA
    
    def ADC_IO_GetInputLevel(self, index):
        level = so_up.adc_io_InputGet(index)
        return level
    


