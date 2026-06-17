"""
Copyright (C) 2025 IVEN-CN(He Yunfeng)
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QHeaderView,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMenu,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)
from loguru import logger

from app.core.device_store import DeviceStore, RemoteDevice
from app.core.ssh_worker import SshCommandWorker
from app.ui.theme import AppTheme

_log = logger.bind(module="ServiceScreen")

_SERVICES = (
    "run-main-auto.service",
    "gpio-setup.service",
    "ttys3-permission.service",
    "board_led_setup.service",
    "run-auto-shell-permission.service",
)

_DESCRIPTION_FALLBACK = {
    "run-main-auto.service": "主程序自动启动服务",
    "gpio-setup.service": "GPIO 初始化服务",
    "ttys3-permission.service": "ttyS3 串口权限设置",
    "board_led_setup.service": "板载 LED 状态灯服务",
    "run-auto-shell-permission.service": "自动脚本可执行权限设置",
}


class ServiceScreen(QWidget):
    """SSH 服务管理页面。"""

    def __init__(self, device_store: DeviceStore, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._device_store = device_store
        self._workers: set[SshCommandWorker] = set()
        self._descriptions = self._load_descriptions()
        self._service_to_row: dict[str, int] = {}

        self._build_ui()
        self._device_store.devices_changed.connect(self._refresh_device_combo)
        self._refresh_device_combo()

    # ------------------------------------------------------------------ UI
    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(16)

        # 顶部工具栏
        top_bar = QHBoxLayout()
        top_bar.setSpacing(12)

        title = QLabel("服务管理")
        title.setStyleSheet(
            f"color: {AppTheme.colors.foreground_primary}; font-size: 22px; font-weight: 600;"
        )
        top_bar.addWidget(title)
        top_bar.addStretch()

        self._device_combo = QComboBox()
        self._device_combo.setMinimumWidth(200)
        top_bar.addWidget(self._device_combo)

        self._refresh_btn = QPushButton("刷新状态")
        self._refresh_btn.setFixedWidth(100)
        self._refresh_btn.clicked.connect(self._on_refresh_all)
        top_bar.addWidget(self._refresh_btn)

        self._status_label = QLabel("就绪")
        self._status_label.setStyleSheet(
            f"color: {AppTheme.colors.foreground_muted}; font-size: 12px; font-family: {AppTheme.fonts.mono};"
        )
        top_bar.addWidget(self._status_label)

        layout.addLayout(top_bar)

        # 服务列表
        self._table = QTableWidget()
        self._table.setColumnCount(6)
        self._table.setHorizontalHeaderLabels(
            ["服务名", "Active", "Enabled", "Load", "描述", "操作"]
        )
        header = self._table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(5, QHeaderView.ResizeMode.Fixed)
        self._table.setColumnWidth(0, 200)
        self._table.setColumnWidth(5, 210)
        self._table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._table.customContextMenuRequested.connect(self._on_context_menu)
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._table.verticalHeader().setVisible(False)
        self._table.verticalHeader().setDefaultSectionSize(48)
        layout.addWidget(self._table, stretch=2)

        self._build_service_rows()

        # 操作输出区
        output_label = QLabel("操作输出")
        output_label.setStyleSheet(f"color: {AppTheme.colors.foreground_secondary}; font-size: 14px;")
        layout.addWidget(output_label)

        self._output_edit = QPlainTextEdit()
        self._output_edit.setReadOnly(True)
        self._output_edit.setLineWrapMode(QPlainTextEdit.LineWrapMode.WidgetWidth)
        layout.addWidget(self._output_edit, stretch=1)

        bottom_bar = QHBoxLayout()
        bottom_bar.addStretch()
        self._clear_btn = QPushButton("清空输出")
        self._clear_btn.setObjectName("secondary")
        self._clear_btn.clicked.connect(self._output_edit.clear)
        bottom_bar.addWidget(self._clear_btn)
        layout.addLayout(bottom_bar)

    def _build_service_rows(self) -> None:
        self._table.setRowCount(len(_SERVICES))
        for row, service in enumerate(_SERVICES):
            self._service_to_row[service] = row

            name_item = QTableWidgetItem(service)
            self._table.setItem(row, 0, name_item)

            self._table.setItem(row, 1, QTableWidgetItem("unknown"))
            self._table.setItem(row, 2, QTableWidgetItem("unknown"))
            self._table.setItem(row, 3, QTableWidgetItem("unknown"))

            desc_item = QTableWidgetItem(self._descriptions.get(service, ""))
            self._table.setItem(row, 4, desc_item)

            ops = QWidget()
            ops.setAutoFillBackground(False)
            ops.setStyleSheet("background-color: transparent;")
            ops_layout = QHBoxLayout(ops)
            ops_layout.setContentsMargins(6, 2, 6, 2)
            ops_layout.setSpacing(10)

            start_btn = QPushButton("启动")
            start_btn.setFixedSize(54, 26)
            start_btn.setStyleSheet(self._op_button_style())
            start_btn.clicked.connect(lambda _=False, s=service: self._on_action(s, "start"))

            stop_btn = QPushButton("停止")
            stop_btn.setFixedSize(54, 26)
            stop_btn.setStyleSheet(self._op_secondary_button_style())
            stop_btn.clicked.connect(lambda _=False, s=service: self._on_action(s, "stop"))

            restart_btn = QPushButton("重启")
            restart_btn.setFixedSize(54, 26)
            restart_btn.setStyleSheet(self._op_secondary_button_style())
            restart_btn.clicked.connect(lambda _=False, s=service: self._on_action(s, "restart"))

            ops_layout.addWidget(start_btn)
            ops_layout.addWidget(stop_btn)
            ops_layout.addWidget(restart_btn)
            ops_layout.addStretch()
            self._table.setCellWidget(row, 5, ops)

    def _op_button_style(self) -> str:
        c = AppTheme.colors
        return (
            f"QPushButton {{"
            f"  background-color: {c.accent_primary};"
            f"  color: {c.foreground_primary};"
            f"  border: 1px solid {c.accent_primary};"
            f"  border-radius: 4px;"
            f"  padding: 2px 8px;"
            f"  font-size: 12px;"
            f"}}"
            f"QPushButton:hover {{"
            f"  background-color: {AppTheme._lighten(c.accent_primary, 20)};"
            f"}}"
        )

    def _op_secondary_button_style(self) -> str:
        c = AppTheme.colors
        return (
            f"QPushButton {{"
            f"  background-color: transparent;"
            f"  color: {c.foreground_primary};"
            f"  border: 1px solid {c.accent_primary};"
            f"  border-radius: 4px;"
            f"  padding: 2px 8px;"
            f"  font-size: 12px;"
            f"}}"
            f"QPushButton:hover {{"
            f"  background-color: {c.accent_error};"
            f"  border-color: {c.accent_error};"
            f"  color: {c.foreground_primary};"
            f"}}"
        )

    # ----------------------------------------------------------- Data helpers
    def _load_descriptions(self) -> dict[str, str]:
        descriptions: dict[str, str] = {}
        for service in _SERVICES:
            path = Path("run_auto") / f"{service}.service"
            description = ""
            try:
                if path.exists():
                    with open(path, "r", encoding="utf-8") as f:
                        for line in f:
                            if line.startswith("Description="):
                                description = line.split("=", 1)[1].strip()
                                break
            except Exception as e:
                _log.debug(f"读取 {path} 失败: {e}")
            descriptions[service] = description or _DESCRIPTION_FALLBACK.get(service, "")
        return descriptions

    def _refresh_device_combo(self) -> None:
        current_data = self._device_combo.currentData()
        self._device_combo.clear()
        self._device_combo.addItem("选择设备", None)
        for device in self._device_store.devices:
            self._device_combo.addItem(device.name, device)
        if isinstance(current_data, RemoteDevice):
            index = self._device_combo.findData(current_data)
            if index >= 0:
                self._device_combo.setCurrentIndex(index)

    def refresh_devices(self) -> None:
        """刷新设备下拉框（供主窗口在服务页切换时调用）。"""
        self._refresh_device_combo()

    # ----------------------------------------------------------- Device/auth
    def _get_current_device(self) -> Optional[tuple[RemoteDevice, str]]:
        device = self._device_combo.currentData()
        if not isinstance(device, RemoteDevice):
            QMessageBox.warning(self, "选择错误", "请先选择一个已有设备")
            return None

        key_path = (device.ssh_key_path or "").strip()
        password = device.ssh_password or ""

        if key_path and Path(key_path).exists():
            return device, password

        if not password:
            text, ok = QInputDialog.getText(
                self,
                "SSH 密码",
                f"设备 {device.name} 未配置密码或密钥，请输入密码:",
                QLineEdit.EchoMode.Password,
            )
            if not ok or not text:
                return None
            password = text

        return device, password

    # ----------------------------------------------------------- SSH workers
    def _start_worker(
        self,
        device: RemoteDevice,
        password: str,
        command: str,
    ) -> SshCommandWorker:
        worker = SshCommandWorker(
            host=device.ip,
            ssh_port=device.ssh_port,
            username=device.ssh_username or "lckfb",
            password=password,
            key_path=device.ssh_key_path or "",
            command=command,
            parent=self,
        )
        worker.output.connect(self._append_output)
        worker.error.connect(self._append_error)
        worker.state_changed.connect(self._update_status)
        worker.finished.connect(lambda: self._on_worker_finished(worker))
        self._workers.add(worker)
        self._update_status()
        worker.start()
        return worker

    def _on_worker_finished(self, worker: SshCommandWorker) -> None:
        self._workers.discard(worker)
        worker.deleteLater()
        self._update_status()

    def _update_status(self, state: Optional[str] = None) -> None:
        if state:
            _log.debug(f"SSH 状态: {state}")
        if self._workers:
            self._status_label.setText(f"执行中 ({len(self._workers)})")
        else:
            self._status_label.setText("就绪")

    # ----------------------------------------------------------- Output
    def _append_output(self, text: str) -> None:
        if not text:
            return
        self._output_edit.appendPlainText(text)
        scrollbar = self._output_edit.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())

    def _append_error(self, message: str) -> None:
        self._append_output(f"[ERROR] {message}")
        self._status_label.setText("错误")

    # ----------------------------------------------------------- Refresh / actions
    def _on_refresh_all(self) -> None:
        dev = self._get_current_device()
        if dev is None:
            return
        device, password = dev
        for service in _SERVICES:
            self._refresh_service_with_auth(device, password, service)

    def _refresh_service(self, service: str) -> None:
        dev = self._get_current_device()
        if dev is None:
            return
        device, password = dev
        self._refresh_service_with_auth(device, password, service)

    def _refresh_service_with_auth(
        self, device: RemoteDevice, password: str, service: str
    ) -> None:
        command = (
            f"systemctl show {service} "
            "--property=ActiveState,SubState,LoadState,UnitFileState --no-pager"
        )
        self._append_output(f"$ {command}")
        worker = self._start_worker(device, password, command)
        worker.output.connect(lambda text, s=service: self._update_row_from_show(s, text))

    def _update_row_from_show(self, service: str, text: str) -> None:
        props: dict[str, str] = {}
        for line in text.splitlines():
            if "=" in line:
                key, value = line.split("=", 1)
                props[key.strip()] = value.strip()

        active = props.get("ActiveState", "unknown").lower() or "unknown"
        sub = props.get("SubState", "").lower()
        load = props.get("LoadState", "unknown").lower() or "unknown"
        enabled = props.get("UnitFileState", "unknown").lower() or "unknown"

        active_text = f"{active} ({sub})" if sub else active
        self._set_service_state(service, active_text, enabled, load)

    def _set_service_state(self, service: str, active: str, enabled: str, load: str) -> None:
        row = self._service_to_row.get(service)
        if row is None:
            return
        self._table.item(row, 1).setText(active)
        self._table.item(row, 2).setText(enabled)
        self._table.item(row, 3).setText(load)

    def _on_action(self, service: str, action: str) -> None:
        dev = self._get_current_device()
        if dev is None:
            return
        device, password = dev
        command = f"sudo systemctl {action} {service}"
        self._append_output(f"$ {command}")
        worker = self._start_worker(device, password, command)
        worker.finished.connect(
            lambda: self._refresh_service_with_auth(device, password, service)
        )

    # ----------------------------------------------------------- Context menu
    def _on_context_menu(self, pos) -> None:
        row = self._table.rowAt(pos.y())
        if row < 0:
            return
        service_item = self._table.item(row, 0)
        if service_item is None:
            return
        service = service_item.text()

        menu = QMenu(self)
        refresh_action = menu.addAction("刷新状态")
        enable_action = menu.addAction("启用开机自启")
        disable_action = menu.addAction("禁用开机自启")

        action = menu.exec(self._table.viewport().mapToGlobal(pos))
        if action == refresh_action:
            self._refresh_service(service)
        elif action == enable_action:
            self._run_simple_action(service, "enable")
        elif action == disable_action:
            self._run_simple_action(service, "disable")

    def _run_simple_action(self, service: str, action: str) -> None:
        dev = self._get_current_device()
        if dev is None:
            return
        device, password = dev
        command = f"sudo systemctl {action} {service}"
        self._append_output(f"$ {command}")
        worker = self._start_worker(device, password, command)
        worker.finished.connect(
            lambda: self._refresh_service_with_auth(device, password, service)
        )
