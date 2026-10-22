from sdk.api import UpAPIBuilder

"""
基础测试：相机通讯

退出：Ctrl + Z
"""

if __name__ == "__main__":

    api = UpAPIBuilder().build()

    while True:

        api.display_camera_frame()