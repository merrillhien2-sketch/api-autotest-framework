"""全局 pytest 配置与公共 fixture。

职责：
- session 级启动内置 Mock 服务（uvicorn 后台线程 + 随机端口），保证 ``pytest`` 即可跑通；
- 提供已登录的 ``api_client`` 与未登录的 ``no_auth_client`` fixture；
- 向 pytest-html 报告注入环境元数据；
- 统一项目根目录到 sys.path，保证包导入稳定。
"""
from __future__ import annotations

import asyncio
import platform
import socket
import sys
import threading
import time
from pathlib import Path
from typing import Any

import pytest
import requests
import uvicorn

# 将项目根目录加入 sys.path，保证 ``from config / common / ...`` 可导入
ROOT_DIR: Path = Path(__file__).resolve().parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from common.auth import AuthHelper  # noqa: E402
from common.http_client import HttpClient  # noqa: E402
from common.logger import logger  # noqa: E402
from config.settings import get_settings  # noqa: E402
from mock_server.app import app as mock_app  # noqa: E402


# ----------------------------------------------------------------------
# Mock 服务生命周期管理
# ----------------------------------------------------------------------
def _find_free_port() -> int:
    """让操作系统分配一个可用端口。"""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _wait_for_server(base_url: str, timeout: float = 30.0) -> None:
    """轮询健康检查接口，直到服务就绪或超时。"""
    deadline = time.time() + timeout
    last_error: Exception | None = None
    health_url = f"{base_url}/api/health"
    while time.time() < deadline:
        try:
            response = requests.get(health_url, timeout=1.0)
            if response.status_code == 200:
                return
        except requests.RequestException as exc:
            last_error = exc
        time.sleep(0.2)
    raise RuntimeError(f"Mock 服务在 {timeout}s 内未就绪: {last_error}")


@pytest.fixture(scope="session")
def mock_server() -> str:
    """启动 Mock 服务并返回其 base_url。

    使用 uvicorn 在后台线程中启动 FastAPI 应用，端口随机分配，
    避免与本地其他服务冲突。测试结束后优雅关闭。
    """
    port = _find_free_port()
    base_url = f"http://127.0.0.1:{port}"

    config = uvicorn.Config(
        mock_app,
        host="127.0.0.1",
        port=port,
        log_level="warning",
        access_log=False,
        lifespan="on",
    )
    server = uvicorn.Server(config)
    # 在后台线程中运行，禁用信号处理（仅主线程可用）
    server.install_signal_handlers = lambda: None  # type: ignore[assignment]

    thread = threading.Thread(
        target=lambda: asyncio.run(server.serve()),
        name="mock-uvicorn",
        daemon=True,
    )
    thread.start()

    logger.info("正在启动 Mock 服务: {}", base_url)
    _wait_for_server(base_url)
    logger.info("Mock 服务已就绪: {}", base_url)

    yield base_url

    server.should_exit = True
    thread.join(timeout=8)
    logger.info("Mock 服务已关闭")


@pytest.fixture(scope="session")
def base_url(mock_server: str) -> str:
    """被测服务基础地址，供需要直接发请求的场景使用。"""
    return mock_server


@pytest.fixture(scope="session")
def auth_token(base_url: str) -> str:
    """session 级登录并返回 token，供后续鉴权请求复用。"""
    settings = get_settings()
    helper = AuthHelper(base_url)
    token = helper.login(settings.TEST_USERNAME, settings.TEST_PASSWORD)
    logger.info("会话级 token 已获取")
    return token


@pytest.fixture()
def api_client(base_url: str, auth_token: str) -> HttpClient:
    """每个用例独立的、已携带鉴权 token 的 HTTP 客户端。"""
    client = HttpClient(base_url=base_url, token=auth_token)
    yield client
    client.close()


@pytest.fixture()
def no_auth_client(base_url: str) -> HttpClient:
    """未携带 token 的 HTTP 客户端，用于鉴权失败类用例。"""
    client = HttpClient(base_url=base_url, token=None)
    yield client
    client.close()


# ----------------------------------------------------------------------
# 数据驱动辅助：加载 YAML / CSV 用例数据
# ----------------------------------------------------------------------
@pytest.fixture(scope="session")
def data_dir() -> Path:
    """返回数据文件目录路径。"""
    return ROOT_DIR / "data"


# ----------------------------------------------------------------------
# 报告钩子：向 HTML 报告注入环境元数据
# ----------------------------------------------------------------------
def pytest_configure(config: pytest.Config) -> None:
    """在报告的 Environment 区块展示关键配置。"""
    settings = get_settings()
    metadata: dict[str, Any] = {
        "项目": "接口自动化测试框架",
        "Python": sys.version.split()[0],
        "Platform": platform.platform(),
        "BASE_URL": settings.BASE_URL,
        "TIMEOUT": f"{settings.TIMEOUT}s",
        "MAX_RETRIES": settings.MAX_RETRIES,
        "TEST_USERNAME": settings.TEST_USERNAME,
    }
    _inject_metadata(config, metadata)


def _inject_metadata(config: pytest.Config, metadata: dict[str, Any]) -> None:
    """兼容不同版本 pytest-metadata 注入环境元数据。

    pytest-metadata 3.x 使用 ``config.stash[metadata_key]``，
    旧版本使用 ``config._metadata``，此处做兼容处理。
    """
    # 优先使用 pytest-metadata 3.x 的 stash 机制
    try:
        from pytest_metadata.plugin import metadata_key

        stash = config.stash[metadata_key]
        if isinstance(stash, dict):
            stash.update(metadata)
            return
    except Exception:  # noqa: BLE001
        pass
    # 回退：旧版本 config._metadata
    existing = getattr(config, "_metadata", None)
    if isinstance(existing, dict):
        existing.update(metadata)
    else:
        try:
            config._metadata = metadata  # type: ignore[attr-defined]
        except Exception:  # noqa: BLE001
            pass


def pytest_html_report_title(report: Any) -> None:
    """自定义 HTML 报告标题。"""
    report.title = "接口自动化测试报告"


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item: Any, call: Any) -> Any:
    """在用例失败时，将响应相关上下文附加到 HTML 报告。"""
    outcome = yield
    report = outcome.get_result()
    if report.when == "call" and report.failed:
        # 从用例上下文中提取最近一次响应信息（若测试中通过 setattr 记录）
        last_response = getattr(item, "_last_response_info", None)
        if last_response:
            extra = getattr(report, "extra", [])
            try:
                # pytest-html 的 extra 列表
                from pytest_html import extras  # type: ignore

                extra.append(extras.text(last_response, name="响应信息"))
            except Exception:  # noqa: BLE001
                pass
