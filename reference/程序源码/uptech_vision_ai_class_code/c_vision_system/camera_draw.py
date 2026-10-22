import cv2

cap = cv2.VideoCapture(0)

while True:
    ret, frame = cap.read()
    frame = cv2.flip(frame, 1)
    frame = cv2.resize(frame, (640, 480))
    cv2.circle(frame, (320, 240), 100, (0, 255, 0), 3)
    cv2.line(frame, (0, 0), (640, 480), (255, 0, 0), 3)
    cv2.rectangle(frame, (100, 100), (540, 380), (0, 0, 255), 3)
    cv2.imshow('frame', frame)
    if cv2.waitKey(1) & 0xFF == ord('q'):
        break