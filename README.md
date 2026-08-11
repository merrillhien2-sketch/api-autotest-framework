# 接口自动化测试框架（pytest 数据驱动 + 批量报告）

一个开箱即跑、自包含的 Python 接口自动化测试框架。内置基于 FastAPI 的 Mock 被测服务，
无需依赖外部环境，执行 `pytest` 即可全绿通过并生成 HTML 报告。适合作为接口自动化测试的
脚手架与简历项目实战。

---

## 一、技术栈

| 能力 | 选型 |
| --- | --- |
| 测试框架 | pytest >= 8 |
| HTTP 请求 | requests（Session 封装，统一超时/重试/日志） |
| HTML 报告 | pytest-html（自包含单文件） |
| 数据驱动 | PyYAML（YAML 用例） + pandas（CSV 用例） |
| 配置管理 | pydantic-settings（从 .env 读取） |
| 日志 | loguru（控制台 + 按天轮转文件） |
| 被测服务 | FastAPI + uvicorn（内置 Mock，JWT 鉴权） |
| 数据提取 | 自实现轻量 JSONPath + 正则（无额外依赖） |

> 兼容 Python 3.10 / 3.11+，已在本机 Python 3.10.12 验证通过。

---

## 二、项目结构

```
api-autotest-framework/
├── config/            # settings.py(配置) 、logging_conf.py(日志初始化)
├── common/            # http_client.py 、assertions.py 、auth.py 、logger.py
├── testcases/         # test_login.py 、test_articles.py 、test_user.py
├── data/              # login_data.yaml 、articles_data.yaml 、users.csv
├── reports/           # HTML 报告输出（.gitignore 忽略）
├── utils/             # extract.py 、generator.py 、db_checker.py
├── mock_server/       # app.py(FastAPI Mock) 、data.db(运行时产物)
├── conftest.py        # session 级启动 Mock、全局 fixture、报告钩子
├── pytest.ini         # addopts / markers / pythonpath
├── run.py             # 运行入口（调用 pytest，可选打开报告）
├── requirements.txt   # 依赖清单
├── .env.example       # 环境变量示例（占位符，无真实密钥）
├── .gitignore
├── start.sh           # 一键启动（Linux/macOS）
├── start.bat          # 一键启动（Windows）
├── README.md          # 项目说明（本文件）
└── 使用文档.md         # 详细使用指南
```

---

## 三、快速开始

### 方式一：一键脚本（推荐）

```bash
bash start.sh
```

脚本会自动完成：创建虚拟环境 → 安装依赖 → 编译检查 → 运行 pytest → 提示报告路径。

Windows 环境双击 `start.bat` 即可。

### 方式二：手动执行

```bash
# 1. 创建并激活虚拟环境
uv venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate

# 2. 安装依赖
uv pip install -r requirements.txt

# 3. 编译检查（可选自检）
python -m compileall .

# 4. 运行测试
python -m pytest

# 或通过入口脚本运行
python run.py
```

测试通过后，HTML 报告生成于 `reports/report.html`。

---

## 四、核心特性

1. **HTTP 客户端封装**：`common/http_client.py` 基于 `requests.Session`，统一超时、
   幂等请求自动重试、请求/响应日志（loguru），自动携带 `Authorization` 头。
2. **数据驱动**：
   - YAML 用例：`data/login_data.yaml`、`data/articles_data.yaml`，`pytest.mark.parametrize` 加载；
   - CSV 用例：`data/users.csv`，pandas 读取，`{rand}` 占位符保证可重复运行。
3. **内置 Mock 被测服务**：`mock_server/app.py`（FastAPI）提供 `/api/login`、
   `/api/articles` CRUD、`/api/users` CRUD，带 JWT 鉴权；`conftest.py` 在 session 级
   用 uvicorn 后台线程随机端口启动，保证 `pytest` 即跑即通。
4. **测试用例**：登录成功/失败、文章增删改查、用户管理、参数化多组数据、鉴权失败、
   参数校验、边界场景，均含断言与日志。
5. **HTML 报告**：`pytest-html` 生成 `reports/report.html`，含用例标题、状态、耗时、
   环境元数据；`--self-contained-html` 单文件便于分发。
6. **配置化**：`BASE_URL`、`TIMEOUT`、重试次数、测试账号、JWT 密钥均从 `.env` 读取，
   代码中不硬编码敏感信息。
7. **统一断言助手**：`common/assertions.py` 提供状态码、业务码、JSONPath、字段、
   响应耗时等语义化断言，失败信息携带实际响应，便于排查。

---

## 五、配置说明

复制 `.env.example` 为 `.env` 并按需修改：

```bash
cp .env.example .env
```

| 变量 | 说明 | 默认值 |
| --- | --- | --- |
| `BASE_URL` | 被测服务地址（Mock 启动后自动覆盖） | `http://127.0.0.1:8000` |
| `TIMEOUT` | 请求超时（秒） | `10` |
| `MAX_RETRIES` | 最大重试次数 | `2` |
| `RETRY_BACKOFF` | 重试退避因子 | `0.5` |
| `TEST_USERNAME` | 测试账号 | `admin` |
| `TEST_PASSWORD` | 测试密码 | `123456` |
| `JWT_SECRET` | Mock 服务 JWT 密钥（占位） | `change-me-in-production` |
| `LOG_LEVEL` | 日志级别 | `INFO` |

> 安全提示：`.env` 已被 `.gitignore` 忽略，禁止提交真实账号与密钥。

---

## 六、常用命令

```bash
# 运行全部用例
python -m pytest

# 只运行登录用例
python -m pytest -k login

# 只运行带 smoke 标记的用例
python -m pytest -m smoke

# 运行并自动打开报告
python run.py --open
```

---

## 七、已知限制

- 内置 Mock 服务数据存储于内存，进程结束后不持久化（重启即重置）。
- `utils/db_checker.py` 为占位实现，真实项目可在此接入数据库断言。
- JSONPath 为轻量自实现，支持 `$.a.b`、`$.a[0]`、`$.a[*]`、`$..key` 等常用表达式，
  复杂表达式可按需引入 `jsonpath-ng` 扩展。
- JWT 使用标准库自行实现（HS256），仅用于演示鉴权流程，生产请使用成熟库。

---

## 八、一句话启动

```bash
bash start.sh
```

更详细的使用说明见 [使用文档.md](使用文档.md)。
