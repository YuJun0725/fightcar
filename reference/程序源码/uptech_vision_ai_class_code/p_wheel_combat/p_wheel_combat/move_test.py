
from motion_controller import MotionController

import time

motion_controller = MotionController()

if __name__ == "__main__":
    
    # 遮挡一下adc3，使得其可以感应上台
    # while True:
    #     ad3 = edge_detector.get_left_distance()
    #     if ad3 > 1000:
    #         break
    #     time.sleep(0.01)
        
    #前进上台
    motion_controller.move_cmd(300, 300)
    time.sleep(3)
        
    #做出默认动作
    motion_controller.default_platform()
        
    #停止运动
    motion_controller.move_cmd(0, 0)
    time.sleep(2)