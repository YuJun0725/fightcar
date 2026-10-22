from sdk.api import UpAPIBuilder
from sdk.mode import TiltState

"""
阶段测试：从倒地状态起身

退出：Ctrl + Z
"""

if __name__ == "__main__":

    api = UpAPIBuilder().build()

    tilt_state = api.detect_tilt_state()

    print(f"tilt_state: {tilt_state}")

    if tilt_state == TiltState.FALL_FORWARD:

        api.action_stand_up_from_fall_forward()

    if tilt_state == TiltState.FALL_BACKWARD:

        api.action_stand_up_from_fall_backward()


