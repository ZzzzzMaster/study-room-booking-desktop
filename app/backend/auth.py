# -*- coding: utf-8 -*-
"""认证：PBKDF2 密码哈希（stdlib，替代 BCrypt）+ HMAC-SHA256 签名 token（类 JWT，无外部依赖）。"""
import base64
import hashlib
import hmac
import json
import os
import time

from config import SECRET_KEY, TOKEN_TTL_HOURS

PBKDF2_ITERATIONS = 100_000
ALGO = "pbkdf2_sha256"


# ── 密码哈希 ───────────────────────────────────────────────────────────
def hash_password(password: str) -> str:
    salt = os.urandom(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, PBKDF2_ITERATIONS)
    return "{}${}${}${}".format(
        ALGO,
        PBKDF2_ITERATIONS,
        base64.b64encode(salt).decode("ascii"),
        base64.b64encode(dk).decode("ascii"),
    )


def verify_password(password: str, stored: str) -> bool:
    try:
        algo, iters, salt_b64, hash_b64 = stored.split("$")
        if algo != ALGO:
            return False
        salt = base64.b64decode(salt_b64.encode("ascii"))
        expect = base64.b64decode(hash_b64.encode("ascii"))
        dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, int(iters))
        return hmac.compare_digest(dk, expect)
    except Exception:
        return False


# ── token（header.payload.signature）───────────────────────────────────
def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64url_decode(s: str) -> bytes:
    pad = "=" * (-len(s) % 4)
    return base64.urlsafe_b64decode((s + pad).encode("ascii"))


def _sign(header_b64: str, payload_b64: str) -> str:
    msg = (header_b64 + "." + payload_b64).encode("ascii")
    return _b64url(hmac.new(SECRET_KEY, msg, hashlib.sha256).digest())


def create_token(user_id: int, role: str) -> str:
    header = _b64url(json.dumps({"alg": "HS256", "typ": "JWT"}).encode("utf-8"))
    payload = _b64url(json.dumps({
        "uid": user_id,
        "role": role,
        "exp": int(time.time()) + TOKEN_TTL_HOURS * 3600,
    }).encode("utf-8"))
    return header + "." + payload + "." + _sign(header, payload)


def verify_token(token: str):
    """返回 {'uid','role','exp'} 或 None（无效/过期）。"""
    try:
        header_b64, payload_b64, sig = token.split(".")
        if not hmac.compare_digest(sig, _sign(header_b64, payload_b64)):
            return None
        payload = json.loads(_b64url_decode(payload_b64).decode("utf-8"))
        if payload.get("exp", 0) < time.time():
            return None
        return payload
    except Exception:
        return None