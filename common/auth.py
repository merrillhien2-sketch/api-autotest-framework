"""鉴权助手。

负责调用被测服务的登录接口换取 JWT token，
并对外提供鉴权请求头。测试中由 conftest 调用以完成登录态准备。
"""
from __future__ import annotations

import requests

from common.logger import logger
from config.settings import get_settings


class AuthError(Exception):
    """鉴权相关异常。"""


class AuthHelper:
    """登录与 token 管理助手。

    Parameters
    ----------
    base_url:
        被测服务基础地址。
    """

    def __init__(self, base_url: str) -> None:
        self.base_url: str = base_url.rstrip("/")
        self._token: str | None = None

    def login(self, username: str | None = None, password: str | None = None) -> str:
        """调用登录接口获取 token。

        账号密码默认从配置读取，也可显式传入。
        """
        settings = get_settings()
        username = username or settings.TEST_USERNAME
        password = password or settings.TEST_PASSWORD

        url = f"{self.base_url}/api/login"
        logger.info("开始登录: {} | 用户={}", url, username)
        try:
            response = requests.post(
                url,
                json={"username": username, "password": password},
                timeout=settings.TIMEOUT,
            )
        except requests.RequestException as exc:
            raise AuthError(f"登录请求失败: {exc}") from exc

        if response.status_code != 200:
            raise AuthError(
                f"登录失败: HTTP {response.status_code} | 响应: {response.text}"
            )

        body = response.json()
        token = body.get("data", {}).get("token")
        if not token:
            raise AuthError(f"登录响应未包含 token: {body}")

        self._token = token
        logger.info("登录成功，已获取 token")
        return token

    @property
    def token(self) -> str | None:
        """当前持有的 token。"""
        return self._token

    def auth_headers(self) -> dict[str, str]:
        """返回带鉴权信息的请求头字典。"""
        if not self._token:
            raise AuthError("尚未登录，无可用 token")
        return {"Authorization": f"Bearer {self._token}"}
