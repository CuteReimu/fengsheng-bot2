@echo off
set PYTHON=python3
where python >nul 2>&1
if %errorlevel% equ 0 set PYTHON=python
set ENVIRONMENT=dev
%PYTHON% bot.py