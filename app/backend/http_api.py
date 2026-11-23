# -*- coding: utf-8 -*-
"""REST API：认证、自习室/座位、预约（4h 上限/间隔冲突/续约/离座/取消）、管理端。"""
import json
import re
from datetime import datetime, timedelta

import db
import config
import ws_server
from auth import hash_password, verify_password, verify_token

# ── 基础工具 ────────────────────────────────────────────────────────────

def json_response(data, status=200):
    return status, {"ok": True, "data": data}


def error(msg, status=400):
    return status, {"ok": False, "error": msg}


def parse_body(body_bytes):
    if not body_bytes:
        return {}
    try:
        data = json.loads(body_bytes.decode("utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return None  # 表示解析失败


def authenticate(headers):
    """从 Authorization 头解析 token；成功返回 (user_row, claims)，否则 None。"""
    auth = headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        return None
    token = auth[7:].strip()
    claims = verify_token(token)
    if not claims:
        return None
    conn = db.connect()
    try:
        row = conn.execute("SELECT id, student_id, name, role FROM users WHERE id = ?",
                           (claims["uid"],)).fetchone()
        return (row, claims) if row else None
    finally:
        conn.close()


def parse_date(s):
    try:
        return datetime.strptime(s, "%Y-%m-%d").date()
    except Exception:
        return None


def parse_hhmm(s):
    """返回当日分钟数（要求整点 HH:00），否则 None。"""
    m = re.fullmatch(r"(\d{2}):(\d{2})", s or "")
    if not m:
        return None
    hh, mm = int(m.group(1)), int(m.group(2))
    if hh > 23 or mm != 0:
        return None
    return hh * 60


def fmt_minutes(m):
    return "{:02d}:{:02d}".format(m // 60, m % 60)


def booking_to_dict(row, minutes_left=None):
    start_m = parse_hhmm(row["start_time"]) or 0
    end_m = parse_hhmm(row["end_time"]) or 0
    return {
        "id": row["id"],
        "user_id": row["user_id"],
        "seat_id": row["seat_id"],
        "room_id": row["room_id"],
        "room_name": row["room_name"],
        "seat_no": row["seat_no"],
        "date": row["date"],
        "start_time": row["start_time"],
        "end_time": row["end_time"],
        "status": row["status"],
        "hours": max((end_m - start_m) // 60, 0),   # 修复：小时而非分钟
        "minutes_left": minutes_left,
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def minutes_left_of(row, now=None):
    """活跃预约的剩余分钟数（按后端时间）；非当天/已结束返回 None。"""
    if row["status"] not in ("reserved", "occupied"):
        return None
    now = now or datetime.now()
    today = now.strftime("%Y-%m-%d")
    if row["date"] != today:
        return None
    end = parse_hhmm(row["end_time"])
    if end is None:
        return None
    now_min = now.hour * 60 + now.minute
    return max(end - now_min, 0)


# ── 认证 ────────────────────────────────────────────────────────────────

def api_register(data):
    student_id = (data.get("student_id") or "").strip()
    name = (data.get("name") or "").strip()
    password = data.get("password") or ""
    confirm = data.get("confirm_password") or ""
    if not student_id or not name or not password:
        return error("学号、姓名、密码不能为空")
    if password != confirm:
        return error("两次输入的密码不一致")
    if len(password) < 6:
        return error("密码长度至少 6 位")
    conn = db.connect()
    try:
        try:
            conn.execute("BEGIN IMMEDIATE")
            cur = conn.execute("SELECT id FROM users WHERE student_id = ?", (student_id,))
            if cur.fetchone():
                return error("该学号已注册，请直接登录", 409)
            cur = conn.execute(
                "INSERT INTO users (student_id, name, password_hash, role, created_at) "
                "VALUES (?,?,?,?,?)",
                (student_id, name, hash_password(password), "student", db.now_str()),
            )
            uid = cur.lastrowid
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        return json_response({"id": uid, "student_id": student_id, "name": name, "role": "student"})
    finally:
        conn.close()


def api_login(data):
    student_id = (data.get("student_id") or "").strip()
    password = data.get("password") or ""
    if not student_id or not password:
        return error("学号或密码不能为空")
    conn = db.connect()
    try:
        row = conn.execute(
            "SELECT id, student_id, name, password_hash, role FROM users WHERE student_id = ?",
            (student_id,),
        ).fetchone()
        if not row or not verify_password(password, row["password_hash"]):
            return error("学号或密码错误", 401)
        from auth import create_token
        token = create_token(row["id"], row["role"])
        return json_response({
            "token": token,
            "user": {"id": row["id"], "student_id": row["student_id"],
                     "name": row["name"], "role": row["role"]},
        })
    finally:
        conn.close()


def api_me(user):
    return json_response({"id": user["id"], "student_id": user["student_id"],
                          "name": user["name"], "role": user["role"]})


# ── 自习室 / 座位 ───────────────────────────────────────────────────────

def _room_list_row(conn, rid=None):
    sql = ("SELECT r.*, "
           "(SELECT COUNT(*) FROM seats s WHERE s.room_id = r.id) AS seat_total, "
           "(SELECT COUNT(*) FROM seats s WHERE s.room_id = r.id AND s.status = 'available') AS seat_available "
           "FROM rooms r ")
    if rid is None:
        return conn.execute(sql + "ORDER BY r.id").fetchall()
    return conn.execute(sql + "WHERE r.id = ?", (rid,)).fetchone()


def api_rooms():
    conn = db.connect()
    try:
        rows = _room_list_row(conn)
        out = [{"id": r["id"], "name": r["name"], "location": r["location"],
                "open_time": r["open_time"], "close_time": r["close_time"],
                "status": r["status"], "seat_total": r["seat_total"],
                "seat_available": r["seat_available"]} for r in rows]
        return json_response(out)
    finally:
        conn.close()


def api_room_seats(rid, query):
    conn = db.connect()
    try:
        room = conn.execute("SELECT * FROM rooms WHERE id = ?", (rid,)).fetchone()
        if not room:
            return error("自习室不存在", 404)

        power = query.get("power", "all")
        if power not in ("all", "1", "0"):
            return error("power 参数仅支持 all/1/0")
        date_s, start_s, end_s = query.get("date"), query.get("start"), query.get("end")
        slot = None
        if date_s and start_s and end_s:
            if not (parse_date(date_s) and parse_hhmm(start_s) is not None and parse_hhmm(end_s) is not None):
                return error("日期/时间格式不正确（时间需为整点 HH:00）")
            occupied = {r["seat_id"] for r in conn.execute(
                "SELECT seat_id FROM bookings WHERE date = ? AND status IN ('reserved','occupied') "
                "AND start_time < ? AND end_time > ?",
                (date_s, end_s, start_s)).fetchall()}
            slot = {"date": date_s, "start": start_s, "end": end_s, "occupied": occupied}

        sql = "SELECT id, room_id, seat_no, has_power, status FROM seats WHERE room_id = ?"
        args = [rid]
        if power in ("1", "0"):
            sql += " AND has_power = ?"
            args.append(int(power))
        rows = conn.execute(sql + " ORDER BY seat_no", args).fetchall()

        out = []
        for s in rows:
            status = s["status"]
            eff, bookable = status, False
            if status == "available":
                in_conflict = bool(slot and s["id"] in slot["occupied"])
                eff = "occupied" if in_conflict else "available"
                bookable = (not in_conflict) and room["status"] == "open"
            out.append({"seat_id": s["id"], "room_id": s["room_id"], "seat_no": s["seat_no"],
                        "has_power": bool(s["has_power"]), "status": status,
                        "effective": eff, "bookable": bookable, "slot": slot})
        return json_response({"room": {
            "id": room["id"], "name": room["name"], "location": room["location"],
            "open_time": room["open_time"], "close_time": room["close_time"],
            "status": room["status"]}, "seats": out})
    finally:
        conn.close()


# ── 预约核心 ────────────────────────────────────────────────────────────

def _validate_slot(room, date_s, start_s, end_s):
    """返回 (start_min, end_min, start_dt) 或错误响应。"""
    d = parse_date(date_s)
    start_min = parse_hhmm(start_s)
    end_min = parse_hhmm(end_s)
    if d is None or start_min is None or end_min is None:
        return None, None, None, error("日期或时间格式不正确（时间需为整点，如 09:00）")
    if end_min <= start_min:
        return None, None, None, error("结束时间必须晚于开始时间")
    open_min, close_min = parse_hhmm(room["open_time"]), parse_hhmm(room["close_time"])
    if start_min < open_min or end_min > close_min:
        return None, None, None, error("预约时间需在自习室开放时间内（{} - {}）".format(
            room["open_time"], room["close_time"]))
    hours = (end_min - start_min) / 60
    if hours > config.MAX_BOOKING_HOURS:
        return None, None, None, error(config.MAX_HOURS_MSG, 422)
    start_dt = datetime.strptime("{} {}".format(date_s, start_s), "%Y-%m-%d %H:%M")
    if start_dt <= datetime.now():
        return None, None, None, error("预约开始时间必须晚于当前时间")
    return start_min, end_min, start_dt, None


def _conflict_exists(conn, seat_id, date_s, start_s, end_s, exclude_id=None):
    sql = ("SELECT id FROM bookings WHERE seat_id = ? AND date = ? "
           "AND status IN ('reserved','occupied') AND start_time < ? AND end_time > ?")
    args = [seat_id, date_s, end_s, start_s]
    if exclude_id is not None:
        sql += " AND id != ?"
        args.append(exclude_id)
    return conn.execute(sql, args).fetchone() is not None


def api_create_booking(user, data):
    room_id = data.get("room_id")
    seat_id = data.get("seat_id")
    date_s, start_s, end_s = data.get("date"), data.get("start_time"), data.get("end_time")
    if not all([room_id, seat_id, date_s, start_s, end_s]):
        return error("参数不完整：需要 room_id/seat_id/date/start_time/end_time")

    conn = db.connect()
    try:
        conn.execute("BEGIN IMMEDIATE")
        room = conn.execute("SELECT * FROM rooms WHERE id = ?", (room_id,)).fetchone()
        if not room:
            conn.rollback()
            return error("自习室不存在", 404)
        if room["status"] != "open":
            conn.rollback()
            return error("该自习室当前未开放")
        seat = conn.execute("SELECT * FROM seats WHERE id = ? AND room_id = ?",
                            (seat_id, room_id)).fetchone()
        if not seat:
            conn.rollback()
            return error("座位不存在", 404)
        if seat["status"] != "available":
            conn.rollback()
            return error("该座位当前不可预约（状态：{}）".format(seat["status"]), 409)

        start_min, end_min, start_dt, err = _validate_slot(room, date_s, start_s, end_s)
        if err:
            conn.rollback()
            return err
        if _conflict_exists(conn, seat_id, date_s, start_s, end_s):
            conn.rollback()
            return error("该座位在该时段已被预约，请选择其他座位或时段", 409)

        cur = conn.execute(
            "INSERT INTO bookings (user_id, seat_id, room_id, date, start_time, end_time, "
            "status, remind_sent, expired_sent, created_at, updated_at) "
            "VALUES (?,?,?,?,?,?, 'reserved', 0, 0, ?, ?)",
            (user["id"], seat_id, room_id, date_s, start_s, end_s,
             db.now_str(), db.now_str()))
        booking_id = cur.lastrowid
        conn.execute("UPDATE seats SET status = 'reserved' WHERE id = ?", (seat_id,))
        conn.commit()
    finally:
        conn.close()

    ws_server.broadcast({"type": "seat_updated", "payload": {
        "seat_id": seat_id, "room_id": room_id, "status": "reserved", "reason": "booked"}})
    return json_response({"id": booking_id, "room_id": room_id, "seat_id": seat_id,
                          "date": date_s, "start_time": start_s, "end_time": end_s,
                          "status": "reserved"}, 201)


def api_my_bookings(user):
    conn = db.connect()
    try:
        rows = conn.execute(
            "SELECT b.*, r.name AS room_name, s.seat_no FROM bookings b "
            "JOIN rooms r ON r.id = b.room_id JOIN seats s ON s.id = b.seat_id "
            "WHERE b.user_id = ? ORDER BY b.date DESC, b.start_time DESC",
            (user["id"],)).fetchall()
        out = [booking_to_dict(r, minutes_left_of(r)) for r in rows]
        return json_response(out)
    finally:
        conn.close()


def _own_booking(conn, user, booking_id):
    return conn.execute(
        "SELECT b.*, r.name AS room_name, s.seat_no FROM bookings b "
        "JOIN rooms r ON r.id = b.room_id JOIN seats s ON s.id = b.seat_id "
        "WHERE b.id = ? AND b.user_id = ?", (booking_id, user["id"])).fetchone()


def api_renew(user, booking_id, data):
    new_end = (data.get("new_end_time") or "").strip()
    conn = db.connect()
    try:
        conn.execute("BEGIN IMMEDIATE")
        b = _own_booking(conn, user, booking_id)
        if not b:
            conn.rollback()
            return error("预约不存在或无权操作", 404)
        if b["status"] not in ("reserved", "occupied"):
            conn.rollback()
            return error("当前状态的预约不能续约")
        new_end_min = parse_hhmm(new_end)
        cur_end_min = parse_hhmm(b["end_time"])
        if new_end_min is None:
            conn.rollback()
            return error("时间格式不正确（需为整点 HH:00）")
        if new_end_min <= cur_end_min:
            conn.rollback()
            return error("续约后的结束时间必须晚于当前结束时间")
        if new_end_min - parse_hhmm(b["start_time"]) > 60 * config.MAX_BOOKING_HOURS:
            conn.rollback()
            return error(config.MAX_HOURS_MSG, 422)
        room = conn.execute("SELECT * FROM rooms WHERE id = ?", (b["room_id"],)).fetchone()
        if room and new_end_min > (parse_hhmm(room["close_time"]) or 0):
            conn.rollback()
            return error("续约后超出自习室关闭时间（{}）".format(room["close_time"]))
        if _conflict_exists(conn, b["seat_id"], b["date"], b["start_time"], new_end, exclude_id=b["id"]):
            conn.rollback()
            return error("该座位在续约时间段内已被他人预约，无法续约", 409)
        conn.execute("UPDATE bookings SET end_time = ?, remind_sent = 0, expired_sent = 0, updated_at = ? "
                     "WHERE id = ?", (new_end, db.now_str(), booking_id))
        conn.commit()
    finally:
        conn.close()

    ws_server.broadcast({"type": "seat_updated", "payload": {
        "seat_id": b["seat_id"], "room_id": b["room_id"], "status": b["status"],
        "reason": "renewed", "end_time": new_end}})
    return json_response({"id": booking_id, "end_time": new_end, "status": b["status"]})


def api_leave(user, booking_id):
    """主动离座：预约置为 completed，座位立即释放（无论 reserved 还是超时占用 occupied）。"""
    conn = db.connect()
    try:
        conn.execute("BEGIN IMMEDIATE")
        b = _own_booking(conn, user, booking_id)
        if not b:
            conn.rollback()
            return error("预约不存在或无权操作", 404)
        if b["status"] not in ("reserved", "occupied"):
            conn.rollback()
            return error("该预约已结束或已取消")
        conn.execute("UPDATE bookings SET status = 'completed', updated_at = ? "
                     "WHERE id = ? AND status IN ('reserved','occupied')",
                     (db.now_str(), booking_id))
        conn.execute("UPDATE seats SET status = 'available' WHERE id = ? AND status IN ('reserved','occupied')",
                     (b["seat_id"],))
        conn.commit()
    finally:
        conn.close()
    ws_server.broadcast({"type": "seat_updated", "payload": {
        "seat_id": b["seat_id"], "room_id": b["room_id"], "status": "available", "reason": "left"}})
    return json_response({"id": booking_id, "status": "completed"})


def api_cancel(user, booking_id):
    """取消预约：仅未开始的 reserved 可取消；进行中/超时占用须用离座。"""
    conn = db.connect()
    try:
        conn.execute("BEGIN IMMEDIATE")
        b = _own_booking(conn, user, booking_id)
        if not b:
            conn.rollback()
            return error("预约不存在或无权操作", 404)
        if b["status"] != "reserved":
            conn.rollback()
            return error("该预约已开始或已结束，不能取消（进行中请使用「离座」释放座位）")
        conn.execute("UPDATE bookings SET status = 'cancelled', updated_at = ? WHERE id = ? AND status = 'reserved'",
                     (db.now_str(), booking_id))
        conn.execute("UPDATE seats SET status = 'available' WHERE id = ? AND status = 'reserved'",
                     (b["seat_id"],))
        conn.commit()
    finally:
        conn.close()
    ws_server.broadcast({"type": "seat_updated", "payload": {
        "seat_id": b["seat_id"], "room_id": b["room_id"], "status": "available", "reason": "cancelled"}})
    return json_response({"id": booking_id, "status": "cancelled"})


# ── 管理端 ──────────────────────────────────────────────────────────────

def api_admin_bookings(query):
    conn = db.connect()
    try:
        sql = ("SELECT b.*, u.student_id, u.name AS user_name, r.name AS room_name, s.seat_no "
               "FROM bookings b JOIN users u ON u.id = b.user_id "
               "JOIN rooms r ON r.id = b.room_id JOIN seats s ON s.id = b.seat_id WHERE 1=1")
        args = []
        if query.get("date"):
            sql += " AND b.date = ?"
            args.append(query["date"])
        if query.get("status") in config.BOOKING_STATUSES:
            sql += " AND b.status = ?"
            args.append(query["status"])
        sql += " ORDER BY b.date DESC, b.start_time DESC LIMIT 500"
        rows = conn.execute(sql, args).fetchall()
        out = [dict(r) for r in rows]
        return json_response(out)
    finally:
        conn.close()


def api_admin_create_room(data):
    name = (data.get("name") or "").strip()
    if not name:
        return error("自习室名称不能为空")
    location = (data.get("location") or "").strip()
    ot, ct = data.get("open_time") or config.OPEN_TIME, data.get("close_time") or config.CLOSE_TIME
    if parse_hhmm(ot) is None or parse_hhmm(ct) is None or parse_hhmm(ct) <= parse_hhmm(ot):
        return error("开放时间格式不正确（须为整点且关闭晚于开放）")
    status = data.get("status", "open")
    if status not in config.ROOM_STATUSES:
        return error("自习室状态仅支持 open/closed")
    conn = db.connect()
    try:
        conn.execute("BEGIN IMMEDIATE")
        cur = conn.execute(
            "INSERT INTO rooms (name, location, open_time, close_time, status, created_at) "
            "VALUES (?,?,?,?,?,?)", (name, location, ot, ct, status, db.now_str()))
        rid = cur.lastrowid
        conn.commit()
        return json_response({"id": rid, "name": name, "location": location,
                              "open_time": ot, "close_time": ct, "status": status, "seat_total": 0,
                              "seat_available": 0}, 201)
    finally:
        conn.close()


def api_admin_update_room(rid, data):
    conn = db.connect()
    try:
        conn.execute("BEGIN IMMEDIATE")
        room = conn.execute("SELECT * FROM rooms WHERE id = ?", (rid,)).fetchone()
        if not room:
            conn.rollback()
            return error("自习室不存在", 404)
        fields = {"name": "name", "location": "location", "open_time": "open_time",
                  "close_time": "close_time", "status": "status"}
        sets, args = [], []
        for key, col in fields.items():
            if key in data and data[key] not in (None, ""):
                val = data[key]
                if key == "status" and val not in config.ROOM_STATUSES:
                    conn.rollback()
                    return error("自习室状态仅支持 open/closed")
                if key in ("open_time", "close_time") and parse_hhmm(val) is None:
                    conn.rollback()
                    return error("时间格式不正确")
                sets.append("{} = ?".format(col))
                args.append(val)
        if not sets:
            conn.rollback()
            return error("没有可更新的字段")
        args.append(rid)
        conn.execute("UPDATE rooms SET {} WHERE id = ?".format(", ".join(sets)), args)
        conn.commit()
        row = conn.execute("SELECT * FROM rooms WHERE id = ?", (rid,)).fetchone()
        return json_response(dict(row))
    finally:
        conn.close()


def api_admin_delete_room(rid):
    conn = db.connect()
    try:
        conn.execute("BEGIN IMMEDIATE")
        room = conn.execute("SELECT * FROM rooms WHERE id = ?", (rid,)).fetchone()
        if not room:
            conn.rollback()
            return error("自习室不存在", 404)
        n = conn.execute("SELECT COUNT(*) AS c FROM bookings WHERE room_id = ?", (rid,)).fetchone()["c"]
        if n:
            conn.rollback()
            return error("该自习室存在 {} 条预约记录，不能删除（可将其状态置为 closed）".format(n), 409)
        conn.execute("DELETE FROM seats WHERE room_id = ?", (rid,))
        conn.execute("DELETE FROM rooms WHERE id = ?", (rid,))
        conn.commit()
        return json_response({"deleted": rid})
    finally:
        conn.close()


def api_admin_create_seat(data):
    room_id, seat_no = data.get("room_id"), (data.get("seat_no") or "").strip()
    has_power = 1 if data.get("has_power") else 0
    if not room_id or not seat_no:
        return error("需要 room_id 与 seat_no")
    conn = db.connect()
    try:
        conn.execute("BEGIN IMMEDIATE")
        if not conn.execute("SELECT id FROM rooms WHERE id = ?", (room_id,)).fetchone():
            conn.rollback()
            return error("自习室不存在", 404)
        try:
            cur = conn.execute("INSERT INTO seats (room_id, seat_no, has_power, status) VALUES (?,?,?,?)",
                               (room_id, seat_no, has_power, "available"))
        except Exception:
            conn.rollback()
            return error("该自习室已存在相同座位号", 409)
        sid = cur.lastrowid
        conn.commit()
        return json_response({"id": sid, "room_id": room_id, "seat_no": seat_no,
                              "has_power": bool(has_power), "status": "available"}, 201)
    finally:
        conn.close()


def api_admin_update_seat(sid, data):
    conn = db.connect()
    try:
        conn.execute("BEGIN IMMEDIATE")
        seat = conn.execute("SELECT * FROM seats WHERE id = ?", (sid,)).fetchone()
        if not seat:
            conn.rollback()
            return error("座位不存在", 404)
        sets, args = [], []
        if "seat_no" in data and data["seat_no"] not in (None, ""):
            sets.append("seat_no = ?")
            args.append(str(data["seat_no"]).strip())
        if "has_power" in data:
            sets.append("has_power = ?")
            args.append(1 if data["has_power"] else 0)
        if not sets:
            conn.rollback()
            return error("没有可更新的字段")
        args.append(sid)
        try:
            conn.execute("UPDATE seats SET {} WHERE id = ?".format(", ".join(sets)), args)
        except Exception:
            conn.rollback()
            return error("该自习室已存在相同座位号", 409)
        conn.commit()
        row = conn.execute("SELECT * FROM seats WHERE id = ?", (sid,)).fetchone()
        return json_response(dict(row))
    finally:
        conn.close()


SEAT_ADMIN_STATUSES = ("available", "disabled", "broken")
REASON_MAP = {"available": "enabled", "disabled": "disabled", "broken": "broken"}


def api_admin_set_seat_status(sid, data):
    status = data.get("status")
    if status not in SEAT_ADMIN_STATUSES:
        return error("状态仅支持 available/disabled/broken")
    conn = db.connect()
    try:
        conn.execute("BEGIN IMMEDIATE")
        seat = conn.execute("SELECT * FROM seats WHERE id = ?", (sid,)).fetchone()
        if not seat:
            conn.rollback()
            return error("座位不存在", 404)
        if status in ("disabled", "broken") and seat["status"] in ("reserved", "occupied"):
            conn.rollback()
            return error("该座位有进行中的预约，请先处理预约再变更状态", 409)
        conn.execute("UPDATE seats SET status = ? WHERE id = ?", (status, sid))
        conn.commit()
    finally:
        conn.close()
    ws_server.broadcast({"type": "seat_updated", "payload": {
        "seat_id": sid, "room_id": seat["room_id"], "status": status,
        "reason": REASON_MAP[status]}})
    return json_response({"id": sid, "status": status})


def api_admin_delete_seat(sid):
    conn = db.connect()
    try:
        conn.execute("BEGIN IMMEDIATE")
        seat = conn.execute("SELECT * FROM seats WHERE id = ?", (sid,)).fetchone()
        if not seat:
            conn.rollback()
            return error("座位不存在", 404)
        n = conn.execute("SELECT COUNT(*) AS c FROM bookings WHERE seat_id = ?", (sid,)).fetchone()["c"]
        if n:
            conn.rollback()
            return error("该座位存在 {} 条预约记录，不能删除（可将其状态置为 disabled）".format(n), 409)
        conn.execute("DELETE FROM seats WHERE id = ?", (sid,))
        conn.commit()
        return json_response({"deleted": sid})
    finally:
        conn.close()


# ── 路由分发 ────────────────────────────────────────────────────────────

_ROUTES = [
    (r"^/api/register$", ["POST"], lambda u, q, d, h: api_register(d), False),
    (r"^/api/login$", ["POST"], lambda u, q, d, h: api_login(d), False),
    (r"^/api/logout$", ["POST"], lambda u, q, d, h: json_response({"ok": True}), True),
    (r"^/api/me$", ["GET"], lambda u, q, d, h: api_me(u), True),
    (r"^/api/rooms$", ["GET"], lambda u, q, d, h: api_rooms(), True),
    (r"^/api/rooms/(\d+)/seats$", ["GET"],
     lambda u, q, d, h, m: api_room_seats(int(m.group(1)), q), True),
    (r"^/api/my-bookings$", ["GET"], lambda u, q, d, h: api_my_bookings(u), True),
    (r"^/api/bookings$", ["POST"], lambda u, q, d, h: api_create_booking(u, d), True),
    (r"^/api/bookings/(\d+)/renew$", ["POST"],
     lambda u, q, d, h, m: api_renew(u, int(m.group(1)), d), True),
    (r"^/api/bookings/(\d+)/leave$", ["POST"],
     lambda u, q, d, h, m: api_leave(u, int(m.group(1))), True),
    (r"^/api/bookings/(\d+)/cancel$", ["POST"],
     lambda u, q, d, h, m: api_cancel(u, int(m.group(1))), True),
    (r"^/api/admin/bookings$", ["GET"], lambda u, q, d, h: api_admin_bookings(q), True, "admin"),
    (r"^/api/admin/rooms$", ["POST"], lambda u, q, d, h: api_admin_create_room(d), True, "admin"),
    (r"^/api/admin/rooms/(\d+)$", ["PUT", "DELETE"],
     lambda u, q, d, h, m: (api_admin_update_room(int(m.group(1)), d)
                            if h == "PUT" else api_admin_delete_room(int(m.group(1)))), True, "admin"),
    (r"^/api/admin/seats$", ["POST"], lambda u, q, d, h: api_admin_create_seat(d), True, "admin"),
    (r"^/api/admin/seats/(\d+)$", ["PUT", "DELETE"],
     lambda u, q, d, h, m: (api_admin_update_seat(int(m.group(1)), d)
                            if h == "PUT" else api_admin_delete_seat(int(m.group(1)))), True, "admin"),
    (r"^/api/admin/seats/(\d+)/status$", ["PUT"],
     lambda u, q, d, h, m: api_admin_set_seat_status(int(m.group(1)), d), True, "admin"),
]


def _call_handler(handler, user, query, data, method, m):
    """按处理器签名调用：带路径参数(m)的接收 5 参，其余接收 4 参。"""
    try:
        import inspect
        n = len(inspect.signature(handler).parameters)
    except Exception:
        n = 4
    if n >= 5:
        return handler(user, query, data, method, m)
    return handler(user, query, data, method)


def dispatch(method, path, query, body_bytes, headers):
    """返回 (http_status, dict)。method 为 'GET','POST','PUT','DELETE'。"""
    for pattern, methods, handler, need_auth, *rest in _ROUTES:
        m = re.match(pattern, path)
        if not m:
            continue
        if method not in methods:
            return error("方法不允许", 405)
        user = None
        if need_auth:
            got = authenticate(headers)
            if not got:
                return error("未登录或凭证无效", 401)
            user = got[0]
            if rest and rest[0] == "admin" and user["role"] != "admin":
                return error("需要管理员权限", 403)
        if method in ("POST", "PUT", "DELETE"):
            data = parse_body(body_bytes)
            if data is None:
                return error("请求体不是合法 JSON")
        else:
            data = {}
        try:
            return _call_handler(handler, user, query, data, method, m)
        except Exception as exc:
            import traceback
            traceback.print_exc()
            return error("服务器内部错误：" + str(exc), 500)
    return error("接口不存在", 404)