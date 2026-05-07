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
from typing import Any, get_origin, get_args

def check_args(*args: tuple[Any, type]):
    """
    检查重载函数的参数类型
    ----
    Args:
        *args: 变量，类型组
    """
    for arg, arg_type in args:
        origin_type = get_origin(arg_type)
        if origin_type is list:
            item_type = get_args(arg_type)[0]
            if not (isinstance(arg, list) and all(isinstance(item, item_type) for item in arg)):
                return False, "Expected List[{item_type}], but got {arg}"
        else:
            if not isinstance(arg, arg_type):
                return False, "Expected {arg_type}, but got {arg}"
    return True, ""

