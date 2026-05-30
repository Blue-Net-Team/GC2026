r"""
Copyright (C) 2025 IVEN-CN(He Yunfeng) and Anan-yy(Weng Kaiyi)

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with this program.  If not, see <https://www.gnu.org/licenses/>.

远程图传
====
该模块包含两个类：

`VideoStreaming`:
----
视频流传输类(服务端)

方法:
    - `__init__(self, host, port)`: 初始化，设置主机IP地址和端口号
    - `connecting(self)`: 连接客户端
    - `start(self)`: 开始传输视频流
    - `send(self, _img: cv2.typing.MatLike) -> bool`: 发送图像数据

`ReceiveImgTCP`:
----
接收视频流类(客户端)

方法:
    - `__init__(self, host, port)`: 初始化，设置主机IP地址和端口号
    - `read(self)`: 读取图像数据

注意:
----
服务端不能主动向客户端发送数据，只能等待客户端连接后发送数据
"""
import asyncio
import io
import socket
import struct
import cv2
import numpy as np
from ImgTrans.IImgTrans import ReceiveImg, SendImg
from loguru import logger

_log = logger.bind(module="ImgTrans")

try:
    import fcntl
except:
    pass

class NeedReConnect(Exception):
    """需要重新连接"""
    pass

class SendImgTCP(SendImg):
    """服务端视频发送"""

    def __init__(self, interface:str, port:int=4444):
        """初始化
        ----
        Args:
            interface (str): 主机发送图像的网口
            port (int): 端口号
        """
        super().__init__(interface, port)
        self.host_name = ""
        self.client_address = ""

        self.open_socket()

    def open_socket(self):
        if self.host and self.port:
            try:
                self.server_socket = socket.socket()
                self.server_socket.bind((self.host, self.port))
                self.server_socket.listen(5)
                self.server_socket.settimeout(0.05)
                self.connection = None
                self.connect = None
                self.stream = io.BytesIO()
                self.is_open = True
            except Exception as e:
                _log.error(f"Error: {e}")

    def connecting(self):
        def _connect(obj):
            try:
                obj.connection, obj.client_address = obj.server_socket.accept()
                obj.connect = obj.connection.makefile("wb")
                obj.host_name = socket.gethostname()
                obj.host_ip = socket.gethostbyname(obj.host_name)

                return True
            except socket.timeout:
                return False
        if self.is_open:
            return _connect(self)
        else:
            # 重新初始化
            self.open_socket()
            return _connect(self)

    def start(self) -> None:
        """
        开始传输视频流
        ----
        运行这个函数之前，必须先运行`connecting`函数
        """
        _log.info(f"Client Host Name: {self.host_name}")
        _log.info(f"Connection from: {self.client_address}")
        _log.info("Streaming...")

    def send(self, _img: cv2.typing.MatLike) -> bool:
        """
        发送图像数据
        ----
        运行这个函数之前，必须运行`connecting`函数

        Args:
            _img (cv2.typing.MatLike): 图像数据
        Returns:
            res (bool): 发送是否成功
        """
        if self.is_open:
            try:
                if self.connect is None:
                    raise ConnectionError("未连接到客户端")

                img_encode = cv2.imencode(".jpg", _img, [int(cv2.IMWRITE_JPEG_QUALITY), 70])[1]
                data_encode = np.array(img_encode)
                self.stream.write(data_encode) # type: ignore
                self.connect.write(struct.pack("<L", self.stream.tell()))
                self.connect.flush()
                self.stream.seek(0)
                self.connect.write(self.stream.read())
                self.stream.seek(0)
                self.stream.truncate()
                self.connect.write(struct.pack("<L", 0))
                return True
            except (ConnectionResetError, ConnectionAbortedError, BrokenPipeError) as e:
                _log.error(f"Connection error: {e}")
                self.close()
                raise NeedReConnect("连接已断开，请重新连接")
            except OSError as e:
                _log.error(f"OS error: {e}")
                self.close()
                raise NeedReConnect("连接已断开，请重新连接")
        else:
            return False

    def close(self):
        """关闭连接"""
        if self.is_open:
            if self.connect:
                try:
                    self.connect.close()
                except OSError as e:
                    _log.error(f"Error closing connect: {e}")
            if self.connection:
                try:
                    self.connection.close()
                except OSError as e:
                    _log.error(f"Error closing connection: {e}")
            if self.server_socket:
                try:
                    self.server_socket.close()
                except OSError as e:
                    _log.error(f"Error closing server_socket: {e}")
            self.is_open = False

