"""框架运行入口。

直接执行 ``python run.py`` 即可调用 pytest 运行全部用例并生成 HTML 报告。
可选参数 ``--open`` 在运行结束后自动打开报告。

示例：
    python run.py                 # 运行全部用例
    python run.py -k login        # 只运行名称含 login 的用例
    python run.py --open          # 运行并自动打开报告
"""
from __future__ import annotations

import argparse
import sys
import webbrowser
from pathlib import Path

import pytest

from common.logger import logger

# HTML 报告默认输出路径
REPORT_PATH: Path = Path(__file__).resolve().parent / "reports" / "report.html"


def main() -> int:
    """运行 pytest 并处理报告。"""
    parser = argparse.ArgumentParser(description="接口自动化测试框架运行入口")
    parser.add_argument("--open", action="store_true", help="运行结束后自动打开 HTML 报告")
    # 解析框架自身参数，剩余参数透传给 pytest
    own_args, pytest_args = parser.parse_known_args()

    logger.info("开始执行接口自动化测试...")
    exit_code = pytest.main(pytest_args)

    if REPORT_PATH.exists():
        logger.info("HTML 报告已生成: {}", REPORT_PATH)
        if own_args.open:
            try:
                webbrowser.open(REPORT_PATH.as_uri())
            except Exception as exc:  # noqa: BLE001
                logger.warning("无法自动打开报告: {}", exc)
    else:
        logger.warning("未找到 HTML 报告: {}", REPORT_PATH)

    logger.info("测试结束，退出码: {}", exit_code)
    return int(exit_code)


if __name__ == "__main__":
    sys.exit(main())
