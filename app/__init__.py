r"""
Copyright (C) 2025 IVEN-CN(He Yunfeng)

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

import sys

import click

from app.main import main

__version__ = "0.1.0"


@click.command()
@click.option("--debug", is_flag=True, default=False, help="启用调试日志")
def cli(debug: bool) -> None:
    """启动 GC2026 桌面调参应用"""
    sys.exit(main(debug=debug))
