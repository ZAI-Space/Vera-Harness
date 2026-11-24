"""Manage independently connected Weixin and Feishu desktop transports."""

from vera.desktop.remote_connection import RemoteConnection
from vera.desktop.remote_gateway import DesktopChannelGateway  # noqa: F401 - compatibility import for existing integrations


class RemoteChannels:
    """Keep login, credentials, execution and stop state scoped to each messaging channel."""

    def __init__(self, desktop):
        self.connections = {name: RemoteConnection(desktop, name) for name in ("weixin", "feishu")}

    def connection(self, channel: str) -> RemoteConnection:
        """Reject unknown transports before accessing credentials or session state."""
        if channel not in self.connections:
            raise ValueError("请选择微信或飞书。")
        return self.connections[channel]

    def status(self) -> dict:
        """Return both independent channel cards; credentials never appear in the projection."""
        channels = {name: connection.status() for name, connection in self.connections.items()}
        return {"channels": channels, "accounts": {name: row["bound"] for name, row in channels.items()}}

    def begin_login(self, args: dict) -> dict:
        self.connection(args["channel"]).begin_login(args)
        return self.status()

    def submit_pin(self, pin: str) -> dict:
        self.connection("weixin").submit_pin(pin)
        return self.status()

    def start(self, args: dict) -> dict:
        self.connection(args["channel"]).start(args)
        return self.status()

    def switch_session(self, args: dict) -> dict:
        connection = self.connection(args["channel"])
        if not connection.gateway or not connection.status()["running"]:
            raise ValueError("请先启动该通道的远程连接。")
        connection.gateway.switch_session(args["sessionId"])
        return self.status()

    def stop(self, channel: str) -> dict:
        self.connection(channel).stop()
        return self.status()

    def logout(self, channel: str) -> dict:
        self.connection(channel).logout(channel)
        return self.status()

    def close(self) -> None:
        for connection in self.connections.values():
            connection.close()