class ReceiveImgTCP(ReceiveImg):
    """客户端接收视频流"""

    def __init__(self, host:str, port:int):
        """初始化"""
        super().__init__(host, port)
        self.host = host
        self.port = port
        try:
            self.client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.client_socket.connect((self.host, self.port))
            self.connection = self.client_socket.makefile("rb")
            self.stream_bytes = b" "

            _log.info("已连接到服务端：")
            _log.info(f"Host : {host}")
            _log.info("请按'q'退出图像传输!")
        except Exception as e:
            _log.error(f"Error: {e}")
            exit()

    def read(self):
        try:
            msg = self.connection.read(4096)
            self.stream_bytes += msg
            first = self.stream_bytes.find(b"\xff\xd8")
            last = self.stream_bytes.find(b"\xff\xd9")

            if first != -1 and last != -1:
                jpg = self.stream_bytes[first : last + 2]
                self.stream_bytes = self.stream_bytes[last + 2 :]
                image = cv2.imdecode(np.frombuffer(jpg, dtype=np.uint8), cv2.IMREAD_COLOR)
                return True, image

        except:
            _log.error("Error：连接出错！")
        return False, None

    def release(self):
        self.connection.close()
        self.client_socket.close()

class SendImgUDP(SendImg):
    """服务端视频发送(UDP)"""
    EOF_MARKER = b'EOF'
    BUFFER_SIZE = 65536  # UDP最大接收缓冲区大小
    CHUNK_MAX_SIZE = 1400  # 每个UDP分片的最大数据大小（适应以太网MTU）
    B_IP = ""
    _ip_lst = set()

    @property
    def clients_ip(self):
        """
        客户端ip列表
        """
        if self.B_IP:
            self._ip_lst.add(self.B_IP)
        return self._ip_lst

    @clients_ip.setter
    def clients_ip(self, ip:list):
        """
        设置客户端ip列表
        ----
        Args:
            ip (list): 客户端ip列表
        """
        self._ip_lst = set(ip)
        if self.B_IP:
            self._ip_lst.add(self.B_IP)

    def __init__(self, interface:str, port:int):
        """
        初始化
        ----
        Args:
            interface (str): 服务端开放的网卡设备
            port (int): 端口号
        """
        super().__init__(interface, port)
        self.server_socket = None
    
    @classmethod
    async def create(cls, interface:str, port:int):
        """
        异步创建对象
        ----
        Args:
            interface (str): 服务端开放的网卡设备
            port (int): 端口号
        Returns:
            SendImgUDP: 初始化完成的对象
        """
        instance = cls(interface, port)
        await instance.openSocket()
        return instance

    def _sync_open_socket(self):
        """同步版本：打开udp套接字"""
        self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        self.server_socket.bind((self.host, self.port))

    async def openSocket(self):
        """
        打开udp套接字
        """
        self._sync_open_socket()

    def _sync_connecting(self):
        """同步版本：等待udp客户端连接"""
        try:
            if self.server_socket is None:
                self._sync_open_socket()
            self.server_socket.settimeout(0.5)
            data, addr = self.server_socket.recvfrom(self.BUFFER_SIZE)
            if addr != (self.host, self.port) and data == b'connect':  # 避免回环请求
                _log.info(f"接收到来自 {addr} 的连接请求")
                # 获取B设备的IP和端口，固定向对端4444端口发送数据
                self.B_IP, _ = addr
                _log.info(f"已与对端建立连接，IP: {self.B_IP}, 端口: {self.port}")
                return True
        except socket.timeout:
            return False
        except OSError:
            self._sync_open_socket()
        except Exception as e:
            _log.error(str(e))
        return False

    async def connecting(self):
        """
        等待udp客户端连接，如果不等待，回向配置中的ip列表发送数据
        """
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self._sync_connecting)

    def _sync_send(self, _img: cv2.typing.MatLike) -> bool:
        """同步版本：发送图像数据（分片发送，避免UDP报文过大）"""
        if not self.clients_ip:
            return False

        _, img_encoded = cv2.imencode('.jpg', _img)
        img_data = img_encoded.tobytes()
        total_length = len(img_data)

        # 分片发送：每个UDP包携带 (total_length + offset) 8字节头部 + 数据块
        offset = 0
        while offset < total_length:
            chunk = img_data[offset:offset + self.CHUNK_MAX_SIZE]
            # 头部：总长度(4) + 偏移量(4)，接收端据此重组
            packet = struct.pack('!II', total_length, offset) + chunk
            for ip in self.clients_ip:
                self.server_socket.sendto(packet, (ip, self.port))
            offset += len(chunk)

        _log.info(f"已发送数据，总大小: {total_length} bytes，分片数: {(total_length + self.CHUNK_MAX_SIZE - 1) // self.CHUNK_MAX_SIZE}")
        return True

    async def send(self, _img: cv2.typing.MatLike) -> bool:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self._sync_send, _img)

    def close(self):
        self.server_socket.close()

