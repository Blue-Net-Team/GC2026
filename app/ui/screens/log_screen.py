"""
Copyright (C) 2025 IVEN-CN(He Yunfeng)

GC2026 桌面调参应用 - 远程设备日志页面
====
通过 SSH 连接到远程设备，实时显示 run-main-auto.service 的 journalctl 日志。
设备的所有 SSH 连接信息（用户名、密码、端口、密钥）均来自 DeviceStore，
本页面只负责选择设备并连接。
"""

from __future__ import annotations

from collections import deque
from pathlib import Path
from typing import Optional

import paramiko
from PyQt6.QtCore import QThread, pyqtSignal
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFileDialog,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)
from loguru import logger

from app.core.device_store import DeviceStore, RemoteDevice
from app.ui.theme import AppTheme

_log = logger.bind(module="LogScreen")

_LEVEL_ORDER = ("全部", "DEBUG", "INFO", "WARNING", "ERROR")
_LEVEL_COLORS = {
    "DEBUG": AppTheme.colors.foreground_muted,
    "INFO": AppTheme.colors.foreground_secondary,
    "WARNING": AppTheme.colors.accent_warning,
    "ERROR": AppTheme.colors.accent_error,
}
_DEFAULT_LEVEL_COLOR = AppTheme.colors.foreground_secondary


def _detect_level(line: str) -> str:
    """从日志行中识别级别，不区分大小写。"""
    upper = line.upper()
    for level in ("ERROR", "WARNING", "INFO", "DEBUG"):
        if level in upper:
            return level
    return "INFO"


