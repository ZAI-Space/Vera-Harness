"""Feishu adapter using the official lark-oapi SDK for authentication, messages and WebSocket events."""

import json
import os

from vera.channels.config import AccountConfig, ChannelError, InboundMessage
from vera.channels.weixin import DeliveryRejected, api_origin


def normalize_event(account: str, value: dict) -> InboundMessage | None:
    """Convert im.message.receive_v1; ignore non-user senders and non-message event types."""
    if value.get("header", {}).get("event_type") != "im.message.receive_v1":
        return None
    event = value.get("event", {})
    sender, message = event.get("sender", {}), event.get("message", {})
    if sender.get("sender_type") != "user":
        return None
    try:
        content = json.loads(message.get("content", "{}"))
    except ValueError:
        raise ChannelError("Feishu message content is invalid JSON.") from None
    text = content.get("text", "") if message.get("message_type") == "text" else ""
    # Strip only actual bot mention keys published by the provider, never arbitrary user text.
    for mention in message.get("mentions", []):
        if mention.get("key"):
            text = text.replace(mention["key"], "")
    return InboundMessage(
        account=account,
        channel="feishu",
        message_id=message["message_id"],
        user=sender["sender_id"]["open_id"],
        conversation=message["chat_id"],
        text=text.strip(),
        context=message["message_id"],
        is_group=message.get("chat_type") != "p2p",
    )


class FeishuClient:
    """An application supplied through protected local credentials or process environment variables."""

    def __init__(self, account: AccountConfig, credentials: dict | None = None):
        try:
            import lark_oapi as lark
        except ImportError:
            raise ChannelError("Install vera-harness[channels] to use the Feishu SDK.") from None
        credentials = credentials or {}
        self.app_id = credentials.get("app_id") or os.getenv(account.app_id_env)
        self.secret = credentials.get("app_secret") or os.getenv(account.app_secret_env)
        if not self.app_id or not self.secret:
            raise ChannelError(
                "Run channels login for this Feishu account, or set its App ID/secret environment variables."
            ) from None
        self.domain = api_origin(account.api_base or "https://open.feishu.cn", weixin=False)
        self.client = (
            lark.Client.builder()
            .app_id(self.app_id)
            .app_secret(self.secret)
            .domain(self.domain)
            .timeout(15)
            .log_level(lark.LogLevel.ERROR)
            .build()
        )

    def send(self, message: InboundMessage, text: str, client_id: str) -> None:
        """Send to the inbound chat using the SDK's tenant-token management and stable uuid."""
        from lark_oapi.api.im.v1 import CreateMessageRequest, CreateMessageRequestBody

        request = (
            CreateMessageRequest.builder()
            .receive_id_type("chat_id")
            .request_body(
                CreateMessageRequestBody.builder()
                .receive_id(message.conversation)
                .msg_type("text")
                .content(json.dumps({"text": text}, ensure_ascii=False))
                .uuid(client_id)
                .build()
            )
            .build()
        )
        try:
            response = self.client.im.v1.message.create(request)
        except Exception as error:
            raise ChannelError(f"Feishu delivery failed ({type(error).__name__}); delivery may be unknown.") from None
        if not response.success():
            raise DeliveryRejected(f"Feishu rejected delivery (code {response.code}).")

    def listen(self, account: str, accept, on_connection=None) -> None:
        """Block in the official SDK's reconnecting WebSocket loop in a dedicated child process."""
        import lark_oapi as lark

        def on_message(event):
            if on_connection:
                on_connection("message_received")
            payload = json.loads(lark.JSON.marshal(event))
            message = normalize_event(account, payload)
            if message:
                accept(message)

        handler = lark.EventDispatcherHandler.builder("", "").register_p2_im_message_receive_v1(on_message).build()

        class ObservedClient(lark.ws.Client):
            async def _connect(self):
                await super()._connect()
                if on_connection:
                    on_connection("connected")

        client = ObservedClient(
            self.app_id,
            self.secret,
            domain=self.domain,
            event_handler=handler,
            log_level=lark.LogLevel.ERROR,
            auto_reconnect=True,
        )
        if on_connection:
            client.on_reconnecting = lambda: on_connection("reconnecting")
        client.start()

    def close(self) -> None:
        """SDK HTTP calls don't expose a persistent client session to close."""

    def check(self) -> str:
        """Verify tenant authentication and bot capability without sending a message."""
        import lark_oapi as lark

        request = (
            lark.BaseRequest.builder()
            .http_method(lark.HttpMethod.GET)
            .uri("/open-apis/bot/v3/info/")
            .token_types({lark.AccessTokenType.TENANT})
            .build()
        )
        try:
            response = self.client.request(request)
        except Exception as error:
            raise ChannelError(f"Feishu application authentication failed ({type(error).__name__}).") from None
        if not response.success():
            raise ChannelError(f"Feishu bot check failed (code {response.code}). Enable the bot and publish the app.")
        return json.loads(response.raw.content).get("bot", {}).get("app_name", "")


def pair_account(config, name: str, show_code, *, credentials: dict | None = None, timeout: int = 300) -> dict:
    """Verify an app and bind a user by a short-lived, single-use code received over the official SDK.

    App secrets are protected by CredentialStore. No peer is approved without the
    locally displayed code; ordinary unsolicited messages never become tasks.
    """
    import hashlib
    import secrets
    import sys
    import time
    from pathlib import Path
    from uuid import uuid4

    from vera.channels.credentials import CredentialStore, private_directory
    from vera.evolution.process import run_process

    settings = config.accounts[name]
    client = FeishuClient(settings, credentials)
    client.check()
    store = CredentialStore(config.state_directory)
    nonce = uuid4().hex
    code = f"{secrets.randbelow(1_000_000):06d}"
    cancel = config.state_directory / f"pairing-{nonce}.stop"
    store.save(
        f"pairing-{nonce}",
        {
            "account": name,
            "settings": settings.model_dump(),
            "credentials": {"app_id": client.app_id, "app_secret": client.secret},
            "code_hash": hashlib.sha256(code.encode()).hexdigest(),
            "expires": time.time() + timeout,
        },
    )
    show_code(code)
    try:
        directory = private_directory(config.state_directory / "artifacts" / f"pairing-{nonce}")
        environment = os.environ | {
            "VERA_SILENT_STARTUP": "1",
            "PYTHONIOENCODING": "utf-8",
            "PYTHONPATH": os.pathsep.join(
                filter(None, [str(Path(__file__).resolve().parents[2]), os.environ.get("PYTHONPATH", "")])
            ),
        }
        run_process(
            [
                sys.executable,
                "-m",
                "vera.channels.worker",
                "--state",
                str(config.state_directory),
                "--pair-feishu",
                nonce,
            ],
            cwd=config.workspace,
            env=environment,
            log=directory / "process.log",
            timeout=timeout,
            cancel=cancel,
        )
        if not store.has(f"paired-{nonce}"):
            raise ChannelError(
                "Feishu pairing did not complete. Check long connection, im.message.receive_v1 subscription, message permissions and app publication; then log in again."
            )
        paired = store.load(f"paired-{nonce}")
        result = {"app_id": client.app_id, "app_secret": client.secret, "allowed_users": paired["allowed_users"]}
        store.save(name, result)
        return {"account": name, "paired": True}
    finally:
        store.delete(f"pairing-{nonce}")
        store.delete(f"paired-{nonce}")
        cancel.unlink(missing_ok=True)
