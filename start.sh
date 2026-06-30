#!/usr/bin/env bash
# 启动脚本
set -euo pipefail

# 设置venv
if [ -d ".venv" ]; then
    source .venv/bin/activate
elif [ -d "venv" ]; then
    source venv/bin/activate
fi

# 设置生产环境标志并启动
ENVIRONMENT=prod python bot.py