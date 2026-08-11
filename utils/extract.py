"""数据提取工具。

提供两类提取能力：
1. ``extract_jsonpath``：轻量级 JSONPath 实现，支持常用表达式，
   避免引入额外的第三方依赖；
2. ``extract_regex``：基于正则的文本提取，适用于非结构化响应。

支持的表达式示例：
- ``$.data.token``
- ``$.data.articles[0].title``
- ``$.data.articles[*].title``
- ``$..title``（递归下降）
"""
from __future__ import annotations

import re
from typing import Any

# 解析 JSONPath 的 token 正则：依次匹配 递归下降 / 普通字段 / 索引或通配
_TOKEN_RE = re.compile(r"\.\.([A-Za-z_][\w]*)|\.([A-Za-z_][\w]*)|\[(\d+|\*)\]")


def _tokenize(expr: str) -> list[tuple[str, Any]]:
    """将去掉 ``$`` 前缀的表达式切分为 token 列表。"""
    tokens: list[tuple[str, Any]] = []
    pos = 0
    length = len(expr)
    while pos < length:
        match = _TOKEN_RE.match(expr, pos)
        if not match:
            # 跳过无法识别的字符（例如多余的点）
            pos += 1
            continue
        if match.group(1) is not None:
            tokens.append(("descend", match.group(1)))
        elif match.group(2) is not None:
            tokens.append(("key", match.group(2)))
        elif match.group(3) is not None:
            if match.group(3) == "*":
                tokens.append(("wildcard", None))
            else:
                tokens.append(("index", int(match.group(3))))
        pos = match.end()
    return tokens


def _apply_token(item: Any, token: tuple[str, Any]) -> list[Any]:
    """对单个数据项应用一个 token，返回匹配结果列表。"""
    kind, value = token
    if item is None:
        return []

    if kind == "key":
        if isinstance(item, dict) and value in item:
            return [item[value]]
        return []

    if kind == "index":
        if isinstance(item, list):
            idx = value if value >= 0 else len(item) + value
            if 0 <= idx < len(item):
                return [item[idx]]
        return []

    if kind == "wildcard":
        if isinstance(item, list):
            return list(item)
        if isinstance(item, dict):
            return list(item.values())
        return []

    if kind == "descend":
        found: list[Any] = []
        # 递归查找所有键等于 value 的值
        def _walk(node: Any) -> None:
            if isinstance(node, dict):
                if value in node:
                    found.append(node[value])
                for v in node.values():
                    _walk(v)
            elif isinstance(node, list):
                for v in node:
                    _walk(v)

        _walk(item)
        return found

    return []


def extract_jsonpath(data: Any, expr: str) -> list[Any]:
    """根据 JSONPath 表达式从数据中提取值。

    Parameters
    ----------
    data:
        解析后的 JSON 数据（dict / list）。
    expr:
        JSONPath 表达式，必须以 ``$`` 开头。

    Returns
    -------
    list
        所有匹配到的值；无匹配时返回空列表。
    """
    if not expr or not expr.startswith("$"):
        return []
    # 去掉前导 $，再交给 tokenizer
    rest = expr[1:]
    tokens = _tokenize(rest)

    results: list[Any] = [data]
    for token in tokens:
        new_results: list[Any] = []
        for item in results:
            new_results.extend(_apply_token(item, token))
        results = new_results
        if not results:
            break
    return results


def extract_regex(text: str, pattern: str, group: int = 1) -> list[str]:
    """使用正则从文本中提取内容。

    Parameters
    ----------
    text:
        待提取的原始文本（通常是响应体）。
    pattern:
        正则表达式，需至少包含一个捕获组。
    group:
        返回的捕获组序号，默认第 1 组。

    Returns
    -------
    list[str]
        所有匹配到的字符串。
    """
    if not text:
        return []
    return [m.group(group) for m in re.finditer(pattern, text) if m.group(group)]
