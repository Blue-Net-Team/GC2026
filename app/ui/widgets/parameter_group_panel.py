"""
Copyright (C) 2025 IVEN-CN(He Yunfeng)

GC2026 桌面调参应用 - 参数分组面板
====
根据一组 ParamDef 自动渲染垂直排列的 ParamSlider，并提供批量读写能力。
"""

from __future__ import annotations

from typing import Optional

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import QVBoxLayout, QWidget

from detector.schema import ParamDef
from app.ui.widgets.param_slider import ParamSlider


class ParameterGroupPanel(QWidget):
    """参数分组面板：垂直排列一组由 ParamDef 定义的滑条。"""

    value_changed = pyqtSignal(str, float)

    def __init__(self, params: list[ParamDef], parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)

        self._sliders: dict[str, ParamSlider] = {}
        for param in params:
            slider = ParamSlider(param)
            slider.value_changed.connect(lambda v, k=param.key: self.value_changed.emit(k, v))
            self._sliders[param.key] = slider
            layout.addWidget(slider)

        layout.addStretch()

    def set_values(self, values: dict[str, float]) -> None:
        """批量设置实际值。"""
        for key, value in values.items():
            slider = self._sliders.get(key)
            if slider is not None:
                slider.set_value(value)

    def get_values(self) -> dict[str, float]:
        """批量读取实际值。"""
        return {key: slider.value() for key, slider in self._sliders.items()}

    def keys(self) -> list[str]:
        """返回当前面板管理的参数 key 列表。"""
        return list(self._sliders.keys())
