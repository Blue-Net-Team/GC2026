"""
Copyright (C) 2025 IVEN-CN(He Yunfeng)

GC2026 桌面调参应用 - UDP 图传接收器
====
基于 ImgTrans/ImgTrans.py 中的 ReceiveImgUDP 逻辑，使用 QThread 在后台运行，
通过 Qt 信号将解码后的帧交付给 UI 线程。
"""

from __future__ import annotations

import socket
import struct
import time
from enum import Enum
from typing import Optional

import cv2
import numpy as np
from PyQt6.QtCore import QObject, QThread, pyqtSignal
from loguru import logger

_log = logger.bind(module="UdpReceiver")


class ConnectionState(Enum):
    """UDP 连接状态"""

    DISCONNECTED = "未连接"
    CONNECTING = "连接中"
    CONNECTED = "已连接"
    RECONNECTING = "重连中"
    ERROR = "错误"


class ReceiverStats:
    """接收统计信息"""

    def __init__(self) -> None:
        self.fps: float = 0.0
        self.frame_count: int = 0
        self.lost_frames: int = 0
        self.error_frames: int = 0
        self.bytes_received: int = 0
        self.connected_at: Optional[float] = None

    def reset(self) -> None:
        self.fps = 0.0
        self.frame_count = 0
        self.lost_frames = 0
        self.error_frames = 0
        self.bytes_received = 0
        self.connected_at = None

    @property
    def connection_duration(self) -> float:
        if self.connected_at is None:
            return 0.0
        return time.time() - self.connected_at


class _UdpReceiverWorker(QObject):
    """UDP 接收工作对象（运行在独立线程中）"""

    frame_received = pyqtSignal(np.ndarray)
    state_changed = pyqtSignal(str)  # ConnectionState.value
    stats_changed = pyqtSignal(object)  # ReceiverStats
    error_occurred = pyqtSignal(str)

    BUFFER_SIZE = 65536
    CHUNK_MAX_SIZE = 1400
    CONNECT_TIMEOUT = 3.0
    FRAME_TIMEOUT = 1.0

    def __init__(
        self,
        server_ip: str,
        port: int,
        self_ip: str = "0.0.0.0",
    ) -> None:
        super().__init__()
        self.server_ip = server_ip
        self.port = port
        self.self_ip = self_ip

        self._socket: Optional[socket.socket] = None
        self._running = False
        self._stats = ReceiverStats()
        self._last_time = time.time()
        self._recv_buffer: Optional[bytearray] = None
        self._recv_total = 0
        self._recv_received = 0

    def start(self) -> None:
        self._running = True
        self._connect()
        self._receive_loop()

    def stop(self) -> None:
        self._running = False
        if self._socket is not None:
            try:
                self._socket.close()
            except OSError as e:
                _log.warning(f"关闭 socket 时出错: {e}")
            self._socket = None

    def switch_device(self, server_ip: str, port: int) -> None:
        """切换到新设备"""
        self.stop()
        self.server_ip = server_ip
        self.port = port
        self._reset_frame_state()
        self._stats.reset()
        self.start()

    def _connect(self) -> None:
        try:
            self.state_changed.emit(ConnectionState.CONNECTING.value)
            self._socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self._socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self._socket.bind((self.self_ip, self.port))
            self._socket.settimeout(self.CONNECT_TIMEOUT)
            self._socket.sendto(b"connect", (self.server_ip, self.port))
            self._stats.connected_at = time.time()
            self.state_changed.emit(ConnectionState.CONNECTED.value)
            _log.info(f"已向 {self.server_ip}:{self.port} 发送 connect 请求")
        except OSError as e:
            self.state_changed.emit(ConnectionState.ERROR.value)
            self.error_occurred.emit(f"无法绑定到 {self.self_ip}:{self.port}: {e}")
            _log.error(f"Socket 初始化失败: {e}")

    def _reset_frame_state(self) -> None:
        self._recv_buffer = None
        self._recv_total = 0
        self._recv_received = 0

    def _receive_loop(self) -> None:
        if self._socket is None:
            return

        # 初始connect后设置帧接收超时
        self._socket.settimeout(self.FRAME_TIMEOUT)

        while self._running:
            try:
                data, addr = self._socket.recvfrom(self.BUFFER_SIZE)
                if addr[0] != self.server_ip:
                    continue

                if len(data) < 8:
                    continue

                total_length, offset = struct.unpack("!II", data[:8])
                chunk_data = data[8:]
                self._stats.bytes_received += len(data)

                if self._recv_buffer is None or self._recv_total != total_length:
                    self._recv_buffer = bytearray(total_length)
                    self._recv_total = total_length
                    self._recv_received = 0

                end = min(offset + len(chunk_data), self._recv_total)
                self._recv_buffer[offset:end] = chunk_data[: end - offset]
                self._recv_received += end - offset

                if self._recv_received >= self._recv_total:
                    self._emit_frame(bytes(self._recv_buffer))
                    self._reset_frame_state()

            except socket.timeout:
                self._reset_frame_state()
                self._stats.lost_frames += 1
                self._reconnect_if_needed()
            except OSError:
                # socket 已被关闭，退出循环
                break
            except Exception as e:
                self._stats.error_frames += 1
                _log.error(f"接收异常: {e}")
                self.error_occurred.emit(str(e))

    def _emit_frame(self, image_bytes: bytes) -> None:
        nparr = np.frombuffer(image_bytes, np.uint8)
        frame = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        if frame is None:
            self._stats.error_frames += 1
            return

        self._stats.frame_count += 1
        now = time.time()
        elapsed = now - self._last_time
        if elapsed >= 1.0:
            self._stats.fps = self._stats.frame_count / elapsed
            self._last_time = now
            self.stats_changed.emit(self._stats)

        self.frame_received.emit(frame)

    def _reconnect_if_needed(self) -> None:
        if not self._running or self._socket is None:
            return
        try:
            self.state_changed.emit(ConnectionState.RECONNECTING.value)
            self._socket.sendto(b"connect", (self.server_ip, self.port))
        except OSError as e:
            _log.warning(f"重连失败: {e}")


