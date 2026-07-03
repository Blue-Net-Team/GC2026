"""
Copyright (C) 2025 IVEN-CN(He Yunfeng)

GC2026 桌面调参应用 - 通用参数滑条组件
====
由 app.core.param_schema.ParamDef 驱动，自动处理：
- int / float
- 小数位与步长
- 奇数约束（卷积核大小）
- UI 值与实际值的 scale 缩放
"""

from __future__ import annotations

from typing import Optional

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QDoubleSpinBox,
    QHBoxLayout,
    QLabel,
    QSlider,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from detector.schema import ParamDef


class ParamSlider(QWidget):
    """由 ParamDef 驱动的通用参数滑条：标签 + 数值框 + 滑动条。

    对外接口全部使用实际值（real value），内部自动转换为 UI 值。
    """

    value_changed = pyqtSignal(float)

    def __init__(self, param: ParamDef, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._param = param

        if param.odd_only and param.scale != 1.0:
            raise ValueError(f"odd_only 参数不允许 scale != 1: {param.key}")

        self._factor = 10**param.decimals

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        # 顶部：标签 + 数值框
        header = QHBoxLayout()
        self._label = QLabel(param.label)
        self._label.setStyleSheet("font-size: 13px;")
        header.addWidget(self._label)

        if param.param_type == "float":
            self._spin = QDoubleSpinBox()
            self._spin.setDecimals(param.decimals)
            self._spin.setSingleStep(param.step)
            self._spin.setRange(param.min, param.max)
        else:
            self._spin = QSpinBox()
            self._spin.setSingleStep(int(max(1, param.step)))
            self._spin.setRange(int(param.min), int(param.max))

        self._spin.setFixedWidth(80)
        self._spin.setButtonSymbols(QSpinBox.ButtonSymbols.NoButtons)
        self._spin.valueChanged.connect(self._on_spin_changed)
        header.addWidget(self._spin)
        layout.addLayout(header)

        # 滑动条：内部以 UI 值 * factor 表示
        slider_min = int(param.min * self._factor / param.scale)
        slider_max = int(param.max * self._factor / param.scale)
        slider_step = max(1, int(param.step * self._factor / param.scale))

        self._slider = QSlider(Qt.Orientation.Horizontal)
        self._slider.setRange(slider_min, slider_max)
        self._slider.setSingleStep(slider_step)
        self._slider.setPageStep(slider_step * 5)
        self._slider.setTracking(False)
        self._slider.valueChanged.connect(self._on_slider_changed)
        self._slider.sliderMoved.connect(self._on_slider_moved)
        layout.addWidget(self._slider)

    # ------------------------------------------------------------------
    # 数值转换
    # ------------------------------------------------------------------
    def _to_real(self, slider_value: int) -> float:
        """slider 内部值 -> 实际值。"""
        ui_value = slider_value / self._factor
        real_value = ui_value * self._param.scale
        if self._param.param_type == "int":
            real_value = int(round(real_value))
        if self._param.odd_only:
            real_value = self._make_odd(int(real_value))
        return real_value

    def _to_slider(self, real_value: float) -> int:
        """实际值 -> slider 内部值。"""
        if self._param.odd_only:
            real_value = self._make_odd(int(real_value))
        ui_value = real_value / self._param.scale
        return int(round(ui_value * self._factor))

    @staticmethod
    def _make_odd(value: int) -> int:
        """确保值为正奇数。"""
        if value < 1:
            return 1
        return value if value % 2 == 1 else value + 1

    def _set_spin(self, real_value: float) -> None:
        """将实际值显示到数值框（已考虑 scale）。"""
        ui_value = real_value / self._param.scale
        if self._param.param_type == "int":
            self._spin.setValue(int(round(ui_value)))
        else:
            self._spin.setValue(ui_value)

    # ------------------------------------------------------------------
    # 事件处理
    # ------------------------------------------------------------------
    def _on_slider_moved(self, slider_value: int) -> None:
        """拖动过程中实时更新数值框并触发预览（由上层防抖）。"""
        real_value = self._to_real(slider_value)
        self._spin.blockSignals(True)
        self._set_spin(real_value)
        self._spin.blockSignals(False)
        self.value_changed.emit(float(real_value))

    def _on_slider_changed(self, slider_value: int) -> None:
        """释放滑条时同步数值框并触发保存/预览。"""
        real_value = self._to_real(slider_value)
        self._spin.blockSignals(True)
        self._set_spin(real_value)
        self._spin.blockSignals(False)
        self.value_changed.emit(float(real_value))

    def _on_spin_changed(self, ui_value: float) -> None:
        """数值框变化时同步 slider 并触发保存/预览。"""
        real_value = ui_value * self._param.scale
        if self._param.param_type == "int":
            real_value = int(round(real_value))
        if self._param.odd_only:
            real_value = self._make_odd(int(real_value))
            # 若因奇数约束导致变化，回写数值框
            expected_ui = real_value / self._param.scale
            if abs(expected_ui - ui_value) > 1e-9:
                self._spin.blockSignals(True)
                if self._param.param_type == "int":
                    self._spin.setValue(int(round(expected_ui)))
                else:
                    self._spin.setValue(expected_ui)
                self._spin.blockSignals(False)

        slider_value = self._to_slider(real_value)
        self._slider.blockSignals(True)
        self._slider.setValue(slider_value)
        self._slider.blockSignals(False)
        self.value_changed.emit(float(real_value))

    # ------------------------------------------------------------------
    # 公共接口（均使用实际值）
    # ------------------------------------------------------------------
    def value(self) -> float:
        """返回当前实际值。"""
        ui_value = self._spin.value()
        real_value = ui_value * self._param.scale
        if self._param.param_type == "int":
            real_value = int(round(real_value))
        if self._param.odd_only:
            real_value = self._make_odd(int(real_value))
        return float(real_value)

    def set_value(self, real_value: float) -> None:
        """使用实际值设置显示。"""
        if self._param.param_type == "int":
            real_value = int(round(real_value))
        if self._param.odd_only:
            real_value = self._make_odd(int(real_value))

        self._spin.blockSignals(True)
        self._slider.blockSignals(True)
        self._set_spin(real_value)
        self._slider.setValue(self._to_slider(real_value))
        self._spin.blockSignals(False)
        self._slider.blockSignals(False)

    def param_key(self) -> str:
        """返回参数 key。"""
        return self._param.key
