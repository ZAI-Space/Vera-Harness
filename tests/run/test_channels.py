"""Validate authorized remote jobs through real provider protocols, SQLite and agent subprocesses."""

import os
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier

import pytest
import yaml

from tests.run.channel_fixture import feishu_event, feishu_socket, provider_service, weixin_message
from vera.channels import AccountConfig, ChannelConfig, ChannelError
from vera.channels.credentials import CredentialStore
from vera.channels.gateway import ChannelGateway, authorized, gateway_lock
from vera.channels.store import ChannelStore, chunks
from vera.channels.weixin import WeixinClient, api_origin, login, normalize_message


def test_weixin_login_pin_wire_headers_and_reply_context(tmp_path):
    with provider_service(login_statuses=["need_verifycode", "scaned", "confirmed"]) as service:
        client = WeixinClient(base_url=service["base_url"])
        shown = []
        credentials = login(client, shown.append, lambda: "123456", timeout=10)
        CredentialStore(tmp_path).save("wechat", credentials)
        assert CredentialStore(tmp_path).load("wechat") == credentials
        protected = next((tmp_path / "credentials").iterdir())
        if os.name == "nt":
            assert "fake-bot-token" not in protected.read_text()
        else:
            assert protected.stat().st_mode & 0o777 == 0o600
        client.close()
        client = WeixinClient(credentials)
        client.updates("previous-cursor")
        message = normalize_message("wechat", weixin_message(1, text="你好"))
        client.send(message, "回复", "stable-client-id")
        client.close()
    assert shown == ["https://example.invalid/test-qr"]
    paths = [request[0] for request in service["requests"]]
    assert "verify_code" not in paths[1] and "verify_code=123456" in paths[2] and "verify_code" not in paths[3]
    assert service["requests"][0][1] == {"local_token_list": []}
    assert "Authorization" not in service["requests"][1][2]
    assert service["requests"][-1][2]["Authorization"] == "Bearer fake-bot-token"
    assert service["replies"][0]["msg"]["context_token"] == "context-owner"
    assert service["replies"][0]["msg"]["client_id"] == "stable-client-id"


@pytest.mark.parametrize(
    "value",
    [
        "https://evil.example",
        "http://ilinkai.weixin.qq.com",
        "https://token@ilinkai.weixin.qq.com",
        "https://ilinkai.weixin.qq.com/credentials",
        "https://ilinkai.weixin.qq.com?x=y",
    ],
)
def test_weixin_redirects_cannot_exfiltrate_credentials(value):
    with pytest.raises(ChannelError):
        api_origin(value)


def test_journal_dedupe_commands_history_cancel_and_uncertain_delivery(tmp_path):
    store = ChannelStore(tmp_path)
    owner = AccountConfig(channel="weixin")
    first = normalize_message("wechat", weixin_message(1))
    outsider = normalize_message("wechat", weixin_message(2, user="intruder"))
    assert authorized(owner, first, "owner") and not authorized(owner, outsider, "owner")
    assert not authorized(owner, first.model_copy(update={"is_group": True}), "owner")
    store.accept([first, first], account="wechat", cursor="safe-cursor")
    assert store.cursor("wechat") == "safe-cursor" and store.status()["tasks"] == {"queued": 1}
    claimed = store.claim()
    store.finish(claimed["id"], "completed", "previous result")
    second = normalize_message("wechat", weixin_message(3, text="Second task"))
    store.accept([second])
    assert "previous result" in store.history(second.key)
    store.accept([normalize_message("wechat", weixin_message(4, text="/cancel"))])
    assert store.get(second.key)["status"] == "cancelled"
    store.accept([normalize_message("wechat", weixin_message(5, text="/new"))])
    third = normalize_message("wechat", weixin_message(6, text="New conversation"))
    store.accept([third])
    assert store.history(third.key) == "[]"
    store.claim()
    assert store.pending_reply({"wechat"}) is not None
    store.reconcile()
    assert store.get(third.key)["status"] == "interrupted"
    assert store.status()["replies"]["unknown"] == 1
    assert store.pending_reply({"another-account"}) is None
    assert all(len(part.encode()) <= 2000 for part in chunks("中文🚀" * 3000))
    assert "".join(chunks("中文🚀" * 3000)) == "中文🚀" * 3000
    assert not CredentialStore(tmp_path).directory.exists()
    with gateway_lock(tmp_path):
        with pytest.raises(ChannelError, match="Another"):
            with gateway_lock(tmp_path):
                pytest.fail("Only one controller may own a store.")


