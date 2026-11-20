"""Local OpenAI protocol peer for desktop UI acceptance, without external inference.

Run with ``python -m tests.run.desktop_ui_fixture --connection-file PATH``.
The real desktop transport, provider adapter, Agent Loop and Bash environment
remain in use. Responses request bounded file writes inside the test workspace.
"""

import argparse
import json
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


class ModelPeer(BaseHTTPRequestHandler):
    """Serve the model catalog and a streamed, deterministic completion."""

    def log_message(self, *_):
        pass

    def do_GET(self):
        payload = json.dumps({"object": "list", "data": [{"id": "gpt-4o-mini", "object": "model"}]}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def do_POST(self):
        request = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        prompt = json.dumps(request.get("messages", []))
        marker = "qa-scheduled.txt" if "QA_SCHEDULE" in prompt else "qa-approved.txt"
        command = f"printf vera-ui-ok > {marker}; echo COMPLETE_TASK_AND_SUBMIT_FINAL_OUTPUT; printf vera-ui-done"
        if not request.get("stream"):
            message = {"role": "assistant", "content": "ok"}
            if request.get("tools"):
                message["tool_calls"] = [
                    {
                        "id": "call_ui",
                        "type": "function",
                        "function": {
                            "name": "bash",
                            "arguments": json.dumps({"command": command}),
                        },
                    }
                ]
            payload = json.dumps(
                {
                    "id": "chatcmpl-ui-probe",
                    "object": "chat.completion",
                    "created": 1,
                    "model": "gpt-4o-mini",
                    "choices": [
                        {
                            "index": 0,
                            "finish_reason": "tool_calls" if request.get("tools") else "stop",
                            "message": message,
                        }
                    ],
                    "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
                }
            ).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
            return
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.end_headers()

        def send(delta, finish=None, usage=None):
            payload = {
                "id": "chatcmpl-ui-acceptance",
                "object": "chat.completion.chunk",
                "created": 1,
                "model": "gpt-4o-mini",
                "choices": [{"index": 0, "delta": delta, "finish_reason": finish}],
            }
            if usage:
                payload["usage"] = usage
            self.wfile.write(("data: " + json.dumps(payload) + "\n\n").encode())
            self.wfile.flush()

        try:
            send({"role": "assistant", "reasoning_content": "QA_REASONING: inspect the requested operation."})
            send({"content": "QA_STREAM_FIRST "})
            time.sleep(0.2)
            send({"content": "QA_STREAM_SECOND"})
            send(
                {
                    "tool_calls": [
                        {
                            "index": 0,
                            "id": "call_ui",
                            "type": "function",
                            "function": {
                                "name": "bash",
                                "arguments": json.dumps({"command": command}),
                            },
                        }
                    ]
                }
            )
            send({}, "tool_calls", {"prompt_tokens": 20, "completion_tokens": 10, "total_tokens": 30})
            self.wfile.write(b"data: [DONE]\n\n")
            self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
            pass


def main():
    """Bind an ephemeral loopback port and publish only its public endpoint."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--connection-file", type=Path, required=True)
    parser.add_argument("--port", type=int, default=0)
    args = parser.parse_args()
    server = ThreadingHTTPServer(("127.0.0.1", args.port), ModelPeer)
    args.connection_file.write_text(json.dumps({"url": f"http://127.0.0.1:{server.server_port}/v1"}), encoding="utf-8")
    try:
        server.serve_forever()
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
