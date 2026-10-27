# 连接配置

集中保存电脑连接开发板时使用的参数。

| 文件或目录 | 功能 |
|---|---|
| [board.json](<board.json>) | `host`：开发板 IP；`user`：SSH 用户名；`port`：SSH 端口；`remote_dir`：板端代码目录。 |

`tools/board_dev.py` 从这里读取配置；修改开发板地址或部署目录时调整此文件。

`sensor_port` 为传感器上位机的默认连接端口，默认 8766。上位机连接隧道本机端口，开发板 IP 和 SSH 参数仍集中放在此配置中。修改端口后，还需相应调整 SSH 隧道命令和板端 `sensor_server.py --port` 参数；板端服务不读取此配置文件。

