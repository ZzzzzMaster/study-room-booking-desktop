# -*- coding: utf-8 -*-
"""SQLite 连接、建表与种子数据。"""
import os
import sqlite3
from datetime import datetime

from auth import hash_password
import config

DB_LOCK = None  # 预留；并发由 sqlite WAL + busy_timeout 保证


def connect() -> sqlite3.Connection:
    os.makedirs(config.DATA_DIR, exist_ok=True)
    conn = sqlite3.connect(config.DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.isolation_level = None  # 自动提交；写事务由调用方显式 BEGIN IMMEDIATE / COMMIT
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA busy_timeout=30000")
    return conn


def now_str() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


# ── 建表 ───────────────────────────────────────────────────────────────
SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    student_id    TEXT NOT NULL UNIQUE,
    name          TEXT NOT NULL,
    password_hash TEXT NOT NULL,
    role          TEXT NOT NULL DEFAULT 'student' CHECK (role IN ('student','admin')),
    created_at    TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS rooms (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    name       TEXT NOT NULL,
    location   TEXT NOT NULL DEFAULT '',
    open_time  TEXT NOT NULL DEFAULT '08:00',
    close_time TEXT NOT NULL DEFAULT '22:00',
    status     TEXT NOT NULL DEFAULT 'open' CHECK (status IN ('open','closed')),
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS seats (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    room_id   INTEGER NOT NULL REFERENCES rooms(id) ON DELETE CASCADE,
    seat_no   TEXT NOT NULL,
    has_power INTEGER NOT NULL DEFAULT 0,
    status    TEXT NOT NULL DEFAULT 'available'
              CHECK (status IN ('available','reserved','occupied','disabled','broken')),
    UNIQUE (room_id, seat_no)
);

CREATE TABLE IF NOT EXISTS bookings (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id       INTEGER NOT NULL REFERENCES users(id),
    seat_id       INTEGER NOT NULL REFERENCES seats(id),
    room_id       INTEGER NOT NULL REFERENCES rooms(id),
    date          TEXT NOT NULL,
    start_time    TEXT NOT NULL,
    end_time      TEXT NOT NULL,
    status        TEXT NOT NULL DEFAULT 'reserved'
                  CHECK (status IN ('reserved','occupied','expired','completed','cancelled')),
    remind_sent   INTEGER NOT NULL DEFAULT 0,
    expired_sent  INTEGER NOT NULL DEFAULT 0,
    created_at    TEXT NOT NULL,
    updated_at    TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_bookings_conflict ON bookings (seat_id, date, status);
CREATE INDEX IF NOT EXISTS idx_bookings_user   ON bookings (user_id, date);
CREATE INDEX IF NOT EXISTS idx_seats_room      ON seats (room_id);
"""


def init_db():
    conn = connect()
    try:
        conn.executescript(SCHEMA)
        conn.commit()
    finally:
        conn.close()


# ── 种子数据 ───────────────────────────────────────────────────────────
# 演示用默认管理员：仅首次建库时写入，部署或公开使用前请改成自己的账号密码
DEFAULT_ADMIN_STUDENT_ID = "admin"
DEFAULT_ADMIN_PASSWORD = "admin123"


def seed(force: bool = False):
    """首次运行写入：默认管理员 + 两个演示自习室（含插座/无插座/损坏/禁用座位）。"""
    conn = connect()
    try:
        cur = conn.execute("SELECT COUNT(*) AS c FROM users")
        if cur.fetchone()["c"] == 0 or force:
            conn.execute(
                "INSERT INTO users (student_id, name, password_hash, role, created_at) VALUES (?,?,?,?,?)",
                (DEFAULT_ADMIN_STUDENT_ID, "系统管理员",
                 hash_password(DEFAULT_ADMIN_PASSWORD), "admin", now_str()),
            )

        cur = conn.execute("SELECT COUNT(*) AS c FROM rooms")
        if cur.fetchone()["c"] == 0 or force:
            rooms = [
                ("图书馆三楼自习室A区", "图书馆 3F 东侧", "08:00", "22:00"),
                ("教学楼201自习室", "第一教学楼 2F 201", "08:00", "22:00"),
            ]
            room_ids = []
            for name, loc, ot, ct in rooms:
                cur = conn.execute(
                    "INSERT INTO rooms (name, location, open_time, close_time, status, created_at) "
                    "VALUES (?,?,?,?,?,?)",
                    (name, loc, ot, ct, "open", now_str()),
                )
                room_ids.append(cur.lastrowid)

            # 房间1：12 座（1-4,6-9,12 有插座；5,10,11 无插座；5 损坏、10 禁用）
            r1 = [(n, 1 if n in (1, 2, 3, 4, 6, 7, 8, 9, 12) else 0,
                   "broken" if n == 5 else ("disabled" if n == 10 else "available")) for n in range(1, 13)]
            # 房间2：8 座（奇数有插座）
            r2 = [(n, 1 if n % 2 == 1 else 0, "available") for n in range(1, 9)]

            for rid, seats in ((room_ids[0], r1), (room_ids[1], r2)):
                for no, power, status in seats:
                    conn.execute(
                        "INSERT INTO seats (room_id, seat_no, has_power, status) VALUES (?,?,?,?)",
                        (rid, f"{no:02d}号", power, status),
                    )
        conn.commit()
    finally:
        conn.close()


def reset_db():
    """清空并重建（供测试/重置演示数据）。"""
    if os.path.exists(config.DB_PATH):
        for suffix in ("", "-wal", "-shm"):
            p = config.DB_PATH + suffix
            if os.path.exists(p):
                os.remove(p)
    init_db()
    seed()