class ReceiveImgUDP(ReceiveImg):
    def __init__(self, server_ip:str, port:int, self_ip:str):
        """
        初始化
        ----
        Args:
            server_ip (str): 服务端IP地址
            port (int): 开放的端口号
            self_ip (str): 本机IP地址
        """
        super().__init__(server_ip, port)
        self.host = server_ip
        self.port = port
        # 打开udp套接字
        self.client_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        # 绑定自身ip
        self.client_socket.bind((self_ip, self.port))
        # 发起连接请求
        self.client_socket.sendto(b'connect', (self.host, self.port))

        # 帧重组状态
        self._recv_buffer: bytearray | None = None
        self._recv_total: int = 0
        self._recv_received: int = 0

    def _reset_frame_state(self):
        """重置帧接收状态"""
        self._recv_buffer = None
        self._recv_total = 0
        self._recv_received = 0

    def read(self):
        try:
            self.client_socket.settimeout(1)

            # 循环接收分片，直到一帧数据收齐
            while True:
                data, addr = self.client_socket.recvfrom(65536)
                if addr != (self.host, self.port):
                    continue

                # 解析头部：total_length(4) + offset(4)
                total_length, offset = struct.unpack('!II', data[:8])
                chunk_data = data[8:]

                # 新帧开始（或总长度变化，说明收到新一帧的第一个分片）
                if self._recv_buffer is None or self._recv_total != total_length:
                    self._recv_buffer = bytearray(total_length)
                    self._recv_total = total_length
                    self._recv_received = 0

                # 将数据块复制到缓冲区对应位置
                end = min(offset + len(chunk_data), self._recv_total)
                self._recv_buffer[offset:end] = chunk_data[:end - offset]
                self._recv_received += (end - offset)

                # 帧接收完毕
                if self._recv_received >= self._recv_total:
                    break

            if self._recv_buffer is None:
                return False, None

            image_bytes = bytes(self._recv_buffer)
            self._reset_frame_state()

            nparr = np.frombuffer(image_bytes, np.uint8)
            frame = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
            if frame is not None:
                return True, frame
            return False, None

        except socket.timeout:
            # 超时则丢弃当前不完整的帧
            self._reset_frame_state()
            img = np.zeros((240, 320, 3), dtype=np.uint8)
            cv2.putText(
                img,
                "read img timeout",
                (20, 50),
                cv2.FONT_HERSHEY_SIMPLEX,
                1,
                (0, 0, 255),
                2
            )
            return False, img

    def release(self):
        self.client_socket.close()

class LoadWebCam:
    """读取远程图传的迭代器"""
    def __init__(self, server_ip:str, port:int, self_ip:str):
        """
        初始化
        ----
        Args:
            server_ip (str): 服务端IP地址
            port (int): 端口号
            self_ip (str): 本机IP地址
        """
        self.streaming = ReceiveImgUDP(server_ip, port, self_ip)

    def __iter__(self):
        return self

    def __next__(self):
        _, img = self.streaming.read()
        return img

    def release(self):
        """释放资源"""
        self.streaming.client_socket.close()
