"""Weixin transport adapted from Tencent/openclaw-weixin's MIT-licensed protocol.

Reference commit: 0ad1ae91347a938f52f1e4e2abd6dcda51e05f9e (3.0.0-beta-0).
See THIRD_PARTY_NOTICES.md for attribution. This is a Python protocol adapter;
OpenClaw and its TypeScript runtime are not installed or embedded.
"""

import base64
import json
import secrets
import time
from collections.abc import Callable
from urllib.parse import urlsplit

import requests

from minisweagent import __version__
from minisweagent.channels.config import ChannelError, InboundMessage

DEFAULT_API = "https://ilinkai.weixin.qq.com"
PROTOCOL_VERSION = f"3.0.0-beta-0/Vera-{__version__}"


class SessionExpired(ChannelError):
    """The bot session expired; require a new login instead of repeatedly retrying it."""


class DeliveryRejected(ChannelError):
    """The provider explicitly rejected delivery; a network failure instead remains uncertain."""


def api_origin(value: str, *, weixin: bool = True) -> str:
    """Allow provider HTTPS origins or explicit loopback protocol-test endpoints, without credentials."""
    try:
        parsed = urlsplit(value)
        host, port = parsed.hostname or "", parsed.port
    except ValueError:
        raise ChannelError("Invalid channel API origin.") from None
    local = host in {"127.0.0.1", "localhost", "::1"}
    allowed = (
        host == "weixin.qq.com" or host.endswith(".weixin.qq.com")
        if weixin
        else host in {"open.feishu.cn", "open.larksuite.com"}
    )
    if parsed.username is not None or parsed.query or parsed.fragment or parsed.path not in {"", "/"}:
        raise ChannelError("API origins cannot contain credentials, paths, queries or fragments.")
    if not ((parsed.scheme == "https" and allowed and port in {None, 443}) or (parsed.scheme == "http" and local)):
        raise ChannelError("Unexpected channel API origin; credentials will not be forwarded.")
    return value.rstrip("/")


def _response(response: requests.Response) -> dict:
    with response:
        if response.status_code >= 500:
            raise ChannelError("Provider server error; delivery may be unknown.")
        if response.status_code >= 400:
            raise DeliveryRejected(f"Provider rejected the request (HTTP {response.status_code}).")
        if response.status_code != 200:
            raise ChannelError("Unexpected provider HTTP status; redirects are disabled.")
        body = response.raw.read(1_048_577, decode_content=True)
    if len(body) > 1_048_576:
        raise ChannelError("Provider response exceeds 1 MiB.")
    try:
        value = json.loads(body)
    except (ValueError, UnicodeError):
        raise ChannelError("Provider returned invalid JSON.") from None
    if not isinstance(value, dict):
        raise ChannelError("Provider returned a non-object response.")
    if any(value.get(key) == -14 for key in ("ret", "errcode")):
        raise SessionExpired("Weixin login expired; run channels login again and restart the gateway.")
    if any(value.get(key, 0) != 0 for key in ("ret", "errcode")):
        raise DeliveryRejected("Provider returned a nonzero business error code.")
    return value


class WeixinClient:
    """Bounded HTTPS JSON calls; tokens are never sent to server-selected untrusted origins."""

    def __init__(self, credentials: dict | None = None, *, base_url: str | None = None):
        credentials = credentials or {}
        self.base_url = api_origin(base_url or credentials.get("baseurl", DEFAULT_API))
        self.token = credentials.get("bot_token", "")
        self.owner = credentials.get("ilink_user_id", "")
        self.bot_id = credentials.get("ilink_bot_id", "")
        self.session = requests.Session()

    def close(self) -> None:
        """Release connection pools when the collector/sender stops."""
        self.session.close()

    def request(self, path: str, body: dict | None = None, *, query: dict | None = None, timeout: int = 15) -> dict:
        """Perform one request without redirects or automatic retries of message delivery."""
        headers = {"iLink-App-Id": "bot", "iLink-App-ClientVersion": str(3 << 16)}
        if body is not None:
            headers.update(
                {
                    "Content-Type": "application/json",
                    "AuthorizationType": "ilink_bot_token",
                    "X-WECHAT-UIN": base64.b64encode(str(secrets.randbits(32)).encode()).decode(),
                }
            )
            if self.token and path != "/ilink/bot/get_bot_qrcode":
                headers["Authorization"] = f"Bearer {self.token}"
                body = body | {"base_info": {"channel_version": PROTOCOL_VERSION, "bot_agent": f"Vera/{__version__}"}}
        try:
            response = self.session.request(
                "POST" if body is not None else "GET",
                self.base_url + path,
                params=query,
                json=body,
                headers=headers,
                timeout=(10, timeout),
                allow_redirects=False,
                stream=True,
            )
            return _response(response)
        except requests.RequestException as error:
            raise ChannelError(f"Weixin transport failed ({type(error).__name__}); delivery may be unknown.") from None

    def updates(self, cursor: str) -> dict:
        """Long-poll up to 35 seconds; cursor acknowledgement belongs to ChannelStore.accept."""
        return self.request("/ilink/bot/getupdates", {"get_updates_buf": cursor}, timeout=40)

    def send(self, message: InboundMessage, text: str, client_id: str) -> None:
        """Reply with the exact inbound conversation token and a stable fragment ID."""
        if not message.context:
            raise DeliveryRejected("Weixin inbound context token is missing; refusing ambiguous delivery.")
        self.request(
            "/ilink/bot/sendmessage",
            {
                "msg": {
                    "from_user_id": "",
                    "to_user_id": message.user,
                    "client_id": client_id,
                    "message_type": 2,
                    "message_state": 2,
                    "context_token": message.context,
                    "item_list": [{"type": 1, "text_item": {"text": text}}],
                }
            },
        )


