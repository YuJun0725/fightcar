# 模拟与离线检查

本目录包含：

- `src/`：自动化测试代码。
- `传感器测试方案.md`：实验方法和待填写记录。
- `log/1026senser_test/`：10 月 26 日的实验原始数据、整理结果与报告。
  其中 `raw_adc_distance/` 保存动态原始曲线，`filtered_adc_distance/` 保存滤波结果，`sensor_records/` 保存静态实验整理表，`report/` 保存 LaTeX 报告及其配图。

测试使用模拟采集、假硬件和临时目录，不连接实车，不加载真实电机库。

在项目根目录执行：

```powershell
py -3 -m unittest discover -s tests/src -v
```

| 文件 | 内容 |
|---|---|
| [test_board_dev.py](src/test_board_dev.py) | 同步目标白名单、厂商接口保留、备份与输入检查。 |
| [test_sensor_server.py](src/test_sensor_server.py) | ADC/IO 采集、连续序号、批量读取复制、队列溢出与清理。 |
| [test_sensor_analysis.py](src/test_sensor_analysis.py) | 统计、滤波、标定验证、位置估计和文件恢复。 |
| [test_sensor_integration.py](src/test_sensor_integration.py) | 经真实 TCP 连接模拟服务，保存数据后重新打开。 |
| [test_sensor_worker.py](src/test_sensor_worker.py) | 注入写盘故障，确认停止后不误报完整，并保留故障原因。 |
| [test_sensor_gui.py](src/test_sensor_gui.py) | 实际 Tk 窗口连接模拟服务，验证点采样、动态标记、标定、灰度模板、绘图、导出和历史恢复。 |

界面测试需要安装桌面绘图依赖，并具有可用的 Tk 显示环境；不满足时跳过对应测试。电脑模拟界面：`py -3 src/desktop/sensor_client.py --simulate`。真实板端的采集吞吐、器件更新周期及轨道同步精度需另外人工验证。
