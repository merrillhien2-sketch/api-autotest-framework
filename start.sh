#!/usr/bin/env bash
# ====================================================================
# 接口自动化测试框架 - 一键启动脚本（Linux / macOS）
# 功能：创建虚拟环境 -> 安装依赖 -> 编译检查 -> 运行 pytest -> 提示报告路径
# ====================================================================
set -e

# 切换到脚本所在目录
cd "$(dirname "$0")"

echo "================ 步骤 1/4：准备虚拟环境 ================"
if [ ! -d ".venv" ]; then
  echo "创建虚拟环境 .venv ..."
  uv venv .venv
fi
# shellcheck disable=SC1091
source .venv/bin/activate

echo "================ 步骤 2/4：安装依赖 ================"
uv pip install -r requirements.txt

echo "================ 步骤 3/4：编译检查（compileall） ================"
python -m compileall .

echo "================ 步骤 4/4：运行 pytest ================"
python -m pytest

echo ""
echo "========================================"
echo " 测试执行完成！"
echo " HTML 报告路径：$(pwd)/reports/report.html"
echo "========================================"
