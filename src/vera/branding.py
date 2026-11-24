"""VERA's display identity and public links, shared by terminal and provider adapters.

Compatibility reads for existing settings remain explicit; new integrations use
the vera namespace and VERA_* environment variables.
"""

import os

APP_NAME = "VERA"
DISTRIBUTION_NAME = "vera-harness"
REPOSITORY_URL = "https://github.com/zml-mis/Vera-Harness"
DOCUMENTATION_URL = f"{REPOSITORY_URL}/tree/main/docs"
ISSUES_URL = f"{REPOSITORY_URL}/issues"


def apply_legacy_environment() -> None:
    """Read inherited MSWEA_* settings only when the corresponding VERA_* key is absent.

    This is read compatibility for existing launch environments/.env files. New
    settings and code use VERA_*; explicit new values always take precedence.
    """
    for name, value in list(os.environ.items()):
        if name.startswith("MSWEA_"):
            os.environ.setdefault("VERA_" + name.removeprefix("MSWEA_"), value)
    if "VERA_CONFIG_PATH" not in os.environ:
        for name in ("MSWEA_MINI_CONFIG_PATH", "VERA_MINI_CONFIG_PATH"):
            if name in os.environ:
                os.environ["VERA_CONFIG_PATH"] = os.environ[name]
                break
