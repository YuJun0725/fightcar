# 鲁班猫程序

在鲁班猫 Ubuntu 上运行，负责接收控制指令并调用厂商电机接口。

| 文件或目录 | 功能 |
|---|---|
| [keyboard_car.py](<keyboard_car.py>) | SSH 终端键盘控制；集中定义左右轮运动计算、方向映射、发送和停车逻辑。 |
| [motor_server.py](<motor_server.py>) | 接收 Windows 上位机的 JSON 控制指令，复用键盘程序的运动函数；支持 `--simulate` 模拟模式。 |
| [motor_check.py](<motor_check.py>) | 分别测试驱动器 ID 1 或 2 的正反转，用于观察各侧电机的实际表现。 |
| [uptech.py](<uptech.py>) | 通过 ctypes 调用板端 `libuptech.so`，封装驱动器通信接口。 |

电脑端可在项目根目录执行 `py -3 src/board/motor_server.py --simulate`。真实电机控制需板端厂商库；键盘、服务端和单路测试程序每次只运行一个。速度参数为控制值，不能当作实测 RPM。

