"""Launch noninteractive backend commands without allocating a Windows console.

Redirecting stdout alone does not hide a console created by a GUI parent. Keep
interactive entry points unchanged; combine this flag with process groups when
supervising a background job. Do not combine it with DETACHED_PROCESS, which
causes Windows to ignore CREATE_NO_WINDOW.
"""

import os
import subprocess

BACKGROUND_CREATION_FLAGS = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
