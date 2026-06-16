"""
Copyright (C) 2025 IVEN-CN(He Yunfeng)

GC2026 桌面调参应用 - 图像源抽象层
====
提供统一的 FrameSource 接口，使 UDP 图传、本地摄像头、已保存设备摄像头
对上层页面提供一致的 read()/release() 语义。
"""

from __future__ import annotations

import socket
import struct
import time
from typing import Optional

import cv2
import numpy as np
from PyQt6.QtCore import QObject, QThread, QTimer, pyqtSignal
from loguru import logger

_log = logger.bind(module="FrameSource")


class FrameSource(QObject):
    """图像源抽象基类

    所有图像源都通过 Qt 信号向上层交付解码后的 BGR 帧。
    子类需要实现 start()、stop()、is_running() 和 source_name()。
    """

    frame_received = pyqtSignal(np.ndarray)
    state_changed = pyqtSignal(str)
    error_occurred = pyqtSignal(str)

    def __init__(self, parent: Optional[QObject] = None) -> None:
        super().__init__(parent)

    def start(self) -> None:
        """启动图像采集"""
        raise NotImplementedError

    def stop(self) -> None:
        """停止并释放资源"""
        raise NotImplementedError

    def is_running(self) -> bool:
        """是否正在采集"""
        raise NotImplementedError

    def source_name(self) -> str:
        """返回人类可读的源名称"""
        raise NotImplementedError


class _UdpWorker(QObject):
    """UDP 图传后台工作对象"""

    frame_received = pyqtSignal(np.ndarray)
    state_changed = pyqtSignal(str)
    error_occurred = pyqtSignal(str)

    BUFFER_SIZE = 65536
    CHUNK_MAX_SIZE = 1400
    CONNECT_TIMEOUT = 3.0
    FRAME_TIMEOUT = 1.0

    def __init__(self, server_ip: str, port: int, self_ip: str = "0.0.0.0") -> None:
        super().__init__()
        self.server_ip = server_ip
        self.port = port
        self.self_ip = self_ip

        self._socket: Optional[socket.socket] = None
        self._running = False
        self._connected = False
        self._recv_buffer: Optional[bytearray] = None
        self._recv_total = 0
        self._recv_received = 0

    def start(self) -> None:
        self._running = True
        self._connected = False
        self._connect()
        self._receive_loop()

    def stop(self) -> None:
        self._running = False
        self._connected = False
        if self._socket is not None:
            try:
                self._socket.close()
            except OSError as e:
                _log.warning(f"关闭 socket 时出错: {e}")
            self._socket = None

    def _connect(self) -> None:
        try:
            self.state_changed.emit("连接中")
            self._socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self._socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self._socket.bind((self.self_ip, self.port))
            self._socket.settimeout(self.CONNECT_TIMEOUT)
            self._socket.sendto(b"connect", (self.server_ip, self.port))
            _log.info(f"已向 {self.server_ip}:{self.port} 发送 connect 请求")
        except OSError as e:
            self.state_changed.emit("错误")
            self.error_occurred.emit(f"无法绑定到 {self.self_ip}:{self.port}: {e}")
            _log.error(f"Socket 初始化失败: {e}")

    def _reset_frame_state(self) -> None:
        self._recv_buffer = None
        self._recv_total = 0
        self._recv_received = 0

    def _receive_loop(self) -> None:
        if self._socket is None:
            return
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
                self._reconnect_if_needed()
            except OSError:
                break
            except Exception as e:
                _log.error(f"接收异常: {e}")
                self.error_occurred.emit(str(e))

    def _emit_frame(self, image_bytes: bytes) -> None:
        nparr = np.frombuffer(image_bytes, np.uint8)
        frame = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        if frame is not None:
            if not self._connected:
                self._connected = True
                self.state_changed.emit("已连接")
            self.frame_received.emit(frame)

    def _reconnect_if_needed(self) -> None:
        if not self._running or self._socket is None:
            return
        try:
            if self._connected:
                self._connected = False
                self.state_changed.emit("重连中")
            self._socket.sendto(b"connect", (self.server_ip, self.port))
        except OSError as e:
            _log.warning(f"重连失败: {e}")


