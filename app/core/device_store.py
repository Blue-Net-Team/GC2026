"""
Copyright (C) 2025 IVEN-CN(He Yunfeng)

GC2026 桌面调参应用 - 设备列表存储
====
管理已保存的远程设备（名称 + IP + 端口 + SSH 连接信息），使用本地 JSON 文件持久化。
"""

from __future__ import annotations

import copy
import json
import uuid
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Optional

from PyQt6.QtCore import QObject, pyqtSignal
from loguru import logger

_log = logger.bind(module="DeviceStore")


@dataclass
class RemoteDevice:
    """远程设备模型"""

    name: str
    ip: str
    port: int = 8080
    id: str = ""
    ssh_username: str = "lckfb"
    ssh_password: str = ""
    ssh_port: int = 22
    ssh_key_path: str = ""
    code_path: str = "/userdata/code/GC2026"

    def __post_init__(self) -> None:
        if not self.id:
            self.id = str(uuid.uuid4())

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "RemoteDevice":
        return cls(
            id=data.get("id", ""),
            name=data.get("name", "未命名设备"),
            ip=data.get("ip", "127.0.0.1"),
            port=int(data.get("port", 8080)),
            ssh_username=data.get("ssh_username", "lckfb"),
            ssh_password=data.get("ssh_password", ""),
            ssh_port=int(data.get("ssh_port", 22)),
            ssh_key_path=data.get("ssh_key_path", ""),
            code_path=data.get("code_path", "/userdata/code/GC2026"),
        )


DEFAULT_DEVICES: list[RemoteDevice] = [
    RemoteDevice(name="泰山派主车", ip="192.168.1.100", port=8080),
]


class DeviceStore(QObject):
    """设备列表本地存储"""

    devices_changed = pyqtSignal()

    def __init__(self, path: Optional[str | Path] = None) -> None:
        super().__init__()
        self.path = Path(path) if path else Path("devices.json")
        self._devices: list[RemoteDevice] = []
        self.load()

    @property
    def devices(self) -> list[RemoteDevice]:
        return copy.deepcopy(self._devices)

    def load(self) -> list[RemoteDevice]:
        if not self.path.exists():
            _log.warning(f"设备列表文件不存在: {self.path}，使用默认设备")
            self._devices = copy.deepcopy(DEFAULT_DEVICES)
            self.save()
            return self._devices

        try:
            with open(self.path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, list):
                self._devices = [RemoteDevice.from_dict(item) for item in data]
            else:
                self._devices = copy.deepcopy(DEFAULT_DEVICES)
            _log.info(f"已加载 {len(self._devices)} 个设备")
        except Exception as e:
            _log.error(f"加载设备列表失败: {e}")
            self._devices = copy.deepcopy(DEFAULT_DEVICES)

        self.devices_changed.emit()
        return self._devices

    def save(self) -> bool:
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.path, "w", encoding="utf-8") as f:
                json.dump(
                    [device.to_dict() for device in self._devices],
                    f,
                    ensure_ascii=False,
                    indent=2,
                )
            self.devices_changed.emit()
            return True
        except Exception as e:
            _log.error(f"保存设备列表失败: {e}")
            return False

    def add(self, device: RemoteDevice) -> None:
        self._devices.append(device)
        self.save()

    def update(self, device: RemoteDevice) -> bool:
        for i, existing in enumerate(self._devices):
            if existing.id == device.id:
                self._devices[i] = device
                self.save()
                return True
        return False

    def remove(self, device_id: str) -> bool:
        for i, existing in enumerate(self._devices):
            if existing.id == device_id:
                self._devices.pop(i)
                self.save()
                return True
        return False

    def get(self, device_id: str) -> Optional[RemoteDevice]:
        for device in self._devices:
            if device.id == device_id:
                return copy.deepcopy(device)
        return None
