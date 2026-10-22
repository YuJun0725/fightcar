# 电脑端工具

在电脑上检查、同步和打包项目。

| 文件或目录 | 功能 |
|---|---|
| [board_dev.py](<board_dev.py>) | 通过 SSH 检查板端目录（check）、拉取脚本快照（pull）、备份并部署代码（deploy）或打开终端（shell）；`--dry-run` 仅做离线预览。 |
| [build_release.py](<build_release.py>) | 检查 Python 语法并生成键盘控制和上位机 ZIP 部署包。 |

同步只处理 `src/board/` 下四个指定脚本，不启动电机；板端已有且不同的 `uptech.py` 会保留。`build_release.py` 仍依赖已移除的 `docs/keyboard_control.md` 和 `docs/console.md`，目前需先修复文档输入才能打包。

