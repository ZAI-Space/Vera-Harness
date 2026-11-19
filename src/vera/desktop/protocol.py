"""Worker frames on reserved stdout; logs belong on stderr."""

import json
import sys


def send(kind: str, **payload) -> None:
    """Flush one JSON frame immediately so a model delta can reach the desktop."""
    sys.__stdout__.write(json.dumps({"type": kind, **payload}, ensure_ascii=False) + "\n")
    sys.__stdout__.flush()
