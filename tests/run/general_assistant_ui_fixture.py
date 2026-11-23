"""Serve a keyless local model alias for real Electron conversation acceptance."""

import argparse
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


class GeneralPeer(BaseHTTPRequestHandler):
    """Return normal text and reported tokens, with no tool calls or price metadata."""

    def log_message(self, *_):
        pass

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        answer = "我是 VERA，可以帮助你问答、写作和编程。我会根据你的任务选择工具，自我介绍不需要读取项目文件。"
        usage = {
            "prompt_tokens": 11,
            "completion_tokens": 7,
            "total_tokens": 18,
            "prompt_tokens_details": {"cached_tokens": 3},
        }
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream" if body.get("stream") else "application/json")
        self.end_headers()
        if not body.get("stream"):
            self.wfile.write(
                json.dumps(
                    {
                        "id": "local",
                        "object": "chat.completion",
                        "created": 1,
                        "model": "deepseek-flash",
                        "choices": [
                            {"index": 0, "finish_reason": "stop", "message": {"role": "assistant", "content": answer}}
                        ],
                        "usage": usage,
                    }
                ).encode()
            )
            return
        for delta, finish, counters in (({"role": "assistant", "content": answer}, None, None), ({}, "stop", usage)):
            value = {
                "id": "local",
                "object": "chat.completion.chunk",
                "created": 1,
                "model": "deepseek-flash",
                "choices": [{"index": 0, "delta": delta, "finish_reason": finish}],
            }
            if counters:
                value["usage"] = counters
            self.wfile.write(("data: " + json.dumps(value) + "\n\n").encode())
            self.wfile.flush()
        self.wfile.write(b"data: [DONE]\n\n")
        self.wfile.flush()


def main():
    """Publish the public fixture URL; credentials and real inference are never used."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--connection-file", type=Path, required=True)
    args = parser.parse_args()
    server = ThreadingHTTPServer(("127.0.0.1", 0), GeneralPeer)
    args.connection_file.write_text(json.dumps({"url": f"http://127.0.0.1:{server.server_port}/v1"}), encoding="utf-8")
    try:
        server.serve_forever()
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
