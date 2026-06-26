"""
Copyright (C) 2025 IVEN-CN(He Yunfeng)

GC2026 桌面调参应用 - 颜色调参页面
====
左侧显示实时原图与二值化 mask 预览，右侧基于 TraditionalColorDetector.TUNABLE_PARAMS
动态渲染 R/G/B 颜色参数与全局参数滑条。
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
from detector.ColorDetect import TraditionalColorDetector

_log = logger.bind(module="ColorTunerScreen")


def _sync_binarize(detector: TraditionalColorDetector, frame: np.ndarray) -> np.ndarray:
    """在线程池中运行异步二值化函数。"""
    coro = detector.binarization(frame)
    try:
        loop = asyncio.new_event_loop()
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def _sync_get_position(
    detector: TraditionalColorDetector, mask: np.ndarray
) -> Optional[tuple[int, int, int, int]]:
    """在线程池中运行异步位置检测函数。"""
    coro = detector.get_color_position(mask)
    try:
        loop = asyncio.new_event_loop()
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def _draw_detection_overlay(frame: np.ndarray, mask: np.ndarray) -> np.ndarray:
    """在原图上绘制检测到的物料外接矩形和中心点。"""
    output = frame.copy()
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if contours:
        largest = max(contours, key=cv2.contourArea)
        x, y, w, h = cv2.boundingRect(largest)
        cx, cy = x + w // 2, y + h // 2
        cv2.rectangle(output, (x, y), (x + w, y + h), (0, 255, 0), 2)
        cv2.circle(output, (cx, cy), 4, (0, 255, 0), -1)
    return output


def _cv_to_pixmap(frame: np.ndarray) -> QPixmap:
    """OpenCV BGR 帧转 QPixmap。"""
    rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    h, w, ch = rgb.shape
    bytes_per_line = ch * w
    image = QImage(rgb.data, w, h, bytes_per_line, QImage.Format.Format_RGB888)
    return QPixmap.fromImage(image)


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


class ColorTunerScreen(QWidget):
    """颜色调参页面。"""

    _preview_ready = pyqtSignal(np.ndarray, np.ndarray)
    _info_ready = pyqtSignal(object)

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

        self._schema = TraditionalColorDetector.TUNABLE_PARAMS
        self._current_color = self._schema.color_groups[0] if self._schema.color_groups else "R"
        self._detector = TraditionalColorDetector()
        self._update_detector_from_config()

        self._latest_frame: Optional[np.ndarray] = None
        self._executor = ThreadPoolExecutor(max_workers=2)

        # 300ms debounce 更新预览
        self._preview_timer = QTimer(self)
        self._preview_timer.setSingleShot(True)
        self._preview_timer.timeout.connect(self._update_preview)

        self._build_ui()

        self._frame_source_manager.frame_received.connect(self._on_frame_received)
        self._preview_ready.connect(self._on_preview_ready)
        self._info_ready.connect(self._on_info_ready)

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
        self._mask_preview.setText("二值化预览")
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

        title = QLabel("颜色调参")
        title.setStyleSheet(
            f"color: {AppTheme.colors.foreground_primary}; font-size: 22px; font-weight: 600;"
        )
        panel_layout.addWidget(title)

        # 颜色 Tab + 全局 Tab
        self._tabs = QTabWidget()
        self._tabs.setDocumentMode(True)
        self._tabs.currentChanged.connect(self._on_tab_changed)

        self._color_panels: dict[str, ParameterGroupPanel] = {}
        color_params = self._schema.color_group_params
        for color in self._schema.color_groups or []:
            # 为每个颜色创建独立的 ParamDef 副本（section 已在 schema 展开时设置）
            params = self._schema.params_by_section(color)
            group_panel = ParameterGroupPanel(params)
            group_panel.value_changed.connect(self._on_slider_changed)
            self._color_panels[color] = group_panel
            self._tabs.addTab(group_panel, color)

        global_params = self._schema.global_params()
        self._global_panel = ParameterGroupPanel(global_params)
        self._global_panel.value_changed.connect(self._on_slider_changed)
        self._tabs.addTab(self._global_panel, "全局")

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

        self._info_label = QLabel("未检测到目标")
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
        self._load_color_values(self._current_color)
        self._load_global_values()

    def _update_detector_from_config(self) -> None:
        for color in self._schema.color_groups or []:
            cfg = self._app_config.color[color]
            self._detector.color_threshold[color] = cfg.to_dict()
        self._detector.min_material_area = self._app_config.min_material_area
        self._detector.max_material_area = self._app_config.max_material_area
        self._detector.update_threshold(self._current_color)

    def _load_color_values(self, color: str) -> None:
        cfg = self._app_config.color[color]
        values = {key: getattr(cfg, key) for key in self._color_panels[color].keys()}
        self._color_panels[color].set_values(values)

    def _load_global_values(self) -> None:
        values = {
            "min_material_area": self._app_config.min_material_area,
            "max_material_area": self._app_config.max_material_area,
        }
        self._global_panel.set_values(values)

    def _store_color_values(self, color: str) -> None:
        cfg = self._app_config.color[color]
        values = self._color_panels[color].get_values()
        for key, value in values.items():
            setattr(cfg, key, int(value))
            self._detector.color_threshold[color][key] = int(value)
        self._detector.update_threshold(color)

    def _store_global_values(self) -> None:
        values = self._global_panel.get_values()
        self._app_config.min_material_area = int(values.get("min_material_area", 0))
        self._app_config.max_material_area = int(values.get("max_material_area", 0))
        self._detector.min_material_area = self._app_config.min_material_area
        self._detector.max_material_area = self._app_config.max_material_area

    def _on_tab_changed(self, index: int) -> None:
        colors = list(self._color_panels.keys()) + ["global"]
        new_section = colors[index]
        if new_section == self._current_color:
            return

        # 切出前保存当前标签的值
        if self._current_color in self._color_panels:
            self._store_color_values(self._current_color)
        elif self._current_color == "global":
            self._store_global_values()

        self._current_color = new_section

        # 切换 detector 到新的颜色
        if new_section in self._color_panels:
            self._detector.update_threshold(new_section)
            self._load_color_values(new_section)
        elif new_section == "global":
            self._load_global_values()

    def _on_slider_changed(self, _key: str, _value: float) -> None:
        if self._current_color in self._color_panels:
            self._store_color_values(self._current_color)
        elif self._current_color == "global":
            self._store_global_values()
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

        def _process() -> tuple[np.ndarray, np.ndarray]:
            mask = _sync_binarize(detector, frame)
            overlay = _draw_detection_overlay(frame, mask)
            mask_bgr = cv2.cvtColor(mask, cv2.COLOR_GRAY2BGR)
            return overlay, mask_bgr

        future = self._executor.submit(_process)

        def _on_done(_future) -> None:
            try:
                overlay, mask_bgr = _future.result()
                self._preview_ready.emit(overlay, mask_bgr)
            except Exception as e:
                _log.error(f"预览计算失败: {e}")

        future.add_done_callback(_on_done)

    def _on_preview_ready(self, overlay: np.ndarray, mask_bgr: np.ndarray) -> None:
        self._mask_preview.set_frame(mask_bgr)
        self._video_preview.set_frame(overlay)
        self._update_info(overlay)

    def _update_info(self, frame: np.ndarray) -> None:
        detector = self._detector

        def _get_pos() -> Optional[tuple[int, int, int, int]]:
            mask = _sync_binarize(detector, frame)
            return _sync_get_position(detector, mask)

        future = self._executor.submit(_get_pos)

        def _on_done(_future) -> None:
            try:
                pos = _future.result()
                self._info_ready.emit(pos)
            except Exception as e:
                _log.error(f"检测信息更新失败: {e}")
                self._info_ready.emit(None)

        future.add_done_callback(_on_done)

    def _on_info_ready(self, pos: Optional[tuple[int, int, int, int]]) -> None:
        if pos is None:
            self._info_label.setText("未检测到目标")
        else:
            cx, cy, w, h = pos
            self._info_label.setText(f"目标: ({cx}, {cy}) 外接矩形: {w}x{h}")

    def _on_save(self) -> None:
        if self._current_color in self._color_panels:
            self._store_color_values(self._current_color)
        elif self._current_color == "global":
            self._store_global_values()
        if self._config_bridge.save():
            self._info_label.setText("配置已保存到 config.yaml")
        else:
            self._info_label.setText("保存失败")

    def _on_reset(self) -> None:
        self._config_bridge.reset_to_default()
        self._app_config = self._config_bridge.config
        self._update_detector_from_config()
        self._load_color_values(self._current_color)
        self._load_global_values()
        self._info_label.setText("已恢复默认配置")

    def closeEvent(self, event) -> None:  # type: ignore[override]
        self._executor.shutdown(wait=False)
        event.accept()
