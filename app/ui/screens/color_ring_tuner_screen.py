"""
Copyright (C) 2025 IVEN-CN(He Yunfeng)

GC2026 桌面调参应用 - 色环调参页面
====
左侧显示实时原图与霍夫圆检测预览，右侧基于 ColorRingDetector.TUNABLE_PARAMS
动态渲染预处理/霍夫检测/后处理参数分组滑条。
"""

from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor
from typing import Optional

import cv2
import numpy as np
from PyQt6.QtCore import QTimer, Qt, pyqtSignal
from PyQt6.QtGui import QImage, QPixmap
from PyQt6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)
from loguru import logger

from app.core.config_bridge import ConfigBridge
from app.core.frame_source_manager import FrameSourceManager
from app.ui.theme import AppTheme
from app.ui.widgets.parameter_group_panel import ParameterGroupPanel
from detector.ColorRingDetect import ColorRingDetector

_log = logger.bind(module="ColorRingTunerScreen")


def _cv_to_pixmap(frame: np.ndarray) -> QPixmap:
    """OpenCV BGR 帧转 QPixmap。"""
    rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    h, w, ch = rgb.shape
    bytes_per_line = ch * w
    image = QImage(rgb.data, w, h, bytes_per_line, QImage.Format.Format_RGB888)
    return QPixmap.fromImage(image)


def _sync_binarize(detector: ColorRingDetector, frame: np.ndarray) -> np.ndarray:
    """在线程池中运行异步二值化函数。"""
    coro = detector.binarization(frame)
    try:
        loop = asyncio.new_event_loop()
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def _sync_get_circles(
    detector: ColorRingDetector, binary: np.ndarray
) -> Optional[list[tuple[int, int, int]]]:
    """在线程池中运行异步霍夫圆检测函数。"""
    coro = detector.get_circles(binary)
    try:
        loop = asyncio.new_event_loop()
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def _draw_circle_overlay(
    frame: np.ndarray, circles: Optional[list[tuple[int, int, int]]]
) -> np.ndarray:
    """在原图上绘制检测到的色环圆和圆心。"""
    output = frame.copy()
    if circles:
        for x, y, r in circles:
            cv2.circle(output, (int(x), int(y)), int(r), (0, 0, 255), 2)
            cv2.circle(output, (int(x), int(y)), 2, (255, 0, 0), 2)
    return output


