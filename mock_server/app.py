"""FastAPI Mock 被测服务。

作为接口自动化测试框架的内置被测对象，保证框架自包含、开箱即跑。
提供以下能力：
- ``POST /api/login``：账号密码登录，签发 JWT；
- ``/api/articles`` 增删改查 + 分页/关键字搜索（需 JWT 鉴权）；
- ``/api/users`` 增删改查（需 JWT 鉴权）；
- ``GET /api/health``：健康检查，供 conftest 探活使用。

说明：
- 为避免引入额外依赖，JWT(HS256) 使用标准库自行实现；
- 业务数据采用内存字典 + 线程锁存储，保证并发安全与可重复运行；
- ``data.db`` 为运行时占位产物（启动时创建空文件），便于在真实项目中替换为数据库存储。
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import sqlite3
import threading
import time
from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import Depends, FastAPI, HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from config.settings import get_settings

# ----------------------------------------------------------------------
# JWT（HS256）轻量实现，仅依赖标准库
# ----------------------------------------------------------------------
_HEADER = {"alg": "HS256", "typ": "JWT"}


def _b64encode(raw: bytes) -> str:
    """URL安全的 Base64 编码并去掉填充符 ``=``。"""
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _b64decode(seg: str) -> bytes:
    """URL安全的 Base64 解码，自动补齐填充。"""
    padding = 4 - len(seg) % 4
    if padding != 4:
        seg += "=" * padding
    return base64.urlsafe_b64decode(seg.encode("ascii"))


def encode_jwt(payload: dict[str, Any], secret: str) -> str:
    """签发 JWT。payload 中应包含 ``exp`` 过期时间戳。"""
    header_seg = _b64encode(json.dumps(_HEADER, separators=(",", ":")).encode("utf-8"))
    payload_seg = _b64encode(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
    signing_input = f"{header_seg}.{payload_seg}".encode("ascii")
    signature = hmac.new(secret.encode("utf-8"), signing_input, hashlib.sha256).digest()
    return f"{header_seg}.{payload_seg}.{_b64encode(signature)}"


def decode_jwt(token: str, secret: str) -> dict[str, Any]:
    """校验并解析 JWT，校验失败抛出 ValueError。"""
    parts = token.split(".")
    if len(parts) != 3:
        raise ValueError("无效的 Token 格式")
    header_seg, payload_seg, sig_seg = parts
    signing_input = f"{header_seg}.{payload_seg}".encode("ascii")
    expected_sig = hmac.new(secret.encode("utf-8"), signing_input, hashlib.sha256).digest()
    if not hmac.compare_digest(_b64encode(expected_sig), sig_seg):
        raise ValueError("Token 签名校验失败")
    payload: dict[str, Any] = json.loads(_b64decode(payload_seg))
    exp = payload.get("exp")
    if exp is not None and exp < time.time():
        raise ValueError("Token 已过期")
    return payload


# ----------------------------------------------------------------------
# 内存数据存储（线程安全）
# ----------------------------------------------------------------------
_lock = threading.Lock()
_users: dict[str, dict[str, Any]] = {}
_articles: dict[int, dict[str, Any]] = {}
_article_seq: int = 0
_user_seq: int = 0

# 运行时占位数据库文件路径
_DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data.db")


# ----------------------------------------------------------------------
# Pydantic 请求模型
# ----------------------------------------------------------------------
class LoginRequest(BaseModel):
    """登录请求体。"""

    username: str = Field(..., min_length=1, description="用户名")
    password: str = Field(..., min_length=1, description="密码")


class ArticleCreate(BaseModel):
    """创建文章请求体。"""

    title: str = Field(..., min_length=1, description="标题")
    content: str = Field(..., min_length=1, description="正文")


class ArticleUpdate(BaseModel):
    """更新文章请求体（字段均可选）。"""

    title: Optional[str] = Field(None, description="标题")
    content: Optional[str] = Field(None, description="正文")


class UserCreate(BaseModel):
    """创建用户请求体。"""

    username: str = Field(..., min_length=3, description="用户名")
    password: str = Field(..., min_length=6, description="密码")
    email: str = Field(..., description="邮箱")
    nickname: Optional[str] = Field(None, description="昵称")


class UserUpdate(BaseModel):
    """更新用户请求体。"""

    email: Optional[str] = Field(None, description="邮箱")
    nickname: Optional[str] = Field(None, description="昵称")


# ----------------------------------------------------------------------
# 业务异常与统一响应
# ----------------------------------------------------------------------
class BizError(Exception):
    """业务异常，携带业务码、消息与 HTTP 状态码。"""

    def __init__(self, message: str, code: int = 1, status_code: int = 400) -> None:
        self.message = message
        self.code = code
        self.status_code = status_code
        super().__init__(message)


def ok(data: Any = None, message: str = "success", code: int = 0) -> dict[str, Any]:
    """构造成功响应体。"""
    return {"code": code, "message": message, "data": data}


# ----------------------------------------------------------------------
# 鉴权依赖
# ----------------------------------------------------------------------
def get_current_user(request: Request) -> dict[str, Any]:
    """解析 Authorization 头并返回当前用户，失败抛出 BizError(401)。"""
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        raise BizError("未提供有效的鉴权信息", code=1002, status_code=status.HTTP_401_UNAUTHORIZED)
    token = auth[len("Bearer "):]
    settings = get_settings()
    try:
        payload = decode_jwt(token, settings.JWT_SECRET)
    except ValueError as exc:
        raise BizError(str(exc), code=1002, status_code=status.HTTP_401_UNAUTHORIZED) from exc

    username = payload.get("sub")
    with _lock:
        user = _users.get(username)
    if not user:
        raise BizError("用户不存在或已被删除", code=1002, status_code=status.HTTP_401_UNAUTHORIZED)
    return user


# ----------------------------------------------------------------------
# 应用与生命周期
# ----------------------------------------------------------------------
def _init_data() -> None:
    """预置初始数据：创建默认管理员账号，并生成占位 data.db。"""
    global _user_seq
    settings = get_settings()
    with _lock:
        _users.clear()
        _articles.clear()
        _user_seq = 1
        _users[settings.TEST_USERNAME] = {
            "id": _user_seq,
            "username": settings.TEST_USERNAME,
            "password": settings.TEST_PASSWORD,
            "email": "admin@autotest.com",
            "nickname": "管理员",
            "created_at": _now(),
        }
    # 创建运行时占位数据库文件（真实项目可在此初始化表结构）
    try:
        sqlite3.connect(_DB_PATH).close()
    except sqlite3.Error:
        pass


def _now() -> str:
    """返回 ISO8601 格式的当前时间字符串。"""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


from contextlib import asynccontextmanager  # noqa: E402


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期：启动时初始化数据。"""
    _init_data()
    yield


