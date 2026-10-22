# q_human_combat

人形格斗机器人比赛示例，包含独立 SDK 和基础、阶段测试。

| 文件或目录 | 功能 |
|---|---|
| [demo_human_combat.py](<demo_human_combat.py>) | 通过状态控制组织巡台、目标识别和机器人动作。 |
| [sdk/](<sdk/README.md>) | 硬件访问、视觉检测、传感器逻辑和动作接口。 |
| [test_basic_arm.py](<test_basic_arm.py>) | 机械臂、舵机基础动作测试。 |
| [test_basic_camera.py](<test_basic_camera.py>) | 摄像头采集与显示测试。 |
| [test_basic_grayscale.py](<test_basic_grayscale.py>) | 灰度传感器读取测试。 |
| [test_basic_move.py](<test_basic_move.py>) | 底盘移动状态与指令测试。 |
| [test_basic_tilt.py](<test_basic_tilt.py>) | 倾角传感器状态测试。 |
| [test_stage_arena.py](<test_stage_arena.py>) | 按时间前进上擂台的阶段测试。 |
| [test_stage_patrol.py](<test_stage_patrol.py>) | 灰度传感器巡台策略测试。 |
| [test_stage_stand_up.py](<test_stage_stand_up.py>) | 机器人站起动作测试。 |
| [test_stage_tag_detect.py](<test_stage_tag_detect.py>) | AprilTag 识别及朝向目标移动测试。 |

这是人形机器人参考程序，其舵机、传感器和动作配置与当前轮式小车不同。

