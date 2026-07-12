"""
Copyright (C) 2025 IVEN-CN(He Yunfeng)

GC2026 桌面调参应用 - 图像源管理器
====
管理当前活动的 FrameSource，负责切换 UDP 图传 / 本地摄像头 / 已保存设备。
所有页面向 Manager 订阅 frame_received 信号，实现画面共享。
"""

from __future__ import annotations

from typing import Optional

import numpy as np
from PyQt6.QtCore import QObject, pyqtSignal
from loguru import logger

from app.core.device_pinger import DevicePinger
from app.core.device_store import RemoteDevice
from app.core.frame_source import (
    FrameSource,
    LocalCameraFrameSource,
    MockImageFrameSource,
    MockVideoFrameSource,
    SavedDeviceFrameSource,
    UdpFrameSource,
)

_log = logger.bind(module="FrameSourceManager")


class FrameSourceManager(QObject):
    """全局图像源管理器"""

    frame_received = pyqtSignal(np.ndarray)
    state_changed = pyqtSignal(str)
    source_name_changed = pyqtSignal(str)
    error_occurred = pyqtSignal(str)
    device_connection_state_changed = pyqtSignal(str)
    device_latency_changed = pyqtSignal(float)

    def __init__(self, parent: Optional[QObject] = None) -> None:
        super().__init__(parent)
        self._current: Optional[FrameSource] = None
        self._current_name: str = "未连接"
        self._pinger = DevicePinger(parent=self)
        self._pinger.state_changed.connect(self.device_connection_state_changed)
        self._pinger.latency_changed.connect(self.device_latency_changed)

    @property
    def current_name(self) -> str:
        return self._current_name

    def is_connected(self) -> bool:
        return self._current is not None and self._current.is_running()

    def is_pinger_running(self) -> bool:
        return self._pinger.is_running()

    def connect_local_camera(self, camera_index: int = 0) -> None:
        self._switch_source(LocalCameraFrameSource(camera_index))

    def connect_udp(self, server_ip: str, port: int = 8080) -> None:
        self._switch_source(UdpFrameSource(server_ip, port))

    def connect_saved_device(self, device: RemoteDevice) -> None:
        self._switch_source(SavedDeviceFrameSource(device.name, device.ip, device.port))

    def connect_mock_image(self, image_path: str) -> None:
        self._switch_source(MockImageFrameSource(image_path))

    def connect_mock_video(self, video_path: str) -> None:
        self._switch_source(MockVideoFrameSource(video_path))

    def disconnect(self) -> None:
        self._pinger.stop()
        if self._current is not None:
            self._current.stop()
            self._current.deleteLater()
            self._current = None
        self._current_name = "未连接"
        self.state_changed.emit("未连接")
        self.source_name_changed.emit(self._current_name)

    def _switch_source(self, source: FrameSource) -> None:
        self.disconnect()
        self._current = source
        self._current_name = source.source_name()

        # 对 UDP 源启动网络可达性探测
        if isinstance(source, UdpFrameSource):
            self._pinger.start(source.server_ip)
            self.device_connection_state_changed.emit("检测中")

        source.frame_received.connect(self.frame_received)
        source.state_changed.connect(self._on_state_changed)
        source.error_occurred.connect(self.error_occurred)
        source.state_changed.connect(self.state_changed)
        source.start()

        self.source_name_changed.emit(self._current_name)
        _log.info(f"切换到图像源: {self._current_name}")

    def _on_state_changed(self, state: str) -> None:
        if state == "未连接":
            self._current_name = "未连接"
            self.source_name_changed.emit(self._current_name)
