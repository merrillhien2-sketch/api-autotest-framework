"""数据库校验器（占位实现）。

真实项目中可在此处实现与数据库的连接与断言，
例如校验接口写入的数据是否落库。本框架为保证自包含可运行，
默认不连接真实数据库，仅提供占位接口，方便后续扩展。
"""
from __future__ import annotations

from typing import Any

from common.logger import logger


class DBChecker:
    """数据库校验器骨架。

    使用时可在 ``__init__`` 中初始化连接，在断言方法中执行 SQL 校验。
    当前为占位实现：所有方法记录日志并返回占位结果，不抛异常。
    """

    def __init__(self, dsn: str | None = None) -> None:
        # 真实场景下应根据 dsn 建立数据库连接
        self.dsn: str | None = dsn
        logger.debug("DBChecker 初始化（占位模式，未连接真实数据库）")

    def execute(self, sql: str, params: tuple[Any, ...] | None = None) -> list[dict[str, Any]]:
        """执行查询 SQL 并返回结果（占位实现返回空列表）。

        真实实现示例（基于 sqlite3）::

            import sqlite3
            conn = sqlite3.connect(self.dsn)
            conn.row_factory = sqlite3.Row
            cur = conn.execute(sql, params or ())
            return [dict(row) for row in cur.fetchall()]
        """
        logger.warning("DBChecker.execute 为占位实现，未执行真实 SQL: {}", sql)
        return []

    def assert_row_exists(self, table: str, conditions: dict[str, Any]) -> bool:
        """断言指定表中存在满足条件的记录（占位实现返回 True）。"""
        logger.warning(
            "DBChecker.assert_row_exists 占位实现，未真实查询: table={} conditions={}",
            table,
            conditions,
        )
        return True

    def close(self) -> None:
        """释放数据库连接（占位实现）。"""
        logger.debug("DBChecker.close（占位实现，无连接需关闭）")