def test_journal_reads_do_not_compete_with_pending_writes(tmp_path):
    """Status polling must read committed state while a worker holds a write transaction."""
    store = ChannelStore(tmp_path)
    message = normalize_message("wechat", weixin_message(1))
    store.accept([message], account="wechat", cursor="committed-cursor")
    store.claim()
    with store.connect() as writer:
        writer.execute("UPDATE messages SET progress = 'pending' WHERE id = ?", (message.key,))
        reader = ChannelStore(tmp_path)
        assert reader.status()["tasks"] == {"running": 1}
        assert reader.get(message.key)["progress"] == ""
        assert reader.cursor("wechat") == "committed-cursor"
        assert reader.history(message.key) == "[]"
    assert reader.get(message.key)["progress"] == "pending"


def test_journal_concurrent_initializers_preserve_deduplication(tmp_path):
    """Concurrent first connections must share one schema and persist each event once."""
    ready = Barrier(4)
    message = normalize_message("wechat", weixin_message(1))

    def initialize_and_accept():
        ready.wait(timeout=10)
        store = ChannelStore(tmp_path)
        store.accept([message])
        return store.status()["tasks"]

    with ThreadPoolExecutor(max_workers=4) as workers:
        results = [future.result(timeout=15) for future in [workers.submit(initialize_and_accept) for _ in range(4)]]
    assert results == [{"queued": 1}] * 4


def test_delivery_uncertainty_and_revoked_permission_are_not_retried(tmp_path):
    with provider_service() as service:
        config = ChannelConfig(
            workspace=tmp_path,
            state_directory=tmp_path / "state",
            sandbox="local",
            accounts={"wechat": AccountConfig(channel="weixin", allowed_users=["owner"])},
        )
        gateway = ChannelGateway(config)
        gateway.senders["wechat"] = WeixinClient(
            {"bot_token": "fake-bot-token", "ilink_user_id": "owner", "baseurl": service["base_url"]}
        )
        first = normalize_message("wechat", weixin_message(1, text="/help"))
        gateway.store.accept([first])
        service["send_status"] = 503
        gateway.tick()
        gateway.tick()
        assert len(service["replies"]) == 1
        assert gateway.store.status()["replies"] == {"unknown": 1}
        assert len(gateway.store.status()["undelivered"]) == 1
        second = normalize_message("wechat", weixin_message(2, text="/status"))
        gateway.store.accept([second])
        config.accounts["wechat"].allowed_users = ["another-user"]
        gateway.tick()
        assert len(service["replies"]) == 1
        assert gateway.store.status()["replies"] == {"failed": 1, "unknown": 1}
        gateway.senders["wechat"].close()


def test_feishu_pairing_requires_private_correct_code_and_protects_app_credentials(tmp_path):
    pytest.importorskip("lark_oapi")
    from vera.channels.feishu import pair_account

    events = []
    with feishu_socket(events) as socket, provider_service(ws_url=socket["url"]) as service:
        config = ChannelConfig(
            workspace=tmp_path,
            state_directory=tmp_path / "state",
            accounts={"feishu": AccountConfig(channel="feishu", api_base=service["base_url"])},
        )

        def show_code(code):
            wrong = f"{(int(code) + 1) % 1_000_000:06d}"
            events.append(feishu_event("wrong", "intruder", "/pair " + wrong))
            group = feishu_event("group", "intruder", "/pair " + code)
            group["event"]["message"]["chat_type"] = "group"
            events.append(group)
            events.append(feishu_event("owner", "owner", "/pair " + code))
            events.append(feishu_event("late", "intruder", "/pair " + code))

        result = pair_account(
            config,
            "feishu",
            show_code,
            credentials={"app_id": "fake-pairing-app", "app_secret": "fake-pair-secret"},
            timeout=40,
        )
        assert result == {"account": "feishu", "paired": True}
        credentials = CredentialStore(config.state_directory).load("feishu")
        assert credentials["allowed_users"] == ["owner"]
        assert credentials["app_id"] == "fake-pairing-app"
        assert credentials["app_secret"] == "fake-pair-secret"
        files = list((config.state_directory / "credentials").iterdir())
        assert len(files) == 1
        if os.name == "nt":
            assert b"fake-pair-secret" not in files[0].read_bytes()


