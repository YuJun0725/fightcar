import sys
sys.path.append("..")

from uptech import UpTech
import time


class FourWhellMove:
    def __init__(self):
        
        self.up = UpTech()
        time.sleep(0.01)
        
        self.up.ADC_IO_Open()
        time.sleep(0.01)
        
        while(True):
            adc_0 = self.up.ADC_Get_Channel(0)
            adc_1 = self.up.ADC_Get_Channel(1)
            adc_2 = self.up.ADC_Get_Channel(2)
            adc_3 = self.up.ADC_Get_Channel(3)
            adc_4 = self.up.ADC_Get_Channel(4)
            adc_5 = self.up.ADC_Get_Channel(5)
            adc_6 = self.up.ADC_Get_Channel(6)
            adc_7 = self.up.ADC_Get_Channel(7)
            adc_8 = self.up.ADC_Get_Channel(8)
            
            print("ADC Channel 0: " +  str(adc_0))
            print("ADC Channel 1: " +  str(adc_1))
            print("ADC Channel 2: " +  str(adc_2))
            print("ADC Channel 3: " +  str(adc_3))
            print("ADC Channel 4: " +  str(adc_4))
            print("ADC Channel 5: " +  str(adc_5))
            print("ADC Channel 6: " +  str(adc_6))
            print("ADC Channel 7: " +  str(adc_7))
            print("ADC Channel 8: " +  str(adc_8))
            
            time.sleep(1)


if __name__ == "__main__":
    move = FourWhellMove()
    


        