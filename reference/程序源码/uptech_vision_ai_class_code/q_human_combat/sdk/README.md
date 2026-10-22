# q_human_combat/sdk

人形格斗示例内部使用的 SDK。

| 文件或目录 | 功能 |
|---|---|
| [api.py](<api.py>) | 硬件配置构建器和统一接口，提供移动、传感器、视觉与舵机动作调用。 |
| [logic.py](<logic.py>) | PID 计算、灰度导航策略和计时器。 |
| [mode.py](<mode.py>) | 舵机、引脚、倾角与导航方向的枚举定义。 |
| [application_layer/](<application_layer/README.md>) | 摄像头、IO/ADC 和舵机访问封装，以及退出通知。 |
| [hardware_layer/](<hardware_layer/README.md>) | 摄像头和厂商动态库的底层资源管理。 |
| [logic_layer/](<logic_layer/README.md>) | 倾倒状态和 AprilTag 识别逻辑。 |
| [utils/](<utils/README.md>) | 绘图、权限检查和类型定义。 |

这里的 PID 属于老师示例，当前项目 `src/` 尚未实现轮速反馈闭环。

