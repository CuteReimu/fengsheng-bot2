#!/usr/bin/env bash
if command -v python &>/dev/null; then
  PYTHON=python
else
  PYTHON=python3
fi
ENVIRONMENT=dev "$PYTHON" bot.py