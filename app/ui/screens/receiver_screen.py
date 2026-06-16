"""
Copyright (C) 2025 IVEN-CN(He Yunfeng)

GC2026 桌面调参应用 - 图传接收页面
====
纯图传接收模式：选择图像源（本地摄像头 / 已保存设备 / 手动输入远程摄像头），
连接后实时显示画面。所有页面共享 FrameSourceManager 提供的同一帧流。
"""

from __future__ import annotations

import time
from typing import Optional

import cv2
import numpy as np
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QImage, QPixmap
from PyQt6.QtWidgets import (
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)
from loguru import logger

from app.core.device_store import DeviceStore, RemoteDevice
from app.core.frame_source_manager import FrameSourceManager
from app.ui.theme import AppTheme

_log = logger.bind(module="ReceiverScreen")


class VideoLabel(QLabel):
    """用于显示图传画面的 QLabel"""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setStyleSheet(
            f"background-color: {AppTheme.colors.surface_secondary}; "
            f"border: 1px solid {AppTheme.colors.border_primary}; "
            f"border-radius: {AppTheme.metrics.radius_md}px;"
        )
        self.setMinimumSize(320, 240)

    def set_frame(self, frame: np.ndarray) -> None:
        """将 OpenCV BGR 帧显示为 QLabel"""
        if frame is None or frame.size == 0:
            return

        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        h, w, ch = rgb.shape
        bytes_per_line = ch * w
        qt_image = QImage(rgb.data, w, h, bytes_per_line, QImage.Format.Format_RGB888)

        scaled_pixmap = QPixmap.fromImage(qt_image).scaled(
            self.size(),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self.setPixmap(scaled_pixmap)

    def resizeEvent(self, event) -> None:  # type: ignore[override]
        super().resizeEvent(event)
        pixmap = self.pixmap()
        if pixmap is not None and not pixmap.isNull():
            self.setPixmap(
                pixmap.scaled(
                    self.size(),
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
            )


class ReceiverScreen(QWidget):
    """图传接收页面"""

    MODE_LOCAL = "local"
    MODE_SAVED = "saved"
    MODE_MANUAL = "manual"

    def __init__(
        self,
        frame_source_manager: FrameSourceManager,
        device_store: DeviceStore,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self._manager = frame_source_manager
        self._device_store = device_store

        self._frame_count = 0
        self._last_fps_time = time.time()
        self._fps = 0.0

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(16)

        # 顶部工具栏
        top_bar = QHBoxLayout()
        top_bar.setSpacing(12)

        self._title = QLabel("图传接收")
        self._title.setStyleSheet(
            f"color: {AppTheme.colors.foreground_primary}; font-size: 22px; font-weight: 600;"
        )
        top_bar.addWidget(self._title)
        top_bar.addStretch()

        # 图像源类型选择下拉框
        self._mode_combo = QComboBox()
        self._mode_combo.setMinimumWidth(160)
        self._mode_combo.currentIndexChanged.connect(self._on_mode_changed)
        top_bar.addWidget(self._mode_combo)

        # 已有设备选择下拉框
        self._device_combo = QComboBox()
        self._device_combo.setMinimumWidth(160)
        self._device_combo.setVisible(False)
        top_bar.addWidget(self._device_combo)

        # 手动输入区域
        self._manual_frame = QFrame()
        manual_layout = QHBoxLayout(self._manual_frame)
        manual_layout.setContentsMargins(0, 0, 0, 0)
        manual_layout.setSpacing(8)

        self._ip_input = QLineEdit()
        self._ip_input.setPlaceholderText("设备 IP")
        self._ip_input.setFixedWidth(150)
        manual_layout.addWidget(self._ip_input)

        self._port_input = QLineEdit()
        self._port_input.setPlaceholderText("端口")
        self._port_input.setText("8080")
        self._port_input.setFixedWidth(70)
        manual_layout.addWidget(self._port_input)

        top_bar.addWidget(self._manual_frame)
        self._manual_frame.hide()

        self._connect_btn = QPushButton("连接")
        self._connect_btn.setFixedWidth(80)
        self._connect_btn.clicked.connect(self._on_connect)
        top_bar.addWidget(self._connect_btn)

        self._disconnect_btn = QPushButton("断开")
        self._disconnect_btn.setFixedWidth(80)
        self._disconnect_btn.setObjectName("secondary")
        self._disconnect_btn.setEnabled(False)
        self._disconnect_btn.clicked.connect(self._on_disconnect)
        top_bar.addWidget(self._disconnect_btn)

        layout.addLayout(top_bar)

        # 视频区域
        self._video = VideoLabel()
        layout.addWidget(self._video, stretch=1)

        # 状态栏
        status_bar = QFrame()
        status_bar.setStyleSheet(
            f"background-color: {AppTheme.colors.surface_secondary}; "
            f"border-radius: {AppTheme.metrics.radius_md}px;"
        )
        status_layout = QHBoxLayout(status_bar)
        status_layout.setContentsMargins(12, 8, 12, 8)

        self._fps_label = QLabel("FPS: 0")
        self._fps_label.setStyleSheet(
            f"color: {AppTheme.colors.foreground_muted}; font-size: 12px; font-family: {AppTheme.fonts.mono};"
        )
        status_layout.addWidget(self._fps_label)

        self._frame_count_label = QLabel("帧数: 0")
        self._frame_count_label.setStyleSheet(
            f"color: {AppTheme.colors.foreground_muted}; font-size: 12px; font-family: {AppTheme.fonts.mono};"
        )
        status_layout.addWidget(self._frame_count_label)

        status_layout.addStretch()

        self._status_label = QLabel("未连接")
        self._status_label.setStyleSheet(
            f"color: {AppTheme.colors.foreground_muted}; font-size: 12px; font-family: {AppTheme.fonts.mono};"
        )
        status_layout.addWidget(self._status_label)

        layout.addWidget(status_bar)

        # 信号连接
        self._manager.frame_received.connect(self._on_frame_received)
        self._manager.state_changed.connect(self._on_state_changed)
        self._manager.source_name_changed.connect(self._on_source_name_changed)
        self._manager.error_occurred.connect(self._on_error)

        # 初始化下拉框
        self._refresh_mode_combo()
        self._refresh_device_combo()

    def _refresh_mode_combo(self) -> None:
        self._mode_combo.clear()
        self._mode_combo.addItem("本机摄像头", self.MODE_LOCAL)
        self._mode_combo.addItem("已有设备", self.MODE_SAVED)
        self._mode_combo.addItem("手动输入图传摄像头", self.MODE_MANUAL)

    def _refresh_device_combo(self) -> None:
        self._device_combo.clear()
        for device in self._device_store.devices:
            self._device_combo.addItem(device.name, device)

    def _on_mode_changed(self, _index: int) -> None:
        mode = self._mode_combo.currentData()
        self._device_combo.setVisible(mode == self.MODE_SAVED)
        self._manual_frame.setVisible(mode == self.MODE_MANUAL)

    def _on_connect(self) -> None:
        mode = self._mode_combo.currentData()

        if mode == self.MODE_LOCAL:
            self._manager.connect_local_camera(0)
        elif mode == self.MODE_SAVED:
            device = self._device_combo.currentData()
            if device is None:
                QMessageBox.warning(self, "选择错误", "请先选择一个已有设备")
                return
            self._manager.connect_saved_device(device)
        elif mode == self.MODE_MANUAL:
            ip = self._ip_input.text().strip()
            port_text = self._port_input.text().strip()
            if not ip:
                QMessageBox.warning(self, "输入错误", "请输入设备 IP 地址")
                return
            try:
                port = int(port_text) if port_text else 8080
            except ValueError:
                QMessageBox.warning(self, "输入错误", "端口号必须为数字")
                return
            self._manager.connect_udp(ip, port)

    def _on_disconnect(self) -> None:
        self._manager.disconnect()
        self._video.setText("等待连接")
        self._video.setAlignment(Qt.AlignmentFlag.AlignCenter)

    def _on_frame_received(self, frame: np.ndarray) -> None:
        self._video.set_frame(frame)
        self._frame_count += 1

        now = time.time()
        elapsed = now - self._last_fps_time
        if elapsed >= 1.0:
            self._fps = self._frame_count / elapsed
            self._frame_count = 0
            self._last_fps_time = now
            self._fps_label.setText(f"FPS: {self._fps:.1f}")
            self._frame_count_label.setText(f"帧数: {self._frame_count}")

    def _on_state_changed(self, state: str) -> None:
        self._status_label.setText(state)
        connected = state == "已连接"
        self._connect_btn.setEnabled(not connected)
        self._disconnect_btn.setEnabled(connected)

    def _on_source_name_changed(self, name: str) -> None:
        self._status_label.setText(name)

    def _on_error(self, message: str) -> None:
        _log.error(message)
        QMessageBox.critical(self, "连接错误", message)
