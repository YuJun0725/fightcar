# 连接配置

集中保存电脑连接开发板时使用的参数。

| 文件或目录 | 功能 |
|---|---|
| [board.json](<board.json>) | `host`：开发板 IP；`user`：SSH 用户名；`port`：SSH 端口；`remote_dir`：板端代码目录。 |

`tools/board_dev.py` 从这里读取配置；修改开发板地址或部署目录时调整此文件。

