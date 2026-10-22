import sys
sys.path.append("..")

from uptech import UpTech
import time


class IO_OUT:
    def __init__(self):
        
        self.up = UpTech()
        time.sleep(0.01)

        self.up.ADC_IO_Open()
        time.sleep(0.01)

        self.up.ADC_IO_SetAllIOMode(1)

        while(True):
            self.up.ADC_IO_SetAllIOLevel(1)
            time.sleep(1.0)
            
if __name__ == "__main__":
    io_in_test = IO_OUT()