"""文章接口测试用例。

包含：
- 文章创建参数化用例（数据来自 articles_data.yaml）；
- 完整的增删改查流程用例；
- 鉴权失败用例（无 token / 无效 token）；
- 更新参数化用例、列表查询、资源不存在等边界场景。
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
from common.http_client import HttpClient
from common.logger import logger
from utils.generator import random_content, random_title

DATA_FILE: Path = Path(__file__).resolve().parent.parent / "data" / "articles_data.yaml"


def _load_data() -> dict[str, Any]:
    """加载文章用例 YAML 数据。"""
    with open(DATA_FILE, encoding="utf-8") as f:
        return yaml.safe_load(f)


_DATA: dict[str, Any] = _load_data()
CREATE_CASES: list[dict[str, Any]] = _DATA["create_cases"]
AUTH_FAIL_CASES: list[dict[str, Any]] = _DATA["auth_fail_cases"]
UPDATE_CASES: list[dict[str, Any]] = _DATA["update_cases"]


# ----------------------------------------------------------------------
# 创建文章参数化用例
# ----------------------------------------------------------------------
@pytest.mark.articles
@pytest.mark.parametrize(
    "case",
    CREATE_CASES,
    ids=[c["case_id"] for c in CREATE_CASES],
)
def test_create_article(case: dict[str, Any], api_client: HttpClient) -> None:
    """参数化创建文章并校验。"""
    logger.info("执行用例: {} - 创建文章: {}", case["case_id"], case["title"])

    response = api_client.post(
        "/api/articles",
        json={"title": case["title"], "content": case["content"]},
    )
    assert_status_code(response, case["expect_status"])
    assert_business_code(response, case["expect_code"])

    # 校验返回数据包含正确的标题与自增 id
    article_id = assert_jsonpath(response, "$.data.id")
    assert_jsonpath(response, "$.data.title", case["title"])

    # 清理：删除刚创建的文章，避免影响其他用例
    api_client.delete(f"/api/articles/{article_id}")
    logger.info("用例通过: {}", case["case_id"])


# ----------------------------------------------------------------------
# 文章增删改查完整流程
# ----------------------------------------------------------------------
@pytest.mark.articles
@pytest.mark.smoke
def test_article_crud_flow(api_client: HttpClient) -> None:
    """文章增删改查完整流程：创建 -> 查询 -> 更新 -> 删除 -> 删除后查询。"""
    logger.info("开始执行文章 CRUD 完整流程")

    # 1. 创建文章
    title = random_title()
    content = random_content()
    resp = api_client.post("/api/articles", json={"title": title, "content": content})
    assert_status_code(resp, 200)
    assert_business_code(resp, 0)
    article_id = assert_jsonpath(resp, "$.data.id")

    # 2. 查询单个文章
    resp = api_client.get(f"/api/articles/{article_id}")
    assert_status_code(resp, 200)
    assert_jsonpath(resp, "$.data.id", article_id)
    assert_jsonpath(resp, "$.data.title", title)

    # 3. 更新文章
    new_title = random_title("已更新")
    new_content = random_content()
    resp = api_client.put(
        f"/api/articles/{article_id}",
        json={"title": new_title, "content": new_content},
    )
    assert_status_code(resp, 200)
    assert_business_code(resp, 0)
    assert_jsonpath(resp, "$.data.title", new_title)
    assert_jsonpath(resp, "$.data.content", new_content)

    # 4. 删除文章
    resp = api_client.delete(f"/api/articles/{article_id}")
    assert_status_code(resp, 200)
    assert_business_code(resp, 0)

    # 5. 删除后再次查询应返回 404
    resp = api_client.get(f"/api/articles/{article_id}")
    assert_status_code(resp, 404)
    assert_business_code(resp, 1003)

    logger.info("文章 CRUD 完整流程通过")


# ----------------------------------------------------------------------
# 文章更新参数化用例
# ----------------------------------------------------------------------
@pytest.mark.articles
@pytest.mark.parametrize(
    "case",
    UPDATE_CASES,
    ids=[c["case_id"] for c in UPDATE_CASES],
)
def test_update_article(case: dict[str, Any], api_client: HttpClient) -> None:
    """先创建文章，再按参数化数据更新并校验。"""
    logger.info("执行用例: {} - 更新文章", case["case_id"])

    # 前置：创建一篇待更新的文章
    resp = api_client.post(
        "/api/articles",
        json={"title": random_title("待更新"), "content": random_content()},
    )
    article_id = assert_jsonpath(resp, "$.data.id")

    # 执行更新
    resp = api_client.put(
        f"/api/articles/{article_id}",
        json={"title": case["title"], "content": case["content"]},
    )
    assert_status_code(resp, case["expect_status"])
    assert_business_code(resp, case["expect_code"])
    assert_jsonpath(resp, "$.data.title", case["title"])

    # 清理
    api_client.delete(f"/api/articles/{article_id}")
    logger.info("用例通过: {}", case["case_id"])


# ----------------------------------------------------------------------
# 文章列表查询与关键字搜索
# ----------------------------------------------------------------------
@pytest.mark.articles
def test_list_and_search_articles(api_client: HttpClient) -> None:
    """文章列表分页查询与关键字搜索。"""
    logger.info("执行用例: 文章列表与搜索")

    # 前置：创建一篇带特定关键字的文章
    keyword = "列表搜索关键字"
    resp = api_client.post(
        "/api/articles",
        json={"title": f"{keyword}-{random_title()}", "content": random_content()},
    )
    article_id = assert_jsonpath(resp, "$.data.id")

    # 列表查询：断言能取到 total 且 articles 为列表
    resp = api_client.get("/api/articles", params={"page": 1, "size": 10})
    assert_status_code(resp, 200)
    assert_business_code(resp, 0)
    assert_jsonpath(resp, "$.data.total")
    assert_jsonpath(resp, "$.data.articles")

    # 关键字搜索：断言至少能搜到刚创建的文章
    resp = api_client.get("/api/articles", params={"keyword": keyword})
    assert_status_code(resp, 200)
    total = assert_jsonpath(resp, "$.data.total")
    assert total >= 1, f"关键字搜索结果为空，期望 >=1，实际 {total}"

    # 清理
    api_client.delete(f"/api/articles/{article_id}")
    logger.info("用例通过: 文章列表与搜索")


# ----------------------------------------------------------------------
# 资源不存在边界场景
# ----------------------------------------------------------------------
@pytest.mark.articles
def test_get_article_not_found(api_client: HttpClient) -> None:
    """查询不存在的文章应返回 404。"""
    logger.info("执行用例: 查询不存在的文章")
    resp = api_client.get("/api/articles/999999")
    assert_status_code(resp, 404)
    assert_business_code(resp, 1003)
    logger.info("用例通过: 查询不存在的文章")


# ----------------------------------------------------------------------
# 鉴权失败用例（无 token / 无效 token / 无 token 创建）
# ----------------------------------------------------------------------
@pytest.mark.auth
@pytest.mark.parametrize(
    "case",
    AUTH_FAIL_CASES,
    ids=[c["case_id"] for c in AUTH_FAIL_CASES],
)
def test_articles_auth_fail(
    case: dict[str, Any],
    base_url: str,
    auth_token: str,
) -> None:
    """鉴权失败场景参数化用例。"""
    logger.info("执行用例: {} - {}", case["case_id"], case["name"])

    # 根据 use_token / override_token 决定携带的凭证
    token: str | None = None
    if case.get("use_token"):
        token = case.get("override_token") or auth_token

    client = HttpClient(base_url=base_url, token=token)
    try:
        method: str = case["method"]
        path: str = case["path"]
        json_body: dict[str, Any] | None = case.get("body")
        resp = client.request(method, path, json=json_body)
        assert_status_code(resp, case["expect_status"])
        assert_business_code(resp, case["expect_code"])
    finally:
        client.close()

    logger.info("用例通过: {}", case["case_id"])
