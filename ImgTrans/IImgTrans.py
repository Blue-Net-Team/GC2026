"""
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
"""
import socket
import struct
try:
    import fcntl
except:
    pass

import cv2


class SendImg(object):
    """
    服务端视频发送接口
    """
    # 服务端ip
    _host:str = ""
    host_ip:str = ""
    # 服务端端口
    _interface:str = ""

    @property
    def host(self):
        return self._host

    @property
    def interface(self):
        return self._interface

    @interface.setter
    def interface(self, value:str):
        self._interface = value
        self._host = self.get_ip_address(value)

    def __init__(self, interface:str, port:int=4444):
        """初始化
        ----
        Args:
            interface (str): 用于图传的网卡
            port (int): 端口号
        """
        self.is_open = False
        self.interface = interface
        self.port = port

    @staticmethod
    def get_ip_address(interface: str) -> str:
        """
        获取IP地址
        ----
        用于树莓派获取IP地址

        Args:
            interface (str): 网卡名称，lo为本地回环网卡，eth0为以太网网卡等
        Returns:
            ip (str): IP地址
        """
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            return socket.inet_ntoa(fcntl.ioctl(
                s.fileno(),
                0x8915,  # SIOCGIFADDR
                struct.pack('256s', interface[:15].encode('utf-8'))
            )[20:24])
        except:
            return ""

    def update_host(self):
        self._host = self.get_ip_address(self.interface)

    def connecting(self):
        """
        连接客户端
        ----
        """
        ...

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
        ...

    def close(self):
        """关闭连接"""
        ...


class ReceiveImg(cv2.VideoCapture):
    """
    接收视频流接口(客户端)
    """
    def __init__(self, host:str, port:int):
        """初始化
        ----
        Args:
            host (str): 主机IP地址
            port (int): 端口号
        """
        ...

    def read(self) -> tuple[bool, cv2.typing.MatLike]:
        """
        读取图像数据
        ----
        Returns:
            tuple (res, img): 是否读取成功，图像数据
        """
        ...

    def release(self):
        """释放资源"""
        ...
