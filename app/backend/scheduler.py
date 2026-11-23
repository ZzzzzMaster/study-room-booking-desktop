# -*- coding: utf-8 -*-
"""定时任务：每 30 秒扫描并执行「到期前 15 分钟提醒 → 到期提示 → 超时 30 分钟自动释放」。

全部以后端时间为准，不依赖前端计时；每步 UPDATE 均带状态/标记条件，保证幂等。
状态机：
  预约创建        -> booking=reserved, seat=reserved
  end_time 到达   -> booking=occupied, seat=occupied（超时占用），推送“到期提示”
  end+30min 未处理 -> booking=expired,  seat=available，广播“座位已释放”
  续约            -> 延长 end_time（重置提醒标记）
  离座/取消        -> booking=completed/cancelled, seat=available
"""
import threading
from datetime import datetime, timedelta

import db
import ws_server
import config

_reminder_msg = "您的座位将在 15 分钟后到期，如需继续使用请点击续约。"
_expired_msg = "您的预约已到期，请尽快续约或离开座位。超过 30 分钟未处理，座位将自动释放。"
_released_msg = "座位已释放"


def _now_time() -> str:
    return datetime.now().strftime("%H:%M")


def _is_expired_release(bdate: str, bend: str, now: datetime) -> bool:
    """是否已进入自动释放条件（end_time 已过宽限期）。"""
    today = now.strftime("%Y-%m-%d")
    if bdate < today:
        return True
    if bdate > today:
        return False
    limit = (now - timedelta(minutes=config.EXPIRE_GRACE)).strftime("%H:%M")
    return bend <= limit


def scan_once():
    """执行一轮扫描，返回 (提醒数, 到期数, 释放数)。"""
    now = datetime.now()
    now_t = now.strftime("%H:%M")
    today = now.strftime("%Y-%m-%d")
    remind_limit = (now + timedelta(minutes=config.REMIND_LEAD)).strftime("%H:%M")

    conn = db.connect()
    r_remind = r_expire = r_release = 0
    try:
        # 1) 到期前 15 分钟提醒（未提醒过）
        rows = conn.execute(
            "SELECT b.id, b.user_id, b.seat_id, b.end_time, s.seat_no, r.name AS room_name "
            "FROM bookings b JOIN seats s ON s.id = b.seat_id JOIN rooms r ON r.id = b.room_id "
            "WHERE b.date = ? AND b.status IN ('reserved','occupied') "
            "  AND b.remind_sent = 0 AND b.end_time > ? AND b.end_time <= ?",
            (today, now_t, remind_limit),
        ).fetchall()
        for row in rows:
            ws_server.send_to_user(row["user_id"], {
                "type": "booking_reminder",
                "payload": {
                    "booking_id": row["id"], "seat_no": row["seat_no"],
                    "room_name": row["room_name"], "end_time": row["end_time"],
                },
                "message": _reminder_msg, "end_time": row["end_time"],
            })
            conn.execute("UPDATE bookings SET remind_sent = 1, updated_at = ? WHERE id = ? AND remind_sent = 0",
                         (db.now_str(), row["id"]))
            r_remind += 1

        # 2) end_time 已到达：推送“到期提示”，并把占座标记转为超时占用（reserved->occupied）
        rows = conn.execute(
            "SELECT b.id, b.user_id, b.seat_id, b.date, b.end_time, s.seat_no, r.name AS room_name "
            "FROM bookings b JOIN seats s ON s.id = b.seat_id JOIN rooms r ON r.id = b.room_id "
            "WHERE b.date = ? AND b.status IN ('reserved','occupied') "
            "  AND b.expired_sent = 0 AND b.end_time <= ?",
            (today, now_t),
        ).fetchall()
        for row in rows:
            ws_server.send_to_user(row["user_id"], {
                "type": "booking_expired",
                "payload": {
                    "booking_id": row["id"], "seat_no": row["seat_no"],
                    "room_name": row["room_name"], "end_time": row["end_time"],
                },
                "message": _expired_msg, "end_time": row["end_time"],
            })
            conn.execute("UPDATE bookings SET status = 'occupied', expired_sent = 1, updated_at = ? "
                         "WHERE id = ? AND status IN ('reserved','occupied') AND expired_sent = 0",
                         (db.now_str(), row["id"]))
            conn.execute("UPDATE seats SET status = 'occupied' WHERE id = ? AND status = 'reserved'",
                         (row["seat_id"],))
            r_expire += 1

        # 3) 超时 30 分钟自动释放（含历史遗留的过期占座，date < today 直接释放）
        rows = conn.execute(
            "SELECT b.id, b.user_id, b.seat_id, b.room_id, b.date, b.end_time "
            "FROM bookings b "
            "WHERE b.status IN ('reserved','occupied')",
        ).fetchall()
        for row in rows:
            if not _is_expired_release(row["date"], row["end_time"], now):
                continue
            conn.execute("UPDATE bookings SET status = 'expired', updated_at = ? "
                         "WHERE id = ? AND status IN ('reserved','occupied')",
                         (db.now_str(), row["id"]))
            conn.execute("UPDATE seats SET status = 'available' WHERE id = ? AND status IN ('reserved','occupied')",
                         (row["seat_id"],))
            ws_server.broadcast({
                "type": "seat_updated",
                "payload": {"seat_id": row["seat_id"], "room_id": row["room_id"], "status": "available",
                            "reason": "expired", "message": _released_msg},
            })
            r_release += 1

        conn.commit()
    finally:
        conn.close()
    return r_remind, r_expire, r_release


def _run():
    while True:
        try:
            scan_once()
        except Exception as exc:  # 定时任务不允许崩溃
            print("[scheduler] scan error:", exc, flush=True)
        threading.Event().wait(config.SCAN_INTERVAL)


def start():
    t = threading.Thread(target=_run, name="scheduler", daemon=True)
    t.start()
    print("[scheduler] started, interval={}s, remind_lead={}min, grace={}min".format(
        config.SCAN_INTERVAL, config.REMIND_LEAD, config.EXPIRE_GRACE), flush=True)
    return t