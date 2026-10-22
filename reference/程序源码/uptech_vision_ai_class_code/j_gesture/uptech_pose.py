from mediapipe import solutions
from mediapipe.framework.formats import landmark_pb2
from mediapipe.tasks import python
from mediapipe.tasks.python import vision
import mediapipe as mp
import numpy as np
import cv2
import time
import sys


MODEL_PATH = sys.path[0] + "/pose_model/pose_landmarker_lite.task"
COUNTER, FPS = 0, 0
START_TIME = time.time()
DETECTION_RESULT = None



def main():
    # 初始化摄像头
    cap = cv2.VideoCapture(0)

    row_size = 50  # pixels
    left_margin = 24  # pixels
    text_color = (0, 0, 0)  # black
    font_size = 1
    font_thickness = 1
    fps_avg_frame_count = 10
    overlay_alpha = 0.5
    mask_color = (100, 100, 0)  # cyan

    def save_result(
        result: vision.PoseLandmarkerResult,
        output_image: mp.Image,
        timestampe_ms: int,
    ):
        global FPS, COUNTER, START_TIME, DETECTION_RESULT
        # 计算FPS
        if COUNTER % fps_avg_frame_count == 0:
            FPS = fps_avg_frame_count / (time.time() - START_TIME)
            START_TIME = time.time()
        DETECTION_RESULT = result
        COUNTER += 1


    def draw_landmarks_on_image(rgb_image, detection_result):
        pose_landmarks_list = detection_result.pose_landmarks
        annotated_image = np.copy(rgb_image)
    
        # 循环画出每一个检测结果
        for idx in range(len(pose_landmarks_list)):
            pose_landmarks = pose_landmarks_list[idx]
            # 画出Pose关键点
            pose_landmarks_proto = landmark_pb2.NormalizedLandmarkList()
            pose_landmarks_proto.landmark.extend([
                landmark_pb2.NormalizedLandmark(x=landmark.x, y=landmark.y, z=landmark.z) for landmark in pose_landmarks
            ])
            solutions.drawing_utils.draw_landmarks(
                    annotated_image,
                    pose_landmarks_proto,
                    solutions.pose.POSE_CONNECTIONS,
                    solutions.drawing_styles.get_default_pose_landmarks_style())
            return annotated_image
    
    # 初始化关节点检测实例
    def init_model_options():
        base_options = python.BaseOptions(model_asset_path=MODEL_PATH)
        options = vision.PoseLandmarkerOptions(
            base_options=base_options,
            num_poses=2,
            running_mode=vision.RunningMode.LIVE_STREAM,
            result_callback=save_result,
            )
    
    
        detector = vision.PoseLandmarker.create_from_options(options)
        return detector


    detector = init_model_options()


    while cap.isOpened():
        success, image = cap.read()
        if not success:
            print("没有读取到视频帧")
            if cv2.waitKey(1) & 0xFF == ord("q"):
                break
            continue

        # 将图像从BGR转换为RGB，因为MediaPipe模型期望的是RGB格式的输入。
        rgb_image = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
        mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb_image)


        detector.detect_async(mp_image, time.time_ns() // 1_000_000)

        # 计算并显示FPS值。
        fps_text = 'FPS = {:.1f}'.format(FPS)
        text_location = (left_margin, row_size)
        current_frame = image
        cv2.putText(current_frame, fps_text, text_location,
                    cv2.FONT_HERSHEY_DUPLEX,
                    font_size, text_color, font_thickness, cv2.LINE_AA)

        if DETECTION_RESULT:
            for pose_landmarks in DETECTION_RESULT.pose_landmarks:
                current_frame = draw_landmarks_on_image(current_frame, DETECTION_RESULT)

        cv2.imshow("Pose Landmarker", current_frame)
        if cv2.waitKey(1) & 0xFF == ord("q"):
            break

    cap.release()
    cv2.destroyAllWindows()  


if __name__ == "__main__":
    main()
