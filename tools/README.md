# 电脑端工具

在电脑上检查、同步和打包项目。

| 文件或目录 | 功能 |
|---|---|
| [board_dev.py](<board_dev.py>) | 通过 SSH 检查板端目录（check）、拉取脚本快照（pull）、备份并部署代码（deploy）或打开终端（shell）；`--dry-run` 仅做离线预览。 |
| [build_release.py](<build_release.py>) | 检查 Python 语法并生成键盘控制和上位机 ZIP 部署包。 |

同步默认处理 `src/board/` 下四个小车控制脚本，不启动电机；板端已有且不同的 `uptech.py` 会保留。`build_release.py` 仍依赖已移除的 `docs/keyboard_control.md` 和 `docs/console.md`，目前需先修复文档输入才能打包。

传感器采集服务使用独立目标，先在项目根目录预览：

```powershell
py -3 tools/board_dev.py deploy --target sensor --dry-run
```

板端在线且 SSH 认证可用时，可执行 `py -3 tools/board_dev.py deploy --target sensor`。该目标只处理 `sensor_server.py` 和 `uptech.py`；厂商接口保留规则相同，不启动采集服务。`check`、`pull` 也支持 `--target sensor`，省略目标时仍处理原来的小车程序。

