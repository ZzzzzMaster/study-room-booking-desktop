# -*- coding: utf-8 -*-
"""全局配置：时段、限制、定时任务参数（支持环境变量覆盖，便于自动化测试）。"""
import os

# ── 服务 ──────────────────────────────────────────────────────────────
# 默认监听所有网卡（0.0.0.0），手机与电脑同一 Wi-Fi 时可通过电脑局域网 IP 访问；
# 仅本机使用可设 SRR_HOST=127.0.0.1。
HOST = os.environ.get("SRR_HOST", "0.0.0.0")
PORT = int(os.environ.get("SRR_PORT", "8000"))

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(BASE_DIR)
FRONTEND_DIR = os.path.join(PROJECT_DIR, "frontend")
DATA_DIR = os.path.join(PROJECT_DIR, "data")
DB_PATH = os.environ.get("SRR_DB_FILE", os.path.join(DATA_DIR, "study_room.db"))
SECRET_KEY_FILE = os.path.join(DATA_DIR, "secret.key")

# ── 会话 ──────────────────────────────────────────────────────────────
def get_secret_key() -> bytes:
    """读取或生成签名密钥（保存到 data/secret.key，重启后 token 仍有效）。"""
    try:
        os.makedirs(DATA_DIR, exist_ok=True)
        if os.path.exists(SECRET_KEY_FILE):
            with open(SECRET_KEY_FILE, "rb") as f:
                key = f.read().strip()
            if len(key) >= 16:
                return key
        key = os.urandom(32)
        with open(SECRET_KEY_FILE, "wb") as f:
            f.write(key)
        return key
    except Exception:
        # 极端情况下退化到进程内随机密钥
        return os.urandom(32)

SECRET_KEY = get_secret_key()
TOKEN_TTL_HOURS = 24

# ── 自习室开放时段（1 小时粒度时间槽起点）────────────────────────────
OPEN_TIME = "08:00"
CLOSE_TIME = "22:00"

# ── 预约规则 ──────────────────────────────────────────────────────────
MAX_BOOKING_HOURS = 4          # 单次预约最长 4 小时
MAX_HOURS_MSG = "单次预约最长 4 小时，请缩短时间段或分段预约。"

# ── 定时任务（默认生产值；测试可用环境变量临时缩短）──────────────────
SCAN_INTERVAL = float(os.environ.get("SRR_SCAN_INTERVAL", "30"))   # 秒
REMIND_LEAD = float(os.environ.get("SRR_REMIND_MINUTES", "15"))    # 提前 15 分钟提醒（分钟）
EXPIRE_GRACE = float(os.environ.get("SRR_GRACE_MINUTES", "30"))    # 超时 30 分钟释放（分钟）

# ── 状态枚举 ──────────────────────────────────────────────────────────
SEAT_STATUSES = ("available", "reserved", "occupied", "disabled", "broken")
BOOKING_STATUSES = ("reserved", "occupied", "expired", "completed", "cancelled")
ROOM_STATUSES = ("open", "closed")
MAX_SEAT_NO_LEN = 32