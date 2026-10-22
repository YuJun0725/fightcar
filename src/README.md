# 项目源码

小车当前使用的程序，按运行平台分为开发板端和 Windows 端。

| 文件或目录 | 功能 |
|---|---|
| [board/](<board/README.md>) | 鲁班猫 Ubuntu 程序：运动计算、键盘控制、电机服务和厂商接口。 |
| [desktop/](<desktop/README.md>) | Windows 上位机：操作界面、参数调整和网络连接。 |

运动计算与方向映射集中在 `board/keyboard_car.py`，服务端复用这些函数。

