"""
Copyright (C) 2025 IVEN-CN(He Yunfeng)

GC2026 桌面调参应用 - 通用 Detector 调参页面
====
根据 DetectorSchema 自动渲染参数滑条，支持：
- color-tabs 布局（颜色检测）
- group-tabs 布局（色环检测）
- flat 单面板布局

左侧上下堆叠显示 overlay / binary 预览，右侧为调参面板。
所有参数读写与预览生成均通过 detector 的通用接口完成，UI 不感知具体参数结构。
"""

from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Optional

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

from app.core.config_bridge import AppConfig, ConfigBridge
from app.core.frame_source_manager import FrameSourceManager
from app.ui.theme import AppTheme
from app.ui.widgets.parameter_group_panel import ParameterGroupPanel
from detector.Detect import Detect
from detector.schema import DetectorSchema, ParamDef

_log = logger.bind(module="DetectorTunerScreen")


def _cv_to_pixmap(frame: np.ndarray) -> QPixmap:
    """OpenCV BGR 帧转 QPixmap。"""
    rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    h, w, ch = rgb.shape
    bytes_per_line = ch * w
    image = QImage(rgb.data, w, h, bytes_per_line, QImage.Format.Format_RGB888)
    return QPixmap.fromImage(image)


def _sync_detect(detector: Detect, frame: np.ndarray) -> tuple[Any, np.ndarray]:
    """在线程池中同步运行 detector.detect(frame)。"""
    coro = detector.detect(frame)
    try:
        loop = asyncio.new_event_loop()
        return loop.run_until_complete(coro)
    finally:
        loop.close()


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


