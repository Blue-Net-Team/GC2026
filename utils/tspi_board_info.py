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
def get_CPU_temp():
    """
    获取CPU温度
    ----
    Returns:
        temp: CPU温度
    """
    with open("/sys/class/thermal/thermal_zone0/temp", "r") as f:
        temp = int(f.read()) / 1000
    return temp

def get_GPU_temp():
    """
    获取GPU温度
    ----
    Returns:
        temp: GPU温度
    """
    try:
        with open("/sys/class/thermal/thermal_zone1/temp", "r") as f:
            temp = int(f.read()) / 1000
    except FileNotFoundError:
        temp = None
    return temp
