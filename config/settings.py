"""全局配置模块。

使用 pydantic-settings 从 ``.env`` 文件与系统环境变量中读取配置，
统一管理 BASE_URL、超时、重试、测试账号、JWT 密钥等参数。
所有敏感信息（账号、密钥）一律通过环境变量注入，禁止在代码中硬编码。
"""
from __future__ import annotations

from functools import lru_cache
from typing import Any

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """全局配置项。

    所有字段均提供默认值，确保即便没有 ``.env`` 文件也能运行；
    实际部署/测试时通过 ``.env`` 或环境变量覆盖即可。
    """

    # ---- 被测服务基础配置 ----
    # 被测服务基础地址（conftest 启动 Mock 后会用实际端口覆盖该值）
    BASE_URL: str = "http://127.0.0.1:8000"
    # 请求统一超时时间（秒）
    TIMEOUT: float = 10.0

    # ---- HTTP 重试配置 ----
    # 最大重试次数（仅对幂等的 GET/PUT 请求生效）
    MAX_RETRIES: int = 2
    # 重试退避因子（指数退避: wait = backoff * (2 ** retry)）
    RETRY_BACKOFF: float = 0.5
    # 触发重试的 HTTP 状态码集合
    RETRY_STATUS_CODES: tuple[int, ...] = (500, 502, 503, 504)

    # ---- 测试账号（占位，实际从 .env 读取）----
    TEST_USERNAME: str = "admin"
    TEST_PASSWORD: str = "123456"

    # ---- JWT 鉴权配置（被测 Mock 服务使用）----
    JWT_SECRET: str = "change-me-in-production"
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRE_MINUTES: int = 60

    # ---- 日志配置 ----
    LOG_LEVEL: str = "INFO"
    LOG_DIR: str = "logs"

    # ---- 数据驱动文件目录 ----
    DATA_DIR: str = "data"

    # 允许 .env 中存在多余字段而不报错；统一使用 utf-8 编码
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=True,
    )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """获取全局配置单例。

    使用 ``lru_cache`` 保证整个进程只构造一次配置对象，
    既提升性能也避免重复读取环境变量。
    """
    return Settings()


def reload_settings(**overrides: Any) -> Settings:
    """重新加载配置并支持临时覆盖部分字段。

    主要用于测试场景下动态修改配置（例如覆盖 BASE_URL）。
    """
    get_settings.cache_clear()
    # 通过环境变量临时注入覆盖项
    import os

    for key, value in overrides.items():
        os.environ[key] = str(value)
    return get_settings()
