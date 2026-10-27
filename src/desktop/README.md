# Windows 上位机

在 Windows 上提供小车操作界面，通过 TCP 连接开发板服务端。

| 文件或目录 | 功能 |
|---|---|
| [windows_client.py](<windows_client.py>) | Tkinter 操作窗口，支持前后移动、原地旋转、按半径转弯和实时调参；处理心跳及松键、失焦、断线时的停车请求。 |
| [启动上位机.cmd](<启动上位机.cmd>) | 双击启动上位机，自动切换到脚本所在目录并调用 `py -3 windows_client.py`。 |
| [sensor_client.py](<sensor_client.py>) | 独立传感器实验窗口：多通道采集、实时绘图、点采样、动态标记、历史对比及数据导出。 |
| [sensor_analysis.py](<sensor_analysis.py>) | 实验统计、光电边界、距离标定、因果滤波和实验文件的保存、重开。 |
| [启动传感器测试.cmd](<启动传感器测试.cmd>) | 双击启动传感器实验软件，可附带 `--simulate` 参数体验模拟采集。 |
| [requirements.txt](<requirements.txt>) | Windows 传感器界面的绘图依赖，板端无需安装。 |

也可在项目根目录执行 `py -3 src/desktop/windows_client.py`。实际连接通过 SSH 隧道访问 `127.0.0.1:8765`，步骤见[项目说明](../../README.md)。

## 传感器实验软件

Windows 使用 Python 3.10 及以上版本，首次安装依赖：

```powershell
py -3 -m pip install -r src/desktop/requirements.txt
```

在项目根目录启动电脑模拟（自动启动本机模拟服务，不加载厂商库）：

```powershell
py -3 src/desktop/sensor_client.py --simulate
```

实际采集先在项目根目录部署服务：

```powershell
py -3 tools/board_dev.py deploy --target sensor --dry-run
py -3 tools/board_dev.py deploy --target sensor
ssh -L 8766:127.0.0.1:8766 bcsh@192.168.3.88
```

部署命令需要已配置可用的 SSH 密钥或代理；也可手动将 `sensor_server.py` 复制到板端目录，保留板端配套 `uptech.py`。在 SSH 终端执行 `cd ~/hsy/ceshi`，然后运行 `sudo python3 sensor_server.py`。保持 SSH 打开，在另一个 Windows 终端运行 `py -3 src/desktop/sensor_client.py` 并连接。连接参数来自 [board.json](../../config/board.json)，`sensor_port` 默认 8766。

### 实验操作

1. 新建实验，选择 P1～P4、D1～D5 或 G1～G3，填写传感器、材料、角度、照明等条件。
2. 勾选需记录的 IO/ADC 通道，指定主通道；采样率默认 50 Hz，状态栏显示实测读取频率。
3. 静态：停稳后填写距离和接近/释放方向，点击点采样。完成后改变距离或条件，再采下一点；D5 用新的距离点验证。
4. 动态：开始连续采集，填写起始距离、速度及方向，通过“运动开始/结束”标记估计位置区间。轨道仍由用户操作；估计位置不等于实测位置。
5. 在“实验记录 / 统计”页比较试次或条件，在“距离标定 / 验证”页建立标定、检查误差；载入历史实验后也可继续分析，导出 CSV 和 PNG。

光电主通道选 IO，距离和灰度主通道选 ADC，其他勾选通道仍会同时保存。一个完整的光电静态重复包含接近和释放的多个点，全部完成后点击“下一次重复”。D1 至少采三个不同距离的点，再建立标定；D5 使用新的距离点验证，验证点不进入建模。材料或角度混合时，在记录表中选择同一组条件建立标定。

“分组对比图”适合看静态点与条件差异；建立标定和验证后会生成换算及误差图。实时绘图可暂停以使用工具栏缩放，采集和保存会继续；实时曲线只显示最近 30 秒。PNG 保存当前图，“原始 CSV”和“统计 CSV”分别导出原始帧和分析表。重开历史后重新分析的结果可显式导出，不会自动写入另一个采集会话。

每次试验的条件按快照保存。默认输出到根目录按需生成的 `measurements/`，也可选择其他目录；更换保存位置前需新建实验。会话保存条件 `metadata.json`、原始帧 `samples.csv`、运动事件 `events.csv`、分析表 `summary.csv`，建立标定后另存 `calibration.json`；事件文件在有标记后生成。原始 CSV 持续写盘，滤波只用于分析，不改原始值。断线或写入失败的试次标为不完整。高读取频率不代表传感器自身具有同样的刷新频率。

采样、标定和各项实验的定义见[传感器测试方案](../../tests/传感器测试方案.md)。

