import cv2  
import apriltag  
  
def detect_apriltags(image_path):  
    # 读取图像  
    image_gray = cv2.imread(image_path, cv2.IMREAD_GRAYSCALE)   
    if image_gray is None:  
        print("无法读取图像文件")  
        return  
  
    at_detector = apriltag.Detector(apriltag.DetectorOptions(families='tag36h11 tag25h9'))
    tags = at_detector.detect(image_gray)

    print("tags: {}".format(tags))

    image_bgr = cv2.cvtColor(image_gray, cv2.COLOR_GRAY2BGR)
    
    for tag in tags:
        print(tuple(tag.corners[0].astype(int)))
        for i in range(4):
            cv2.circle(image_bgr, tuple(tag.corners[i].astype(int)), 4, (255, 0, 0), 2)

        cv2.circle(image_bgr, tuple(tag.center.astype(int)), 4, (2, 180, 200), 4)

  
    # 显示带有AprilTag检测框的图像  
    cv2.imshow("AprilTag Detection", image_bgr)  
    cv2.waitKey(0)  
    cv2.destroyAllWindows()  
  
if __name__ == "__main__":  
    # 指定要检测的图像路径  
    image_path = "apriltag.png"  
    detect_apriltags(image_path)