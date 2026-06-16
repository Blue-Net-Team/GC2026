"""
Copyright (C) 2025 IVEN-CN(He Yunfeng)

GC2026 桌面调参应用 - 图传接收页面
====
纯图传接收模式：显示实时画面、FPS/丢包统计、连接控制。
"""

from __future__ import annotations

from typing import Optional

import cv2
import numpy as np
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QImage, QPixmap
from PyQt6.QtWidgets import (
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

from app.core.udp_receiver import ReceiverStats, UdpReceiver
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
        # 保留原有 pixmap 的缩放
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

    def __init__(
        self,
        udp_receiver: UdpReceiver,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self._udp_receiver = udp_receiver

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

        self._ip_input = QLineEdit()
        self._ip_input.setPlaceholderText("设备 IP，例如 192.168.123.8")
        self._ip_input.setFixedWidth(200)
        top_bar.addWidget(self._ip_input)

        self._port_input = QLineEdit()
        self._port_input.setPlaceholderText("端口")
        self._port_input.setText("8080")
        self._port_input.setFixedWidth(80)
        top_bar.addWidget(self._port_input)

        self._connect_btn = QPushButton("连接")
        self._connect_btn.setFixedWidth(80)
        self._connect_btn.clicked.connect(self._on_connect)
        top_bar.addWidget(self._connect_btn)

        self._disconnect_btn = QPushButton("断开")
        self._disconnect_btn.setFixedWidth(80)
        self._disconnect_btn.setObjectName("secondary")
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

        self._lost_label = QLabel("丢帧: 0")
        self._lost_label.setStyleSheet(
            f"color: {AppTheme.colors.accent_error}; font-size: 12px; font-family: {AppTheme.fonts.mono};"
        )
        status_layout.addWidget(self._lost_label)

        status_layout.addStretch()

        self._status_label = QLabel("UDP • 等待连接")
        self._status_label.setStyleSheet(
            f"color: {AppTheme.colors.foreground_muted}; font-size: 12px; font-family: {AppTheme.fonts.mono};"
        )
        status_layout.addWidget(self._status_label)

        layout.addWidget(status_bar)

        # 信号连接
        self._udp_receiver.frame_received.connect(self._on_frame_received)
        self._udp_receiver.state_changed.connect(self._on_state_changed)
        self._udp_receiver.stats_changed.connect(self._on_stats_changed)
        self._udp_receiver.error_occurred.connect(self._on_error)

    def _on_connect(self) -> None:
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

        self._udp_receiver.connect_to(ip, port)

    def _on_disconnect(self) -> None:
        self._udp_receiver.disconnect()
        self._status_label.setText("UDP • 已断开")
        self._video.setText("等待连接")
        self._video.setAlignment(Qt.AlignmentFlag.AlignCenter)

    def _on_frame_received(self, frame: np.ndarray) -> None:
        self._video.set_frame(frame)

    def _on_state_changed(self, state: str) -> None:
        self._status_label.setText(f"UDP • {state}")

    def _on_stats_changed(self, stats: ReceiverStats) -> None:
        self._fps_label.setText(f"FPS: {stats.fps:.1f}")
        self._frame_count_label.setText(f"帧数: {stats.frame_count}")
        self._lost_label.setText(f"丢帧: {stats.lost_frames}")

    def _on_error(self, message: str) -> None:
        _log.error(message)
        QMessageBox.critical(self, "连接错误", message)
