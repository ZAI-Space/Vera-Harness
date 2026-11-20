"""Produce an actual worker event trace for the TypeScript display contract test.

The deterministic model is the existing test provider; Bash, the worker process,
SQLite and transport projection are real. No external provider is contacted.
"""

import json
import tempfile
import time
from pathlib import Path

from vera.desktop.service import DesktopService


def main():
    """Write one JSON result to stdout; all worker logs remain private artifacts."""
    with tempfile.TemporaryDirectory(prefix="vera-desktop-contract-") as directory:
        root = Path(directory)
        service = DesktopService(
            root / "state",
            {
                "model": {
                    "model_class": "deterministic",
                    "model_name": "contract",
                    "cost_per_call": 0,
                    "outputs": [
                        {
                            "role": "assistant",
                            "content": "Run the actual verification.",
                            "reasoning_content": "Visible provider reasoning.",
                            "extra": {"actions": [{"command": "printf contract-ok > actual.txt"}]},
                        },
                        {
                            "role": "assistant",
                            "content": "Read the result.",
                            "extra": {
                                "actions": [{"command": "echo COMPLETE_TASK_AND_SUBMIT_FINAL_OUTPUT; cat actual.txt"}]
                            },
                        },
                    ],
                },
                "agent": {
                    "system_template": "Use Bash.",
                    "instance_template": "{{task}}",
                    "mode": "yolo",
                    "cost_limit": 1,
                },
            },
        )
        try:
            key = service.invoke("createSession", {"options": {"cwd": str(root)}})["sessionId"]
            service.invoke("setSessionSelections", {"sessionId": key, "permissionPolicy": "yolo"})
            service.invoke("prompt", {"sessionId": key, "text": "Verify the desktop contract."})
            deadline = time.monotonic() + 30
            while service.sessions.baseline(key)["transcript"]["agentActive"] and time.monotonic() < deadline:
                time.sleep(0.03)
            if service.sessions.baseline(key)["transcript"]["agentActive"]:
                raise TimeoutError("Desktop contract worker did not finish.")
            events = [
                row["payload"]["event"] for row in service.events.read(0, 0)["events"] if row["method"] == "onEvent"
            ]
            print(
                json.dumps(
                    {
                        "events": events,
                        "output": (root / "actual.txt").read_text(),
                        "baseline": service.sessions.baseline(key),
                    }
                )
            )
        finally:
            service.close()


if __name__ == "__main__":
    main()
