"""Launch a historical Vera implementation against a writable candidate tree.

This file is executed by absolute path from the trusted controller installation.
PYTHONPATH selects the archived optimizer implementation before any Vera import.
Only source in the selected generation is executed as the optimizer runtime.
"""

import json
import sys
from pathlib import Path


def main() -> None:
    """Read a controller request, run the normal Vera entry point and report usage."""
    from minisweagent.run.mini import app

    request = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    agent = app(
        [
            "-c",
            "mini.yaml",
            "-c",
            request["config"],
            "-t",
            request["task"],
            "-y",
            "--exit-immediately",
            "-o",
            request["trajectory"],
        ],
        standalone_mode=False,
    )
    Path(request["result"]).write_text(
        json.dumps({"status": agent.messages[-1].get("extra", {}).get("exit_status"), "cost": agent.cost}),
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