class DetectorTunerScreen(QWidget):
    """通用 detector 调参页面。"""

    _preview_ready = pyqtSignal(np.ndarray, np.ndarray)
    _info_ready = pyqtSignal(object)

    def __init__(
        self,
        detector_cls: type[Detect],
        title: str,
        config_bridge: ConfigBridge,
        frame_source_manager: FrameSourceManager,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self._title = title
        self._config_bridge = config_bridge
        self._frame_source_manager = frame_source_manager
        self._app_config = config_bridge.config

        self._detector = detector_cls()
        self._schema = self._detector.tunable_schema()
        self._detector.load_tunable_from_app_config(self._app_config)

        self._current_section: Optional[str] = None
        self._panels: dict[str, ParameterGroupPanel] = {}

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

    # ------------------------------------------------------------------
    # UI 构建
    # ------------------------------------------------------------------
    def _build_ui(self) -> None:
        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(20, 20, 20, 20)
        main_layout.setSpacing(20)

        # 左侧预览区
        preview_area = QVBoxLayout()
        preview_area.setSpacing(12)

        self._overlay_preview = VideoPreview()
        self._overlay_preview.setText("等待图传画面")
        preview_area.addWidget(self._overlay_preview, stretch=1)

        self._binary_preview = VideoPreview()
        self._binary_preview.setText("二值化预览")
        preview_area.addWidget(self._binary_preview, stretch=1)

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

        title = QLabel(self._title)
        title.setStyleSheet(
            f"color: {AppTheme.colors.foreground_primary}; font-size: 22px; font-weight: 600;"
        )
        panel_layout.addWidget(title)

        self._tabs = QTabWidget()
        self._tabs.setDocumentMode(True)
        self._tabs.currentChanged.connect(self._on_tab_changed)
        self._build_param_tabs()
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

        # 初始加载当前 tab 的值
        self._load_current_tab_values()

    def _build_param_tabs(self) -> None:
        """根据 schema 布局构建 Tab。"""
        if self._schema.color_groups:
            self._build_color_tabs()
        elif self._schema.groups:
            self._build_group_tabs()
        else:
            self._build_flat_tab()

    def _make_panel(
        self, params: list[ParamDef], section: Optional[str] = None
    ) -> ParameterGroupPanel:
        panel = ParameterGroupPanel(params)
        panel.value_changed.connect(
            lambda key, _value, sec=section: self._on_slider_changed(key, sec)
        )
        return panel

    def _build_color_tabs(self) -> None:
        """颜色检测：R/G/B + 全局。"""
        for color in self._schema.color_groups or []:
            params = self._schema.params_by_section(color)
            panel = self._make_panel(params, section=color)
            self._panels[color] = panel
            self._tabs.addTab(panel, color)

        global_params = self._schema.global_params()
        if global_params:
            panel = self._make_panel(global_params, section="global")
            self._panels["global"] = panel
            self._tabs.addTab(panel, "全局")

        self._current_section = self._schema.color_groups[0] if self._schema.color_groups else "global"

    def _build_group_tabs(self) -> None:
        """色环检测：按 group 分 Tab。"""
        grouped = self._schema.params_by_group()
        for group in self._schema.groups or []:
            params = grouped.get(group, [])
            if not params:
                continue
            panel = self._make_panel(params, section=None)
            self._panels[group] = panel
            self._tabs.addTab(panel, group)

        self._current_section = self._schema.groups[0] if self._schema.groups else None

    def _build_flat_tab(self) -> None:
        """无分组：单面板。"""
        params = self._schema.params
        if params:
            panel = self._make_panel(params, section=None)
            self._panels["flat"] = panel
            self._tabs.addTab(panel, "参数")
        self._current_section = "flat"

    # ------------------------------------------------------------------
    # 参数加载与保存
    # ------------------------------------------------------------------
    def _section_key(self, index: int) -> Optional[str]:
        """根据 tab index 返回当前 section key。"""
        if self._schema.color_groups:
            groups = list(self._schema.color_groups or []) + (
                ["global"] if self._schema.global_params() else []
            )
            return groups[index] if index < len(groups) else None
        if self._schema.groups:
            return self._schema.groups[index] if index < len(self._schema.groups) else None
        return "flat"

    def _load_current_tab_values(self) -> None:
        section = self._current_section
        panel = self._panels.get(section)
        if panel is None:
            return

        values: dict[str, Any] = {}
        for param in self._params_for_section(section):
            values[param.key] = self._detector.get_tunable_value(param.key, section=section)
        panel.set_values(values)

    def _store_current_tab_values(self) -> None:
        section = self._current_section
        panel = self._panels.get(section)
        if panel is None:
            return

        for key, value in panel.get_values().items():
            self._detector.set_tunable_value(key, value, section=section)

        # 颜色检测：更新当前工作颜色到类属性
        if self._schema.color_groups and section in self._schema.color_groups:
            self._detector.update_threshold(section)

    def _params_for_section(self, section: Optional[str]) -> list[ParamDef]:
        if self._schema.color_groups:
            if section == "global":
                return self._schema.global_params()
            return self._schema.params_by_section(section or "")
        if self._schema.groups:
            return self._schema.params_by_group().get(section or "", [])
        return self._schema.params

    def _on_tab_changed(self, index: int) -> None:
        new_section = self._section_key(index)
        if new_section == self._current_section:
            return

        # 切出前保存当前标签的值
        self._store_current_tab_values()

        self._current_section = new_section
        self._load_current_tab_values()

        # 颜色检测：切到某个颜色时同步更新 detector 工作属性
        if self._schema.color_groups and new_section in self._schema.color_groups:
            self._detector.update_threshold(new_section)

    def _on_slider_changed(self, _key: str, section: Optional[str]) -> None:
        self._store_current_tab_values()
        self._preview_timer.stop()
        self._preview_timer.start(300)

    def _on_save(self) -> None:
        self._store_current_tab_values()
        self._detector.save_tunable_to_app_config(self._app_config)
        if self._config_bridge.save():
            self._info_label.setText("配置已保存到 config.yaml")
        else:
            self._info_label.setText("保存失败")

    def _on_reset(self) -> None:
        self._config_bridge.reset_to_default()
        self._app_config = self._config_bridge.config
        self._detector.load_tunable_from_app_config(self._app_config)
        self._load_current_tab_values()
        self._info_label.setText("已恢复默认配置")

    # ------------------------------------------------------------------
    # 预览
    # ------------------------------------------------------------------
    def _on_frame_received(self, frame: np.ndarray) -> None:
        self._latest_frame = frame
        if not self._preview_timer.isActive():
            self._update_preview()

    def _update_preview(self) -> None:
        frame = self._latest_frame
        if frame is None:
            return

        detector = self._detector

        def _process() -> tuple[np.ndarray, np.ndarray, Any]:
            result, binary = _sync_detect(detector, frame)
            overlay = detector.draw_overlay(frame, result, binary)
            return overlay, binary, result

        future = self._executor.submit(_process)

        def _on_done(_future) -> None:
            try:
                overlay, binary, result = _future.result()
                self._preview_ready.emit(overlay, binary)
                self._info_ready.emit(result)
            except Exception as e:
                _log.error(f"预览计算失败: {e}")

        future.add_done_callback(_on_done)

    def _on_preview_ready(self, overlay: np.ndarray, binary: np.ndarray) -> None:
        self._overlay_preview.set_frame(overlay)
        if binary.ndim == 2:
            binary_bgr = cv2.cvtColor(binary, cv2.COLOR_GRAY2BGR)
        else:
            binary_bgr = binary
        self._binary_preview.set_frame(binary_bgr)

    def _on_info_ready(self, result: Any) -> None:
        self._info_label.setText(self._detector.format_detection_info(result))

    def closeEvent(self, event) -> None:  # type: ignore[override]
        self._executor.shutdown(wait=False)
        event.accept()