class SshLogWorker(QThread):
    """在独立线程中通过 SSH 执行命令并逐行返回 stdout。"""

    log_line = pyqtSignal(str)
    state_changed = pyqtSignal(str)
    error_occurred = pyqtSignal(str)

    def __init__(
        self,
        host: str,
        ssh_port: int,
        username: str,
        password: str,
        key_path: str,
        command: str,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self._host = host
        self._ssh_port = ssh_port
        self._username = username
        self._password = password
        self._key_path = key_path
        self._command = command
        self._client: Optional[paramiko.SSHClient] = None
        self._channel: Optional[paramiko.Channel] = None
        self._running = True

    def run(self) -> None:
        self.state_changed.emit("连接中")
        try:
            client = paramiko.SSHClient()
            client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

            connect_kwargs: dict = {
                "hostname": self._host,
                "port": self._ssh_port,
                "username": self._username,
                "timeout": 10,
                "look_for_keys": False,
            }
            key_file = self._key_path.strip()
            if key_file and Path(key_file).exists():
                connect_kwargs["key_filename"] = key_file
            else:
                connect_kwargs["password"] = self._password

            client.connect(**connect_kwargs)
            self._client = client
            self.state_changed.emit("已连接")
            _log.info(f"SSH 已连接 {self._host}:{self._ssh_port}")

            transport = client.get_transport()
            if transport is None:
                raise RuntimeError("无法获取 SSH transport")

            self._channel = transport.open_session()
            self._channel.get_pty(width=200, height=80)
            self._channel.exec_command(self._command)

            stdout = self._channel.makefile("r", encoding="utf-8", errors="replace")
            while self._running:
                try:
                    line = stdout.readline()
                except Exception:
                    break
                if not line:
                    break
                self.log_line.emit(line.rstrip("\n"))

            self.state_changed.emit("已断开")
            _log.info("SSH 会话正常结束")
        except Exception as e:
            message = str(e) or type(e).__name__
            _log.error(f"SSH 会话异常: {message}")
            self.error_occurred.emit(message)
            self.state_changed.emit("连接失败")
        finally:
            self._close()

    def stop(self) -> None:
        self._running = False
        self._close()
        self.wait(2000)

    def _close(self) -> None:
        try:
            if self._channel is not None:
                self._channel.close()
        except Exception as e:
            _log.debug(f"关闭 SSH channel 时出错: {e}")
        self._channel = None

        try:
            if self._client is not None:
                self._client.close()
        except Exception as e:
            _log.debug(f"关闭 SSH client 时出错: {e}")
        self._client = None


class LogScreen(QWidget):
    """远程设备日志页面。"""

    def __init__(
        self,
        device_store: DeviceStore,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self._device_store = device_store
        self._worker: Optional[SshLogWorker] = None
        self._cache: deque[tuple[str, str]] = deque(maxlen=2000)
        self._filter_level = "全部"

        self._build_ui()
        self._refresh_device_combo()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(16)

        # 顶部工具栏
        top_bar = QHBoxLayout()
        top_bar.setSpacing(12)

        title = QLabel("远程日志")
        title.setStyleSheet(
            f"color: {AppTheme.colors.foreground_primary}; font-size: 22px; font-weight: 600;"
        )
        top_bar.addWidget(title)
        top_bar.addStretch()

        self._device_combo = QComboBox()
        self._device_combo.setMinimumWidth(200)
        self._device_combo.currentIndexChanged.connect(self._on_device_changed)
        top_bar.addWidget(self._device_combo)

        self._connect_btn = QPushButton("连接")
        self._connect_btn.setFixedWidth(80)
        self._connect_btn.clicked.connect(self._on_connect)
        top_bar.addWidget(self._connect_btn)

        self._disconnect_btn = QPushButton("断开")
        self._disconnect_btn.setFixedWidth(80)
        self._disconnect_btn.setObjectName("secondary")
        self._disconnect_btn.setEnabled(False)
        self._disconnect_btn.clicked.connect(self._on_disconnect)
        top_bar.addWidget(self._disconnect_btn)

        layout.addLayout(top_bar)

        # 设备连接信息提示
        self._info_label = QLabel("未选择设备")
        self._info_label.setStyleSheet(
            f"color: {AppTheme.colors.foreground_muted}; font-size: 12px; font-family: {AppTheme.fonts.mono};"
        )
        layout.addWidget(self._info_label)

        # 日志显示区
        self._log_edit = QPlainTextEdit()
        self._log_edit.setReadOnly(True)
        self._log_edit.setLineWrapMode(QPlainTextEdit.LineWrapMode.WidgetWidth)
        layout.addWidget(self._log_edit, stretch=1)

        # 底部工具栏
        bottom_bar = QHBoxLayout()
        bottom_bar.setSpacing(12)

        self._filter_combo = QComboBox()
        for level in _LEVEL_ORDER:
            self._filter_combo.addItem(level)
        self._filter_combo.setMinimumWidth(120)
        self._filter_combo.currentTextChanged.connect(self._on_filter_changed)
        bottom_bar.addWidget(QLabel("过滤:"))
        bottom_bar.addWidget(self._filter_combo)

        self._auto_scroll_cb = QCheckBox("自动滚动到底部")
        self._auto_scroll_cb.setChecked(True)
        bottom_bar.addWidget(self._auto_scroll_cb)

        bottom_bar.addStretch()

        self._clear_btn = QPushButton("清空")
        self._clear_btn.setObjectName("secondary")
        self._clear_btn.clicked.connect(self._on_clear)
        bottom_bar.addWidget(self._clear_btn)

        self._export_btn = QPushButton("导出日志")
        self._export_btn.setObjectName("secondary")
        self._export_btn.clicked.connect(self._on_export)
        bottom_bar.addWidget(self._export_btn)

        layout.addLayout(bottom_bar)

        # 状态栏
        self._status_label = QLabel("未连接")
        self._status_label.setStyleSheet(
            f"color: {AppTheme.colors.foreground_muted}; font-size: 12px; font-family: {AppTheme.fonts.mono};"
        )
        layout.addWidget(self._status_label)

    def _refresh_device_combo(self) -> None:
        self._device_combo.clear()
        self._device_combo.addItem("选择设备", None)
        for device in self._device_store.devices:
            self._device_combo.addItem(device.name, device)

    def _on_device_changed(self, _index: int) -> None:
        device = self._device_combo.currentData()
        if not isinstance(device, RemoteDevice):
            self._info_label.setText("未选择设备")
            return
        auth = "密钥" if device.ssh_key_path else ("密码" if device.ssh_password else "未配置密码")
        self._info_label.setText(
            f"{device.ssh_username}@{device.ip}:{device.ssh_port}  ·  认证方式: {auth}"
        )

    def _on_connect(self) -> None:
        if self._worker is not None:
            return

        device = self._device_combo.currentData()
        if not isinstance(device, RemoteDevice):
            QMessageBox.warning(self, "选择错误", "请先选择一个已有设备")
            return

        username = device.ssh_username or "lckfb"
        password = device.ssh_password
        key_path = device.ssh_key_path

        if not key_path and not password:
            text, ok = QInputDialog.getText(
                self,
                "SSH 密码",
                f"设备 {device.name} 未配置密码或密钥，请输入密码:",
                QLineEdit.EchoMode.Password,
            )
            if not ok or not text:
                return
            password = text

        command = "journalctl -u run-main-auto.service -n 200 -f"
        self._worker = SshLogWorker(
            host=device.ip,
            ssh_port=device.ssh_port,
            username=username,
            password=password,
            key_path=key_path,
            command=command,
            parent=self,
        )
        self._worker.log_line.connect(self._on_log_line)
        self._worker.state_changed.connect(self._on_state_changed)
        self._worker.error_occurred.connect(self._on_error)
        self._worker.finished.connect(self._on_worker_finished)
        self._worker.start()

        self._connect_btn.setEnabled(False)
        self._disconnect_btn.setEnabled(True)
        self._cache.clear()
        self._log_edit.clear()

    def _on_disconnect(self) -> None:
        if self._worker is not None:
            self._worker.stop()
            self._worker = None
        self._connect_btn.setEnabled(True)
        self._disconnect_btn.setEnabled(False)
        self._status_label.setText("未连接")

    def _on_worker_finished(self) -> None:
        self._worker = None
        self._connect_btn.setEnabled(True)
        self._disconnect_btn.setEnabled(False)

    def _on_state_changed(self, state: str) -> None:
        self._status_label.setText(state)

    def _on_error(self, message: str) -> None:
        QMessageBox.critical(self, "SSH 错误", message)
        self._connect_btn.setEnabled(True)
        self._disconnect_btn.setEnabled(False)
        self._status_label.setText("连接失败")

    def _on_log_line(self, line: str) -> None:
        level = _detect_level(line)
        self._cache.append((line, level))
        if self._filter_level == "全部" or self._filter_level == level:
            self._append_colored_line(line, level)

    def _append_colored_line(self, line: str, level: str) -> None:
        color = _LEVEL_COLORS.get(level, _DEFAULT_LEVEL_COLOR)
        escaped = line.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        self._log_edit.appendHtml(f'<span style="color:{color}">{escaped}</span>')
        if self._auto_scroll_cb.isChecked():
            self._log_edit.verticalScrollBar().setValue(
                self._log_edit.verticalScrollBar().maximum()
            )

    def _on_filter_changed(self, level: str) -> None:
        self._filter_level = level
        self._log_edit.clear()
        for line, lvl in self._cache:
            if level == "全部" or level == lvl:
                self._append_colored_line(line, lvl)

    def _on_clear(self) -> None:
        self._cache.clear()
        self._log_edit.clear()

    def _on_export(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self, "导出日志", "remote-log.txt", "Text Files (*.txt);;All Files (*)"
        )
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8") as f:
                for line, _ in self._cache:
                    f.write(line + "\n")
            _log.info(f"日志已导出到 {path}")
        except Exception as e:
            QMessageBox.critical(self, "导出失败", str(e))

    def closeEvent(self, event) -> None:  # type: ignore[override]
        self._on_disconnect()
        event.accept()
