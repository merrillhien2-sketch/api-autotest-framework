"""HTTP 客户端封装。

基于 ``requests.Session`` 封装，提供：
- 统一超时控制；
- 幂等请求的自动重试（基于 urllib3 Retry）；
- 请求/响应的统一日志输出（loguru）；
- 自动携带 ``Authorization`` 请求头；
- 对 GET/POST/PUT/DELETE 的便捷方法。
"""
from __future__ import annotations

from typing import Any

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from common.logger import logger
from config.settings import get_settings


class HttpClient:
    """封装后的 HTTP 客户端。

    Parameters
    ----------
    base_url:
        被测服务的基础地址，例如 ``http://127.0.0.1:8000``。
    token:
        鉴权 token，设置后会自动以 ``Authorization: Bearer <token>`` 形式携带。
    timeout:
        单次请求超时时间（秒），默认读取配置 ``TIMEOUT``。
    """

    def __init__(
        self,
        base_url: str = "",
        token: str | None = None,
        timeout: float | None = None,
    ) -> None:
        settings = get_settings()
        self.base_url: str = base_url.rstrip("/")
        self.token: str | None = token
        self.timeout: float = timeout if timeout is not None else settings.TIMEOUT

        # 创建 Session 并挂载带重试策略的 Adapter
        self.session: requests.Session = requests.Session()
        retry = Retry(
            total=settings.MAX_RETRIES,
            connect=settings.MAX_RETRIES,
            read=settings.MAX_RETRIES,
            backoff_factor=settings.RETRY_BACKOFF,
            status_forcelist=list(settings.RETRY_STATUS_CODES),
            allowed_methods=frozenset(["GET", "PUT", "DELETE", "HEAD", "OPTIONS"]),
            raise_on_status=False,
        )
        adapter = HTTPAdapter(max_retries=retry)
        self.session.mount("http://", adapter)
        self.session.mount("https://", adapter)

    # ------------------------------------------------------------------
    # 内部工具方法
    # ------------------------------------------------------------------
    def _build_url(self, path: str) -> str:
        """拼接完整 URL；若 path 已是完整地址则直接返回。"""
        if path.startswith("http://") or path.startswith("https://"):
            return path
        if not path.startswith("/"):
            path = "/" + path
        return f"{self.base_url}{path}"

    def _build_headers(self, headers: dict[str, str] | None = None) -> dict[str, str]:
        """构建请求头，自动注入鉴权信息。"""
        default_headers: dict[str, str] = {"Accept": "application/json"}
        if self.token:
            default_headers["Authorization"] = f"Bearer {self.token}"
        if headers:
            default_headers.update(headers)
        return default_headers

    def request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json: Any | None = None,
        data: Any | None = None,
        headers: dict[str, str] | None = None,
        timeout: float | None = None,
        **kwargs: Any,
    ) -> requests.Response:
        """发送 HTTP 请求并记录日志。

        Returns
        -------
        requests.Response
            原始响应对象，由调用方自行断言。
        """
        url = self._build_url(path)
        final_headers = self._build_headers(headers)
        # 记录请求日志（敏感头脱敏：只显示是否存在 Authorization）
        logger.info(
            "=> {} {} | params={} | json={}",
            method.upper(),
            url,
            params,
            json if json is not None else data,
        )

        try:
            response = self.session.request(
                method=method.upper(),
                url=url,
                params=params,
                json=json,
                data=data,
                headers=final_headers,
                timeout=timeout if timeout is not None else self.timeout,
                **kwargs,
            )
        except requests.RequestException as exc:
            logger.error("请求异常: {} {} | {}", method.upper(), url, exc)
            raise

        # 记录响应日志
        logger.info(
            "<= {} | status={} | elapsed={:.3f}s | body={}",
            method.upper(),
            response.status_code,
            response.elapsed.total_seconds(),
            self._truncate(response.text),
        )
        return response

    @staticmethod
    def _truncate(text: str, max_len: int = 1000) -> str:
        """截断过长的响应体，避免日志爆掉。"""
        if not text:
            return ""
        return text if len(text) <= max_len else text[:max_len] + "...(truncated)"

    # ------------------------------------------------------------------
    # 便捷方法
    # ------------------------------------------------------------------
    def get(self, path: str, **kwargs: Any) -> requests.Response:
        return self.request("GET", path, **kwargs)

    def post(self, path: str, **kwargs: Any) -> requests.Response:
        return self.request("POST", path, **kwargs)

    def put(self, path: str, **kwargs: Any) -> requests.Response:
        return self.request("PUT", path, **kwargs)

    def delete(self, path: str, **kwargs: Any) -> requests.Response:
        return self.request("DELETE", path, **kwargs)

    def patch(self, path: str, **kwargs: Any) -> requests.Response:
        return self.request("PATCH", path, **kwargs)

    def update_token(self, token: str) -> None:
        """更新鉴权 token（例如登录后重新设置）。"""
        self.token = token
        logger.debug("HTTP 客户端 token 已更新")

    def close(self) -> None:
        """关闭底层 Session，释放连接池。"""
        self.session.close()
