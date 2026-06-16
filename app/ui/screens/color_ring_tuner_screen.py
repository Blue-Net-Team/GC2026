"""
Copyright (C) 2025 IVEN-CN(He Yunfeng)

GC2026 桌面调参应用 - 色环调参页面
====
左侧显示实时原图与霍夫圆检测预览，右侧提供预处理/霍夫检测/后处理参数分组滑动条。
直接复用 detector.ColorRingDetect.ColorRingDetector 的识别逻辑。
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
    QDoubleSpinBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSlider,
    QSpinBox,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)
from loguru import logger

from app.core.config_bridge import AppConfig, ConfigBridge
from app.core.frame_source_manager import FrameSourceManager
from app.ui.theme import AppTheme
from detector.ColorRingDetect import ColorRingDetector

_log = logger.bind(module="ColorRingTunerScreen")


def _cv_to_pixmap(frame: np.ndarray) -> QPixmap:
    """OpenCV BGR 帧转 QPixmap"""
    rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    h, w, ch = rgb.shape
    bytes_per_line = ch * w
    image = QImage(rgb.data, w, h, bytes_per_line, QImage.Format.Format_RGB888)
    return QPixmap.fromImage(image)


class VideoPreview(QLabel):
    """等比缩放、完整显示的视频预览标签"""

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


class AdvancedParamSlider(QWidget):
    """通用参数滑动条：支持整数/浮点数、步长、奇数约束"""

    value_changed = pyqtSignal(float)

    def __init__(
        self,
        name: str,
        min_val: float,
        max_val: float,
        decimals: int = 0,
        step: float = 1.0,
        odd_only: bool = False,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self._decimals = decimals
        self._factor = 10**decimals
        self._odd_only = odd_only
        self._step = step

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        header = QHBoxLayout()
        self._label = QLabel(name)
        self._label.setStyleSheet(
            f"color: {AppTheme.colors.foreground_secondary}; font-size: 13px;"
        )
        header.addWidget(self._label)

        if decimals > 0:
            self._spin = QDoubleSpinBox()
            self._spin.setDecimals(decimals)
            self._spin.setSingleStep(step)
            self._spin.setRange(min_val, max_val)
        else:
            self._spin = QSpinBox()
            self._spin.setSingleStep(int(step))
            self._spin.setRange(int(min_val), int(max_val))

        self._spin.setFixedWidth(80)
        self._spin.setButtonSymbols(QSpinBox.ButtonSymbols.NoButtons)
        self._spin.valueChanged.connect(self._on_spin_changed)
        header.addWidget(self._spin)

        layout.addLayout(header)

        slider_min = int(min_val * self._factor)
        slider_max = int(max_val * self._factor)
        slider_step = max(1, int(step * self._factor))

        self._slider = QSlider(Qt.Orientation.Horizontal)
        self._slider.setRange(slider_min, slider_max)
        self._slider.setSingleStep(slider_step)
        self._slider.setPageStep(slider_step * 5)
        self._slider.setTracking(False)
        self._slider.valueChanged.connect(self._on_slider_changed)
        layout.addWidget(self._slider)

    def _to_real(self, slider_value: int) -> float:
        real = slider_value / self._factor
        if self._decimals == 0:
            real = int(real)
        if self._odd_only and isinstance(real, int):
            if real % 2 == 0:
                real = max(1, real + 1)
        return real

    def _to_slider(self, real_value: float) -> int:
        if self._odd_only:
            v = int(real_value)
            if v % 2 == 0:
                v = max(1, v + 1)
            return int(v * self._factor)
        return int(round(real_value * self._factor))

    def _set_spin_value(self, value: float) -> None:
        if isinstance(self._spin, QSpinBox):
            self._spin.setValue(int(value))
        else:
            self._spin.setValue(value)

    def _spin_value(self) -> float:
        return float(self._spin.value())

    def _on_slider_changed(self, value: int) -> None:
        real = self._to_real(value)
        self._spin.blockSignals(True)
        self._set_spin_value(real)
        self._spin.blockSignals(False)
        self.value_changed.emit(float(real))

    def _on_spin_changed(self, value: float) -> None:
        if self._odd_only:
            v = int(value)
            if v % 2 == 0:
                v = max(1, v + 1)
                self._spin.blockSignals(True)
                self._set_spin_value(v)
                self._spin.blockSignals(False)
                value = v
        slider_value = self._to_slider(value)
        self._slider.blockSignals(True)
        self._slider.setValue(slider_value)
        self._slider.blockSignals(False)
        self.value_changed.emit(float(value))

    def value(self) -> float:
        return self._spin_value()

    def set_value(self, value: float) -> None:
        if self._odd_only:
            v = int(value)
            if v % 2 == 0:
                v = max(1, v + 1)
            value = float(v)
        self._spin.blockSignals(True)
        self._set_spin_value(value)
        self._spin.blockSignals(False)
        self._slider.blockSignals(True)
        self._slider.setValue(self._to_slider(value))
        self._slider.blockSignals(False)


class ColorRingTunerScreen(QWidget):
    """色环调参页面"""

    _preview_ready = pyqtSignal(np.ndarray, object)

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

        # 参数分组 Tab
        self._tabs = QTabWidget()
        self._tabs.setDocumentMode(True)
        self._tabs.setElideMode(Qt.TextElideMode.ElideNone)
        self._tabs.tabBar().setExpanding(False)

        self._sliders: dict[str, AdvancedParamSlider] = {}

        preprocess_tab = self._build_group_tab(
            [
                ("erode_iter", "腐蚀迭代", 0, 10, 0, 1, False),
                ("dilate_kernel_size", "膨胀核大小", 3, 15, 0, 2, True),
                ("clahe_clip_limit", "CLAHE 限制", 0.5, 5.0, 1, 0.1, False),
                ("clahe_tile_size", "CLAHE 网格", 2, 16, 0, 1, False),
            ]
        )
        self._tabs.addTab(preprocess_tab, "预处理")

        hough_tab = self._build_group_tab(
            [
                ("hough_dp", "霍夫分辨率", 0.5, 2.0, 1, 0.1, False),
                ("hough_min_dist", "圆心最小距", 10, 200, 0, 1, False),
                ("hough_param1", "Canny 阈值", 10, 200, 0, 1, False),
                ("hough_param2", "累加器阈值", 10, 200, 0, 1, False),
                ("min_radius", "最小半径", 10, 300, 0, 1, False),
                ("max_radius", "最大半径", 50, 500, 0, 1, False),
                ("expected_circles", "期望圆数", 1, 10, 0, 1, False),
            ]
        )
        self._tabs.addTab(hough_tab, "霍夫检测")

        postprocess_tab = self._build_group_tab(
            [
                ("morph_kernel_size", "形态学核", 3, 15, 0, 2, True),
                ("gaussian_kernel_size", "高斯核", 3, 21, 0, 2, True),
                ("gaussian_sigma", "高斯 sigma", 0.5, 5.0, 1, 0.1, False),
                ("alpha", "对比度增强", 1.0, 10.0, 1, 0.1, False),
                ("threshold_value", "二值化阈值", 0, 255, 0, 1, False),
            ]
        )
        self._tabs.addTab(postprocess_tab, "后处理")

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

        self._deploy_btn = QPushButton("保存并部署")
        self._deploy_btn.setObjectName("secondary")
        self._deploy_btn.clicked.connect(self._on_deploy)
        btn_layout.addWidget(self._deploy_btn)

        self._reset_btn = QPushButton("恢复默认")
        self._reset_btn.setObjectName("secondary")
        self._reset_btn.clicked.connect(self._on_reset)
        btn_layout.addWidget(self._reset_btn)

        panel_layout.addLayout(btn_layout)
        panel_layout.addStretch()

        main_layout.addWidget(panel)

        # 初始加载
        self._load_values()

    def _build_group_tab(
        self,
        defs: list[tuple[str, str, float, float, int, float, bool]],
    ) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(0, 12, 0, 0)
        layout.setSpacing(12)

        for key, label, min_v, max_v, decimals, step, odd in defs:
            slider = AdvancedParamSlider(
                label, min_v, max_v, decimals=decimals, step=step, odd_only=odd
            )
            slider.value_changed.connect(self._on_slider_changed)
            self._sliders[key] = slider
            layout.addWidget(slider)

        layout.addStretch()
        return tab

    def _update_detector_from_config(self) -> None:
        cfg = self._app_config.color_ring
        for key, value in cfg.items():
            if hasattr(self._detector, key):
                setattr(self._detector, key, value)

    def _load_values(self) -> None:
        cfg = self._app_config.color_ring
        for key, slider in self._sliders.items():
            if key in cfg:
                slider.set_value(float(cfg[key]))

    def _store_values(self) -> None:
        cfg = self._app_config.color_ring
        for key, slider in self._sliders.items():
            real_value = slider.value()
            if slider._decimals == 0:
                real_value = int(real_value)
            cfg[key] = real_value
            if hasattr(self._detector, key):
                setattr(self._detector, key, real_value)

    def _on_slider_changed(self, _value: float) -> None:
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

        def _process() -> tuple[np.ndarray, Any]:
            try:
                loop = asyncio.new_event_loop()
                result, processed = loop.run_until_complete(detector.detect(frame))
                return processed, result
            finally:
                loop.close()

        future = self._executor.submit(_process)

        def _on_done(_future) -> None:
            try:
                processed, result = _future.result()
                self._preview_ready.emit(processed, result)
            except Exception as e:
                _log.error(f"色环预览计算失败: {e}")

        future.add_done_callback(_on_done)

    def _on_preview_ready(self, processed: np.ndarray, result: Any) -> None:
        self._mask_preview.set_frame(processed)

        if result:
            centers = ", ".join(f"({x}, {y})" for x, y in result)
            self._info_label.setText(f"检测到 {len(result)} 个圆: {centers}")
        else:
            self._info_label.setText("未检测到色环")

    def _on_save(self) -> None:
        self._store_values()
        if self._config_bridge.save():
            self._info_label.setText("配置已保存到 config.yaml")
        else:
            self._info_label.setText("保存失败")

    def _on_deploy(self) -> None:
        self._store_values()
        self._config_bridge.save()
        self._info_label.setText("本地已保存，SSH 部署待实现")

    def _on_reset(self) -> None:
        self._config_bridge.reset_to_default()
        self._app_config = self._config_bridge.config
        self._update_detector_from_config()
        self._load_values()
        self._info_label.setText("已恢复默认配置")

    def closeEvent(self, event) -> None:  # type: ignore[override]
        self._executor.shutdown(wait=False)
        event.accept()
