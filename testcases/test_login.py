"""登录接口数据驱动测试用例。

用例数据来源于 ``data/login_data.yaml``，通过 ``pytest.mark.parametrize`` 加载，
覆盖登录成功、密码错误、用户不存在、参数校验失败等场景。
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml

from common.assertions import (
    assert_business_code,
    assert_jsonpath,
    assert_status_code,
)
from common.logger import logger

# 定位数据文件
DATA_FILE: Path = Path(__file__).resolve().parent.parent / "data" / "login_data.yaml"


def _load_cases() -> list[dict[str, Any]]:
    """从 YAML 加载登录用例数据。"""
    with open(DATA_FILE, encoding="utf-8") as f:
        return yaml.safe_load(f)["testcases"]


# 模块加载时读取一次，供 parametrize 使用
_CASES: list[dict[str, Any]] = _load_cases()


@pytest.mark.login
@pytest.mark.parametrize(
    "case",
    _CASES,
    ids=[c["case_id"] for c in _CASES],
)
def test_login(case: dict[str, Any], no_auth_client: Any) -> None:
    """登录接口参数化用例。

    断言内容：
    - HTTP 状态码符合预期；
    - 业务码 code 符合预期；
    - 可选：JSONPath 能取到关键值；
    - 可选：指定字段值符合预期。
    """
    logger.info("执行用例: {} - {}", case["case_id"], case["name"])

    response = no_auth_client.post(
        "/api/login",
        json={"username": case["username"], "password": case["password"]},
    )

    # 状态码与业务码断言
    assert_status_code(response, case["expect_status"])
    assert_business_code(response, case["expect_code"])

    # 可选：JSONPath 取值断言（例如登录成功需返回 token）
    expect_jsonpath = case.get("expect_jsonpath")
    if expect_jsonpath:
        assert_jsonpath(response, expect_jsonpath)

    # 可选：字段值断言（使用 JSONPath 支持嵌套字段）
    expect_field: dict[str, Any] | None = case.get("expect_field")
    if expect_field:
        assert_jsonpath(response, expect_field["jsonpath"], expect_field["value"])

    logger.info("用例通过: {}", case["case_id"])