app = FastAPI(
    title="接口自动化测试 Mock 服务",
    description="框架内置被测服务，提供登录、文章与用户的 CRUD 接口及 JWT 鉴权。",
    version="1.0.0",
    lifespan=lifespan,
)


# ----------------------------------------------------------------------
# 全局异常处理（统一响应格式）
# ----------------------------------------------------------------------
@app.exception_handler(BizError)
async def biz_error_handler(request: Request, exc: BizError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={"code": exc.code, "message": exc.message, "data": None},
    )


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={"code": exc.status_code, "message": str(exc.detail), "data": None},
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    """参数校验失败统一返回 422。"""
    return JSONResponse(
        status_code=422,
        content={
            "code": 422,
            "message": "请求参数校验失败",
            "data": exc.errors(),
        },
    )


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """兜底异常处理，避免暴露堆栈给客户端。"""
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"code": 500, "message": f"服务器内部错误: {exc}", "data": None},
    )


# ----------------------------------------------------------------------
# 健康检查
# ----------------------------------------------------------------------
@app.get("/api/health")
def health_check() -> dict[str, Any]:
    """健康检查接口，供 conftest 探活。"""
    return ok({"status": "up", "time": _now()})


# ----------------------------------------------------------------------
# 登录
# ----------------------------------------------------------------------
@app.post("/api/login")
def login(req: LoginRequest) -> dict[str, Any]:
    """账号密码登录，成功返回 JWT。"""
    settings = get_settings()
    with _lock:
        user = _users.get(req.username)
    if not user or user.get("password") != req.password:
        raise BizError("用户名或密码错误", code=1001, status_code=status.HTTP_401_UNAUTHORIZED)

    payload = {
        "sub": req.username,
        "exp": int(time.time()) + settings.JWT_EXPIRE_MINUTES * 60,
        "iat": int(time.time()),
    }
    token = encode_jwt(payload, settings.JWT_SECRET)
    return ok({"token": token, "username": req.username, "nickname": user.get("nickname")})


