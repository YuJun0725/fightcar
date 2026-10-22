import cv2
 
img = cv2.imread("cat.jpeg")
imgGrey = cv2.imread("cat.jpeg", False)
 
print(img.shape)
print(imgGrey.shape)
 
print(img.size)
print(img.dtype)
 
cv2.imshow('Image', img)   
cv2.imshow('Image Grey', imgGrey)  
cv2.waitKey(0)  
cv2.destroyAllWindows()