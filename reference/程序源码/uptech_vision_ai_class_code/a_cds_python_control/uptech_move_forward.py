import sys
sys.path.append("..")

from uptech import UpTech
import time


class FourWhellMove:
    def __init__(self):
        self.up = UpTech()
        time.sleep(0.01)
        self.up.CDS_Open()
        time.sleep(0.2)
        self.up.CDS_SetMode(1,1) #0舵机，1电机
        self.up.CDS_SetMode(2,1)
        self.up.CDS_SetMode(3,1)
        self.up.CDS_SetMode(4,1)
        time.sleep(2.0)
        count = 0
        while(True):
            count += 1
            if(count <= 10):
                self.move_forward(512)
            else:
                self.stop()
                time.sleep(1.0)
                self.close()
                break;
            time.sleep(1.0)
    
    def move_forward(self, speed):
        self.up.CDS_SetSpeed(1,speed)
        self.up.CDS_SetSpeed(3,speed)
        self.up.CDS_SetSpeed(2,-speed)
        self.up.CDS_SetSpeed(4,-speed) 

    def move_backward(self, speed):
        self.up.CDS_SetSpeed(1,-speed)
        self.up.CDS_SetSpeed(3,-speed)
        self.up.CDS_SetSpeed(2,speed)
        self.up.CDS_SetSpeed(4,speed)    

    def move_left(self, speed):
        self.up.CDS_SetSpeed(1,-speed)
        self.up.CDS_SetSpeed(3,speed)
        self.up.CDS_SetSpeed(2,-speed)
        self.up.CDS_SetSpeed(4,speed)  

    def move_right(self, speed):
        self.up.CDS_SetSpeed(1,speed)
        self.up.CDS_SetSpeed(3,-speed)
        self.up.CDS_SetSpeed(2,speed)
        self.up.CDS_SetSpeed(4,-speed)  

    def turn_left(self, speed):
        self.up.CDS_SetSpeed(1,-speed)
        self.up.CDS_SetSpeed(3,-speed)
        self.up.CDS_SetSpeed(2,-speed)
        self.up.CDS_SetSpeed(4,-speed)  

    def turn_right(self, speed):
        self.up.CDS_SetSpeed(1,speed)
        self.up.CDS_SetSpeed(3,speed)
        self.up.CDS_SetSpeed(2,speed)
        self.up.CDS_SetSpeed(4,speed)  

    def stop(self):
        self.up.CDS_SetSpeed(1,0)
        self.up.CDS_SetSpeed(2,0)
        self.up.CDS_SetSpeed(3,0)
        self.up.CDS_SetSpeed(4,0)  
    
    def close(self):
        self.up.CDS_Close()     


if __name__ == "__main__":
    move = FourWhellMove()
    

        

