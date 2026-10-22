#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""从当前源码生成部署包；不连接开发板、不加载电机库。"""

import ast
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

PROJECT = Path(__file__).resolve().parent.parent


def main():
    # 打包前检查语法，不执行源码；兼容开发板 Python 3.8 及以上版本。
    for directory in ("src/board", "src/desktop", "tools"):
        for path in (PROJECT / directory).glob("*.py"):
            ast.parse(path.read_text(encoding="utf-8-sig"),
                      filename=str(path), feature_version=(3, 8))

    keyboard = {name: PROJECT / "src" / "board" / name
                for name in ("keyboard_car.py", "motor_check.py", "uptech.py")}
    keyboard["键盘控制使用说明.md"] = PROJECT / "docs" / "keyboard_control.md"
    console = {
        "windows/windows_client.py": PROJECT / "src" / "desktop" / "windows_client.py",
        "windows/启动上位机.cmd": PROJECT / "src" / "desktop" / "启动上位机.cmd",
        "上位机使用说明.md": PROJECT / "docs" / "console.md",
    }
    for name in ("motor_server.py", "keyboard_car.py", "uptech.py"):
        console["ubuntu/" + name] = PROJECT / "src" / "board" / name
    packages = {"keyboard_car_ubuntu.zip": keyboard, "小车上位机_完整包.zip": console}

    # 先读取全部输入文件，防止输入缺失时覆盖已有部署包。
    contents = {name: {target: source.read_bytes() for target, source in files.items()}
                for name, files in packages.items()}
    output = PROJECT / "dist"
    output.mkdir(exist_ok=True)
    for name, files in contents.items():
        target = output / name
        temporary = target.with_suffix(".zip.tmp")
        try:
            with ZipFile(temporary, "w", ZIP_DEFLATED) as package:
                for filename, data in files.items():
                    package.writestr(filename, data)
            with ZipFile(temporary) as package:
                if package.testzip() is not None:
                    raise OSError("压缩包校验失败：" + name)
            temporary.replace(target)
        finally:
            if temporary.exists():
                temporary.unlink()
        print("Built: " + str(target))


if __name__ == "__main__":
    main()
