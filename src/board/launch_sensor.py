"""IO3 与 IO7 同时遮挡后启动上台试车。"""

from fightcar.launch_test import main


if __name__ == "__main__":
    raise SystemExit(main(trigger="sensor", default_hardware=True))
