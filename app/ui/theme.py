"""
Copyright (C) 2025 IVEN-CN(He Yunfeng)

GC2026 桌面调参应用 - 单一深色主题系统
====
设计稿来源: docs/app.pen
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ThemeColors:
    """主题色板"""

    # 背景/表面色
    surface_primary: str = "#1E1E2E"
    surface_secondary: str = "#2A2A3C"
    surface_tertiary: str = "#35354A"
    surface_elevated: str = "#41415C"

    # 前景/文字色
    foreground_primary: str = "#FFFFFF"
    foreground_secondary: str = "#A0A0B0"
    foreground_muted: str = "#6E6E80"

    # 强调色
    accent_primary: str = "#4A9FD8"
    accent_secondary: str = "#5CE1E6"
    accent_success: str = "#4ADE80"
    accent_warning: str = "#FBBF24"
    accent_error: str = "#F87171"

    # 边框色
    border_primary: str = "#40405C"
    border_subtle: str = "#2E2E42"


@dataclass(frozen=True)
class ThemeMetrics:
    """主题尺寸与间距"""

    radius_sm: int = 4
    radius_md: int = 8

    spacing_xs: int = 4
    spacing_sm: int = 8
    spacing_md: int = 16
    spacing_lg: int = 24
    spacing_xl: int = 32

    sidebar_width: int = 220
    panel_width: int = 420


@dataclass(frozen=True)
class ThemeFonts:
    """主题字体族"""

    body: str = "Inter, Microsoft YaHei UI, PingFang SC, sans-serif"
    mono: str = "IBM Plex Mono, Consolas, Courier New, monospace"


class AppTheme:
    """应用单一深色主题"""

    colors = ThemeColors()
    metrics = ThemeMetrics()
    fonts = ThemeFonts()

    @classmethod
    def build_stylesheet(cls) -> str:
        """生成全局 QSS 样式表"""
        c = cls.colors
        m = cls.metrics
        f = cls.fonts

        return f"""
QWidget {{
    background-color: {c.surface_primary};
    color: {c.foreground_primary};
    font-family: {f.body};
    font-size: 14px;
    border: none;
}}

QLabel {{
    background-color: transparent;
    color: {c.foreground_primary};
}}

QPushButton {{
    background-color: {c.accent_primary};
    color: {c.foreground_primary};
    border: none;
    border-radius: {m.radius_md}px;
    padding: 10px 16px;
    font-weight: 500;
}}

QPushButton:hover {{
    background-color: {cls._lighten(c.accent_primary, 10)};
}}

QPushButton:pressed {{
    background-color: {cls._darken(c.accent_primary, 10)};
}}

QPushButton:disabled {{
    background-color: {c.surface_elevated};
    color: {c.foreground_muted};
}}

QPushButton#secondary {{
    background-color: transparent;
    color: {c.foreground_secondary};
    border: 1px solid {c.border_primary};
}}

QPushButton#secondary:hover {{
    background-color: {c.surface_tertiary};
    color: {c.foreground_primary};
}}

QLineEdit {{
    background-color: {c.surface_tertiary};
    color: {c.foreground_primary};
    border: 1px solid {c.border_primary};
    border-radius: {m.radius_md}px;
    padding: 8px 12px;
}}

QLineEdit:focus {{
    border: 1px solid {c.accent_primary};
}}

QSlider::groove:horizontal {{
    height: 6px;
    background-color: {c.surface_elevated};
    border-radius: 3px;
}}

QSlider::sub-page:horizontal {{
    background-color: {c.accent_primary};
    border-radius: 3px;
}}

QSlider::handle:horizontal {{
    background-color: {c.foreground_primary};
    width: 14px;
    height: 14px;
    margin: -4px 0;
    border-radius: 7px;
}}

QSlider::handle:horizontal:hover {{
    background-color: {c.accent_secondary};
}}

QSpinBox {{
    background-color: {c.surface_tertiary};
    color: {c.foreground_primary};
    border: 1px solid {c.border_primary};
    border-radius: {m.radius_sm}px;
    padding: 4px 8px;
}}

QTabWidget::pane {{
    border: none;
    background-color: transparent;
}}

QTabBar::tab {{
    background-color: transparent;
    color: {c.foreground_secondary};
    border: none;
    padding: 10px 16px;
    margin-right: 4px;
    border-radius: {m.radius_md}px;
}}

QTabBar::tab:selected {{
    background-color: {c.surface_tertiary};
    color: {c.foreground_primary};
}}

QTabBar::tab:hover:!selected {{
    background-color: {c.surface_secondary};
}}

QListWidget {{
    background-color: {c.surface_secondary};
    border: 1px solid {c.border_primary};
    border-radius: {m.radius_md}px;
    padding: 8px;
    outline: none;
}}

QListWidget::item {{
    padding: 10px 12px;
    border-radius: {m.radius_sm}px;
    color: {c.foreground_secondary};
}}

QListWidget::item:selected {{
    background-color: {c.surface_tertiary};
    color: {c.foreground_primary};
}}

QListWidget::item:hover {{
    background-color: {c.surface_tertiary};
}}

QScrollBar:vertical {{
    background-color: {c.surface_secondary};
    width: 8px;
    border-radius: 4px;
}}

QScrollBar::handle:vertical {{
    background-color: {c.surface_elevated};
    border-radius: 4px;
    min-height: 32px;
}}

QScrollBar::handle:vertical:hover {{
    background-color: {c.foreground_muted};
}}

QScrollBar::add-line:vertical,
QScrollBar::sub-line:vertical {{
    height: 0px;
}}
"""

    @staticmethod
    def _lighten(hex_color: str, percent: int) -> str:
        """简单提亮 HEX 颜色"""
        r = int(hex_color[1:3], 16)
        g = int(hex_color[3:5], 16)
        b = int(hex_color[5:7], 16)
        factor = 1 + percent / 100
        r = min(255, int(r * factor))
        g = min(255, int(g * factor))
        b = min(255, int(b * factor))
        return f"#{r:02x}{g:02x}{b:02x}"

    @staticmethod
    def _darken(hex_color: str, percent: int) -> str:
        """简单压暗 HEX 颜色"""
        r = int(hex_color[1:3], 16)
        g = int(hex_color[3:5], 16)
        b = int(hex_color[5:7], 16)
        factor = 1 - percent / 100
        r = max(0, int(r * factor))
        g = max(0, int(g * factor))
        b = max(0, int(b * factor))
        return f"#{r:02x}{g:02x}{b:02x}"
