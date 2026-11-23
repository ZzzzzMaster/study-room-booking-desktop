@echo off
rem 源码方式启动：需要本机已安装 Python 3.10+
chcp 65001 >nul
cd /d "%~dp0app\backend"
python server.py
pause
