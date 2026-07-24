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
import asyncio
import sys

import cv2
import yaml

from ImgTrans import SendImgUDP
from ImgTrans.ImgTrans import LoadWebCam, NeedReConnect
from utils import Cap
from loguru import logger

_log = logger.bind(module="img_trans")


def _load_system_config(path: str = "config.yaml") -> dict:
    """从配置文件中读取 system 段，失败时返回空字典。"""
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        return data.get("system", {}) if isinstance(data, dict) else {}
    except Exception:
        return {}


async def main_linux():
    """Linux平台的主函数"""
    system = _load_system_config()
    interface = str(system.get("udp_interface", ""))
    camera_name = str(system.get("camera_name", "icspring camera"))
    stream = await SendImgUDP.create(interface, 4444)
    cap = Cap(camera_name=camera_name)

    # 等待连接
    _log.info(f"等待连接... 当前ip: {stream.host}")
    while True:
        if await stream.connecting():
            _log.info(f"连接成功，对端ip: {stream.clients_ip}")
            break
    
    # 主循环
    while True:
        try:
            img = cap.read()[1]
            if img is None:
                _log.warning("读取到空图片")
                continue
            await stream.send(img)
        except NeedReConnect:
            while True:
                if await stream.connecting():
                    break

async def main_windows():
    """Windows平台的主函数"""
    cap = LoadWebCam("192.168.123.6", 4444, "192.168.123.2")
    cv2.namedWindow("img", cv2.WINDOW_NORMAL)
    for img in cap:
        if img is None:
            continue
        cv2.imshow("img", img)
        if cv2.waitKey(1) == ord("q"):
            break

async def main():
    """主函数"""
    if sys.platform == "linux":
        await main_linux()
    elif sys.platform == "win32":
        await main_windows()

def cli():
    asyncio.run(main())
