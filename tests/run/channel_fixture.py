"""Real local HTTP/WebSocket provider endpoints for channel integration tests, without monkeypatching."""

import asyncio
import json
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Event, Thread

from tests.run.test_web_tools import _model_response


def weixin_message(identifier, user="owner", text="Write a file", **extra):
    return {
        "message_id": identifier,
        "message_type": 1,
        "message_state": 2,
        "from_user_id": user,
        "context_token": f"context-{user}",
        "item_list": [{"type": 1, "text_item": {"text": text}}],
        **extra,
    }


def feishu_event(identifier="one", user="owner", text="Write a file"):
    return {
        "schema": "2.0",
        "header": {
            "event_id": identifier,
            "event_type": "im.message.receive_v1",
            "create_time": "1700000000000",
            "tenant_key": "tenant",
        },
        "event": {
            "sender": {"sender_id": {"open_id": user}, "sender_type": "user"},
            "message": {
                "message_id": identifier,
                "chat_id": "chat",
                "chat_type": "p2p",
                "message_type": "text",
                "content": json.dumps({"text": text}),
            },
        },
    }


@contextmanager
def provider_service(messages=(), *, ws_url="", login_statuses=None):
    state = {
        "messages": list(messages),
        "requests": [],
        "replies": [],
        "models": [],
        "statuses": list(login_statuses or []),
        "send_status": 200,
        "tenant_token_error": None,
        "bot_info_error": None,
    }

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def send_json(self, value, status=200):
            body = json.dumps(value).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            state["requests"].append((self.path, None, dict(self.headers)))
            if self.path == "/open-apis/bot/v3/info/":
                self.send_json(state["bot_info_error"] or {"code": 0, "bot": {"app_name": "test"}})
                return
            status = state["statuses"].pop(0) if state["statuses"] else "confirmed"
            self.send_json(
                {
                    "status": status,
                    "bot_token": "fake-bot-token",
                    "ilink_user_id": "owner",
                    "ilink_bot_id": "bot",
                    "baseurl": state["base_url"],
                }
            )

        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            state["requests"].append((self.path, body, dict(self.headers)))
            if self.path == "/model":
                state["models"].append(body)
                finished = any(message.get("role") == "tool" for message in body["messages"])
                action = (
                    ("bash", {"command": "printf 'once\\n' >> executions.txt"})
                    if not finished
                    else ("channel_finish", {"summary": "done"})
                )
                self.send_json(_model_response([action], False))
            elif self.path.startswith("/ilink/bot/get_bot_qrcode"):
                self.send_json({"qrcode": "fake-qr-key", "qrcode_img_content": "https://example.invalid/test-qr"})
            elif self.path == "/ilink/bot/getupdates":
                batch, state["messages"] = state["messages"], []
                if not batch:
                    __import__("time").sleep(0.1)
                self.send_json({"ret": 0, "msgs": batch, "get_updates_buf": "cursor-saved"})
            elif self.path == "/ilink/bot/sendmessage":
                state["replies"].append(body)
                self.send_json({"ret": 0}, state["send_status"])
            elif self.path == "/callback/ws/endpoint":
                self.send_json(
                    {
                        "code": 0,
                        "data": {
                            "URL": ws_url,
                            "ClientConfig": {
                                "ReconnectCount": 10,
                                "ReconnectInterval": 1,
                                "ReconnectNonce": 1,
                                "PingInterval": 60,
                            },
                        },
                    }
                )
            elif self.path == "/open-apis/auth/v3/tenant_access_token/internal":
                self.send_json(
                    state["tenant_token_error"]
                    or {"code": 0, "tenant_access_token": "fake-tenant-token", "expire": 7200}
                )
            elif self.path.startswith("/open-apis/im/v1/messages"):
                state["replies"].append(body)
                self.send_json({"code": 0, "data": {"message_id": "delivered"}})
            else:
                self.send_json({}, 404)

    with ThreadingHTTPServer(("127.0.0.1", 0), Handler) as server:
        state["base_url"] = f"http://127.0.0.1:{server.server_port}"
        thread = Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            yield state
        finally:
            server.shutdown()
            thread.join(timeout=5)


@contextmanager
def feishu_socket(events):
    import websockets.asyncio.server
    from lark_oapi.ws.pb.pbbp2_pb2 import Frame

    ready, stop = Event(), Event()
    state = {"acks": []}

    async def connection(socket):
        for index, event in enumerate(events):
            frame = Frame(SeqID=index + 1, LogID=index + 1, service=1, method=1, payload=json.dumps(event).encode())
            for key, value in {
                "message_id": str(index),
                "trace_id": str(index),
                "sum": "1",
                "seq": "0",
                "type": "event",
            }.items():
                header = frame.headers.add()
                header.key, header.value = key, value
            await socket.send(frame.SerializeToString())
            while True:
                received = Frame()
                received.ParseFromString(await asyncio.wait_for(socket.recv(), 20))
                if received.method == 1:
                    state["acks"].append(json.loads(received.payload))
                    break
        while not stop.is_set():
            await asyncio.sleep(0.05)

    async def serve():
        async with websockets.asyncio.server.serve(connection, "127.0.0.1", 0) as server:
            state["url"] = f"ws://127.0.0.1:{server.sockets[0].getsockname()[1]}?device_id=test&service_id=1"
            ready.set()
            while not stop.is_set():
                await asyncio.sleep(0.05)

    thread = Thread(target=lambda: asyncio.run(serve()), daemon=True)
    thread.start()
    assert ready.wait(10)
    try:
        yield state
    finally:
        stop.set()
        thread.join(timeout=10)
