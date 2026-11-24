"""Keep numeric SDK failures actionable without exposing credentials or server-echoed values."""

from uuid import uuid4

import pytest

from tests.run.channel_fixture import provider_service
from vera.channels.config import AccountConfig, ChannelError
from vera.channels.feishu import FeishuClient


@pytest.mark.parametrize(
    ("failure", "code", "hint"),
    [
        ("tenant_token_error", 20002, "同一自建应用"),
        ("tenant_token_error", 21001, "访问控制策略拒绝"),
        ("bot_info_error", 99991672, "机器人能力"),
    ],
)
def test_official_sdk_auth_errors_preserve_code_and_strip_credentials(failure, code, hint):
    with provider_service() as peer:
        secret = "local-fake-secret-for-error-test"
        peer[failure] = {"code": code, "msg": "upstream echoed " + secret}
        app_id = "local-auth-" + uuid4().hex
        client = FeishuClient(
            AccountConfig(channel="feishu", api_base=peer["base_url"]),
            {"app_id": " " + app_id + "\n", "app_secret": "\t" + secret + " "},
        )
        try:
            with pytest.raises(ChannelError) as caught:
                client.check()
            message = str(caught.value)
            assert str(code) in message and hint in message
            assert secret not in message and app_id not in message and "upstream echoed" not in message
            if code == 21001:
                assert "这不表示 App Secret 填错" in message and "重新复制" not in message
            requests = [body for path, body, _ in peer["requests"] if path.endswith("/tenant_access_token/internal")]
            assert len(requests) == 1 and requests[0]["app_id"] == app_id and requests[0]["app_secret"] == secret
        finally:
            client.close()
