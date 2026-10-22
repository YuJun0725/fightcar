from sdk.api import UpAPIBuilder
import time

"""
基础测试：舵机通讯

先执行攻击动作，然后复位
"""

if __name__ == "__main__":
    api = UpAPIBuilder().build()

    print("攻击")
    api.action_attack()

    time.sleep(3.0)

    print("复位")
    api.action_standby()

    time.sleep(3.0)

    print("程序结束")
