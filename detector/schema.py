"""
Copyright (C) 2025 IVEN-CN(He Yunfeng)

GC2026 桌面调参应用 - Detector 可调参数 Schema
====
定义 detector 与调参 UI 之间的契约：
- detector 类通过 TUNABLE_PARAMS 声明哪些参数可被调节
- UI 根据该声明自动渲染滑条、分组、Tab
- ConfigBridge 可据此推导默认配置

Schema 是纯数据，不依赖 PyQt，因此 detector 模块可以直接引用。
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Any, Literal, Optional


@dataclass
class ParamDef:
    """单个可调参数的定义。

    字段说明:
        key: 参数在 detector 实例上的属性名，也是配置文件的 key。
        label: 在 UI 上显示的中文名称。
        param_type: 参数类型，"int" 或 "float"。
        min: 最小值（UI 显示值）。
        max: 最大值（UI 显示值）。
        step: 滑条/数值框的步长（UI 值单位）。
        decimals: 浮点数保留小数位，仅 param_type="float" 时有效。
        odd_only: 是否强制为奇数（如卷积核大小）。
        scale: UI 值与实际值的缩放因子，real_value = ui_value * scale。
        group: 色环调参中的分组名（如 "预处理"），颜色检测中不使用。
        section: 颜色检测中的段落标记："global" 表示全局参数，否则为颜色名。
    """

    key: str
    label: str
    param_type: Literal["int", "float"]
    min: float
    max: float
    step: float = 1.0
    decimals: int = 0
    odd_only: bool = False
    scale: float = 1.0
    group: Optional[str] = None
    section: Optional[str] = None

    def __post_init__(self) -> None:
        if self.param_type == "int" and self.decimals != 0:
            raise ValueError(f"整数参数 {self.key} 的 decimals 必须为 0")
        if self.odd_only and self.param_type != "int":
            raise ValueError(f"odd_only 只对整数参数有效: {self.key}")
        if self.scale <= 0:
            raise ValueError(f"scale 必须大于 0: {self.key}")

    def to_ui_value(self, real_value: float) -> float:
        """实际值转换为 UI 显示值。"""
        ui_value = real_value / self.scale
        if self.param_type == "int":
            ui_value = int(round(ui_value))
        return ui_value

    def to_real_value(self, ui_value: float) -> float:
        """UI 显示值转换为实际值。"""
        real_value = ui_value * self.scale
        if self.param_type == "int":
            real_value = int(round(real_value))
        return real_value

    def clamp(self, ui_value: float) -> float:
        """将 UI 值限制在合法范围内。"""
        value = max(self.min, min(self.max, ui_value))
        if self.param_type == "int":
            value = int(round(value))
        return value


@dataclass
class DetectorSchema:
    """一个 detector 的可调参数集合。

    字段说明:
        name: 配置文件中对应的顶层 key，如 "color" / "color_ring"。
        params: 非按颜色分组的参数定义（如色环参数、颜色检测的全局参数）。
        color_groups: 颜色检测专用，表示有哪些颜色分组（如 ["R", "G", "B"]）。
        color_group_params: 颜色检测专用，会在每个 color_group 中复制一份的参数模板。
        groups: 色环调参专用，表示分组 Tab 的顺序（如 ["预处理", "霍夫检测", "后处理"]）。
    """

    name: str
    params: list[ParamDef] = field(default_factory=list)
    color_groups: Optional[list[str]] = None
    color_group_params: list[ParamDef] = field(default_factory=list)
    groups: Optional[list[str]] = None

    def all_params(self) -> list[ParamDef]:
        """展开 color_group_params 后返回所有参数定义。"""
        result = list(self.params)
        for color in self.color_groups or []:
            for p in self.color_group_params:
                result.append(replace(p, section=color))
        return result

    def params_by_key(self) -> dict[str, ParamDef]:
        """以 key 为索引返回参数定义（不区分 section/group）。"""
        return {p.key: p for p in self.all_params()}

    def params_by_group(self) -> dict[str, list[ParamDef]]:
        """按 group 分组返回参数定义。"""
        result: dict[str, list[ParamDef]] = {}
        for p in self.params:
            group = p.group or ""
            result.setdefault(group, []).append(p)
        return result

    def params_by_section(self, section: str) -> list[ParamDef]:
        """返回属于指定 section 的参数（颜色检测用）。"""
        return [p for p in self.all_params() if p.section == section]

    def global_params(self) -> list[ParamDef]:
        """返回颜色检测中的全局参数（section == "global"）。"""
        return [p for p in self.params if p.section == "global"]

    def get_param(self, key: str, section: Optional[str] = None) -> Optional[ParamDef]:
        """根据 key 查找参数定义；可额外指定 section。"""
        for p in self.all_params():
            if p.key == key and (section is None or p.section == section):
                return p
        return None


def get_class_default(cls: type, key: str) -> Any:
    """从类属性上读取默认值；如果不存在则返回 None。"""
    return getattr(cls, key, None)
