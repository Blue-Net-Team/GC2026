"""
Copyright (C) 2025 IVEN-CN(He Yunfeng)

GC2026 桌面调参应用 - 设备配置管理页面
====
管理已保存的远程设备（IP、图传端口、SSH 连接信息），使用本地 JSON 文件持久化。
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from PyQt6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)
from loguru import logger

from core.config_bridge import ConfigBridge
from app.core.device_store import DeviceStore, RemoteDevice
from app.core.ssh_worker import SshCommandWorker
from app.ui.theme import AppTheme

_log = logger.bind(module="ConfigScreen")


class DeviceDialog(QDialog):
    """添加/编辑设备对话框"""

    def __init__(
        self,
        device: Optional[RemoteDevice] = None,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self._device = device
        self.setWindowTitle("编辑设备" if device else "添加设备")
        self.setMinimumWidth(420)
        self.setStyleSheet(f"background-color: {AppTheme.colors.surface_primary};")

        self._build_ui()
        if device is not None:
            self._load_device(device)

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(16)

        form = QFormLayout()
        form.setSpacing(12)

        self._name_edit = QLineEdit()
        self._name_edit.setPlaceholderText("例如：泰山派主车")
        form.addRow("名称", self._name_edit)

        self._ip_edit = QLineEdit()
        self._ip_edit.setPlaceholderText("例如：192.168.1.100")
        form.addRow("IP 地址", self._ip_edit)

        self._port_spin = QSpinBox()
        self._port_spin.setRange(1, 65535)
        self._port_spin.setValue(8080)
        form.addRow("图传端口", self._port_spin)

        self._ssh_username_edit = QLineEdit()
        self._ssh_username_edit.setText("lckfb")
        form.addRow("SSH 用户名", self._ssh_username_edit)

        self._ssh_password_edit = QLineEdit()
        self._ssh_password_edit.setEchoMode(QLineEdit.EchoMode.Password)
        form.addRow("SSH 密码", self._ssh_password_edit)

        self._ssh_port_spin = QSpinBox()
        self._ssh_port_spin.setRange(1, 65535)
        self._ssh_port_spin.setValue(22)
        form.addRow("SSH 端口", self._ssh_port_spin)

        self._code_path_edit = QLineEdit()
        self._code_path_edit.setPlaceholderText("例如：/userdata/code/GC2026")
        self._code_path_edit.setText("/userdata/code/GC2026")
        form.addRow("代码路径", self._code_path_edit)

        key_layout = QHBoxLayout()
        key_layout.setSpacing(8)
        self._ssh_key_edit = QLineEdit()
        self._ssh_key_edit.setPlaceholderText("私钥文件路径（可选）")
        key_layout.addWidget(self._ssh_key_edit)

        browse_btn = QPushButton("浏览")
        browse_btn.setFixedWidth(70)
        browse_btn.clicked.connect(self._on_browse_key)
        key_layout.addWidget(browse_btn)
        form.addRow("私钥路径", key_layout)

        layout.addLayout(form)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _load_device(self, device: RemoteDevice) -> None:
        self._name_edit.setText(device.name)
        self._ip_edit.setText(device.ip)
        self._port_spin.setValue(device.port)
        self._ssh_username_edit.setText(device.ssh_username)
        self._ssh_password_edit.setText(device.ssh_password)
        self._ssh_port_spin.setValue(device.ssh_port)
        self._code_path_edit.setText(device.code_path)
        self._ssh_key_edit.setText(device.ssh_key_path)

    def _on_browse_key(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "选择 SSH 私钥", "", "All Files (*)"
        )
        if path:
            self._ssh_key_edit.setText(path)

    def _on_accept(self) -> None:
        name = self._name_edit.text().strip()
        ip = self._ip_edit.text().strip()
        if not name:
            QMessageBox.warning(self, "输入错误", "请输入设备名称")
            return
        if not ip:
            QMessageBox.warning(self, "输入错误", "请输入设备 IP 地址")
            return
        self.accept()

    def to_device(self) -> RemoteDevice:
        """将表单内容转换为 RemoteDevice"""
        device_id = self._device.id if self._device is not None else ""
        return RemoteDevice(
            id=device_id,
            name=self._name_edit.text().strip(),
            ip=self._ip_edit.text().strip(),
            port=self._port_spin.value(),
            ssh_username=self._ssh_username_edit.text().strip() or "lckfb",
            ssh_password=self._ssh_password_edit.text(),
            ssh_port=self._ssh_port_spin.value(),
            ssh_key_path=self._ssh_key_edit.text().strip(),
            code_path=self._code_path_edit.text().strip() or "/userdata/code/GC2026",
        )


class ConfigScreen(QWidget):
    """设备配置管理页面。"""

    def __init__(
        self,
        device_store: DeviceStore,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self._device_store = device_store
        self._config_bridge = ConfigBridge()
        self._workers: set[SshCommandWorker] = set()

        self._build_ui()
        self.refresh()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(16)

        # 顶部标题与添加按钮
        top_bar = QHBoxLayout()
        top_bar.setSpacing(12)

        title = QLabel("设备配置")
        title.setStyleSheet(
            f"color: {AppTheme.colors.foreground_primary}; font-size: 22px; font-weight: 600;"
        )
        top_bar.addWidget(title)
        top_bar.addStretch()

        self._add_device_btn = QPushButton("添加设备")
        self._add_device_btn.clicked.connect(self._on_add_device)
        top_bar.addWidget(self._add_device_btn)

        layout.addLayout(top_bar)

        # 设备表格
        self._device_table = QTableWidget()
        self._device_table.setColumnCount(8)
        self._device_table.setHorizontalHeaderLabels(
            ["名称", "IP", "图传端口", "SSH 用户名", "SSH 端口", "代码路径", "认证方式", "操作"]
        )
        header = self._device_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for col in (1, 2, 3, 4, 5, 6):
            header.setSectionResizeMode(col, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(7, QHeaderView.ResizeMode.Fixed)
        self._device_table.setColumnWidth(7, 260)
        self._device_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._device_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._device_table.verticalHeader().setVisible(False)
        self._device_table.verticalHeader().setMinimumSectionSize(48)
        self._device_table.setStyleSheet(self._table_style())
        layout.addWidget(self._device_table, stretch=1)

    def _table_style(self) -> str:
        c = AppTheme.colors
        m = AppTheme.metrics
        return (
            f"QTableWidget {{"
            f"  background-color: {c.surface_secondary};"
            f"  border: 1px solid {c.border_primary};"
            f"  border-radius: {m.radius_md}px;"
            f"  gridline-color: {c.border_subtle};"
            f"  outline: none;"
            f"}}"
            f"QHeaderView::section {{"
            f"  background-color: {c.surface_tertiary};"
            f"  color: {c.foreground_primary};"
            f"  padding: 8px 12px;"
            f"  border: none;"
            f"  border-bottom: 1px solid {c.border_primary};"
            f"}}"
            f"QTableWidget::item {{"
            f"  color: {c.foreground_secondary};"
            f"  padding: 8px 12px;"
            f"  border: none;"
            f"}}"
            f"QTableWidget::item:selected {{"
            f"  background-color: {c.surface_tertiary};"
            f"  color: {c.foreground_primary};"
            f"}}"
            f"QTableWidget::item:hover {{"
            f"  background-color: {c.surface_tertiary};"
            f"}}"
        )

    def _on_add_device(self) -> None:
        dialog = DeviceDialog(parent=self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        device = dialog.to_device()
        self._device_store.add(device)
        self.refresh()
        _log.info(f"已添加设备: {device.name} ({device.ip})")

    def _on_edit_device(self, device_id: str) -> None:
        device = self._device_store.get(device_id)
        if device is None:
            return
        dialog = DeviceDialog(device=device, parent=self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        updated = dialog.to_device()
        if self._device_store.update(updated):
            self.refresh()
            _log.info(f"已更新设备: {updated.name} ({updated.ip})")

    def _on_delete_device(self, device_id: str) -> None:
        device = self._device_store.get(device_id)
        if device is None:
            return
        reply = QMessageBox.question(
            self,
            "删除设备",
            f"确定要删除设备 \"{device.name}\" 吗？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        if self._device_store.remove(device_id):
            self.refresh()
            _log.info(f"已删除设备: {device.name}")

    def _on_upload_config(self, device_id: str) -> None:
        auth = self._get_device_auth(device_id)
        if auth is None:
            return
        device, password = auth

        reply = QMessageBox.question(
            self,
            "上传配置",
            f"确定要用本地 config.yaml 覆盖设备 \"{device.name}\" 上的配置吗？\n\n"
            f"目标路径: {device.code_path}/config.yaml",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        config_path = self._config_bridge.path
        if not config_path.exists():
            QMessageBox.critical(self, "缺少配置文件", f"本地未找到配置文件: {config_path}")
            return

        try:
            content = config_path.read_text(encoding="utf-8")
        except Exception as e:
            QMessageBox.critical(self, "读取失败", f"读取本地配置失败: {e}")
            return

        remote_path = f"{device.code_path}/config.yaml"
        command = f"sudo -S bash -c 'cat > {remote_path}'"
        worker = self._start_ssh_worker(
            device,
            password,
            command,
            stdin_data=f"{password}\n{content}",
        )
        worker.output.connect(lambda text: self._on_upload_done(device, text))
        worker.error.connect(lambda msg: QMessageBox.critical(self, "上传失败", msg))

    def _on_upload_done(self, device: RemoteDevice, text: str) -> None:
        if "permission denied" in text.lower() or "denied" in text.lower():
            QMessageBox.critical(self, "上传失败", f"权限不足，请确认 sudo 密码正确。\n\n{text}")
            return
        QMessageBox.information(
            self,
            "上传完成",
            f"本地配置已上传到 \"{device.name}\": {device.code_path}/config.yaml",
        )

    def _on_download_config(self, device_id: str) -> None:
        auth = self._get_device_auth(device_id)
        if auth is None:
            return
        device, password = auth

        reply = QMessageBox.question(
            self,
            "下载配置",
            f"确定要用设备 \"{device.name}\" 上的配置覆盖本地 config.yaml 吗？\n\n"
            f"源路径: {device.code_path}/config.yaml",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        remote_path = f"{device.code_path}/config.yaml"
        command = f"cat {remote_path}"
        worker = self._start_ssh_worker(device, password, command)
        worker.output.connect(lambda text: self._on_download_done(device, text))
        worker.error.connect(lambda msg: QMessageBox.critical(self, "下载失败", msg))

    def _on_download_done(self, device: RemoteDevice, text: str) -> None:
        if not text.strip():
            QMessageBox.critical(
                self,
                "下载失败",
                f"从 \"{device.name}\" 获取的配置内容为空，请检查远程文件是否存在。",
            )
            return

        try:
            self._config_bridge.path.write_text(text, encoding="utf-8")
            self._config_bridge.load()
        except Exception as e:
            QMessageBox.critical(self, "保存失败", f"写入本地配置失败: {e}")
            return

        QMessageBox.information(
            self,
            "下载完成",
            f"已用 \"{device.name}\" 上的配置覆盖本地 config.yaml，\n"
            f"请切换到调参页面查看最新参数。",
        )

    def _auth_method(self, device: RemoteDevice) -> str:
        if device.ssh_key_path:
            return "密钥"
        if device.ssh_password:
            return "密码"
        return "未配置"

    def _get_device_auth(self, device_id: str) -> Optional[tuple[RemoteDevice, str]]:
        device = self._device_store.get(device_id)
        if device is None:
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

    def _start_ssh_worker(
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
        worker.finished.connect(lambda: self._on_worker_finished(worker))
        self._workers.add(worker)
        worker.start()
        return worker

    def _on_worker_finished(self, worker: SshCommandWorker) -> None:
        self._workers.discard(worker)
        worker.deleteLater()

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

    def refresh(self) -> None:
        """从 device_store 刷新设备表格"""
        devices = self._device_store.devices
        self._device_table.setRowCount(len(devices))

        for row, device in enumerate(devices):
            self._device_table.setItem(row, 0, QTableWidgetItem(device.name))
            self._device_table.setItem(row, 1, QTableWidgetItem(device.ip))
            self._device_table.setItem(row, 2, QTableWidgetItem(str(device.port)))
            self._device_table.setItem(row, 3, QTableWidgetItem(device.ssh_username))
            self._device_table.setItem(row, 4, QTableWidgetItem(str(device.ssh_port)))
            self._device_table.setItem(row, 5, QTableWidgetItem(device.code_path))
            self._device_table.setItem(row, 6, QTableWidgetItem(self._auth_method(device)))

            op_widget = QWidget()
            op_widget.setAutoFillBackground(False)
            op_widget.setStyleSheet("background-color: transparent;")
            op_layout = QHBoxLayout(op_widget)
            op_layout.setContentsMargins(4, 0, 4, 0)
            op_layout.setSpacing(4)

            upload_btn = QPushButton("上传")
            upload_btn.setFixedSize(54, 24)
            upload_btn.setStyleSheet(self._op_button_style())
            upload_btn.setToolTip("上传本地 config.yaml 覆盖远程设备配置")
            upload_btn.clicked.connect(lambda _checked, did=device.id: self._on_upload_config(did))

            download_btn = QPushButton("下载")
            download_btn.setFixedSize(54, 24)
            download_btn.setStyleSheet(self._op_button_style())
            download_btn.setToolTip("从远程设备下载 config.yaml 覆盖本地配置")
            download_btn.clicked.connect(lambda _checked, did=device.id: self._on_download_config(did))

            edit_btn = QPushButton("编辑")
            edit_btn.setFixedSize(54, 24)
            edit_btn.setStyleSheet(self._op_button_style())
            edit_btn.clicked.connect(lambda _checked, did=device.id: self._on_edit_device(did))

            del_btn = QPushButton("删除")
            del_btn.setFixedSize(54, 24)
            del_btn.setStyleSheet(self._op_secondary_button_style())
            del_btn.clicked.connect(lambda _checked, did=device.id: self._on_delete_device(did))

            op_layout.addWidget(upload_btn)
            op_layout.addWidget(download_btn)
            op_layout.addWidget(edit_btn)
            op_layout.addWidget(del_btn)
            op_layout.addStretch()
            self._device_table.setCellWidget(row, 7, op_widget)

        _log.debug("设备配置页面已刷新")
