import cv2
 
img = cv2.imread("cat.jpeg")

region = img[150:600, 150:650]
cv2.imshow('Image', img)   
cv2.imshow("Region", region) 
cv2.waitKey(0)  
cv2.destroyAllWindows()