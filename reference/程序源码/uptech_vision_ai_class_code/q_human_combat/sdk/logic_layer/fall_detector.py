class FallDetector:
    def __init__(self):
        self.min_limit_stand = 1100
        self.max_limit_stand = 2850
        self.limit_fall_forward = 3400
        self.limit_fall_backward = 700

    def detect_angle(self, adc_data):
        # 没有倒
        if self.min_limit_stand < adc_data < self.max_limit_stand:
            return 1
        # 前倾
        elif adc_data > self.limit_fall_forward:
            return 2
        # 后倾
        elif adc_data < self.limit_fall_backward:
            return 3
        # 边缘状态
        else:
            return 0