class UdpReceiver(QObject):
    """UDP 图传接收器（线程安全封装）"""

    frame_received = pyqtSignal(np.ndarray)
    state_changed = pyqtSignal(str)
    stats_changed = pyqtSignal(object)
    error_occurred = pyqtSignal(str)

    def __init__(self, parent: Optional[QObject] = None) -> None:
        super().__init__(parent)
        self._thread = QThread(self)
        self._worker: Optional[_UdpReceiverWorker] = None
        self._server_ip: str = ""
        self._port: int = 8080

    @property
    def server_ip(self) -> str:
        return self._server_ip

    @property
    def port(self) -> int:
        return self._port

    def connect_to(self, server_ip: str, port: int = 8080) -> None:
        """连接到指定设备"""
        self._server_ip = server_ip
        self._port = port

        if self._worker is not None:
            self._worker.switch_device(server_ip, port)
            return

        self._worker = _UdpReceiverWorker(server_ip, port)
        self._worker.moveToThread(self._thread)
        self._worker.frame_received.connect(self.frame_received)
        self._worker.state_changed.connect(self.state_changed)
        self._worker.stats_changed.connect(self.stats_changed)
        self._worker.error_occurred.connect(self.error_occurred)
        self._thread.started.connect(self._worker.start)
        self._thread.start()

    def disconnect(self) -> None:
        """断开连接并释放资源"""
        if self._worker is not None:
            self._worker.stop()
            self._worker = None
        if self._thread.isRunning():
            self._thread.quit()
            self._thread.wait(3000)

    def __del__(self) -> None:
        try:
            self.disconnect()
        except RuntimeError:
            # QThread 可能已被 Qt 回收，忽略
            pass
