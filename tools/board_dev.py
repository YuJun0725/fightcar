#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""电脑端开发工具：检查SSH、读取板端快照、备份并同步代码；不启动电机。"""

import argparse
import ast
import base64
from datetime import datetime
import json
from pathlib import Path
import shlex
import shutil
import subprocess

HERE = Path(__file__).resolve().parent
PROJECT = HERE.parent
SOURCES = {
    name: PROJECT / "src" / "board" / name
    for name in ("keyboard_car.py", "motor_check.py", "motor_server.py", "uptech.py")
}

# 通过SSH发送给板端Python执行，无需在板上安装此工具或Codex。
REMOTE_SCRIPT = r'''
import base64, hashlib, json, os, pathlib, platform, shutil, socket, sys, uuid
from datetime import datetime
request = json.load(sys.stdin)
base = pathlib.Path(request['remote_dir']).expanduser().resolve()
names = ('keyboard_car.py', 'motor_check.py', 'motor_server.py', 'uptech.py')
action = request['command']
result = {'remote_dir': str(base), 'hostname': socket.gethostname(),
          'python': platform.python_version(), 'machine': platform.machine()}
if action == 'check':
    result['exists'] = base.is_dir()
    result['files'] = [name for name in names if (base / name).is_file()]
elif action == 'pull':
    result['files'] = {name: base64.b64encode((base/name).read_bytes()).decode('ascii')
                       for name in names if (base/name).is_file()}
elif action == 'deploy':
    if base == pathlib.Path(base.anchor):
        raise ValueError('Refusing to deploy into a filesystem root')
    incoming = request['files']
    decoded = {}
    for name, content in incoming.items():
        if name not in names:
            raise ValueError('Unexpected filename: ' + name)
        decoded[name] = base64.b64decode(content, validate=True)
        compile(decoded[name].decode('utf-8-sig'), name, 'exec')
    # 全部新文件先通过板端Python语法检查，再进行任何写入。
    base.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime('%Y%m%d_%H%M%S_%f')
    backup = base / '.codex_backups' / stamp
    result['updated'], result['unchanged'], result['preserved'] = [], [], []
    for name, data in decoded.items():
        target = base / name
        if target.is_file() and target.read_bytes() == data:
            result['unchanged'].append(name)
            continue
        if name == 'uptech.py' and target.exists():
            # 厂商接口可能与板端固件配套，已有版本不覆盖。
            result['preserved'].append(name)
            continue
        if target.exists():
            if not target.is_file():
                raise ValueError('Target is not a file: ' + str(target))
            backup.mkdir(parents=True, exist_ok=True)
            shutil.copy2(str(target), str(backup / name))
        temporary = base / ('.codex_' + uuid.uuid4().hex + '.tmp')
        try:
            temporary.write_bytes(data)
            os.replace(str(temporary), str(target))
        finally:
            if temporary.exists():
                temporary.unlink()
        if hashlib.sha256(target.read_bytes()).digest() != hashlib.sha256(data).digest():
            raise OSError('File verification failed: ' + name)
        result['updated'].append(name)
    result['backup_dir'] = str(backup) if backup.exists() else None
else:
    raise ValueError('Unsupported command')
print('__BOARD_DEV_RESULT__' + json.dumps(result, ensure_ascii=True))
'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("check", "pull", "deploy", "shell"), nargs="?", default="check")
    parser.add_argument("--dry-run", action="store_true", help="仅检查本地文件并预览，不连接开发板")
    args = parser.parse_args()
    config = json.loads((PROJECT / "config" / "board.json").read_text(encoding="utf-8-sig"))
    for key in ("host", "user", "remote_dir"):
        if not isinstance(config.get(key), str) or not config[key].strip():
            parser.error("board.json 缺少有效的 " + key)
    if type(config.get("port")) is not int or not 1 <= config["port"] <= 65535:
        parser.error("board.json 中port应为1~65535的整数")
    target = config["user"] + "@" + config["host"]
    payload = dict(command=args.command, remote_dir=config["remote_dir"])
    if args.command == "deploy" or args.dry_run:
        payload["files"] = {}
        for name, path in SOURCES.items():
            data = path.read_bytes()
            ast.parse(data.decode("utf-8-sig"), filename=str(path), feature_version=(3, 8))
            payload["files"][name] = base64.b64encode(data).decode("ascii")
    if args.dry_run:
        print(json.dumps(dict(command=args.command, target=target, remote_dir=config["remote_dir"],
                              files=list(SOURCES), network_access=False), ensure_ascii=False, indent=2))
        return
    if not shutil.which("ssh"):
        parser.error("未找到ssh命令，请安装Windows OpenSSH客户端")
    ssh = ["ssh", "-p", str(config["port"]), "-o", "ConnectTimeout=5"]
    if args.command == "shell":
        subprocess.run(ssh + [target], check=True)
        return
    # 自动任务不等待密码输入；免密SSH待连板后单独验证/配置。
    remote_command = "python3 -c " + shlex.quote(REMOTE_SCRIPT)
    completed = subprocess.run(ssh + ["-T", "-o", "BatchMode=yes", target, remote_command],
                               input=json.dumps(payload), text=True, encoding="utf-8", capture_output=True)
    if completed.returncode:
        raise SystemExit("SSH/板端操作失败，未启动电机：\n" + completed.stderr.strip())
    marker = "__BOARD_DEV_RESULT__"
    results = [line[len(marker):] for line in completed.stdout.splitlines() if line.startswith(marker)]
    if not results:
        raise SystemExit("板端未返回有效结果：\n" + completed.stdout)
    result = json.loads(results[-1])
    if args.command == "pull":
        snapshot = PROJECT / "archive" / "board_snapshots" / datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        for name, content in result["files"].items():
            if name not in SOURCES:
                raise ValueError("板端返回了未允许的文件名")
            snapshot.mkdir(parents=True, exist_ok=True)
            (snapshot / name).write_bytes(base64.b64decode(content, validate=True))
        result["local_snapshot"] = str(snapshot) if result["files"] else None
        result["files"] = list(result["files"])
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
