"""Validated host-owned configuration and normalized inbound messages for two channels."""

import hashlib
import json
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

from minisweagent import global_config_dir


class ChannelError(RuntimeError):
    """An actionable channel configuration, connection or persistence failure."""


class AccountConfig(BaseModel):
    """One bot identity; only configured user IDs may trigger tasks or read status."""

    model_config = ConfigDict(extra="forbid")
    channel: Literal["weixin", "feishu"]
    enabled: bool = True
    allowed_users: list[str] = Field(default_factory=list)
    allow_groups: bool = False
    app_id_env: str = "FEISHU_APP_ID"
    app_secret_env: str = "FEISHU_APP_SECRET"
    api_base: str | None = None


class ChannelConfig(BaseModel):
    """A fixed workspace/profile and durable private state, never selected by chat messages."""

    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    workspace: Path
    agent_config: str = "mini.yaml"
    state_directory: Path = global_config_dir / "channels"
    sandbox: Literal["auto", "docker", "bubblewrap", "local"] = "auto"
    accounts: dict[str, AccountConfig] = Field(default_factory=lambda: {"weixin": AccountConfig(channel="weixin")})
    step_limit: int = Field(default=30, ge=1, le=200)
    cost_limit: float = Field(default=1, gt=0, le=10)
    task_timeout: int = Field(default=180, ge=10, le=3600)

    @model_validator(mode="after")
    def validate_accounts(self):
        import re

        if not 1 <= len(self.accounts) <= 8 or any(
            not re.fullmatch(r"[a-z][a-z0-9-]{0,31}", name) for name in self.accounts
        ):
            raise ValueError("Use 1-8 stable lowercase account names.")
        return self


def load_config(path: Path) -> ChannelConfig:
    """Resolve user paths relative to the config file, independent of startup shell/cwd."""
    try:
        config = ChannelConfig.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))
        base = path.resolve().parent
        config.workspace = (base / config.workspace.expanduser()).resolve()
        config.state_directory = (base / config.state_directory.expanduser()).resolve()
        if (base / config.agent_config).is_file():
            config.agent_config = str((base / config.agent_config).resolve())
        if not config.workspace.is_dir():
            raise ChannelError("The configured workspace must exist.")
        return config
    except (OSError, ValueError, yaml.YAMLError) as error:
        raise ChannelError(f"Cannot load channel config: {type(error).__name__}.") from None


class InboundMessage(BaseModel):
    """Only provider-validated text/routing data crosses the transport boundary."""

    model_config = ConfigDict(extra="forbid")
    account: str
    channel: Literal["weixin", "feishu"]
    message_id: str = Field(min_length=1, max_length=256)
    user: str = Field(min_length=1, max_length=256)
    conversation: str = Field(min_length=1, max_length=256)
    text: str = Field(max_length=16_000)
    context: str = Field(default="", max_length=16_384)
    is_group: bool = False

    @property
    def session_id(self) -> str:
        """Isolate account, provider, conversation and sender; no raw ID becomes a path."""
        return hashlib.sha256(
            json.dumps([self.channel, self.account, self.conversation, self.user]).encode()
        ).hexdigest()

    @property
    def key(self) -> str:
        """Deduplicate provider redelivery within an account, including across restarts."""
        return hashlib.sha256(json.dumps([self.channel, self.account, self.message_id]).encode()).hexdigest()
