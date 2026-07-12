"""
Copyright (C) 2025 IVEN-CN(He Yunfeng)

GC2026 桌面调参应用 - 设备网络可达性探测
====
在后台线程中周期性 ping 目标 IP，通过 Qt 信号将结果交付给 UI 线程。
用于左下角连接状态指示，与 UDP 图传接收逻辑解耦。
"""

from __future__ import annotations

import platform
import subprocess
import time
from typing import Optional

from PyQt6.QtCore import QObject, QThread, pyqtSignal
from loguru import logger

_log = logger.bind(module="DevicePinger")


class _DevicePingerWorker(QObject):
    """ping 后台工作对象（运行在独立线程中）"""

    state_changed = pyqtSignal(str)  # "检测中" / "已连接" / "未连接"
    latency_changed = pyqtSignal(float)  # ms，-1.0 表示超时
    finished = pyqtSignal()

    def __init__(
        self,
        ip: str,
        interval_ms: int = 2000,
        timeout_ms: int = 1500,
    ) -> None:
        super().__init__()
        self.ip = ip
        self.interval_ms = interval_ms
        self.timeout_ms = timeout_ms
        self._running = False

    def run(self) -> None:
        self._running = True
        self.state_changed.emit("检测中")

        while self._running:
            start = time.time()
            reachable = self._ping_once()
            latency = (time.time() - start) * 1000.0

            if not self._running:
                break

            if reachable:
                self.state_changed.emit("已连接")
                self.latency_changed.emit(latency)
            else:
                self.state_changed.emit("未连接")
                self.latency_changed.emit(-1.0)

            # 分段 sleep，方便快速响应 stop
            slices = max(1, self.interval_ms // 100)
            for _ in range(slices):
                if not self._running:
                    break
                time.sleep(0.1)

        self.finished.emit()

    def stop(self) -> None:
        self._running = False

    def _ping_once(self) -> bool:
        system = platform.system().lower()
        if system == "windows":
            # -w 单位为毫秒
            cmd = ["ping", "-n", "1", "-w", str(self.timeout_ms), self.ip]
        else:
            # -W 单位为秒，取整
            cmd = [
                "ping",
                "-c",
                "1",
                "-W",
                str(max(1, self.timeout_ms // 1000)),
                self.ip,
            ]

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                timeout=(self.timeout_ms / 1000.0) + 1.0,
            )
            return result.returncode == 0
        except (subprocess.TimeoutExpired, FileNotFoundError, OSError) as e:
            _log.debug(f"ping {self.ip} 失败: {e}")
            return False


class DevicePinger(QObject):
    """设备网络可达性探测器（线程安全封装）"""

    state_changed = pyqtSignal(str)
    latency_changed = pyqtSignal(float)

    def __init__(self, parent: Optional[QObject] = None) -> None:
        super().__init__(parent)
        self._thread: Optional[QThread] = None
        self._worker: Optional[_DevicePingerWorker] = None
        self._target_ip = ""

    @property
    def target_ip(self) -> str:
        return self._target_ip

    def start(self, ip: str) -> None:
        """开始周期性 ping 指定 IP"""
        self.stop()
        self._target_ip = ip

        self._thread = QThread(self)
        self._worker = _DevicePingerWorker(ip)
        self._worker.moveToThread(self._thread)
        self._worker.state_changed.connect(self.state_changed)
        self._worker.latency_changed.connect(self.latency_changed)
        self._thread.started.connect(self._worker.run)
        self._worker.finished.connect(self._thread.quit)
        self._worker.finished.connect(self._worker.deleteLater)
        self._thread.finished.connect(self._thread.deleteLater)
        self._thread.start()
        _log.info(f"开始 ping 探测: {ip}")

    def stop(self) -> None:
        """停止探测并释放资源"""
        if self._worker is not None:
            self._worker.stop()
        if self._thread is not None:
            if self._thread.isRunning():
                self._thread.quit()
                self._thread.wait(3000)
            self._thread = None
        self._worker = None
        self._target_ip = ""

    def is_running(self) -> bool:
        return self._thread is not None and self._thread.isRunning()

    def __del__(self) -> None:
        try:
            self.stop()
        except RuntimeError:
            # QThread 可能已被 Qt 回收，忽略
            pass
