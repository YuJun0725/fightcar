import cv2


cv2.namedWindow("test", cv2.WINDOW_NORMAL)

#1调用摄像头
cap = cv2.VideoCapture(0)

#保存的姓名，分为g1和g2可在这里更改
person_name = "g2"

dirname = "data/" + person_name + "/"

count = 0

#2人脸识别器分类器
classfier=cv2.CascadeClassifier("haarcascade_frontalface_alt.xml")

color=(0,255,0)

cv2.namedWindow("test", cv2.WINDOW_NORMAL) 

while cap.isOpened():#当摄像头打开时
    
    ok,frame=cap.read()
    frame = cv2.resize(frame, (640, 480))
    
    if not ok:
        break
    
    #3灰度转换
    grey=cv2.cvtColor(frame,cv2.COLOR_BGR2GRAY)
    
    #4人脸检测,图片缩放比例和需要检测的有效点数
    faceRects = classfier.detectMultiScale(grey, scaleFactor = 1.2, minNeighbors = 3, minSize = (32, 32))
    
    if len(faceRects) > 0:            #大于0则检测到人脸      
        print("检测到人脸")                             
        for faceRect in faceRects:  #单独框出每一张人脸
             x, y, w, h = faceRect  #5画图   
             cv2.rectangle(frame, (x - 10, y - 10), (x + w + 10, y + h + 10), color, 3)
    
    cv2.imshow("test",frame)#显示窗口
    
    if len(faceRects) == 1:
        x, y, w, h = faceRects[0]
        face = cv2.resize(grey[y:y+h, x:x+w], (200, 200))
        
    if cv2.waitKey(1)&0xFF==ord('p'): #输入p保存图片
        print("Save Image!!!!")
        cv2.imwrite(dirname + '%s.pgm' % str(count), face)
        count += 1
        
    if cv2.waitKey(1) & 0xFF == ord('q'):
        break
        
cap.release()
cv2.destroyAllWindows()#关闭窗口