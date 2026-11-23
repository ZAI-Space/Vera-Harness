"""Own one independently paired desktop messaging connection."""

import base64
import sqlite3
import threading
import time
from contextlib import closing
from io import BytesIO
from pathlib import Path

from vera.channels.config import AccountConfig, ChannelConfig, ChannelError
from vera.channels.credentials import CredentialStore
from vera.channels.weixin import WeixinClient, login
from vera.desktop.remote_gateway import DesktopChannelGateway


class RemoteConnection:
    """Own explicit login and connection lifetimes; no inbound LAN port or auto-start on launch."""

    def __init__(self, desktop, channel: str):
        self.desktop = desktop
        self.channel = channel
        self.directory = desktop.store.directory / "remote-channels"
        self.credentials = CredentialStore(self.directory)
        self.gateway = None
        self.thread = None
        self.login_thread = None
        self.lock = threading.RLock()
        self.generation = 0
        self.login_state = "idle"
        self.qr = None
        self.pair_code = None
        self.pin = None
        self.error = None
        self.pair_cancel = None

    def status(self) -> dict:
        """Expose connection metadata and a short-lived QR; never return app secrets or bot tokens."""
        with self.lock:
            gateway = self.gateway
            return {
                "bound": self.credentials.has(self.channel),
                "running": bool(self.thread and self.thread.is_alive() and gateway and not gateway.stop_event.is_set()),
                "stopping": bool(self.thread and self.thread.is_alive() and gateway and gateway.stop_event.is_set()),
                "loginState": self.login_state,
                "qrDataUrl": self.qr,
                "pairCode": self.pair_code,
                "error": self.error,
                "sessionId": gateway.root_session
                if gateway
                else self.desktop.store.get("remote-binding", self.channel),
                "executionSessionId": gateway.execution_session if gateway else None,
                "currentSessionId": gateway.last_session if gateway else None,
                "channel": self.channel,
                "journal": gateway.store.status() if gateway and self.thread and self.thread.is_alive() else None,
            }

    def begin_login(self, args: dict) -> dict:
        """Start official-service login in the background; only operator confirmation persists credentials."""
        with self.lock:
            if self.login_thread and self.login_thread.is_alive():
                raise ValueError("登录正在进行，请完成当前扫码或等待其过期。")
            if self.thread and self.thread.is_alive():
                raise ValueError("请先断开当前远程连接，再更换绑定。")
            channel = args["channel"]
            if channel not in {"weixin", "feishu"}:
                raise ValueError("请选择微信或飞书。")
            self.generation += 1
            generation = self.generation
            self.login_state, self.qr, self.pair_code, self.pin, self.error = "loading", None, None, None, None
            self.login_thread = threading.Thread(target=self._login, args=(channel, args, generation), daemon=True)
            self.login_thread.start()
            return self.status()

    def _login(self, channel, args, generation):
        try:
            if channel == "weixin":

                def show_qr(value):
                    import qrcode

                    image = BytesIO()
                    qrcode.make(value).save(image, format="PNG")
                    with self.lock:
                        if generation != self.generation:
                            raise ChannelError("登录已取消。")
                        self.qr = "data:image/png;base64," + base64.b64encode(image.getvalue()).decode()
                        self.login_state = "scan"

                def read_pin():
                    self.login_state = "pin"
                    while generation == self.generation and not self.pin:
                        time.sleep(0.2)
                    if generation != self.generation:
                        raise ChannelError("登录已取消。")
                    value, self.pin = self.pin, None
                    return value

                client = WeixinClient()
                try:
                    credentials = login(client, show_qr, read_pin)
                    with self.lock:
                        if generation == self.generation:
                            self.credentials.save(channel, credentials)
                finally:
                    client.close()
            else:
                from vera.channels.feishu import pair_account

                self.directory.mkdir(parents=True, exist_ok=True)
                self.pair_cancel = self.directory / f"desktop-pairing-{generation}.stop"
                self.pair_cancel.unlink(missing_ok=True)
                if generation != self.generation:
                    return
                session = self.desktop.sessions.get(args["sessionId"])
                config = ChannelConfig(
                    workspace=Path(session["meta"]["cwd"]),
                    state_directory=self.directory,
                    accounts={"feishu": AccountConfig(channel="feishu")},
                )

                def show_code(code):
                    self.pair_code, self.login_state = code, "pair"

                pair_account(
                    config,
                    "feishu",
                    show_code,
                    credentials={"app_id": args["appId"], "app_secret": args["appSecret"]},
                    cancel_path=self.pair_cancel,
                )
            with self.lock:
                if generation == self.generation:
                    self.login_state, self.qr, self.pair_code = "ready", None, None
        except Exception as error:
            with self.lock:
                if generation == self.generation:
                    self.login_state, self.qr = "error", None
                    self.error = (
                        str(error) if isinstance(error, ChannelError) else "登录失败，请检查网络与本机通道依赖。"
                    )

    def submit_pin(self, pin: str) -> dict:
        """Accept only the phone-displayed PIN for an outstanding Weixin verification step."""
        with self.lock:
            if self.login_state != "pin" or not pin.isdecimal() or not 4 <= len(pin) <= 12:
                raise ValueError("请输入微信手机端显示的 4–12 位验证码。")
            self.pin = pin
            self.login_state = "verifying"
            return self.status()

    def start(self, args: dict) -> dict:
        """Bind one paired transport to a selected desktop chat, inheriting its model and permission gates."""
        with self.lock:
            if self.thread and self.thread.is_alive():
                raise ValueError("连接仍在运行或停止中，请稍后重试。")
            channel = args["channel"]
            if channel not in {"weixin", "feishu"} or not self.credentials.has(channel):
                raise ValueError("请先完成微信扫码或飞书配对。")
            from vera.desktop.remote_gateway import validate_session

            value = validate_session(self.desktop, args["sessionId"])
            config = ChannelConfig(
                workspace=Path(value["meta"]["cwd"]),
                state_directory=self.directory / channel,
                accounts={channel: AccountConfig(channel=channel)},
            )
            self.migrate_journal(config.state_directory)
            CredentialStore(config.state_directory).save(channel, self.credentials.load(channel))
            self.gateway = DesktopChannelGateway(config, self.desktop, args["sessionId"])
            self.desktop.store.save("remote-binding", channel, args["sessionId"])
            self.error = None
            self.thread = threading.Thread(target=self._serve, args=(self.gateway,), daemon=True)
            self.thread.start()
            return self.status()

    def migrate_journal(self, directory: Path) -> None:
        """Preserve the former shared inbox's cursor/dedup history when splitting channel runtimes.

        Only this channel's records are retained. Unfinished old turns become
        interrupted, so migration never replays possible file or network effects.
        """
        legacy, destination = self.directory / "channels.sqlite3", directory / "channels.sqlite3"
        if not legacy.is_file() or destination.exists():
            return
        directory.mkdir(parents=True, exist_ok=True)
        with closing(sqlite3.connect(legacy)) as source, closing(sqlite3.connect(destination)) as target:
            source.backup(target)
            with target:
                for table in ("outbox", "cursors", "connections"):
                    target.execute(f"DELETE FROM {table} WHERE account != ?", (self.channel,))
                target.execute("DELETE FROM messages WHERE json_extract(payload, '$.account') != ?", (self.channel,))
                target.execute("DELETE FROM sessions WHERE id NOT IN (SELECT session FROM messages)")
                target.execute(
                    "UPDATE messages SET status='interrupted' WHERE status IN ('running','queued','received')"
                )
                target.execute("UPDATE outbox SET status='unknown' WHERE status IN ('sending','pending')")

    def _serve(self, gateway):
        try:
            gateway.serve()
        except Exception as error:
            self.error = str(error) if isinstance(error, ChannelError) else "远程通道异常，请检查本机日志与配置。"

    def stop(self) -> dict:
        """Stop reception without blocking the settings button; interrupt only an owned remote turn."""
        if self.gateway:
            self.gateway.stop_event.set()
            self.gateway.stop_path.touch()
            if self.gateway.execution_session:
                self.desktop.sessions.abort(self.gateway.execution_session)
        return self.status()

    def logout(self, channel: str) -> dict:
        """Remove local credentials after the connection has stopped; never remotely revoke other accounts."""
        if channel not in {"weixin", "feishu"}:
            raise ValueError("请选择微信或飞书。")
        if self.thread and self.thread.is_alive() or self.login_thread and self.login_thread.is_alive():
            raise ValueError("请先停止连接并等待当前登录结束，再解除绑定。")
        self.credentials.delete(channel)
        CredentialStore(self.directory / channel).delete(channel)
        self.gateway = None
        self.error = None
        return self.status()

    def close(self) -> None:
        """Revoke pending login writes and stop owned transports when the desktop exits."""
        self.generation += 1
        if self.pair_cancel:
            self.pair_cancel.touch()
        self.stop()
