"""Verify desktop attachments become real multimodal requests and survive reload."""

import base64
import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from vera.desktop.service import DesktopService


def test_real_worker_sends_structured_image_and_persists_attachment(tmp_path):
    received = []

    class Peer(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def do_POST(self):
            received.append(json.loads(self.rfile.read(int(self.headers["Content-Length"]))))
            chunk = {
                "id": "image-response",
                "object": "chat.completion.chunk",
                "created": 1,
                "model": "vision",
                "choices": [
                    {"index": 0, "delta": {"role": "assistant", "content": "IMAGE_RECEIVED"}, "finish_reason": "stop"}
                ],
                "usage": {"prompt_tokens": 10, "completion_tokens": 2, "total_tokens": 12},
            }
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.end_headers()
            self.wfile.write(("data: " + json.dumps(chunk) + "\n\ndata: [DONE]\n\n").encode())

    peer = ThreadingHTTPServer(("127.0.0.1", 0), Peer)
    thread = threading.Thread(target=peer.serve_forever, daemon=True)
    thread.start()
    service = DesktopService(tmp_path / "state")
    try:
        service.providers.configure(
            {
                "id": "vision",
                "template": "custom",
                "api": "openai-completions",
                "apiKey": "local-test-key",
                "baseUrl": f"http://127.0.0.1:{peer.server_port}/v1",
                "models": [{"id": "vision", "imageInput": True}, {"id": "text", "imageInput": False}],
            }
        )
        image = {"mimeType": "image/png", "data": base64.b64encode(b"test-image-payload").decode()}
        meta = service.invoke(
            "createSession", {"options": {"cwd": str(tmp_path), "provider": "vision", "modelId": "vision"}}
        )
        key = meta["sessionId"]
        service.invoke("prompt", {"sessionId": key, "text": "Inspect image", "images": [image]})
        deadline = time.monotonic() + 30
        while service.sessions.baseline(key)["transcript"]["agentActive"] and time.monotonic() < deadline:
            time.sleep(0.05)
        assert received
        content = received[0]["messages"][-1]["content"]
        assert isinstance(content, list)
        assert {"type": "image_url", "image_url": {"url": "data:image/png;base64," + image["data"]}} in content
        assert service.sessions.get(key)["messages"][0]["images"] == [image]
        service.close()
        service = DesktopService(tmp_path / "state")
        assert service.sessions.baseline(key)["transcript"]["messages"][0]["images"] == [image]
        service.invoke("setModel", {"sessionId": key, "provider": "vision", "modelId": "text"})
        with pytest.raises(ValueError, match="图片"):
            service.invoke("prompt", {"sessionId": key, "text": "Reject image", "images": [image]})
        assert len(received) == 1
    finally:
        service.close()
        peer.shutdown()
        peer.server_close()
        thread.join(timeout=5)