def normalize_message(account: str, value: dict) -> InboundMessage | None:
    """Accept finished user messages, preserving provider IDs and voice transcripts; ignore bot echoes."""
    if value.get("message_type") != 1 or value.get("message_state", 2) != 2 or not value.get("from_user_id"):
        return None
    text = []
    for item in value.get("item_list", []):
        if item.get("type") == 1:
            text.append(item.get("text_item", {}).get("text", ""))
        elif item.get("type") == 3:
            text.append(item.get("voice_item", {}).get("text", ""))
    identifier = value.get("message_id", value.get("client_id"))
    if identifier is None:
        raise ChannelError("Inbound Weixin message has no stable deduplication ID.")
    return InboundMessage(
        account=account,
        channel="weixin",
        message_id=str(identifier),
        user=value["from_user_id"],
        conversation=value.get("group_id") or value["from_user_id"],
        text="\n".join(text),
        context=value.get("context_token", ""),
        is_group=bool(value.get("group_id")),
    )


def login(
    client: WeixinClient, show_qr: Callable[[str], None], read_pin: Callable[[], str], *, timeout: int = 480
) -> dict:
    """Bind the operator's own Weixin account, including PIN/expiry/IDC redirect states.

    No credentials are written until confirmed. The operator must scan and approve
    the QR code themselves. Third-party owner real-name enrollment isn't performed.
    """
    deadline = time.monotonic() + timeout
    pin, refresh = "", 0
    original = client.base_url
    qr = client.request(
        "/ilink/bot/get_bot_qrcode",
        {"local_token_list": [client.token] if client.token else []},
        query={"bot_type": "3"},
    )
    show_qr(qr["qrcode_img_content"])
    while time.monotonic() < deadline:
        query = {"qrcode": qr["qrcode"]}
        if pin:
            query["verify_code"] = pin
        try:
            response = client.request("/ilink/bot/get_qrcode_status", query=query, timeout=35)
        except ChannelError:
            time.sleep(1)
            continue
        status = response.get("status")
        if status == "confirmed":
            required = ("bot_token", "ilink_bot_id", "ilink_user_id", "baseurl")
            if any(not isinstance(response.get(key), str) or not response[key] for key in required):
                raise ChannelError("Login response omitted required account credentials.")
            response["baseurl"] = api_origin(response["baseurl"])
            return {key: response[key] for key in required}
        if "need_verifycode" in str(status):
            pin = read_pin().strip()
            if not pin.isdecimal() or not 4 <= len(pin) <= 12:
                raise ChannelError("Enter the 4-12 digit PIN displayed by Weixin.")
        elif status == "scaned":
            pin = ""
        elif status == "scaned_but_redirect":
            client.base_url = api_origin("https://" + response["redirect_host"])
        elif status in {"expired", "verify_code_blocked"}:
            refresh += 1
            if refresh >= 3:
                raise ChannelError("Login QR expired/blocked repeatedly; restart login.")
            pin = ""
            client.base_url = original
            qr = client.request("/ilink/bot/get_bot_qrcode", {"local_token_list": []}, query={"bot_type": "3"})
            show_qr(qr["qrcode_img_content"])
        elif status == "binded_redirect":
            raise ChannelError("This account is already bound elsewhere; confirm its binding in Weixin.")
        else:
            time.sleep(0.5)
    raise ChannelError("Weixin QR login timed out.")
