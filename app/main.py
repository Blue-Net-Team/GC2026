"""
Copyright (C) 2025 IVEN-CN(He Yunfeng)

GC2026 桌面调参应用 - 入口
====
初始化 PyQt6 + qasync 事件循环，加载主题与主窗口。
"""

from __future__ import annotations

import asyncio
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

import qasync
from PyQt6.QtWidgets import QApplication
from loguru import logger

from app.core.config_bridge import ConfigBridge
from app.core.device_store import DeviceStore
from app.core.frame_source_manager import FrameSourceManager
from app.ui.main_window import MainWindow
from app.ui.theme import AppTheme


def main(debug: bool = False) -> int:
    logger.remove()
    logger.add(
        sys.stderr,
        level="DEBUG" if debug else "INFO",
        format="<green>{time:HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan> - <level>{message}</level>",
    )

    app = QApplication(sys.argv)
    app.setStyleSheet(AppTheme.build_stylesheet())

    loop = qasync.QEventLoop(app)
    asyncio.set_event_loop(loop)

    config_bridge = ConfigBridge("config.yaml")
    config_bridge.load()

    device_store = DeviceStore("devices.json")
    frame_source_manager = FrameSourceManager()

    window = MainWindow(config_bridge, frame_source_manager, device_store)
    window.show()

    with loop:
        loop.run_forever()

    return 0
