# 鲁班猫程序

在鲁班猫 Ubuntu 上运行，提供电机控制与 ADC/IO 传感器采集入口。

| 文件或目录 | 功能 |
|---|---|
| [keyboard_car.py](<keyboard_car.py>) | SSH 终端键盘控制；集中定义左右轮运动计算、方向映射、发送和停车逻辑。 |
| [motor_server.py](<motor_server.py>) | 接收 Windows 上位机的 JSON 控制指令，复用键盘程序的运动函数；支持 `--simulate` 模拟模式。 |
| [sensor_server.py](<sensor_server.py>) | 独立传感器采集服务，读取所选 IO/ADC 通道并发送时间戳及实验事件；支持模拟，不访问电机接口。 |
| [motor_check.py](<motor_check.py>) | 分别测试驱动器 ID 1 或 2 的正反转，用于观察各侧电机的实际表现。 |
| [uptech.py](<uptech.py>) | 通过 ctypes 调用板端 `libuptech.so`，封装驱动器通信接口。 |

电脑端可在项目根目录执行 `py -3 src/board/motor_server.py --simulate`。真实电机控制需板端厂商库；键盘、服务端和单路测试程序每次只运行一个。速度参数为控制值，不能当作实测 RPM。

传感器服务在板端部署目录手动启动：`sudo python3 sensor_server.py --port 8766`。默认仅监听回环地址，Windows 经 SSH 隧道连接；采集仅在上位机点击开始后打开 ADC/IO，停止或断线时清理。硬件采集时应独占传感器接口，避免同时运行其他 ADC/IO 示例。电脑调试可执行 `py -3 src/board/sensor_server.py --simulate`。

采集帧包含所选 IO 0～7、ADC 0～8、试次编号、连续序号及读取起止时间。时间为板端单调时钟，不能当作日期，也不代表所有通道同时采样；ADC 保留原始码值，不预设实物位数或参考电压。请求频率默认 50 Hz，可设为 1～1000 Hz，实际读取速度以时间戳统计为准。

上位机的运动标记仅记录实验事件，服务端不控制轨道。发送队列溢出或硬件异常时会报告不完整；厂商调用长期无响应时停止接受后续采集，需人工检查控制器并重启服务。

