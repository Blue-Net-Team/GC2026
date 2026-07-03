"""
硬件 no-op 占位类
====
当 GPIO/LED/开关/OLED 等状态指示硬件无法初始化时，使用这些占位对象
保证主流程代码不需要额外判断硬件是否存在。
"""


class NoOpLED:
    """LED 占位类：初始化失败时安全降级"""

    def __init__(self, *args, **kwargs) -> None:
        pass

    async def on(self):
        pass

    async def off(self):
        pass


class NoOpSwitch:
    """开关占位类：初始化失败时始终返回 False"""

    status: bool = False

    def __init__(self, *args, **kwargs) -> None:
        pass

    async def read_status(self) -> bool:
        return False


class NoOpOLED:
    """OLED 占位类：初始化失败时忽略所有绘制操作"""

    def __init__(self, *args, **kwargs) -> None:
        pass

    async def text(self, *args, **kwargs):
        pass

    async def display(self, *args, **kwargs):
        pass

    async def clear(self):
        pass