class UdpFrameSource(FrameSource):
    """UDP 远程图传图像源"""

    def __init__(
        self,
        server_ip: str,
        port: int = 8080,
        self_ip: str = "0.0.0.0",
        parent: Optional[QObject] = None,
    ) -> None:
        super().__init__(parent)
        self.server_ip = server_ip
        self.port = port
        self.self_ip = self_ip

        self._thread = QThread(self)
        self._worker: Optional[_UdpWorker] = None

    def start(self) -> None:
        if self._worker is not None:
            return
        self._worker = _UdpWorker(self.server_ip, self.port, self.self_ip)
        self._worker.moveToThread(self._thread)
        self._worker.frame_received.connect(self.frame_received)
        self._worker.state_changed.connect(self.state_changed)
        self._worker.error_occurred.connect(self.error_occurred)
        self._thread.started.connect(self._worker.start)
        self._thread.start()

    def stop(self) -> None:
        if self._worker is not None:
            self._worker.stop()
            self._worker = None
        if self._thread.isRunning():
            self._thread.quit()
            self._thread.wait(3000)

    def is_running(self) -> bool:
        return self._thread.isRunning()

    def source_name(self) -> str:
        return f"UDP {self.server_ip}:{self.port}"


class SavedDeviceFrameSource(UdpFrameSource):
    """从已保存设备列表中读取配置的 UDP 图像源"""

    def __init__(self, name: str, server_ip: str, port: int = 8080, parent: Optional[QObject] = None) -> None:
        super().__init__(server_ip, port, parent=parent)
        self._name = name

    def source_name(self) -> str:
        return self._name


class _CameraInitThread(QThread):
    """在后台线程中尝试打开本地摄像头，避免阻塞 UI"""

    ready = pyqtSignal(int)
    error = pyqtSignal(str)

    def __init__(self, camera_index: int) -> None:
        super().__init__()
        self.camera_index = camera_index

    def run(self) -> None:
        cap = cv2.VideoCapture(self.camera_index)
        if cap.isOpened():
            cap.release()
            self.ready.emit(self.camera_index)
        else:
            self.error.emit(f"无法打开本地摄像头 {self.camera_index}")


class LocalCameraFrameSource(FrameSource):
    """本地摄像头图像源

    使用后台线程初始化摄像头（避免 UI 卡顿），初始化成功后在主线程通过
    QTimer 定期读取帧，避免 QThread 生命周期管理问题。
    """

    def __init__(self, camera_index: int = 0, parent: Optional[QObject] = None) -> None:
        super().__init__(parent)
        self.camera_index = camera_index
        self._cap: Optional[cv2.VideoCapture] = None
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._read_frame)
        self._running = False
        self._init_thread: Optional[_CameraInitThread] = None

    def start(self) -> None:
        if self._running:
            return
        self.state_changed.emit("连接中")
        self._init_thread = _CameraInitThread(self.camera_index)
        self._init_thread.ready.connect(self._on_init_ready)
        self._init_thread.error.connect(self.error_occurred)
        self._init_thread.finished.connect(self._cleanup_init_thread)
        self._init_thread.start()

    def _on_init_ready(self, camera_index: int) -> None:
        self._cap = cv2.VideoCapture(camera_index)
        if not self._cap.isOpened():
            self.error_occurred.emit(f"无法打开本地摄像头 {camera_index}")
            return

        self._running = True
        self.state_changed.emit("已连接")
        # 约 30fps
        self._timer.start(33)

    def _cleanup_init_thread(self) -> None:
        self._init_thread = None

    def _read_frame(self) -> None:
        if self._cap is None:
            return
        ret, frame = self._cap.read()
        if ret and frame is not None:
            self.frame_received.emit(frame)

    def stop(self) -> None:
        self._timer.stop()
        if self._cap is not None:
            self._cap.release()
            self._cap = None
        self._running = False
        if self._init_thread is not None and self._init_thread.isRunning():
            self._init_thread.wait(1000)
            self._init_thread = None

    def is_running(self) -> bool:
        return self._running

    def source_name(self) -> str:
        return f"本地摄像头 {self.camera_index}"
