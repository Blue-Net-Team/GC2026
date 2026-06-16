"""
Copyright (C) 2025 IVEN-CN(He Yunfeng)

GC2026 桌面调参应用 - 配置桥接
====
负责与 GC2026 的 config.yaml 格式保持兼容，提供颜色/色环参数的读写。
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

import yaml
from loguru import logger

_log = logger.bind(module="ConfigBridge")


DEFAULT_COLOR_PARAMS: dict[str, dict[str, int]] = {
    "R": {"centre": 0, "error": 12, "L_S": 41, "L_V": 29, "U_S": 255, "U_V": 255},
    "G": {"centre": 69, "error": 12, "L_S": 41, "L_V": 29, "U_S": 255, "U_V": 255},
    "B": {"centre": 108, "error": 12, "L_S": 41, "L_V": 29, "U_S": 255, "U_V": 255},
}

DEFAULT_COLOR_RING_PARAMS: dict[str, Any] = {
    "alpha": 4.4,
    "clahe_clip_limit": 1.2,
    "clahe_tile_size": 8,
    "dilate_kernel_size": 5,
    "erode_iter": 1,
    "expected_circles": 5,
    "gaussian_kernel_size": 9,
    "gaussian_sigma": 1.5,
    "hough_dp": 0.9,
    "hough_min_dist": 68,
    "hough_param1": 72,
    "hough_param2": 100,
    "max_radius": 281,
    "min_radius": 54,
    "morph_kernel_size": 3,
    "threshold_value": 34,
}


@dataclass
class ColorConfig:
    """颜色调参配置"""

    centre: int = 0
    error: int = 12
    L_S: int = 41
    U_S: int = 255
    L_V: int = 29
    U_V: int = 255

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ColorConfig":
        return cls(
            centre=int(data.get("centre", 0)),
            error=int(data.get("error", 12)),
            L_S=int(data.get("L_S", 41)),
            U_S=int(data.get("U_S", 255)),
            L_V=int(data.get("L_V", 29)),
            U_V=int(data.get("U_V", 255)),
        )

    def to_dict(self) -> dict[str, int]:
        return {
            "centre": self.centre,
            "error": self.error,
            "L_S": self.L_S,
            "U_S": self.U_S,
            "L_V": self.L_V,
            "U_V": self.U_V,
        }


@dataclass
class AppConfig:
    """应用运行时配置（与 GC2026 config.yaml 兼容）"""

    color: dict[str, ColorConfig] = field(
        default_factory=lambda: {
            name: ColorConfig.from_dict(params)
            for name, params in DEFAULT_COLOR_PARAMS.items()
        }
    )
    color_ring: dict[str, Any] = field(default_factory=lambda: copy.deepcopy(DEFAULT_COLOR_RING_PARAMS))
    min_material_area: int = 5940
    max_material_area: int = 300000
    need2cut_height: int = 0
    target_angle: int = 46

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "AppConfig":
        color_data = data.get("color", DEFAULT_COLOR_PARAMS)
        color = {
            name: ColorConfig.from_dict(color_data.get(name, DEFAULT_COLOR_PARAMS[name]))
            for name in ("R", "G", "B")
        }
        return cls(
            color=color,
            color_ring={**DEFAULT_COLOR_RING_PARAMS, **data.get("color_ring", {})},
            min_material_area=int(data.get("min_material_area", 5940)),
            max_material_area=int(data.get("max_material_area", 300000)),
            need2cut_height=int(data.get("need2cut_height", 0)),
            target_angle=int(data.get("target_angle", 46)),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "color": {name: cfg.to_dict() for name, cfg in self.color.items()},
            "color_ring": self.color_ring,
            "min_material_area": self.min_material_area,
            "max_material_area": self.max_material_area,
            "need2cut_height": self.need2cut_height,
            "target_angle": self.target_angle,
        }


class ConfigBridge:
    """配置桥接：加载/保存 GC2026 的 config.yaml"""

    def __init__(self, path: Optional[str | Path] = None) -> None:
        self.path = Path(path) if path else Path("config.yaml")
        self._config = AppConfig()
        self._loaded = False

    @property
    def config(self) -> AppConfig:
        return self._config

    def load(self, path: Optional[str | Path] = None) -> AppConfig:
        target = Path(path) if path else self.path
        if not target.exists():
            _log.warning(f"配置文件不存在: {target}，使用默认配置")
            self._config = AppConfig()
            self._loaded = True
            return self._config

        try:
            with open(target, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
            self._config = AppConfig.from_dict(data)
            self._loaded = True
            _log.info(f"已加载配置: {target}")
        except Exception as e:
            _log.error(f"加载配置失败: {e}")
            self._config = AppConfig()
            self._loaded = True

        return self._config

    def save(self, path: Optional[str | Path] = None) -> bool:
        target = Path(path) if path else self.path
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            with open(target, "w", encoding="utf-8") as f:
                yaml.safe_dump(
                    self._config.to_dict(),
                    f,
                    default_flow_style=False,
                    allow_unicode=True,
                    sort_keys=False,
                )
            _log.info(f"已保存配置: {target}")
            return True
        except Exception as e:
            _log.error(f"保存配置失败: {e}")
            return False

    def reset_to_default(self) -> None:
        self._config = AppConfig()
        _log.info("配置已恢复默认")
