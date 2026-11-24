"""Opt-in LAN observation and scoped control over the existing desktop runtime."""

import base64
import hmac
import json
import secrets
import socket
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib.util import find_spec
from io import BytesIO
from pathlib import Path
from socketserver import TCPServer
from urllib.parse import parse_qs, urlsplit

ASSETS = Path(__file__).resolve().parents[1] / "config/desktop/lan"


class LanHttpServer(ThreadingHTTPServer):
    """Bind the numeric LAN address without HTTPServer's unnecessary reverse DNS lookup."""

    def server_bind(self) -> None:
        TCPServer.server_bind(self)
        self.server_name, self.server_port = self.server_address


class LanService:
    """Own an independent LAN listener; desktop credentials/configuration are never exposed.

    Observation and remote writes are separate opt-ins. Access tokens rotate on
    each enable, travel in URL fragments and authenticate API requests as headers.
    Restarting the desktop leaves this listener disabled until explicitly enabled.
    """

    def __init__(self, desktop):
        self.desktop = desktop
        self.lock = threading.RLock()
        self.server = None
        self.thread = None
        self.token = ""
        self.remote_control = False
        self.clients = {}
        self.urls = []
        self.qr = None

    def status(self) -> dict:
        """Return the live listener state and private pairing URLs to the desktop only."""
        with self.lock:
            self.clients = {key: seen for key, seen in self.clients.items() if time.monotonic() - seen < 15}
            return {
                "enabled": self.server is not None,
                "port": self.server.server_port if self.server else None,
                "urls": self.urls,
                "qrDataUrl": self.qr,
                "clients": len(self.clients),
                "remoteControl": self.remote_control,
            }

    def set_enabled(self, enabled: bool) -> dict:
        """Start/stop the owned HTTP service; fail visibly if binding is unavailable."""
        if not isinstance(enabled, bool):
            raise ValueError("Expected enabled to be boolean.")
        if not enabled:
            self.close()
            return self.status()
        with self.lock:
            if self.server:
                return self.status()
            try:
                addresses = {entry[4][0] for entry in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET)}
            except OSError:
                addresses = set()
            addresses = sorted(address for address in addresses if not address.startswith(("127.", "169.254."))) or [
                "127.0.0.1"
            ]
            self.token = secrets.token_urlsafe(32)
            server = LanHttpServer(("0.0.0.0", 0), LanHandler)
            server.daemon_threads = True
            server.controller = self
            self.server = server
            self.urls = [f"http://{address}:{server.server_port}/#token={self.token}" for address in addresses]
            server.allowed_hosts = {
                f"{address}:{server.server_port}" for address in [*addresses, "127.0.0.1", "localhost"]
            }
            if find_spec("qrcode"):
                try:
                    import qrcode

                    buffer = BytesIO()
                    qrcode.make(self.urls[0]).save(buffer, format="PNG")
                    self.qr = "data:image/png;base64," + base64.b64encode(buffer.getvalue()).decode()
                except ImportError:
                    # QR images are optional; pairing by copied URL remains available.
                    self.qr = None
            self.thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True)
            self.thread.start()
            return self.status()

    def set_remote_control(self, enabled: bool) -> dict:
        """Allow only prompt/abort/approval on existing sessions, never arbitrary desktop methods."""
        with self.lock:
            if not isinstance(enabled, bool) or not self.server:
                raise ValueError("请先开启跨设备互联，再设置远程控制。")
            self.remote_control = enabled
            return self.status()

    def snapshot(self, key: str | None) -> dict:
        """Expose bounded text projections, excluding provider keys, paths to configs and images."""
        rows = sorted(self.desktop.metas(), key=lambda row: row.get("modifiedAt", 0), reverse=True)
        rows = [row for row in rows if not row.get("archivedAt")][:100]
        sessions = [
            {
                "sessionId": row["sessionId"],
                "name": row.get("name", "新会话"),
                "active": row["sessionId"] in self.desktop.sessions.running,
            }
            for row in rows
        ]
        key = key or (sessions[0]["sessionId"] if sessions else None)
        if key and key not in {row["sessionId"] for row in sessions}:
            raise ValueError("会话不存在或已归档。")
        messages = []
        if key:
            baseline = self.desktop.sessions.baseline(key)["transcript"]
            records = baseline["messages"][-79:]
            if stream := baseline.get("streaming"):
                records = [
                    *records,
                    {"kind": "assistant", "text": stream.get("text", ""), "tools": stream.get("tools", [])},
                ]
            remaining = 256000
            for message in reversed(records):
                row = {
                    "kind": message.get("kind", "assistant"),
                    "text": str(message.get("text", ""))[-16000:],
                    "tools": [
                        {"name": tool.get("name", "tool"), "output": str(tool.get("output", ""))[-8000:]}
                        for tool in message.get("tools", [])[-5:]
                    ],
                }
                size = len(row["text"]) + sum(len(tool["output"]) for tool in row["tools"])
                if size > remaining:
                    break
                remaining -= size
                messages.insert(0, row)
        with self.desktop.sessions.lock:
            permissions = [
                {"id": row["id"], "title": row["title"], "message": row["message"]}
                for row in self.desktop.sessions.approvals.values()
                if row["sessionId"] == key
            ]
        return {
            "sessions": sessions,
            "sessionId": key,
            "messages": messages,
            "permissions": permissions,
            "remoteControl": self.remote_control,
        }

    def close(self) -> None:
        """Invalidate the pairing token immediately, stop listening and revoke remote control."""
        with self.lock:
            server, self.server = self.server, None
            thread, self.thread = self.thread, None
            self.token, self.urls, self.qr = "", [], None
            self.remote_control = False
            self.clients.clear()
        if server:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)


