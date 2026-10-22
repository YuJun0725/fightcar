# UpTech 教学示例

老师提供的教学源码，按实验主题组织。

| 文件或目录 | 功能 |
|---|---|
| [uptech.py](<uptech.py>) | 共享厂商接口，封装驱动器、舵机、ADC 和 IO 的动态库调用。 |
| [.gitignore](<.gitignore>) | 老师示例目录的本地文件忽略规则。 |
| [a_cds_python_control/](<a_cds_python_control/README.md>) | 基础底盘运动控制。 |
| [b_adc_io_python/](<b_adc_io_python/README.md>) | ADC 模拟量和数字 IO 读写。 |
| [c_vision_system/](<c_vision_system/README.md>) | 摄像头与图像读写、绘制。 |
| [d_image_deal/](<d_image_deal/README.md>) | 像素、通道及图像区域处理。 |
| [e_image_calcate/](<e_image_calcate/README.md>) | 灰度化、滤波、二值化和图像变换。 |
| [f_feature_match/](<f_feature_match/README.md>) | 边缘、角点、特征与模板匹配。 |
| [g_apriltag_detect/](<g_apriltag_detect/README.md>) | AprilTag 标记识别。 |
| [h_color_shape_line/](<h_color_shape_line/README.md>) | 颜色、形状识别与视觉巡线。 |
| [i_face_and_emotion/](<i_face_and_emotion/README.md>) | 人脸检测、识别与表情判断。 |
| [j_gesture/](<j_gesture/README.md>) | 手势与人体姿态识别。 |
| [k_yolo/](<k_yolo/README.md>) | RKNN 模型的 YOLO 目标检测。 |
| [l_face_reidentification/](<l_face_reidentification/README.md>) | 人脸检测、特征提取与身份比对。 |
| [m_selfcheck/](<m_selfcheck/README.md>) | Linux 主机资源状态检查。 |
| [n_tracking_car/](<n_tracking_car/README.md>) | 视觉目标跟踪与底盘跟随。 |
| [p_wheel_combat/](<p_wheel_combat/README.md>) | 轮式格斗小车比赛与动作示例。 |
| [q_human_combat/](<q_human_combat/README.md>) | 人形格斗机器人示例及 SDK。 |
| [z_test/](<z_test/README.md>) | 闭环驱动器、扎气球、捡球和六足机器人实验。 |

这是参考程序集合，当前小车的主程序在项目根目录的 `src/`；部分示例使用四个驱动器或额外舵机。运行环境与第三方依赖以各文件的导入和配置为准。

