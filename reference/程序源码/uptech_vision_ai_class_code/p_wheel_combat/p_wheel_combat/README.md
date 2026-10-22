# p_wheel_combat/p_wheel_combat

轮式格斗小车运动、传感器检测和比赛示例。

| 文件或目录 | 功能 |
|---|---|
| [motion_controller.py](<motion_controller.py>) | 左右驱动器运动指令、前后机械爪和上下台动作封装。 |
| [platform_detect.py](<platform_detect.py>) | 台面、围栏检测及上台相关流程。 |
| [edge_detect.py](<edge_detect.py>) | 台面边缘与目标检测及运动流程。 |
| [apriltag_test.py](<apriltag_test.py>) | 摄像头 AprilTag 识别线程示例。 |
| [match_demo.py](<match_demo.py>) | 整合检测结果与底盘动作的比赛流程。 |
| [motion_test.py](<motion_test.py>) | 默认姿态、前上台和后上台动作演示。 |
| [move_test.py](<move_test.py>) | 前进上台、恢复默认姿态并停车的示例。 |

机械爪动作和传感器阈值属于老师示例的硬件配置；当前小车只确认使用两个底盘驱动器，不能据此认定已适配全部动作。