class LanHandler(BaseHTTPRequestHandler):
    """Same-origin, authenticated API with no generic invoke endpoint or credential query strings."""

    timeout = 10

    def log_message(self, *_):
        pass

    def reply(self, status, content, mime="application/json; charset=utf-8"):
        payload = content if isinstance(content, bytes) else json.dumps(content, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header("Content-Type", mime)
        self.send_header("Cache-Control", "no-store")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header(
            "Content-Security-Policy",
            "default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'; frame-ancestors 'none'",
        )
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        try:
            self.wfile.write(payload)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def authorized(self):
        host, origin = self.headers.get("Host", ""), self.headers.get("Origin")
        control = self.server.controller
        return (
            host in self.server.allowed_hosts
            and (not origin or origin == "http://" + host)
            and bool(control.token)
            and hmac.compare_digest(self.headers.get("Authorization", ""), "Bearer " + control.token)
        )

    def do_GET(self):
        address = urlsplit(self.path)
        if address.path in {"/", "/app.js", "/style.css"} and self.headers.get("Host") in self.server.allowed_hosts:
            filename, mime = {
                "/": ("index.html", "text/html; charset=utf-8"),
                "/app.js": ("app.js", "text/javascript; charset=utf-8"),
                "/style.css": ("style.css", "text/css; charset=utf-8"),
            }[address.path]
            return self.reply(200, (ASSETS / filename).read_bytes(), mime)
        if not self.authorized():
            return self.reply(401, {"error": "访问链接无效或已过期，请重新从电脑获取。"})
        if address.path != "/api/snapshot":
            return self.reply(404, {"error": "Unknown route."})
        try:
            control = self.server.controller
            with control.lock:
                if not self.authorized():
                    return self.reply(401, {"error": "Unauthorized."})
                if len(control.clients) < 1024:
                    control.clients[self.client_address[0]] = time.monotonic()
                value = control.snapshot(parse_qs(address.query).get("sessionId", [None])[0])
            return self.reply(200, value)
        except ValueError as error:
            return self.reply(400, {"error": str(error)})

    def do_POST(self):
        if not self.authorized():
            return self.reply(401, {"error": "Unauthorized."})
        control = self.server.controller
        if self.path != "/api/action":
            return self.reply(404, {"error": "Unknown route."})
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if not 0 < length <= 65536:
                return self.reply(413, {"error": "Request exceeds 64 KiB."})
            # Remote clients cannot hold the owner's revocation lock while
            # supplying network bytes. Recheck authentication before dispatch.
            value = json.loads(self.rfile.read(length))
            if not isinstance(value, dict):
                raise ValueError("Expected a JSON object.")
        except (OSError, ValueError):
            return self.reply(400, {"error": "Invalid or incomplete request body."})
        with control.lock:
            if not self.authorized():
                return self.reply(401, {"error": "Unauthorized."})
            if not control.remote_control:
                return self.reply(403, {"error": "电脑端尚未允许远程控制。"})
            try:
                method = value.get("method")
                if method not in {"prompt", "abort", "respondPermission"}:
                    return self.reply(403, {"error": "此操作不允许从远程调用。"})
                key = value["sessionId"]
                control.snapshot(key)
                if method == "prompt":
                    text = value.get("text")
                    if (
                        not isinstance(text, str)
                        or not text.strip()
                        or len(text) > 32000
                        or text.lstrip().startswith("/")
                    ):
                        raise ValueError("请输入非空消息（远程不支持修改配置的斜杠命令）。")
                    args = {"sessionId": key, "text": text}
                elif method == "respondPermission":
                    args = {"sessionId": key, "requestId": value["requestId"], "answer": value["answer"]}
                else:
                    args = {"sessionId": key}
                control.desktop.invoke(method, args)
                return self.reply(200, {"ok": True})
            except (KeyError, TypeError, ValueError):
                return self.reply(400, {"error": "请求无效或会话状态已改变，请刷新后重试。"})
