#!/usr/bin/env bash
# 一次性 verify 服务入口：构建检查 -> 代码测试 -> 导排 API 冒烟。
# 任一阶段失败即以非零退出码退出（供 docker compose 通过退出码报告结果）。
set -euo pipefail

cd /app
export PYTHONPATH=/app
export PYTHONDONTWRITEBYTECODE=1
BASE_URL="${BASE_URL:-http://web:8080}"

echo "================ [1/3] 构建检查（字节码编译） ================"
python -m compileall -q app scripts

echo "================ [2/3] 代码测试（pytest） ================"
python -m pytest -q

echo "================ [3/3] 导排 API 冒烟（$BASE_URL） ================"
python scripts/smoke.py

echo "verify：构建、测试、冒烟全部通过。"
