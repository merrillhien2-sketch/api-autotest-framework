"""日志单例封装。

对外暴露统一的 ``logger`` 对象，业务代码只需 ``from common.logger import logger``。
首次导入时自动完成日志初始化（仅一次），避免重复 add handler。
"""
from __future__ import annotations

from loguru import logger as _logger

from config.logging_conf import setup_logging

# 模块级标志：保证 setup_logging 只执行一次
_initialized: bool = False


def _ensure_initialized() -> None:
    """确保日志只初始化一次（线程安全的简单实现）。"""
    global _initialized
    if not _initialized:
        setup_logging()
        _initialized = True


# 导入即初始化，使用方直接拿到配置好的 logger
_ensure_initialized()

# 对外暴露的 logger 单例
logger = _logger
