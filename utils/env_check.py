"""
环境检测工具模块
"""
import os
import platform


def is_desktop_environment() -> bool:
    """检测当前是否为桌面环境（支持图形显示）"""
    # SSH 会话无图形显示能力
    if os.environ.get("SSH_CLIENT") or os.environ.get("SSH_CONNECTION"):
        return False
    system = platform.system()
    if system == "Windows":
        return True
    if system == "Darwin":  # macOS
        return True
    if system == "Linux":
        # 检查 DISPLAY 环境变量
        display = os.environ.get("DISPLAY")
        if display:
            return True
        # 检查 Wayland
        wayland = os.environ.get("WAYLAND_DISPLAY")
        if wayland:
            return True
        return False
    return False