class VideoPreview(QLabel):
    """等比缩放、完整显示的视频预览标签。"""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setStyleSheet(
            f"background-color: {AppTheme.colors.surface_secondary}; "
            f"border: 1px solid {AppTheme.colors.border_primary}; "
            f"border-radius: {AppTheme.metrics.radius_md}px;"
        )
        self.setMinimumSize(280, 200)

    def set_frame(self, frame: np.ndarray) -> None:
        pixmap = _cv_to_pixmap(frame)
        self.setPixmap(
            pixmap.scaled(
                self.size(),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        )

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


class ColorRingTunerScreen(QWidget):
    """色环调参页面。"""

    _preview_ready = pyqtSignal(np.ndarray, np.ndarray, object)

    def __init__(
        self,
        config_bridge: ConfigBridge,
        frame_source_manager: FrameSourceManager,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self._config_bridge = config_bridge
        self._frame_source_manager = frame_source_manager
        self._app_config = config_bridge.config

        self._schema = ColorRingDetector.TUNABLE_PARAMS
        self._detector = ColorRingDetector()
        self._update_detector_from_config()

        self._latest_frame: Optional[np.ndarray] = None
        self._executor = ThreadPoolExecutor(max_workers=2)

        self._preview_timer = QTimer(self)
        self._preview_timer.setSingleShot(True)
        self._preview_timer.timeout.connect(self._update_preview)

        self._build_ui()

        self._frame_source_manager.frame_received.connect(self._on_frame_received)
        self._preview_ready.connect(self._on_preview_ready)

    def _build_ui(self) -> None:
        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(20, 20, 20, 20)
        main_layout.setSpacing(20)

        # 左侧预览区
        preview_area = QVBoxLayout()
        preview_area.setSpacing(12)

        self._video_preview = VideoPreview()
        self._video_preview.setText("等待图传画面")
        preview_area.addWidget(self._video_preview, stretch=1)

        self._mask_preview = VideoPreview()
        self._mask_preview.setText("色环检测预览")
        preview_area.addWidget(self._mask_preview, stretch=1)

        main_layout.addLayout(preview_area, stretch=55)

        # 右侧调参面板
        panel = QFrame()
        panel.setStyleSheet(
            f"background-color: {AppTheme.colors.surface_secondary}; "
            f"border-radius: {AppTheme.metrics.radius_md}px;"
        )
        panel.setFixedWidth(AppTheme.metrics.panel_width)
        panel_layout = QVBoxLayout(panel)
        panel_layout.setContentsMargins(20, 20, 20, 20)
        panel_layout.setSpacing(16)

        title = QLabel("色环调参")
        title.setStyleSheet(
            f"color: {AppTheme.colors.foreground_primary}; font-size: 22px; font-weight: 600;"
        )
        panel_layout.addWidget(title)

        # 参数分组 Tab：根据 schema.groups 顺序动态创建
        self._tabs = QTabWidget()
        self._tabs.setDocumentMode(True)
        self._tabs.setElideMode(Qt.TextElideMode.ElideNone)
        self._tabs.tabBar().setExpanding(False)

        self._group_panels: dict[str, ParameterGroupPanel] = {}
        params_by_group = self._schema.params_by_group()
        for group in self._schema.groups or []:
            params = params_by_group.get(group, [])
            group_panel = ParameterGroupPanel(params)
            group_panel.value_changed.connect(self._on_slider_changed)
            self._group_panels[group] = group_panel
            self._tabs.addTab(group_panel, group)

        panel_layout.addWidget(self._tabs)

        # 检测信息
        self._info_card = QFrame()
        self._info_card.setStyleSheet(
            f"background-color: {AppTheme.colors.surface_tertiary}; "
            f"border-radius: {AppTheme.metrics.radius_md}px;"
        )
        info_layout = QVBoxLayout(self._info_card)
        info_layout.setContentsMargins(12, 12, 12, 12)
        info_layout.setSpacing(8)

        info_title = QLabel("检测信息")
        info_title.setStyleSheet(
            f"color: {AppTheme.colors.foreground_muted}; font-size: 12px;"
        )
        info_layout.addWidget(info_title)

        self._info_label = QLabel("未检测到色环")
        self._info_label.setStyleSheet(
            f"color: {AppTheme.colors.foreground_secondary}; font-size: 13px; font-family: {AppTheme.fonts.mono};"
        )
        info_layout.addWidget(self._info_label)

        panel_layout.addWidget(self._info_card)

        # 操作按钮
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(10)

        self._save_btn = QPushButton("保存")
        self._save_btn.clicked.connect(self._on_save)
        btn_layout.addWidget(self._save_btn)

        self._reset_btn = QPushButton("恢复默认")
        self._reset_btn.setObjectName("secondary")
        self._reset_btn.clicked.connect(self._on_reset)
        btn_layout.addWidget(self._reset_btn)

        panel_layout.addLayout(btn_layout)
        panel_layout.addStretch()

        main_layout.addWidget(panel)

        # 初始加载
        self._load_values()

    def _update_detector_from_config(self) -> None:
        cfg = self._app_config.color_ring
        for key, value in cfg.items():
            if hasattr(self._detector, key):
                setattr(self._detector, key, value)

    def _load_values(self) -> None:
        cfg = self._app_config.color_ring
        for panel in self._group_panels.values():
            values = {key: cfg.get(key, 0) for key in panel.keys()}
            panel.set_values(values)

    def _store_values(self) -> None:
        cfg = self._app_config.color_ring
        for panel in self._group_panels.values():
            for key, value in panel.get_values().items():
                param = self._schema.get_param(key)
                if param is not None and param.param_type == "int":
                    value = int(value)
                cfg[key] = value
                if hasattr(self._detector, key):
                    setattr(self._detector, key, value)

    def _on_slider_changed(self, _key: str, _value: float) -> None:
        self._store_values()
        self._preview_timer.stop()
        self._preview_timer.start(300)

    def _on_frame_received(self, frame: np.ndarray) -> None:
        self._latest_frame = frame
        self._video_preview.set_frame(frame)
        if not self._preview_timer.isActive():
            self._update_preview()

    def _update_preview(self) -> None:
        frame = self._latest_frame
        if frame is None:
            return

        detector = self._detector

        def _process() -> tuple[np.ndarray, np.ndarray, Optional[list[tuple[int, int, int]]]]:
            binary = _sync_binarize(detector, frame)
            circles = _sync_get_circles(detector, binary)
            overlay = _draw_circle_overlay(frame, circles)
            binary_bgr = cv2.cvtColor(binary, cv2.COLOR_GRAY2BGR)
            return overlay, binary_bgr, circles

        future = self._executor.submit(_process)

        def _on_done(_future) -> None:
            try:
                overlay, binary_bgr, circles = _future.result()
                self._preview_ready.emit(overlay, binary_bgr, circles)
            except Exception as e:
                _log.error(f"色环预览计算失败: {e}")

        future.add_done_callback(_on_done)

    def _on_preview_ready(
        self,
        overlay: np.ndarray,
        binary_bgr: np.ndarray,
        circles: Optional[list[tuple[int, int, int]]],
    ) -> None:
        self._video_preview.set_frame(overlay)
        self._mask_preview.set_frame(binary_bgr)

        if circles:
            centers = ", ".join(f"({x}, {y})" for x, y, _ in circles)
            self._info_label.setText(f"检测到 {len(circles)} 个圆: {centers}")
        else:
            self._info_label.setText("未检测到色环")

    def _on_save(self) -> None:
        self._store_values()
        if self._config_bridge.save():
            self._info_label.setText("配置已保存到 config.yaml")
        else:
            self._info_label.setText("保存失败")

    def _on_reset(self) -> None:
        self._config_bridge.reset_to_default()
        self._app_config = self._config_bridge.config
        self._update_detector_from_config()
        self._load_values()
        self._info_label.setText("已恢复默认配置")

    def closeEvent(self, event) -> None:  # type: ignore[override]
        self._executor.shutdown(wait=False)
        event.accept()
