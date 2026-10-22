# i_face_and_emotion

人脸检测、样本采集、身份识别和表情判断示例。

| 文件或目录 | 功能 |
|---|---|
| [face_detect.py](<face_detect.py>) | 检测人脸并标记 68 个人脸关键点。 |
| [face_emotion.py](<face_emotion.py>) | 根据人脸特征判断表情，并包含底盘控制示例。 |
| [face_recognize.py](<face_recognize.py>) | 使用样本人脸数据进行识别。 |
| [take_photo.py](<take_photo.py>) | 从摄像头采集人脸样本，保存到 data 下的指定分组。 |
| [shape_predictor_68_face_landmarks.dat](<shape_predictor_68_face_landmarks.dat>) | dlib 的 68 点人脸关键点模型。 |
| [dlib_face_recognition_resnet_model_v1.dat](<dlib_face_recognition_resnet_model_v1.dat>) | 随示例提供的人脸特征提取模型。 |
| [haarcascade_frontalface_alt.xml](<haarcascade_frontalface_alt.xml>) | OpenCV 人脸检测分类器。 |
| [face.jpeg](<face.jpeg>) | 人脸关键点检测示例图片。 |
| [data/](<data/README.md>) | 按 g1、g2 分组保存的人脸样本。 |

