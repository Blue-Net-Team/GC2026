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
import subprocess

def connect_to_wifi(ssid:str, password:str, reflash:bool=False) -> tuple[bool, str]:
    """
    连接到指定的WiFi网络
    ----
    Args:
        ssid(str): WiFi网络的SSID
        password(str): WiFi网络的密码
        reflash(bool): 是否强制刷新WiFi列表，默认值为False
    Returns:
        tuple[bool, str]: 返回一个元组，第一个元素为bool类型，表示是否连接成功，第二个元素为str类型，表示错误信息
    """
    try:
        if reflash:
            # 强制刷新WiFi列表
            subprocess.run(
                ["sudo", "nmcli", "device", "wifi", "rescan"],
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
        # 连接到指定的SSID
        subprocess.run(
            ["sudo", "nmcli", "device", "wifi", "connect", ssid, "password", password],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        return True, ""
    except subprocess.CalledProcessError as e:
        if e.args[0] == 1:
            return False, "扫描频率过于频繁"
        elif e.args[0] == 10:
            return False, f"没有找到ssid为{ssid}的wifi"
        else:
            return False, e.stderr
