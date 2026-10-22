import sys
sys.path.append("..")

from uptech import UpTech
import time


class IO_IN:
    def __init__(self):
        
        self.up = UpTech()
        time.sleep(0.01)

        self.up.ADC_IO_Open()
        time.sleep(0.01)

        while(True):
            io_channel_0 = self.up.ADC_IO_GetInputLevel(0)
            io_channel_1 = self.up.ADC_IO_GetInputLevel(1)
            io_channel_2 = self.up.ADC_IO_GetInputLevel(2)
            io_channel_3 = self.up.ADC_IO_GetInputLevel(3)
            io_channel_4 = self.up.ADC_IO_GetInputLevel(4)
            io_channel_5 = self.up.ADC_IO_GetInputLevel(5)
            io_channel_6 = self.up.ADC_IO_GetInputLevel(6)
            io_channel_7 = self.up.ADC_IO_GetInputLevel(7)
            
            time.sleep(0.1)
            
            print("IO_Channel 0: " + str(io_channel_0))
            print("IO_Channel 1: " + str(io_channel_1))
            print("IO_Channel 2: " + str(io_channel_2))
            print("IO_Channel 3: " + str(io_channel_3))
            print("IO_Channel 4: " + str(io_channel_4))
            print("IO_Channel 5: " + str(io_channel_5))
            print("IO_Channel 6: " + str(io_channel_6))
            print("IO_Channel 7: " + str(io_channel_7))


if __name__ == "__main__":
    io_in_test = IO_IN()
    


        