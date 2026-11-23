"""只读显示板端 IO0–IO7 的当前电平。"""

import time


def main():
    from uptech import UpTech

    up = UpTech()
    status = up.ADC_IO_Open()
    if isinstance(status, int) and status < 0:
        print(f"打开 ADC/IO 失败 · 返回值 {status}", flush=True)
        return 1

    try:
        print("读取 IO0–IO7 · 请逐个遮挡和松开传感器 · Ctrl+C 退出", flush=True)
        while True:
            values = up.ADC_IO_GetAllInputLevel()
            print("  ".join(f"IO{i}={level}" for i, level in enumerate(values)), flush=True)
            time.sleep(0.2)
    except KeyboardInterrupt:
        print("\n测试结束", flush=True)
    finally:
        up.ADC_IO_Close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
