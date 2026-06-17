"""
Copyright (C) 2025 IVEN-CN(He Yunfeng)
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import paramiko
from PyQt6.QtCore import QObject, QThread, pyqtSignal
from loguru import logger

_log = logger.bind(module="SshCommandWorker")


class SshCommandWorker(QThread):
    """在独立线程中通过 SSH 执行单次命令，并将 stdout/stderr 回传 UI。"""

    output = pyqtSignal(str)
    error = pyqtSignal(str)
    state_changed = pyqtSignal(str)

    def __init__(
        self,
        host: str,
        ssh_port: int,
        username: str,
        password: str,
        key_path: str,
        command: str,
        parent: Optional[QObject] = None,
    ) -> None:
        super().__init__(parent)
        self._host = host
        self._ssh_port = ssh_port
        self._username = username
        self._password = password
        self._key_path = key_path
        self._command = command

    def run(self) -> None:
        self.state_changed.emit("连接中")
        client: Optional[paramiko.SSHClient] = None
        try:
            client = paramiko.SSHClient()
            client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

            connect_kwargs: dict = {
                "hostname": self._host,
                "port": self._ssh_port,
                "username": self._username,
                "timeout": 10,
                "look_for_keys": False,
                "allow_agent": False,
            }
            key_file = self._key_path.strip()
            if key_file and Path(key_file).exists():
                connect_kwargs["key_filename"] = key_file
            else:
                connect_kwargs["password"] = self._password

            client.connect(**connect_kwargs)
            self.state_changed.emit("已连接")
            _log.info(f"SSH 已连接 {self._host}:{self._ssh_port}")

            _log.debug(f"SSH 执行命令: {self._command}")
            stdin, stdout, stderr = client.exec_command(self._command, timeout=30)
            out = stdout.read().decode("utf-8", errors="replace")
            err = stderr.read().decode("utf-8", errors="replace")

            text = out
            if err.strip():
                text = f"{text}\n{err}" if text else err
            self.output.emit(text.strip())

            self.state_changed.emit("已断开")
            _log.info("SSH 命令执行完毕")
        except Exception as e:
            message = str(e) or type(e).__name__
            _log.error(f"SSH 命令异常: {message}")
            self.error.emit(message)
            self.state_changed.emit("失败")
        finally:
            if client is not None:
                try:
                    client.close()
                except Exception as e:
                    _log.debug(f"关闭 SSH client 时出错: {e}")
