"""Verify remote messages drive real desktop workers, approvals and durable provider replies."""

import threading
import time

import pytest

from tests.run.channel_fixture import provider_service, weixin_message
from vera.channels.config import AccountConfig, ChannelConfig
from vera.desktop.remote_channels import DesktopChannelGateway
from vera.desktop.service import DesktopService


def until(predicate):
    deadline = time.monotonic() + 35
    while time.monotonic() < deadline:
        if value := predicate():
            return value
        time.sleep(0.05)
    pytest.fail("Remote desktop operation did not settle")


@pytest.fixture
def remote_desktop(tmp_path):
    service = DesktopService(
        tmp_path / "desktop",
        {
            "model": {
                "model_class": "deterministic",
                "model_name": "remote-fixture",
                "cost_per_call": 0,
                "outputs": [
                    {
                        "role": "assistant",
                        "content": "Write proof",
                        "extra": {"actions": [{"command": "printf 'once\n' >> remote-proof.txt"}]},
                    },
                    {
                        "role": "assistant",
                        "content": "Complete",
                        "extra": {
                            "actions": [
                                {"command": "echo COMPLETE_TASK_AND_SUBMIT_FINAL_OUTPUT; echo REMOTE_DESKTOP_VERIFIED"}
                            ]
                        },
                    },
                ],
            },
            "agent": {
                "system_template": "Use Bash.",
                "instance_template": "{{task}}",
                "cost_limit": 0,
                "step_limit": 0,
            },
        },
    )
    root = service.invoke("createSession", {"options": {"cwd": str(tmp_path)}})["sessionId"]
    with provider_service(
        [weixin_message("first"), weixin_message("first"), weixin_message("bad", user="stranger")]
    ) as peer:
        config = ChannelConfig(
            workspace=tmp_path,
            state_directory=tmp_path / "remote",
            accounts={
                "weixin": AccountConfig(channel="weixin", api_base=peer["base_url"]),
            },
        )
        gateway = DesktopChannelGateway(config, service, root)
        gateway.credentials.save(
            "weixin",
            {
                "bot_token": "local-test-bot",
                "ilink_user_id": "owner",
                "ilink_bot_id": "bot",
                "baseurl": peer["base_url"],
            },
        )
        connection = service.remote_channels.connection("weixin")
        connection.gateway = gateway
        thread = threading.Thread(target=gateway.serve, daemon=True)
        connection.thread = thread
        thread.start()
        yield service, gateway, peer, root, tmp_path
        service.close()
        thread.join(timeout=8)
        assert not thread.is_alive()


def test_weixin_remote_approval_dedup_and_desktop_transcript(remote_desktop):
    service, gateway, peer, root, workspace = remote_desktop
    approval = until(lambda: next(iter(service.sessions.approvals.values()), None))
    until(
        lambda: any(
            "/allow " + approval["id"] in value["msg"]["item_list"][0]["text_item"]["text"] for value in peer["replies"]
        )
    )
    assert not (workspace / "remote-proof.txt").exists()
    peer["messages"].append(weixin_message("wrong-nonce", text="/allow wrong-id"))
    until(lambda: gateway.store.status()["tasks"].get("command") == 1)
    assert approval["id"] in service.sessions.approvals
    approved = set()
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline and not gateway.store.status()["tasks"].get("completed"):
        for pending in list(service.sessions.approvals.values()):
            if pending["id"] not in approved:
                peer["messages"].append(
                    weixin_message(
                        "allow-" + pending["id"], text="/allow" if not approved else "/allow " + pending["id"]
                    )
                )
                approved.add(pending["id"])
        time.sleep(0.05)
    assert gateway.store.status()["tasks"].get("completed") == 1
    assert (workspace / "remote-proof.txt").read_text() == "once\n"
    until(
        lambda: any(
            "REMOTE_DESKTOP_VERIFIED" in value["msg"]["item_list"][0]["text_item"]["text"] for value in peer["replies"]
        )
    )
    assert service.sessions.get(root)["lastRunResult"]["exit_status"] == "Submitted"
    assert any(row.get("tools") for row in service.sessions.baseline(root)["transcript"]["messages"])
    assert all(value["msg"]["to_user_id"] == "owner" for value in peer["replies"])


def test_weixin_remote_cancel_stops_waiting_desktop_worker(remote_desktop):
    service, gateway, peer, root, workspace = remote_desktop
    until(lambda: bool(service.sessions.approvals))
    peer["messages"].append(weixin_message("cancel", text="/cancel"))
    until(lambda: gateway.store.status()["tasks"].get("cancelled") == 1)
    assert not service.sessions.baseline(root)["transcript"]["agentActive"]
    assert not (workspace / "remote-proof.txt").exists()
    assert service.sessions.get(root)["lastRunResult"]["exit_status"] == "Cancelled"


def test_remote_connection_never_starts_without_binding(tmp_path):
    service = DesktopService(tmp_path)
    try:
        status = service.invoke("remoteGetStatus")
        assert not any(row["running"] for row in status["channels"].values()) and not any(status["accounts"].values())
        for channel in ("weixin", "feishu"):
            with pytest.raises(ValueError, match="先完成"):
                service.invoke("remoteStart", {"channel": channel, "sessionId": "missing"})
        with pytest.raises(ValueError, match="请选择"):
            service.invoke("remoteStart", {"channel": "unknown", "sessionId": "missing"})
        with pytest.raises(ValueError, match="验证码"):
            service.invoke("remoteSubmitPin", {"pin": "123456"})
    finally:
        service.close()
