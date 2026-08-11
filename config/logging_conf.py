"""日志初始化配置。

基于 loguru 统一配置日志输出：控制台彩色输出 + 按天轮转的文件日志。
该模块在 ``common.logger`` 中被调用，保证全局只初始化一次。
"""
from __future__ import annotations

import sys
from pathlib import Path

from loguru import logger

from config.settings import get_settings


def setup_logging() -> None:
    """初始化 loguru 日志。

    - 移除默认 handler，避免重复输出；
    - 控制台输出带颜色，便于本地调试；
    - 文件日志按天轮转并保留 7 天，统一存放在 ``LOG_DIR`` 目录。
    """
    settings = get_settings()
    log_dir = Path(settings.LOG_DIR)
    log_dir.mkdir(parents=True, exist_ok=True)

    # 清除 loguru 默认 handler
    logger.remove()

    # 控制台输出：简洁格式 + 彩色
    logger.add(
        sys.stderr,
        level=settings.LOG_LEVEL,
        format=(
            "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | "
            "<level>{level: <8}</level> | "
            "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - "
            "<level>{message}</level>"
        ),
        enqueue=True,
        backtrace=False,
        diagnose=False,
    )

    # 文件输出：完整格式 + 按天轮转
    logger.add(
        log_dir / "autotest_{time:YYYY-MM-DD}.log",
        level=settings.LOG_LEVEL,
        format=(
            "{time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <8} | "
            "{name}:{function}:{line} - {message}"
        ),
        rotation="00:00",  # 每天 0 点轮转
        retention="7 days",  # 保留 7 天
        encoding="utf-8",
        enqueue=True,
        backtrace=True,
        diagnose=True,
    )
