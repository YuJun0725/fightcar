import cv2
import mediapipe as mp
import math
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

draw = mp.solutions.drawing_utils
hands = mp.solutions.hands.Hands(
    static_image_mode=False,
    max_num_hands=2,
    min_detection_confidence=0.75,
    min_tracking_confidence=0.75)

def findHind(img, hands, draw):
    imgRGB = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)  # 转换为RGB
	
    handlmsstyle = draw.DrawingSpec(color=(0, 0, 255), thickness=5)
    handconstyle = draw.DrawingSpec(color=(0, 255, 0), thickness=5)

    results = hands.process(imgRGB)
    if results.multi_hand_landmarks:
        for handLms in results.multi_hand_landmarks:
            draw.draw_landmarks(img, handLms, mp.solutions.hands.HAND_CONNECTIONS, handlmsstyle, handconstyle)
    return results.multi_hand_landmarks


def detectNumber(hand_landmarks, img):
    """
    :param hand_landmarks: 手势特征
    :param img: 实时图像
    :return: 返回识别到的数字，如果没有则返回-1
    """

    h, w, c = img.shape

    myhand = hand_landmarks[0]
    hand_landmark = myhand.landmark
    thumb_tip_id = 4  # 大拇指指尖
    index_finger_tip_id = 8  # 食指指尖
    middle_finger_tip_id = 12  # 中指指尖
    ring_finger_tip_id = 16  # 无名指指尖
    pinky_finger_tip_id = 20  # 小指指尖
    pinky_finger_mcp_id = 17  # 小指指根（用于判断4和5）
    wrist_id = 0  # 手腕（用于识别数字6）

    # 提取y坐标
    thumb_tip_y = hand_landmark[thumb_tip_id].y * h
    index_tip_y = hand_landmark[index_finger_tip_id].y * h
    middle_tip_y = hand_landmark[middle_finger_tip_id].y * h
    ring_tip_y = hand_landmark[ring_finger_tip_id].y * h
    pinky_tip_y = hand_landmark[pinky_finger_tip_id].y * h
    pinky_mcp_y = hand_landmark[pinky_finger_mcp_id].y * h
    wrist_y = hand_landmark[wrist_id].y * h

    # 提取x坐标
    thumb_tip_x = hand_landmark[thumb_tip_id].x * w
    index_tip_x = hand_landmark[index_finger_tip_id].x * w
    middle_tip_x = hand_landmark[middle_finger_tip_id].x * w
    ring_tip_x = hand_landmark[ring_finger_tip_id].x * w
    pinky_tip_x = hand_landmark[pinky_finger_tip_id].x * w
    pinky_mcp_x = hand_landmark[pinky_finger_mcp_id].x * w
    wrist_x = hand_landmark[wrist_id].x * w

    dist_thumb2wrist = math.sqrt((thumb_tip_x - wrist_x)**2 + (thumb_tip_y - wrist_y)**2)
    dist_index2wrist = math.sqrt((index_tip_x - wrist_x) ** 2 + (index_tip_y - wrist_y) ** 2)
    dist_middle2wrist = math.sqrt((middle_tip_x - wrist_x) ** 2 + (middle_tip_y - wrist_y) ** 2)
    dist_ring2wrist = math.sqrt((ring_tip_x - wrist_x) ** 2 + (ring_tip_y - wrist_y) ** 2)
    dist_pinky2wrist = math.sqrt((pinky_tip_x - wrist_x) ** 2 + (pinky_tip_y - wrist_y) ** 2)
    dist_pinky_mcp2wrist = math.sqrt((thumb_tip_x - pinky_mcp_x)**2 + (thumb_tip_y - pinky_mcp_y)**2)

    # 相当于取dist_thumb2wrist_ratio == 1
    dist_index2wrist_ratio = dist_index2wrist / dist_thumb2wrist
    dist_middle2wrist_ratio = dist_middle2wrist / dist_thumb2wrist
    dist_ring2wrist_ratio = dist_ring2wrist / dist_thumb2wrist
    dist_pinky2wrist_ratio = dist_pinky2wrist / dist_thumb2wrist
    dist_pinky_mcp2wrist_ratio = dist_pinky_mcp2wrist / dist_thumb2wrist

    # print(dist_index2wrist_ratio, dist_middle2wrist_ratio, dist_ring2wrist_ratio, dist_pinky2wrist_ratio, dist_pinky_mcp2wrist_ratio)

    if dist_index2wrist_ratio < 1.9 and dist_middle2wrist_ratio < 1.8 and dist_ring2wrist_ratio < 1.6 and dist_pinky2wrist_ratio < 1.4 and dist_pinky_mcp2wrist_ratio < 0.8:
        return 0
    elif 2.0 < dist_index2wrist_ratio and dist_middle2wrist_ratio < 1.8 and dist_ring2wrist_ratio < 1.6 and dist_pinky2wrist_ratio < 1.4 and dist_pinky_mcp2wrist_ratio < 0.8:
        return 1
    elif 2.0 < dist_index2wrist_ratio and 1.9 < dist_middle2wrist_ratio and dist_ring2wrist_ratio < 1.6 and dist_pinky2wrist_ratio < 1.4 and dist_pinky_mcp2wrist_ratio < 0.8:
        return 2
    elif 2.0 < dist_index2wrist_ratio and 1.9 < dist_middle2wrist_ratio and 1.75 < dist_ring2wrist_ratio and dist_pinky2wrist_ratio < 1.4 and dist_pinky_mcp2wrist_ratio < 0.8:
        return 3
    elif 2.0 < dist_index2wrist_ratio and 1.9 < dist_middle2wrist_ratio and 1.75 < dist_ring2wrist_ratio and 1.5 < dist_pinky2wrist_ratio and dist_pinky_mcp2wrist_ratio < 0.8:
        return 4
    elif dist_index2wrist_ratio > 0.5 and dist_middle2wrist_ratio > 0.5 and dist_ring2wrist_ratio > 0.5 and 0.9 < dist_pinky_mcp2wrist_ratio < 1.2:
        return 5
    elif dist_index2wrist_ratio < 0.5 and dist_middle2wrist_ratio < 0.5 and dist_ring2wrist_ratio < 0.5:
        return 6
    else:
        return -1



cap = cv2.VideoCapture(0)

movement = FourWhellMove()

cv2.namedWindow('MediaPipe Hands', cv2.WINDOW_NORMAL) 

while True:
    
    ret, frame = cap.read()
    frame = cv2.resize(frame, (640, 480))
    
    hands_landmarks = findHind(frame, hands, draw)
    
    if hands_landmarks:
        # 调用detectNumber函数
        resultNumber = detectNumber(hands_landmarks, frame)
        if (resultNumber >= 0):
            cv2.putText(frame, str(resultNumber), (150, 150), 19, 5, (255, 0, 255), 5, cv2.LINE_AA)
            if(resultNumber == 5):
                movement.move_forward(256)
            elif (resultNumber == 0):
                movement.move_backward(256)
        else:
            cv2.putText(frame, "NO NUMBER", (150, 150), 20, 1, (0, 0, 255))
            movement.stop()
    cv2.imshow('MediaPipe Hands', frame)
    
    if cv2.waitKey(1) & 0xFF == 27:
        break
    
cap.release()
