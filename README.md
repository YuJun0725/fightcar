# 小车控制程序

开发板运行电机控制，Windows 运行上位机。Python 程序使用标准库；实车控制还需开发板已有的厂商 `libuptech.so`。

## 目录与修改位置

```text
fightcar/
├── src/                     产品源码
│   ├── board/               鲁班猫上运行的程序
│   │   ├── keyboard_car.py  运动计算、总线发送、键盘控制
│   │   ├── motor_server.py  接收上位机指令，复用键盘程序的控制函数
│   │   ├── motor_check.py   单独测试 ID 1 或 ID 2
│   │   └── uptech.py        厂商接口，调用 libuptech.so
│   └── desktop/             Windows 上位机
│       ├── windows_client.py 界面、参数调整和网络连接
│       └── 启动上位机.cmd   双击启动窗口
├── config/
│   └── board.json           开发板 IP、用户名、远端代码目录
├── tools/
│   ├── board_dev.py         检查连接、拉取快照、备份部署
│   └── build_release.py     从当前源码重新生成压缩包
├── reference/               老师源码及硬件参考资料
├── .gitignore               本地工作文件、缓存及参考视频的排除规则
└── README.md                本说明
```

改运动逻辑看 `src/board/keyboard_car.py`，改窗口看 `src/desktop/windows_client.py`，改网络服务看 `src/board/motor_server.py`。源码统一放在`src/`，开发辅助脚本放在`tools/`；保留直接运行的脚本结构，不需要安装Python包。

## Windows 开发入口

以下命令都在项目根目录执行：

```powershell
# 打开上位机，也可双击 src/desktop/启动上位机.cmd
py -3 src/desktop/windows_client.py

# 模拟服务，不连接电机；在另一个终端打开上位机
py -3 src/board/motor_server.py --simulate

# 离线检查同步计划；真正部署前需具备 SSH 登录条件
py -3 tools/board_dev.py deploy --dry-run

# 打包工具仍引用已移除的 docs/keyboard_control.md 和 docs/console.md，需先适配
```

需要实际同步时依次执行 `py -3 tools/board_dev.py check`、`pull`、`deploy`。IP 和远端目录只改 [config/board.json](config/board.json)，板端快照保存在 `archive/board_snapshots/`。同步工具不会启动电机，也不会同步 Windows 界面或整个工程目录。

## 鲁班猫运行入口

当前配置：`bcsh@192.168.3.88`，代码目录 `/home/bcsh/hsy/ceshi`。同步后四个板端脚本仍直接放在该目录，开发板的启动命令保持不变：

```bash
cd ~/hsy/ceshi
sudo python3 keyboard_car.py --speed 300 --spin-speed 200
```

使用上位机时，Windows 先运行：

```powershell
ssh -L 8765:127.0.0.1:8765 bcsh@192.168.3.88
```

在这个 SSH 终端中进入 `~/hsy/ceshi`，运行 `sudo python3 motor_server.py`，保持终端打开。上位机连接 `127.0.0.1:8765`。键盘程序、测试程序和服务端每次只运行一个。

若把整个工程复制到开发板，而非用同步工具或部署包，则先 `cd` 到工程的 `src/board/` 再运行相同命令。同步工具和压缩包仍直接提供板端脚本，不会在远端额外创建`src/`目录。

## 参考资料与 Git 提交范围

老师的原始源码、实验指导书与硬件资料在 `reference/`。老师源码作为普通文件由本项目跟踪，不需要单独克隆嵌套仓库。

本地 agent 工作文件、缓存、构建输出、板端快照和 `reference/` 下的视频由 `.gitignore` 排除，保留在本机，不提交到 GitHub。

当前不保留 `docs/`、`dist/`、`archive/`。日常直接修改源码并通过同步工具部署；`pull` 需要保存快照时会按需创建 `archive/board_snapshots/`。打包脚本的文档输入尚需适配。

## 当前硬件验证记录

四个电机分属 ID 1、2 两个驱动器，当前没有接入转速反馈。已报告前进、后退正常；原地旋转曾只有一侧转，近似原地转弯对照后报告两侧转动，但 A/D 是否恢复及根因尚未最终确认。保持这一问题为待验证项，不把相同速度值的处理异常当作已证实结论。此次整理不修改运动算法或速度映射，也不自动更新开发板。
