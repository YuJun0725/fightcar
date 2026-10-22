# Windows 上位机

在 Windows 上提供小车操作界面，通过 TCP 连接开发板服务端。

| 文件或目录 | 功能 |
|---|---|
| [windows_client.py](<windows_client.py>) | Tkinter 操作窗口，支持前后移动、原地旋转、按半径转弯和实时调参；处理心跳及松键、失焦、断线时的停车请求。 |
| [启动上位机.cmd](<启动上位机.cmd>) | 双击启动上位机，自动切换到脚本所在目录并调用 `py -3 windows_client.py`。 |

也可在项目根目录执行 `py -3 src/desktop/windows_client.py`。实际连接通过 SSH 隧道访问 `127.0.0.1:8765`，步骤见[项目说明](../../README.md)。

