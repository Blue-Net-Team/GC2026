"""
文件 hash 工具
====
提供轻量的文件内容摘要计算，用于配置文件热加载等场景。
"""

import hashlib
from pathlib import Path

from loguru import logger

_log = logger.bind(module="file_hash")


def compute_file_hash(path: str) -> str | None:
    """计算文件内容的 SHA-256 hash，文件不存在或读取失败时返回 None。"""
    file_path = Path(path)
    if not file_path.exists():
        return None
    try:
        return hashlib.sha256(file_path.read_bytes()).hexdigest()
    except Exception as e:
        _log.error(f"计算文件 hash 失败: {e}")
        return None
