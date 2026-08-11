"""用户接口测试用例。

包含：
- CSV 数据驱动的用户创建参数化用例（data/users.csv + pandas 加载）；
- 用户增删改查完整流程；
- 重复用户名、参数校验、删除自身被禁止等边界场景。
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd
import pytest

from common.assertions import (
    assert_business_code,
    assert_jsonpath,
    assert_status_code,
)
from common.http_client import HttpClient
from common.logger import logger
from utils.generator import (
    random_email,
    random_nickname,
    random_string,
    random_username,
)

CSV_FILE: Path = Path(__file__).resolve().parent.parent / "data" / "users.csv"


def _load_csv_cases() -> list[dict[str, Any]]:
    """使用 pandas 读取 CSV 用例数据，并将 ``{rand}`` 占位符替换为随机串。

    替换占位符可保证每次运行用户名唯一，避免重复创建冲突。
    """
    df = pd.read_csv(CSV_FILE, dtype=str)
    cases: list[dict[str, Any]] = []
    for _, row in df.iterrows():
        case = {col: str(row[col]) for col in df.columns}
        case["username"] = case["username"].replace("{rand}", random_string(6))
        cases.append(case)
    return cases


_CSV_CASES: list[dict[str, Any]] = _load_csv_cases()


# ----------------------------------------------------------------------
# CSV 数据驱动：参数化创建用户
# ----------------------------------------------------------------------
@pytest.mark.users
@pytest.mark.parametrize(
    "case",
    _CSV_CASES,
    ids=[c["case_id"] for c in _CSV_CASES],
)
def test_create_user(case: dict[str, Any], api_client: HttpClient) -> None:
    """CSV 数据驱动：创建用户并校验。"""
    logger.info("执行用例: {} - 创建用户: {}", case["case_id"], case["username"])

    response = api_client.post(
        "/api/users",
        json={
            "username": case["username"],
            "password": "Test123456",
            "email": case["email"],
            "nickname": case["nickname"],
        },
    )
    assert_status_code(response, int(case["expect_status"]))
    assert_business_code(response, int(case["expect_code"]))
    # 创建成功时校验返回用户名
    if int(case["expect_code"]) == 0:
        assert_jsonpath(response, "$.data.username", case["username"])
        # 响应不应包含密码字段
        body = response.json()
        assert "password" not in body.get("data", {}), "响应数据不应包含密码字段"

    # 清理：删除创建的用户（避免影响后续用例）
    api_client.delete(f"/api/users/{case['username']}")
    logger.info("用例通过: {}", case["case_id"])


# ----------------------------------------------------------------------
# 用户增删改查完整流程
# ----------------------------------------------------------------------
@pytest.mark.users
@pytest.mark.smoke
def test_user_crud_flow(api_client: HttpClient) -> None:
    """用户增删改查完整流程：创建 -> 查询 -> 更新 -> 删除 -> 删除后查询。"""
    logger.info("开始执行用户 CRUD 完整流程")

    username = random_username("crud")
    email = random_email()

    # 1. 创建用户
    resp = api_client.post(
        "/api/users",
        json={
            "username": username,
            "password": "Pass1234",
            "email": email,
            "nickname": random_nickname(),
        },
    )
    assert_status_code(resp, 200)
    assert_business_code(resp, 0)
    assert_jsonpath(resp, "$.data.username", username)

    # 2. 查询单个用户
    resp = api_client.get(f"/api/users/{username}")
    assert_status_code(resp, 200)
    assert_jsonpath(resp, "$.data.username", username)
    assert_jsonpath(resp, "$.data.email", email)

    # 3. 更新用户（邮箱、昵称）
    new_email = random_email()
    new_nickname = random_nickname()
    resp = api_client.put(
        f"/api/users/{username}",
        json={"email": new_email, "nickname": new_nickname},
    )
    assert_status_code(resp, 200)
    assert_business_code(resp, 0)
    assert_jsonpath(resp, "$.data.email", new_email)
    assert_jsonpath(resp, "$.data.nickname", new_nickname)

    # 4. 删除用户
    resp = api_client.delete(f"/api/users/{username}")
    assert_status_code(resp, 200)
    assert_business_code(resp, 0)

    # 5. 删除后查询应 404
    resp = api_client.get(f"/api/users/{username}")
    assert_status_code(resp, 404)
    assert_business_code(resp, 1005)

    logger.info("用户 CRUD 完整流程通过")


# ----------------------------------------------------------------------
# 边界场景：重复用户名
# ----------------------------------------------------------------------
@pytest.mark.users
def test_create_duplicate_user(api_client: HttpClient) -> None:
    """重复用户名创建应返回 400 + 业务码 1004。"""
    logger.info("执行用例: 重复用户名创建")
    username = random_username("dup")

    # 第一次创建成功
    resp = api_client.post(
        "/api/users",
        json={
            "username": username,
            "password": "Pass1234",
            "email": random_email(),
            "nickname": random_nickname(),
        },
    )
    assert_status_code(resp, 200)

    # 第二次创建同名应失败
    resp = api_client.post(
        "/api/users",
        json={
            "username": username,
            "password": "Pass1234",
            "email": random_email(),
            "nickname": random_nickname(),
        },
    )
    assert_status_code(resp, 400)
    assert_business_code(resp, 1004)

    # 清理
    api_client.delete(f"/api/users/{username}")
    logger.info("用例通过: 重复用户名创建")


# ----------------------------------------------------------------------
# 边界场景：参数校验失败（用户名过短）
# ----------------------------------------------------------------------
@pytest.mark.users
def test_create_user_short_username(api_client: HttpClient) -> None:
    """用户名短于 3 位应触发参数校验 422。"""
    logger.info("执行用例: 用户名过短参数校验")
    resp = api_client.post(
        "/api/users",
        json={
            "username": "ab",
            "password": "Pass1234",
            "email": "short@autotest.com",
        },
    )
    assert_status_code(resp, 422)
    assert_business_code(resp, 422)
    logger.info("用例通过: 用户名过短参数校验")


# ----------------------------------------------------------------------
# 边界场景：禁止删除当前登录用户自身
# ----------------------------------------------------------------------
@pytest.mark.users
@pytest.mark.auth
def test_delete_self_forbidden(api_client: HttpClient) -> None:
    """删除当前登录用户（admin）应被禁止，返回 400 + 业务码 1006。"""
    logger.info("执行用例: 禁止删除自身")
    from config.settings import get_settings

    current_user = get_settings().TEST_USERNAME
    resp = api_client.delete(f"/api/users/{current_user}")
    assert_status_code(resp, 400)
    assert_business_code(resp, 1006)
    logger.info("用例通过: 禁止删除自身")


# ----------------------------------------------------------------------
# 边界场景：查询不存在的用户
# ----------------------------------------------------------------------
@pytest.mark.users
def test_get_user_not_found(api_client: HttpClient) -> None:
    """查询不存在的用户应返回 404。"""
    logger.info("执行用例: 查询不存在的用户")
    resp = api_client.get("/api/users/no_such_user_xyz")
    assert_status_code(resp, 404)
    assert_business_code(resp, 1005)
    logger.info("用例通过: 查询不存在的用户")
