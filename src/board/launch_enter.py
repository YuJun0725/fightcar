"""按回车启动上台试车。"""

from fightcar.launch_test import main


if __name__ == "__main__":
    raise SystemExit(main(trigger="enter", default_hardware=True))
