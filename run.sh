#!/usr/bin/env bash
# 源码方式启动：需要 Python 3.10+
cd "$(dirname "$0")/app/backend" && exec python3 server.py
