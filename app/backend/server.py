# -*- coding: utf-8 -*-
"""服务入口：HTTP（REST + 静态页面）+ WebSocket + 定时任务。

启动：python server.py   （默认 http://127.0.0.1:8000）
前端为同一端口托管的原生 SPA；未匹配 /api 的路径回退到 frontend/index.html。
"""
import os
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs
from socketserver import ThreadingMixIn

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import config
import db
import http_api
import scheduler
import ws_server

MIME = {
    ".html": "text/html; charset=utf-8",
    ".js": "application/javascript; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".json": "application/json; charset=utf-8",
    ".svg": "image/svg+xml",
    ".png": "image/png",
    ".ico": "image/x-icon",
}


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    server_version = "StudyRoomServer/1.0"

    # ── 工具 ──────────────────────────────────────────────────────────
    def _send_json(self, status, obj):
        body = (__import__("json").dumps(obj, ensure_ascii=False)).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _send_bytes(self, status, body, ctype):
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _read_body(self):
        length = int(self.headers.get("Content-Length") or 0)
        return self.rfile.read(length) if length else b""

    def _serve_static(self, path):
        """静态文件；找不到回退 index.html（SPA）。"""
        rel = path.lstrip("/") or "index.html"
        full = os.path.normpath(os.path.join(config.FRONTEND_DIR, rel))
        if not full.startswith(os.path.normpath(config.FRONTEND_DIR)):
            full = os.path.join(config.FRONTEND_DIR, "index.html")
        if not os.path.isfile(full):
            full = os.path.join(config.FRONTEND_DIR, "index.html")
        try:
            with open(full, "rb") as f:
                body = f.read()
            ext = os.path.splitext(full)[1].lower()
            # 静态资源不缓存，避免浏览器加载到旧版本 JS/CSS
            self.send_response(200)
            self.send_header("Content-Type", MIME.get(ext, "application/octet-stream"))
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-cache")
            self.end_headers()
            self.wfile.write(body)
        except Exception:
            self._send_json(404, {"ok": False, "error": "页面不存在"})

    # ── WebSocket 升级 ────────────────────────────────────────────────
    def _handle_ws_upgrade(self, query):
        key = self.headers.get("Sec-WebSocket-Key", "")
        if not key:
            self._send_json(400, {"ok": False, "error": "缺少 Sec-WebSocket-Key"})
            return
        accept = ws_server._make_accept_key(key)
        self.send_response(101)
        self.send_header("Upgrade", "websocket")
        self.send_header("Connection", "Upgrade")
        self.send_header("Sec-WebSocket-Accept", accept)
        self.end_headers()
        # 连接线程内运行帧读循环（阻塞直到断开）
        ws_server.handle_websocket(self.connection, dict(self.headers), query)

    def _dispatch(self, method):
        parsed = urlparse(self.path)
        path = parsed.path
        if path == "/ws":
            query = {k: v[0] for k, v in parse_qs(parsed.query).items()}
            self._handle_ws_upgrade(query)
            return
        if path.startswith("/api/"):
            try:
                status, obj = http_api.dispatch(
                    method, path,
                    {k: v[0] for k, v in parse_qs(parsed.query).items()},
                    self._read_body(), self.headers)
            except Exception as exc:
                import traceback
                traceback.print_exc()
                status, obj = 500, {"ok": False, "error": "服务器内部错误：" + str(exc)}
            self._send_json(status, obj)
            return
        if method == "GET":
            self._serve_static(path)
        else:
            self._send_json(405, {"ok": False, "error": "方法不允许"})

    def do_GET(self):
        self._dispatch("GET")

    def do_POST(self):
        self._dispatch("POST")

    def do_PUT(self):
        self._dispatch("PUT")

    def do_DELETE(self):
        self._dispatch("DELETE")

    def handle_error(self, request, client_address):
        # 浏览器/探测客户端断连是常态，不打印完整堆栈
        exc = sys.exc_info()[1]
        if isinstance(exc, (ConnectionResetError, BrokenPipeError, TimeoutError)):
            return
        super().handle_error(request, client_address)

    def log_message(self, fmt, *args):
        sys.stdout.write("[http] %s\n" % (fmt % args))
        sys.stdout.flush()


def main():
    db.init_db()
    db.seed()

    try:
        httpd = ThreadingHTTPServer((config.HOST, config.PORT), Handler)
    except OSError as exc:
        print("无法绑定 {}:{}：{}".format(config.HOST, config.PORT, exc), flush=True)
        sys.exit(1)

    scheduler.start()
    print("自习室预约系统已启动: http://{}:{}/".format(config.HOST, config.PORT), flush=True)
    print("默认管理员: 学号 {} / 密码 {}".format(
        db.DEFAULT_ADMIN_STUDENT_ID, db.DEFAULT_ADMIN_PASSWORD), flush=True)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n已停止", flush=True)


if __name__ == "__main__":
    main()