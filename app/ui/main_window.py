"""
Copyright (C) 2025 IVEN-CN(He Yunfeng)

GC2026 桌面调参应用 - 主窗口
====
包含左侧导航栏、主内容区、连接状态卡片，负责切换不同功能页面。
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from PyQt6.QtCore import Qt, pyqtSignal, QSize
from PyQt6.QtGui import QColor, QFont, QIcon, QPainter, QPixmap
from PyQt6.QtSvg import QSvgRenderer
from PyQt6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QSizePolicy,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)
from loguru import logger

from core.config_bridge import ConfigBridge
from app.core.device_store import DeviceStore
from app.core.frame_source_manager import FrameSourceManager
from app.ui.theme import AppTheme
from detector.ColorDetect import TraditionalColorDetector
from detector.ColorRingDetect import ColorRingDetector

_log = logger.bind(module="MainWindow")


# Detector 注册表：每个条目 = (detector 类, 页面标题, fallback 图标名, 图标文件名, 是否彩色图标)
DETECTOR_REGISTRY: list[tuple[type, str, str, str, bool]] = [
    (TraditionalColorDetector, "颜色调参", "palette", "RGB.svg", True),
    (ColorRingDetector, "色环调参", "donut_large", "圆环.svg", False),
]


class NavItem(QWidget):
    """侧边栏导航项"""

    clicked = pyqtSignal()

    def __init__(
        self,
        icon_text: str,
        label: str,
        icon_path: Optional[str | Path] = None,
        colored: bool = False,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self._active = False
        self._icon_text = icon_text
        self._icon_path = Path(icon_path) if icon_path else None
        self._colored = colored
        self._layout = QHBoxLayout(self)
        self._layout.setContentsMargins(14, 10, 14, 10)
        self._layout.setSpacing(12)

        self._icon = QLabel()
        self._icon.setFixedSize(24, 24)
        self._set_icon()

        self._label = QLabel(label)
        self._label.setStyleSheet(f"color: {AppTheme.colors.foreground_secondary};")

        self._layout.addWidget(self._icon)
        self._layout.addWidget(self._label)
        self._layout.addStretch()

        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.set_active(False)

    def _set_icon(self) -> None:
        if self._icon_path is not None and self._icon_path.exists():
            base = self._load_icon(self._icon_path)
            if self._colored:
                self._icon_normal = base
                self._icon_active = base
            else:
                self._icon_normal = self._tint_icon(base, AppTheme.colors.foreground_muted)
                self._icon_active = self._tint_icon(base, AppTheme.colors.foreground_primary)
            self._icon.setPixmap(self._icon_normal)
            self._icon.setStyleSheet("")
        else:
            self._icon_normal = None
            self._icon_active = None
            self._icon.setText(self._icon_text)
            self._icon.setFont(QFont("Material Symbols Outlined", 20))
            self._icon.setStyleSheet(f"color: {AppTheme.colors.foreground_muted};")

    def _load_icon(self, path: Path) -> QPixmap:
        suffix = path.suffix.lower()
        target = QSize(24, 24)
        if suffix == ".svg":
            pixmap = QPixmap(target)
            pixmap.fill(Qt.GlobalColor.transparent)
            renderer = QSvgRenderer(str(path))
            painter = QPainter(pixmap)
            renderer.render(painter)
            painter.end()
            return pixmap
        pixmap = QPixmap(str(path))
        if pixmap.isNull():
            return pixmap
        return pixmap.scaled(
            target,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )

    def _tint_icon(self, pixmap: QPixmap, color: str) -> QPixmap:
        tinted = QPixmap(pixmap.size())
        tinted.fill(Qt.GlobalColor.transparent)
        painter = QPainter(tinted)
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Source)
        painter.drawPixmap(0, 0, pixmap)
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceIn)
        painter.fillRect(tinted.rect(), QColor(color))
        painter.end()
        return tinted

    def set_active(self, active: bool) -> None:
        self._active = active
        c = AppTheme.colors
        if active:
            self.setStyleSheet(
                f"background-color: {c.surface_tertiary}; border-radius: {AppTheme.metrics.radius_md}px;"
            )
            if self._icon_active is not None:
                self._icon.setPixmap(self._icon_active)
            else:
                self._icon.setStyleSheet(f"color: {c.foreground_primary};")
            self._label.setStyleSheet(f"color: {c.foreground_primary};")
        else:
            self.setStyleSheet(
                f"background-color: transparent; border-radius: {AppTheme.metrics.radius_md}px;"
            )
            if self._icon_normal is not None:
                self._icon.setPixmap(self._icon_normal)
            else:
                self._icon.setStyleSheet(f"color: {c.foreground_muted};")
            self._label.setStyleSheet(f"color: {c.foreground_secondary};")

    def mousePressEvent(self, event) -> None:  # type: ignore[override]
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()

    def enterEvent(self, event) -> None:  # type: ignore[override]
        if not self._active:
            self.setStyleSheet(
                f"background-color: {AppTheme.colors.surface_secondary}; "
                f"border-radius: {AppTheme.metrics.radius_md}px;"
            )

    def leaveEvent(self, event) -> None:  # type: ignore[override]
        self.set_active(self._active)


class Sidebar(QWidget):
    """左侧导航栏"""

    screen_changed = pyqtSignal(int)

    def __init__(
        self,
        nav_items: list[tuple[str, str, Optional[str | Path], bool]],
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.setFixedWidth(AppTheme.metrics.sidebar_width)
        self.setStyleSheet(f"background-color: {AppTheme.colors.surface_secondary};")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(8)

        # Logo
        logo = QLabel("工创2026调参")
        logo.setStyleSheet(
            f"color: {AppTheme.colors.foreground_primary}; font-size: 20px; font-weight: 700; background-color: transparent;"
        )
        layout.addWidget(logo)

        sub_logo = QLabel("广东海洋大学蓝网科创定制")
        sub_logo.setStyleSheet(
            f"color: {AppTheme.colors.foreground_muted}; font-size: 11px; font-family: {AppTheme.fonts.mono}; background-color: transparent;"
        )
        layout.addWidget(sub_logo)

        divider = QFrame()
        divider.setFrameShape(QFrame.Shape.HLine)
        divider.setStyleSheet(f"background-color: {AppTheme.colors.border_subtle};")
        divider.setFixedHeight(1)
        layout.addWidget(divider)

        # 导航项
        self._nav_items: list[NavItem] = []
        for idx, (icon, label, icon_path, colored) in enumerate(nav_items):
            path = Path(icon_path) if icon_path else None
            item = NavItem(icon, label, icon_path=path, colored=colored)
            item.clicked.connect(lambda checked=False, i=idx: self._on_item_clicked(i))
            self._nav_items.append(item)
            layout.addWidget(item)

        layout.addStretch()

        # 连接状态卡片
        card = QFrame()
        card.setStyleSheet(
            f"background-color: {AppTheme.colors.surface_tertiary}; "
            f"border-radius: {AppTheme.metrics.radius_md}px;"
        )
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(12, 12, 12, 12)
        card_layout.setSpacing(8)

        conn_label = QLabel("连接状态")
        conn_label.setStyleSheet(
            f"color: {AppTheme.colors.foreground_muted}; font-size: 12px;"
        )
        card_layout.addWidget(conn_label)

        self._status_badge = QLabel("● 未连接")
        self._status_badge.setStyleSheet(
            f"color: {AppTheme.colors.foreground_secondary}; font-size: 11px; font-family: {AppTheme.fonts.mono};"
        )
        card_layout.addWidget(self._status_badge)

        self._device_label = QLabel("未选择设备")
        self._device_label.setStyleSheet(
            f"color: {AppTheme.colors.foreground_primary}; font-size: 13px;"
        )
        card_layout.addWidget(self._device_label)

        self._ip_label = QLabel("--")
        self._ip_label.setStyleSheet(
            f"color: {AppTheme.colors.foreground_muted}; font-size: 11px; font-family: {AppTheme.fonts.mono};"
        )
        card_layout.addWidget(self._ip_label)

        layout.addWidget(card)

    def _on_item_clicked(self, index: int) -> None:
        for i, item in enumerate(self._nav_items):
            item.set_active(i == index)
        self.screen_changed.emit(index)

    def set_active_screen(self, index: int) -> None:
        for i, item in enumerate(self._nav_items):
            item.set_active(i == index)

    def update_connection_status(
        self, status: str, device_name: str = "未选择设备", address: str = "--"
    ) -> None:
        color = AppTheme.colors.foreground_secondary
        if "已连接" in status:
            color = AppTheme.colors.accent_success
        elif "错误" in status:
            color = AppTheme.colors.accent_error
        elif "连接中" in status or "重连" in status or "检测中" in status:
            color = AppTheme.colors.accent_warning

        self._status_badge.setText(f"● {status}")
        self._status_badge.setStyleSheet(f"color: {color}; font-size: 11px;")
        self._device_label.setText(device_name)
        self._ip_label.setText(address)


class MainWindow(QMainWindow):
    """应用主窗口"""

    def __init__(
        self,
        config_bridge: ConfigBridge,
        frame_source_manager: FrameSourceManager,
        device_store: DeviceStore,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self._config_bridge = config_bridge
        self._frame_source_manager = frame_source_manager
        self._device_store = device_store
        self._device_connection_state = "未连接"

        self.setWindowTitle("工创2026调参")
        self.resize(1280, 800)
        self.setStyleSheet(f"background-color: {AppTheme.colors.surface_primary};")

        icon_path = Path(__file__).parent.parent / "resources" / "icons" / "icon.svg"
        if icon_path.exists():
            self.setWindowIcon(QIcon(str(icon_path)))

        central = QWidget()
        self.setCentralWidget(central)
        layout = QHBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        icon_dir = Path(__file__).parent.parent / "resources" / "icons"

        # 延迟导入页面，避免循环依赖
        from app.ui.screens.receiver_screen import ReceiverScreen
        from app.ui.screens.detector_tuner_screen import DetectorTunerScreen
        from app.ui.screens.log_screen import LogScreen
        from app.ui.screens.config_screen import ConfigScreen
        from app.ui.screens.service_screen import ServiceScreen

        # 静态页面
        self._receiver_screen = ReceiverScreen(frame_source_manager, device_store)
        self._log_screen = LogScreen(device_store)
        self._config_screen = ConfigScreen(device_store)
        self._service_screen = ServiceScreen(device_store)

        # 按注册表动态创建 detector 调参页面
        self._detector_screens: list[DetectorTunerScreen] = []
        for detector_cls, title, _icon, icon_file, colored in DETECTOR_REGISTRY:
            screen = DetectorTunerScreen(
                detector_cls, title, config_bridge, frame_source_manager
            )
            self._detector_screens.append(screen)

        # 构建导航项：静态页 + detector 页 + 其他静态页
        nav_items: list[tuple[str, str, Optional[str | Path], bool]] = [
            ("videocam", "图传接收", str(icon_dir / "图传.svg"), False),
        ]
        for _detector_cls, title, fallback_icon, icon_file, colored in DETECTOR_REGISTRY:
            icon_path = icon_dir / icon_file
            if not icon_path.exists():
                icon_path = None  # type: ignore[assignment]
            nav_items.append((fallback_icon, title, str(icon_path) if icon_path else None, colored))
        nav_items.extend([
            ("article", "日志", str(icon_dir / "日志.svg"), False),
            ("settings", "配置", str(icon_dir / "配置管理.svg"), False),
            ("build", "服务", str(icon_dir / "服务.svg"), False),
        ])

        # 侧边栏
        self._sidebar = Sidebar(nav_items)
        self._sidebar.screen_changed.connect(self._on_screen_changed)
        layout.addWidget(self._sidebar)

        # 主内容区
        self._stack = QStackedWidget()
        layout.addWidget(self._stack)

        self._stack.addWidget(self._receiver_screen)
        for screen in self._detector_screens:
            self._stack.addWidget(screen)
        self._stack.addWidget(self._log_screen)
        self._stack.addWidget(self._config_screen)
        self._stack.addWidget(self._service_screen)

        self._sidebar.set_active_screen(0)

        # 连接图像源状态变化
        self._frame_source_manager.state_changed.connect(self._on_source_state_changed)
        self._frame_source_manager.source_name_changed.connect(self._on_source_name_changed)
        self._frame_source_manager.device_connection_state_changed.connect(
            self._on_device_connection_state_changed
        )

    def _on_screen_changed(self, index: int) -> None:
        self._stack.setCurrentIndex(index)
        widget = self._stack.widget(index)
        if widget is self._config_screen:
            self._config_screen.refresh()
        elif widget is self._service_screen:
            self._service_screen.refresh_devices()

    def _on_device_connection_state_changed(self, state: str) -> None:
        self._device_connection_state = state
        self._update_sidebar_connection_status()

    def _on_source_state_changed(self, state: str) -> None:
        self._update_sidebar_connection_status()

    def _on_source_name_changed(self, name: str) -> None:
        if self._frame_source_manager.is_pinger_running():
            self._device_connection_state = "检测中"
        self._update_sidebar_connection_status()

    def _update_sidebar_connection_status(self) -> None:
        name = self._frame_source_manager.current_name
        address = "--"
        if name and name != "未连接" and not name.startswith("本地摄像头"):
            address = name

        if self._frame_source_manager.is_pinger_running():
            state = self._device_connection_state
        elif self._frame_source_manager.is_connected():
            state = "已连接"
        else:
            state = "未连接"

        self._sidebar.update_connection_status(state, device_name=name, address=address)

    def closeEvent(self, event) -> None:  # type: ignore[override]
        self._frame_source_manager.disconnect()
        event.accept()
