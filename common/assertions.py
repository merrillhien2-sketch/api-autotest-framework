"""响应断言助手。

提供一组语义化的断言函数，封装常用校验：
- 状态码断言；
- JSON 字段相等 / 存在性断言；
- JSONPath 取值断言；
- 响应耗时断言；
- 业务码断言。
断言失败时会抛出 ``AssertionError``，并在消息中带上实际响应内容，便于排查。
"""
from __future__ import annotations

from typing import Any

import requests

from common.logger import logger
from utils.extract import extract_jsonpath


def _safe_json(response: requests.Response) -> Any:
    """安全解析响应 JSON，失败时返回原始文本以便报错展示。"""
    try:
        return response.json()
    except ValueError:
        return None


def assert_status_code(response: requests.Response, expected: int) -> requests.Response:
    """断言 HTTP 状态码等于期望值。"""
    actual = response.status_code
    assert actual == expected, (
        f"状态码断言失败: 期望 {expected}, 实际 {actual} | 响应体: {response.text}"
    )
    logger.debug("状态码断言通过: {}", expected)
    return response


def assert_status_in(response: requests.Response, expected_codes: tuple[int, ...]) -> requests.Response:
    """断言 HTTP 状态码属于期望集合。"""
    actual = response.status_code
    assert actual in expected_codes, (
        f"状态码断言失败: 期望属于 {expected_codes}, 实际 {actual} | 响应体: {response.text}"
    )
    return response


def assert_json_field(response: requests.Response, field: str, expected: Any) -> requests.Response:
    """断言 JSON 顶层某字段等于期望值。

    Parameters
    ----------
    field:
        顶层字段名，例如 ``code``、``message``。
    expected:
        期望值。
    """
    body = _safe_json(response)
    assert isinstance(body, dict), f"响应不是 JSON 对象，无法取字段 '{field}': {response.text}"
    assert field in body, f"响应中不存在字段 '{field}': {body}"
    actual = body[field]
    assert actual == expected, (
        f"字段断言失败: {field} 期望 {expected!r}, 实际 {actual!r} | 完整响应: {body}"
    )
    logger.debug("字段断言通过: {} == {}", field, expected)
    return response


def assert_field_exists(response: requests.Response, field: str) -> requests.Response:
    """断言 JSON 顶层存在某字段（不校验值）。"""
    body = _safe_json(response)
    assert isinstance(body, dict), f"响应不是 JSON 对象: {response.text}"
    assert field in body, f"响应中不存在字段 '{field}': {body}"
    logger.debug("字段存在断言通过: {}", field)
    return response


def assert_jsonpath(
    response: requests.Response,
    expr: str,
    expected: Any | None = None,
    *,
    contains: bool = False,
) -> Any:
    """通过 JSONPath 取值并断言。

    Parameters
    ----------
    expr:
        JSONPath 表达式，例如 ``$.data.token``、``$.data[0].title``。
    expected:
        期望值；为 ``None`` 时仅校验能取到值。
    contains:
        为 True 时校验取到的值为列表且 ``expected`` 在其中。
    """
    body = _safe_json(response)
    values = extract_jsonpath(body, expr)
    assert values, f"JSONPath '{expr}' 未匹配到任何值 | 响应: {body}"

    actual = values[0] if len(values) == 1 else values
    if expected is not None:
        if contains:
            assert expected in values, (
                f"JSONPath '{expr}' 值 {values} 不包含 {expected!r}"
            )
        else:
            assert actual == expected, (
                f"JSONPath '{expr}' 期望 {expected!r}, 实际 {actual!r} | 响应: {body}"
            )
    logger.debug("JSONPath 断言通过: {} -> {}", expr, actual)
    return actual


def assert_response_time(response: requests.Response, max_seconds: float) -> None:
    """断言响应耗时不超过阈值（秒）。"""
    elapsed = response.elapsed.total_seconds()
    assert elapsed <= max_seconds, (
        f"响应耗时断言失败: 期望 <= {max_seconds}s, 实际 {elapsed:.3f}s"
    )
    logger.debug("响应耗时断言通过: {:.3f}s <= {}s", elapsed, max_seconds)


def assert_business_code(response: requests.Response, expected: int = 0) -> requests.Response:
    """断言业务码（约定响应体 code 字段）等于期望值，默认 0 表示成功。"""
    return assert_json_field(response, "code", expected)


def assert_message_contains(response: requests.Response, keyword: str) -> requests.Response:
    """断言响应 message 字段包含关键字。"""
    body = _safe_json(response)
    assert isinstance(body, dict), f"响应不是 JSON 对象: {response.text}"
    message = str(body.get("message", ""))
    assert keyword in message, (
        f"消息断言失败: 期望包含 '{keyword}', 实际 '{message}' | 完整响应: {body}"
    )
    return response
