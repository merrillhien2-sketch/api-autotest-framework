"""随机测试数据生成器。

用于在测试中生成唯一的用户名、邮箱、手机号、文章标题等，
保证参数化用例之间的数据互不冲突，便于反复执行。
"""
from __future__ import annotations

import random
import string
import time
import uuid


def random_string(length: int = 8, chars: str = string.ascii_lowercase) -> str:
    """生成指定长度的随机字符串。"""
    return "".join(random.choices(chars, k=length))


def random_username(prefix: str = "user") -> str:
    """生成唯一用户名：前缀 + 时间戳后 6 位 + 随机串。"""
    return f"{prefix}_{int(time.time()) % 1000000:06d}_{random_string(4)}"


def random_email(domain: str = "autotest.com") -> str:
    """生成随机邮箱地址。"""
    return f"{random_string(8)}_{uuid.uuid4().hex[:6]}@{domain}"


def random_phone() -> str:
    """生成符合大陆手机号格式的随机号码（1 开头，第二位 3-9，共 11 位）。"""
    second = str(random.randint(3, 9))
    tail = "".join(random.choices(string.digits, k=9))
    return f"1{second}{tail}"


def random_password(length: int = 12) -> str:
    """生成包含大小写字母与数字的随机密码。"""
    pool = string.ascii_letters + string.digits
    # 保证至少含一个字母和一个数字
    chars = [
        random.choice(string.ascii_lowercase),
        random.choice(string.ascii_uppercase),
        random.choice(string.digits),
    ]
    chars += random.choices(pool, k=length - 3)
    random.shuffle(chars)
    return "".join(chars)


def random_title(prefix: str = "自动化测试文章") -> str:
    """生成随机文章标题。"""
    return f"{prefix}_{uuid.uuid4().hex[:8]}"


def random_content(paragraph: str = "这是一段由接口自动化测试框架生成的正文内容，用于校验文章 CRUD 接口。") -> str:
    """生成随机文章正文。"""
    return f"{paragraph}（序号 {uuid.uuid4().hex[:6]}）"


def random_nickname() -> str:
    """生成随机昵称。"""
    return f"昵称_{random_string(6)}"