def start_gateway(tmp_path, service, channel, *, agent_profile=None, model_environment=None):
    """Start the real gateway, optionally using a composed runtime profile."""
    state = tmp_path / "state"
    state.mkdir()
    if channel == "weixin":
        CredentialStore(state).save(
            "bot",
            {
                "bot_token": "fake-bot-token",
                "baseurl": service["base_url"],
                "ilink_user_id": "owner",
                "ilink_bot_id": "bot",
            },
        )
    profile = tmp_path / "agent.yaml"
    profile.write_text(
        yaml.safe_dump(
            agent_profile
            if agent_profile is not None
            else {
                "agent": {"system_template": "Use Bash and submit the result.", "instance_template": "{{task}}"},
                "model": {"model_class": "tests.run.test_web_tools.LocalFixtureModel", "model_name": "fixture"},
            }
        )
    )
    config = tmp_path / "channels.yaml"
    config.write_text(
        yaml.safe_dump(
            {
                "workspace": str(tmp_path),
                "state_directory": str(state),
                "agent_config": str(profile),
                "sandbox": "local",
                "accounts": {"bot": {"channel": channel, "allowed_users": ["owner"], "api_base": service["base_url"]}},
                "task_timeout": 30,
            }
        )
    )
    repository = Path(__file__).resolve().parents[2]
    environment = (
        os.environ
        | {
            "VERA_SILENT_STARTUP": "1",
            "LITELLM_LOCAL_MODEL_COST_MAP": "True",
            "VERA_GLOBAL_CONFIG_DIR": str(tmp_path / "user-config"),
            "VERA_TEST_MODEL_URL": service["base_url"] + "/model",
            "PYTHONPATH": os.pathsep.join([str(repository / "src"), str(repository)]),
            "FEISHU_APP_ID": "fake-app",
            "FEISHU_APP_SECRET": "fake-app-secret",
        }
        | (model_environment or {})
    )
    output = (tmp_path / "gateway.log").open("wb")
    process = subprocess.Popen(
        [sys.executable, "-m", "vera.run.utilities.channels", "start", "--config", str(config)],
        env=environment,
        cwd=tmp_path,
        stdout=output,
        stderr=subprocess.STDOUT,
    )
    return process, output, state


def wait_for(predicate, process, log, timeout=50):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        assert process.poll() is None, log.read_text(errors="replace")
        time.sleep(0.1)
    pytest.fail(log.read_text(errors="replace"))


def stop_gateway(process, output, state):
    (state / "gateway.stop").touch()
    try:
        process.wait(timeout=55)
    finally:
        if process.poll() is None:
            process.kill()
        output.close()


def test_real_weixin_gateway_runtime_and_scoped_conversation(tmp_path):
    first = weixin_message(1, text="First task")
    with provider_service(
        [first, first, weixin_message(2, user="intruder"), weixin_message(3, text="Second task")]
    ) as service:
        process, output, state = start_gateway(tmp_path, service, "weixin")
        try:
            wait_for(
                lambda: (
                    len(service["models"]) == 4
                    and sum(
                        "[completed]" in reply["msg"]["item_list"][0]["text_item"]["text"]
                        for reply in service["replies"]
                    )
                    == 2
                ),
                process,
                tmp_path / "gateway.log",
            )
            assert (tmp_path / "executions.txt").read_text().splitlines() == ["once", "once"]
            assert "First task" in service["models"][2]["messages"][1]["content"]
            assert "Second task" in service["models"][2]["messages"][1]["content"]
            assert all(reply["msg"]["to_user_id"] == "owner" for reply in service["replies"])
            assert ChannelStore(state).status()["tasks"] == {"completed": 2}
        finally:
            stop_gateway(process, output, state)
    assert process.returncode == 0


def test_real_feishu_sdk_websocket_auth_http_reply_and_deduplication(tmp_path):
    pytest.importorskip("lark_oapi")
    event = feishu_event()
    with feishu_socket([event, event, feishu_event("evil", user="intruder")]) as socket:
        with provider_service(ws_url=socket["url"]) as service:
            process, output, state = start_gateway(tmp_path, service, "feishu")
            try:
                wait_for(
                    lambda: len(service["replies"]) >= 2 and len(socket["acks"]) == 3, process, tmp_path / "gateway.log"
                )
                wait_for(
                    lambda: ChannelStore(state).status()["tasks"].get("completed") == 1,
                    process,
                    tmp_path / "gateway.log",
                )
                assert len(service["models"]) == 2
                assert (tmp_path / "executions.txt").read_text().splitlines() == ["once"]
                assert all(reply["receive_id"] == "chat" for reply in service["replies"])
                assert all(ack["code"] == 200 for ack in socket["acks"])
                assert any(
                    headers.get("Authorization") == "Bearer fake-tenant-token"
                    for path, body, headers in service["requests"]
                    if path.startswith("/open-apis/im/v1/messages")
                )
            finally:
                stop_gateway(process, output, state)
    assert process.returncode == 0
