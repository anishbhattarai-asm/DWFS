import cv2
import numpy as np

IMG_PATH = "C:\\Users\\USER\\OneDrive\\Pictures\\anish-bhattarai-pp.jpg"
BLUR = 5
CANNY_LOW = 80
CANNY_HIGH = 160
DILATE_KERNEL = 1

img = cv2.imread(IMG_PATH)
gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

blur = cv2.GaussianBlur(gray, (BLUR, BLUR), 0)
edges = cv2.Canny(blur, CANNY_LOW, CANNY_HIGH)

kernel = np.ones((DILATE_KERNEL, DILATE_KERNEL), np.uint8)
edges = cv2.dilate(edges, kernel, iterations=1)

outline = 255 - edges

cv2.imwrite("outline.png", outline)

cv2.imshow("Outline", outline)
cv2.waitKey(0)
cv2.destroyAllWindows()
