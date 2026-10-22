import os, sys


def check_root():
    """
    检查 root 权限

    :return root: 是否右 root 权限
    """
    root = os.getuid() != 0
    return root
