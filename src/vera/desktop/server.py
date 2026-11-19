"""Authenticated loopback-only JSON requests and ordered long-poll events."""

import argparse
import hmac
import json
import os
import secrets
import signal
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from vera import global_config_dir
from vera.desktop.service import DesktopService


class DesktopServer(ThreadingHTTPServer):
    """Never listen on a public interface; deny cross-origin browser requests."""

    daemon_threads = True

    def __init__(self, address, service: DesktopService, token: str):
        if address[0] != "127.0.0.1" or len(token) < 32:
            raise ValueError("Desktop requires loopback and a bearer token of at least 32 characters.")
        self.service, self.token = service, token
        super().__init__(address, Handler)


class Handler(BaseHTTPRequestHandler):
    """Bound request sizes and authenticate before parsing client-controlled JSON."""

    def log_message(self, *_):
        pass

    def _authorized(self):
        origin = self.headers.get("Origin")
        return not origin and hmac.compare_digest(self.headers.get("Authorization", ""), "Bearer " + self.server.token)

    def _reply(self, status: int, value):
        payload = json.dumps(value, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        try:
            self.wfile.write(payload)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def do_GET(self):
        if not self._authorized():
            return self._reply(401, {"error": "Unauthorized local desktop client."})
        address = urlsplit(self.path)
        if address.path == "/health":
            return self._reply(200, {"ok": True, "protocolVersion": 1, "cursor": self.server.service.events.sequence})
        if address.path == "/events":
            try:
                cursor = int(parse_qs(address.query).get("after", ["0"])[0])
                return self._reply(200, self.server.service.events.read(cursor))
            except ValueError:
                return self._reply(400, {"error": "Invalid event cursor."})
        return self._reply(404, {"error": "Unknown route."})

    def do_POST(self):
        if not self._authorized():
            return self._reply(401, {"error": "Unauthorized local desktop client."})
        if self.path != "/invoke":
            return self._reply(404, {"error": "Unknown route."})
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if not 0 < length <= 12_000_000:
                return self._reply(413, {"error": "Request too large or empty."})
            value = json.loads(self.rfile.read(length))
            result = self.server.service.invoke(value["method"], value.get("args"))
            return self._reply(200, {"result": result})
        except __import__("pydantic").ValidationError as error:
            fields = [".".join(map(str, item["loc"])) for item in error.errors(include_input=False)]
            return self._reply(400, {"error": "Invalid configuration fields: " + ", ".join(fields)[:500]})
        except (KeyError, ValueError, TypeError) as error:
            return self._reply(400, {"error": str(error)[:600]})
        except Exception:
            # Provider errors and raw configs may contain credentials; keep them private.
            return self._reply(500, {"error": "Operation failed. Check configuration and local service logs."})


def main():
    """Launch independently of Electron, with optional private config and discovery file."""
    parser = argparse.ArgumentParser(description="VERA desktop local service")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--directory", type=Path, default=global_config_dir / "desktop")
    parser.add_argument("--config", type=Path)
    parser.add_argument("--connection-file", type=Path)
    args = parser.parse_args()
    from vera.config import get_config_from_spec

    token = os.environ.get("VERA_DESKTOP_TOKEN") or secrets.token_urlsafe(48)
    config = get_config_from_spec(str(args.config)) if args.config else None
    service = DesktopService(args.directory, config)
    server = DesktopServer(("127.0.0.1", args.port), service, token)
    if args.connection_file:
        from vera.evolution.process import write_json

        args.connection_file.parent.mkdir(parents=True, exist_ok=True)
        write_json(args.connection_file, {"url": f"http://127.0.0.1:{server.server_port}", "token": token})
        if os.name != "nt":
            args.connection_file.chmod(0o600)
    print(f"VERA desktop service: http://127.0.0.1:{server.server_port}", flush=True)

    def stop_server(*_):
        raise KeyboardInterrupt

    signal.signal(signal.SIGTERM, stop_server)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        service.close()
        server.server_close()
        if args.connection_file:
            args.connection_file.unlink(missing_ok=True)


if __name__ == "__main__":
    main()