# ----------------------------------------------------------------------
# 文章 CRUD
# ----------------------------------------------------------------------
@app.get("/api/articles")
def list_articles(
    page: int = 1,
    size: int = 10,
    keyword: str = "",
    _: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    """文章列表（支持分页与标题关键字搜索）。"""
    with _lock:
        items = list(_articles.values())
    if keyword:
        items = [a for a in items if keyword.lower() in a.get("title", "").lower()]
    total = len(items)
    # 分页
    start = (page - 1) * size
    end = start + size
    page_items = items[start:end]
    return ok({"articles": page_items, "total": total, "page": page, "size": size})


@app.post("/api/articles")
def create_article(
    body: ArticleCreate,
    current: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    """创建文章。"""
    global _article_seq
    with _lock:
        _article_seq += 1
        article = {
            "id": _article_seq,
            "title": body.title,
            "content": body.content,
            "author": current["username"],
            "created_at": _now(),
            "updated_at": _now(),
        }
        _articles[_article_seq] = article
    return ok(article, message="文章创建成功")


@app.get("/api/articles/{article_id}")
def get_article(
    article_id: int,
    _: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    """查询单个文章。"""
    with _lock:
        article = _articles.get(article_id)
    if not article:
        raise BizError("文章不存在", code=1003, status_code=status.HTTP_404_NOT_FOUND)
    return ok(article)


@app.put("/api/articles/{article_id}")
def update_article(
    article_id: int,
    body: ArticleUpdate,
    _: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    """更新文章。"""
    with _lock:
        article = _articles.get(article_id)
        if not article:
            raise BizError("文章不存在", code=1003, status_code=status.HTTP_404_NOT_FOUND)
        if body.title is not None:
            article["title"] = body.title
        if body.content is not None:
            article["content"] = body.content
        article["updated_at"] = _now()
    return ok(article, message="文章更新成功")


@app.delete("/api/articles/{article_id}")
def delete_article(
    article_id: int,
    _: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    """删除文章。"""
    with _lock:
        if article_id not in _articles:
            raise BizError("文章不存在", code=1003, status_code=status.HTTP_404_NOT_FOUND)
        _articles.pop(article_id)
    return ok(None, message="文章删除成功")


# ----------------------------------------------------------------------
# 用户 CRUD
# ----------------------------------------------------------------------
@app.get("/api/users")
def list_users(
    keyword: str = "",
    _: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    """用户列表（支持用户名关键字搜索）。"""
    with _lock:
        items = list(_users.values())
    if keyword:
        items = [u for u in items if keyword.lower() in u.get("username", "").lower()]
    # 脱敏：不返回密码
    safe = [{k: v for k, v in u.items() if k != "password"} for u in items]
    return ok({"users": safe, "total": len(safe)})


@app.post("/api/users")
def create_user(
    body: UserCreate,
    _: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    """创建用户。"""
    global _user_seq
    with _lock:
        if body.username in _users:
            raise BizError("用户名已存在", code=1004, status_code=status.HTTP_400_BAD_REQUEST)
        _user_seq += 1
        user = {
            "id": _user_seq,
            "username": body.username,
            "password": body.password,
            "email": body.email,
            "nickname": body.nickname or body.username,
            "created_at": _now(),
        }
        _users[body.username] = user
    safe = {k: v for k, v in user.items() if k != "password"}
    return ok(safe, message="用户创建成功")


@app.get("/api/users/{username}")
def get_user(
    username: str,
    _: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    """查询单个用户。"""
    with _lock:
        user = _users.get(username)
    if not user:
        raise BizError("用户不存在", code=1005, status_code=status.HTTP_404_NOT_FOUND)
    safe = {k: v for k, v in user.items() if k != "password"}
    return ok(safe)


@app.put("/api/users/{username}")
def update_user(
    username: str,
    body: UserUpdate,
    _: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    """更新用户信息（邮箱、昵称）。"""
    with _lock:
        user = _users.get(username)
        if not user:
            raise BizError("用户不存在", code=1005, status_code=status.HTTP_404_NOT_FOUND)
        if body.email is not None:
            user["email"] = body.email
        if body.nickname is not None:
            user["nickname"] = body.nickname
    safe = {k: v for k, v in user.items() if k != "password"}
    return ok(safe, message="用户更新成功")


@app.delete("/api/users/{username}")
def delete_user(
    username: str,
    current: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    """删除用户（不允许删除当前登录用户自身）。"""
    if username == current["username"]:
        raise BizError("不允许删除当前登录用户", code=1006, status_code=status.HTTP_400_BAD_REQUEST)
    with _lock:
        if username not in _users:
            raise BizError("用户不存在", code=1005, status_code=status.HTTP_404_NOT_FOUND)
        _users.pop(username)
    return ok(None, message="用户删除成功")
