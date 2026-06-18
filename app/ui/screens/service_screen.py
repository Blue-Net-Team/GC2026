"""
Copyright (C) 2025 IVEN-CN(He Yunfeng)
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
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
    QTextEdit,
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
        self._load_buttons: dict[str, QPushButton] = {}
        self._op_button_groups: dict[str, tuple[QPushButton, QPushButton, QPushButton]] = {}

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

            load_btn = QPushButton("加载")
            load_btn.setFixedSize(54, 26)
            load_btn.setStyleSheet(self._op_button_style())
            load_btn.setVisible(False)
            load_btn.clicked.connect(lambda _=False, s=service: self._on_load_service(s))
            self._load_buttons[service] = load_btn

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

            self._op_button_groups[service] = (start_btn, stop_btn, restart_btn)

            ops_layout.addWidget(load_btn)
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
            path = Path("run_auto") / service
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
        stdin_data: Optional[str] = None,
    ) -> SshCommandWorker:
        worker = SshCommandWorker(
            host=device.ip,
            ssh_port=device.ssh_port,
            username=device.ssh_username or "lckfb",
            password=password,
            key_path=device.ssh_key_path or "",
            command=command,
            stdin_data=stdin_data,
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
        self._update_op_buttons(service, load == "loaded")

    def _set_service_state(self, service: str, active: str, enabled: str, load: str) -> None:
        row = self._service_to_row.get(service)
        if row is None:
            return
        self._table.item(row, 1).setText(active)
        self._table.item(row, 2).setText(enabled)
        self._table.item(row, 3).setText(load)

    def _update_op_buttons(self, service: str, loaded: bool) -> None:
        load_btn = self._load_buttons.get(service)
        start_btn, stop_btn, restart_btn = self._op_button_groups.get(service, (None, None, None))
        if load_btn is not None:
            load_btn.setVisible(not loaded)
        if start_btn is not None:
            start_btn.setVisible(loaded)
        if stop_btn is not None:
            stop_btn.setVisible(loaded)
        if restart_btn is not None:
            restart_btn.setVisible(loaded)

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

    # ----------------------------------------------------------- Load service
    def _on_load_service(self, service: str) -> None:
        dev = self._get_current_device()
        if dev is None:
            return
        device, password = dev

        local_path = Path("run_auto") / service
        if not local_path.exists():
            QMessageBox.critical(
                self,
                "缺少服务文件",
                f"本地未找到服务文件：{local_path}\n\n"
                f"请在项目根目录维护 run_auto/{service} 后再试。",
            )
            return

        try:
            raw_content = local_path.read_text(encoding="utf-8")
        except Exception as e:
            QMessageBox.critical(self, "读取失败", f"读取服务文件失败：{e}")
            return

        default_user = device.ssh_username or "lckfb"
        default_code_path = device.code_path or "/userdata/code/GC2026"
        dialog = self._LoadServiceDialog(
            service,
            raw_content,
            default_user=default_user,
            default_code_path=default_code_path,
            parent=self,
        )
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        project_path = dialog.project_path.strip().rstrip("/")
        user = dialog.user.strip()
        uv_path = dialog.uv_path.strip()
        content = self._render_service_content(raw_content, project_path, user, uv_path)

        self._append_output(f"# 加载服务 {service} 到 {device.ip}")
        self._append_output(f"# 项目路径: {project_path}")
        self._append_output(f"# 运行用户: {user}")
        self._append_output(f"# uv 路径: {uv_path}")

        command = (
            f"sudo -S bash -c "
            f"'cat > /etc/systemd/system/{service} && systemctl daemon-reload'"
        )
        self._append_output(f"$ sudo -S ... < {service}.service")
        worker = self._start_worker(
            device,
            password,
            command,
            stdin_data=f"{password}\n{content}",
        )
        worker.finished.connect(
            lambda: self._refresh_service_with_auth(device, password, service)
        )

    def _render_service_content(
        self,
        content: str,
        project_path: str,
        user: str,
        uv_path: str,
    ) -> str:
        rendered = content
        rendered = rendered.replace("User=lckfb", f"User={user}")
        rendered = rendered.replace("/userdata/code/GC2026", project_path)
        rendered = rendered.replace("/home/lckfb/.local/bin/uv", uv_path)
        return rendered

    class _LoadServiceDialog(QDialog):
        def __init__(
            self,
            service: str,
            content: str,
            default_user: str = "lckfb",
            default_code_path: str = "/userdata/code/GC2026",
            parent: Optional[QWidget] = None,
        ) -> None:
            super().__init__(parent)
            self.setWindowTitle(f"加载服务：{service}")
            self.setMinimumWidth(560)

            layout = QVBoxLayout(self)
            layout.setSpacing(12)

            hint = QLabel(
                "服务文件将从本地 run_auto 目录上传到对端 /etc/systemd/system/，"
                "并根据下方配置替换其中的路径与用户名。上传完成后会自动 daemon-reload。"
            )
            hint.setWordWrap(True)
            hint.setStyleSheet(
                f"color: {AppTheme.colors.foreground_secondary}; font-size: 12px;"
            )
            layout.addWidget(hint)

            form_layout = QFormLayout()
            form_layout.setSpacing(10)

            self.project_path_edit = QLineEdit(default_code_path)
            form_layout.addRow("项目路径：", self.project_path_edit)

            self.user_edit = QLineEdit(default_user)
            form_layout.addRow("运行用户：", self.user_edit)

            default_uv = f"/home/{default_user}/.local/bin/uv"
            self.uv_path_edit = QLineEdit(default_uv)
            form_layout.addRow("uv 路径：", self.uv_path_edit)

            layout.addLayout(form_layout)

            preview_label = QLabel("预览（将上传的内容）：")
            preview_label.setStyleSheet(
                f"color: {AppTheme.colors.foreground_secondary}; font-size: 12px;"
            )
            layout.addWidget(preview_label)

            self.preview_edit = QTextEdit()
            self.preview_edit.setReadOnly(True)
            self.preview_edit.setPlainText(content)
            self.preview_edit.setMaximumBlockCount(200)
            layout.addWidget(self.preview_edit, stretch=1)

            buttons = QDialogButtonBox(
                QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
            )
            buttons.accepted.connect(self.accept)
            buttons.rejected.connect(self.reject)
            layout.addWidget(buttons)

            self._original_content = content
            self.project_path_edit.textChanged.connect(self._update_preview)
            self.user_edit.textChanged.connect(self._update_preview)
            self.uv_path_edit.textChanged.connect(self._update_preview)
            self._update_preview()

        def _update_preview(self) -> None:
            screen = self.parent()
            if not isinstance(screen, ServiceScreen):
                return
            rendered = screen._render_service_content(
                self._original_content,
                self.project_path_edit.text().strip().rstrip("/"),
                self.user_edit.text().strip(),
                self.uv_path_edit.text().strip(),
            )
            self.preview_edit.setPlainText(rendered)

        @property
        def project_path(self) -> str:
            return self.project_path_edit.text()

        @property
        def user(self) -> str:
            return self.user_edit.text()

        @property
        def uv_path(self) -> str:
            return self.uv_path_edit.text()
