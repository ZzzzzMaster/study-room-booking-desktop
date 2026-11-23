# -*- coding: utf-8 -*-
"""原生 WebSocket（RFC 6455，纯标准库）：握手、帧编解码、按用户推送/全员广播、心跳。"""
import base64
import hashlib
import json
import socket
import struct
import threading

from auth import verify_token

WS_GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"

# 连接表: {conn_id: Conn}
_CONNECTIONS = {}
_CONN_LOCK = threading.Lock()
_next_id = [0]


class Conn:
    __slots__ = ("conn_id", "sock", "user_id", "role", "send_lock")

    def __init__(self, conn_id, sock, user_id, role):
        self.conn_id = conn_id
        self.sock = sock
        self.user_id = user_id
        self.role = role
        self.send_lock = threading.Lock()


def _make_accept_key(key: str) -> str:
    digest = hashlib.sha1((key + WS_GUID).encode("ascii")).digest()
    return base64.b64encode(digest).decode("ascii")


def _send_frame(sock, opcode: int, payload: bytes):
    header = bytearray([0x80 | opcode])
    n = len(payload)
    if n < 126:
        header.append(n)
    elif n < 65536:
        header.append(126)
        header += struct.pack(">H", n)
    else:
        header.append(127)
        header += struct.pack(">Q", n)
    sock.sendall(bytes(header) + payload)


def _recv_exact(sock, n: int) -> bytes:
    buf = b""
    while len(buf) < n:
        chunk = sock.recv(n - len(buf))
        if not chunk:
            raise ConnectionError("socket closed")
        buf += chunk
    return buf


def handle_websocket(sock, headers: dict, query: dict):
    """处理已通过 HTTP 升级校验的连接（在连接线程内执行读循环）。"""
    # 鉴权：token 从查询参数取
    token = (query or {}).get("token", "")
    payload = verify_token(token) if token else None
    if payload is None:
        try:
            _send_frame(sock, 0x8, b"auth failed")
        except Exception:
            pass
        sock.close()
        return

    with _CONN_LOCK:
        _next_id[0] += 1
        cid = _next_id[0]
        conn = Conn(cid, sock, payload["uid"], payload.get("role", "student"))
        _CONNECTIONS[cid] = conn

    try:
        _read_loop(conn)
    finally:
        with _CONN_LOCK:
            _CONNECTIONS.pop(conn.conn_id, None)
        try:
            sock.close()
        except Exception:
            pass


def _read_loop(conn: Conn):
    sock = conn.sock
    fragment = b""
    while True:
        try:
            b1, b2 = _recv_exact(sock, 2)
        except Exception:
            return
        fin = b1 & 0x80
        opcode = b1 & 0x0F
        masked = b2 & 0x80
        length = b2 & 0x7F
        if length == 126:
            length = struct.unpack(">H", _recv_exact(sock, 2))[0]
        elif length == 127:
            length = struct.unpack(">Q", _recv_exact(sock, 8))[0]
        if masked:
            mask_key = _recv_exact(sock, 4)
        else:
            mask_key = None
        payload = _recv_exact(sock, length) if length else b""
        if mask_key:
            payload = bytes(c ^ mask_key[i % 4] for i, c in enumerate(payload))

        if opcode == 0x8:  # close
            try:
                _send_frame(sock, 0x8, payload)
            except Exception:
                pass
            return
        if opcode == 0x9:  # ping
            try:
                with conn.send_lock:
                    _send_frame(sock, 0xA, payload)
            except Exception:
                return
        elif opcode == 0xA:  # pong -> 忽略
            pass
        elif opcode == 0x0:  # continuation
            fragment += payload
            if fin:
                _handle_text(conn, fragment)
                fragment = b""
        elif opcode == 0x1:  # text
            if fin:
                _handle_text(conn, payload)
            else:
                fragment = payload
        # 其它 opcode 忽略


def _handle_text(conn: Conn, raw: bytes):
    try:
        msg = json.loads(raw.decode("utf-8"))
    except Exception:
        return
    if isinstance(msg, dict) and msg.get("type") == "ping":
        try:
            with conn.send_lock:
                _send_frame(conn.sock, 0x1, json.dumps({"type": "pong"}).encode("utf-8"))
        except Exception:
            pass


# ── 对外推送 ────────────────────────────────────────────────────────────
def _encode(msg: dict) -> bytes:
    return json.dumps(msg, ensure_ascii=False).encode("utf-8")


def send_to_user(user_id, msg: dict):
    text = _encode(msg)
    with _CONN_LOCK:
        targets = [c for c in _CONNECTIONS.values() if c.user_id == user_id]
    for c in targets:
        try:
            with c.send_lock:
                _send_frame(c.sock, 0x1, text)
        except Exception:
            pass  # 读循环会负责清理


def broadcast(msg: dict):
    """广播给所有在线客户端。"""
    text = _encode(msg)
    with _CONN_LOCK:
        targets = list(_CONNECTIONS.values())
    for c in targets:
        try:
            with c.send_lock:
                _send_frame(c.sock, 0x1, text)
        except Exception:
            pass


def online_count() -> int:
    with _CONN_LOCK:
        return len(_CONNECTIONS)