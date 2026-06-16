r"""
Copyright (C) 2025 IVEN-CN(He Yunfeng)

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with this program.  If not, see <https://www.gnu.org/licenses/>.
"""

import asyncio
import sys

# 在导入 loguru 前统一标准流编码，避免 Windows 终端中文乱码
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

import qasync
from PyQt6.QtWidgets import QApplication, QLabel, QVBoxLayout, QWidget
from loguru import logger


def _setup_logging(debug: bool) -> None:
    level = "DEBUG" if debug else "INFO"
    logger.remove()
    logger.add(sys.stderr, level=level)


def main(debug: bool = False) -> int:
    """桌面应用入口"""
    _setup_logging(debug)
    logger.info("启动 GC2026 桌面调参应用")

    app = QApplication(sys.argv)
    loop = qasync.QEventLoop(app)
    asyncio.set_event_loop(loop)

    window = QWidget()
    window.setWindowTitle("工创2026调参")
    window.resize(1280, 720)
    window.setStyleSheet("background-color: #1A1A2E;")

    layout = QVBoxLayout(window)
    label = QLabel("GC2026 桌面调参应用启动成功\n后续按 docs/app.pen 设计稿实现界面")
    label.setStyleSheet("color: white; font-size: 18px;")
    layout.addWidget(label)

    window.show()

    with loop:
        loop.run_forever()

    return 0
