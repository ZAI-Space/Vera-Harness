"""Run both messaging transports and routing controls against real HTTP/WebSocket peers."""

import json
import threading
from contextlib import ExitStack
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

from tests.run.channel_fixture import feishu_event, feishu_socket, provider_service, weixin_message
from tests.run.test_desktop_remote_channels import until
from vera.channels.config import AccountConfig, ChannelConfig
from vera.channels.store import ChannelStore
from vera.channels.weixin import normalize_message
from vera.desktop.remote_gateway import DesktopChannelGateway
from vera.desktop.service import DesktopService


@pytest.fixture
def routed_desktop(tmp_path):
    class ModelPeer(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            last_user = max(index for index, row in enumerate(body["messages"]) if row["role"] == "user")
            finished = any(row["role"] == "tool" for row in body["messages"][last_user:])
            delta = (
                {"content": "ROUTING_VERIFIED"}
                if finished
                else {
                    "tool_calls": [
                        {
                            "index": 0,
                            "id": "routing-tool",
                            "type": "function",
                            "function": {
                                "name": "bash",
                                "arguments": json.dumps({"command": "printf 'once\\n' >> bridge-proof.txt"}),
                            },
                        }
                    ]
                }
            )
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.end_headers()
            frame = {
                "id": "routing",
                "object": "chat.completion.chunk",
                "created": 1,
                "model": "route-model",
                "choices": [{"index": 0, "delta": delta, "finish_reason": None}],
            }
            self.wfile.write(("data: " + json.dumps(frame) + "\n\n").encode())
            frame["choices"] = [{"index": 0, "delta": {}, "finish_reason": "stop" if finished else "tool_calls"}]
            frame["usage"] = {"prompt_tokens": 50, "completion_tokens": 20, "total_tokens": 70}
            self.wfile.write(("data: " + json.dumps(frame) + "\n\ndata: [DONE]\n\n").encode())
            self.wfile.flush()

    peer = ThreadingHTTPServer(("127.0.0.1", 0), ModelPeer)
    peer.daemon_threads = True
    thread = threading.Thread(target=peer.serve_forever, daemon=True)
    thread.start()
    desktop = DesktopService(tmp_path / "state")
    desktop.providers.configure(
        {
            "id": "route-local",
            "name": "Route peer",
            "api": "openai-completions",
            "baseUrl": f"http://127.0.0.1:{peer.server_port}/v1",
            "models": [{"id": "route-model"}],
        }
    )
    sessions = []
    for name in ("wx", "fs", "other"):
        workspace = tmp_path / name
        workspace.mkdir()
        meta = desktop.invoke(
            "createSession",
            {
                "options": {
                    "cwd": str(workspace),
                    "provider": "route-local",
                    "modelId": "route-model",
                    "thinkingLevel": "default",
                }
            },
        )
        sessions.append(meta["sessionId"])
    try:
        yield desktop, sessions
    finally:
        desktop.close()
        peer.shutdown()
        peer.server_close()
        thread.join(timeout=5)


def test_weixin_and_feishu_live_together_with_independent_approvals_and_stop(routed_desktop):
    pytest.importorskip("lark_oapi")
    desktop, (wx_key, fs_key, other_key) = routed_desktop
    gateways, threads = {}, []
    with ExitStack() as stack:
        socket = stack.enter_context(feishu_socket([feishu_event("fs-first")]))
        peers = {
            "weixin": stack.enter_context(provider_service([weixin_message("wx-first")])),
            "feishu": stack.enter_context(provider_service(ws_url=socket["url"])),
        }
        try:
            for channel, key in (("weixin", wx_key), ("feishu", fs_key)):
                connection = desktop.remote_channels.connection(channel)
                directory = connection.directory / channel
                config = ChannelConfig(
                    workspace=Path(desktop.sessions.get(key)["meta"]["cwd"]),
                    state_directory=directory,
                    accounts={
                        channel: AccountConfig(
                            channel=channel, api_base=peers[channel]["base_url"], allowed_users=["owner"]
                        )
                    },
                )
                gateway = DesktopChannelGateway(config, desktop, key)
                credentials = (
                    {"bot_token": "local-only", "ilink_user_id": "owner", "baseurl": peers[channel]["base_url"]}
                    if channel == "weixin"
                    else {"app_id": "local-app", "app_secret": "local-secret", "allowed_users": ["owner"]}
                )
                gateway.credentials.save(channel, credentials)
                connection.credentials.save(channel, credentials)
                connection.gateway = gateways[channel] = gateway
                connection.thread = threading.Thread(target=connection._serve, args=(gateway,), daemon=True)
                threads.append(connection.thread)
                connection.thread.start()
            until(lambda: len(desktop.sessions.approvals) == 2)
            status = desktop.invoke("remoteGetStatus")
            assert all(row["running"] for row in status["channels"].values())
            assert gateways["weixin"].store.path != gateways["feishu"].store.path
            with pytest.raises(ValueError, match="执行中或排队"):
                desktop.invoke("remoteSwitchSession", {"channel": "weixin", "sessionId": other_key})
            wx_pending = next(row for row in desktop.sessions.approvals.values() if row["sessionId"] == wx_key)
            peers["weixin"]["messages"].append(weixin_message("wrong-user", user="intruder", text="/allow"))
            peers["weixin"]["messages"].append(weixin_message("allow", text="/allow"))
            until(lambda: wx_pending["id"] not in desktop.sessions.approvals)
            assert any(row["sessionId"] == fs_key for row in desktop.sessions.approvals.values())
            until(lambda: gateways["weixin"].store.status()["tasks"].get("completed") == 1)
            fs_pending = next(row for row in desktop.sessions.approvals.values() if row["sessionId"] == fs_key)
            desktop.sessions.respond({"requestId": fs_pending["id"], "sessionId": fs_key, "answer": "allow"})
            until(lambda: gateways["feishu"].store.status()["tasks"].get("completed") == 1)
            for key in (wx_key, fs_key):
                assert (Path(desktop.sessions.get(key)["meta"]["cwd"]) / "bridge-proof.txt").read_text() == "once\n"
            desktop.invoke("remoteSwitchSession", {"channel": "weixin", "sessionId": other_key})
            assert gateways["weixin"].root_session == other_key and gateways["feishu"].root_session == fs_key
            until(lambda: bool(peers["feishu"]["replies"]))
            desktop.invoke("remoteStop", {"channel": "weixin"})
            until(lambda: not desktop.remote_channels.connection("weixin").thread.is_alive())
            assert desktop.invoke("remoteGetStatus")["channels"]["feishu"]["running"]
            desktop.invoke("remoteLogout", {"channel": "weixin"})
            assert not desktop.remote_channels.connection("weixin").credentials.has("weixin")
            assert desktop.remote_channels.connection("feishu").credentials.has("feishu")
        finally:
            desktop.remote_channels.close()
            for thread in threads:
                thread.join(timeout=10)
            assert not any(thread.is_alive() for thread in threads)


def test_remote_session_commands_switch_new_and_preserve_model_permissions(routed_desktop):
    desktop, (root, target, _) = routed_desktop
    config = ChannelConfig(
        workspace=Path(desktop.sessions.get(root)["meta"]["cwd"]),
        state_directory=desktop.store.directory / "routing",
        accounts={"weixin": AccountConfig(channel="weixin")},
    )
    gateway = DesktopChannelGateway(config, desktop, root)
    first = normalize_message("weixin", weixin_message("list", text="/sessions"))
    gateway.store.accept([first])
    assert target in json.loads(gateway.store.pending_reply({"weixin"})["payload"])["text"]
    gateway.store.accept([normalize_message("weixin", weixin_message("list-alias", text="/session"))])
    assert target in json.loads(gateway.store.pending_reply({"weixin"})["payload"])["text"]
    switch = normalize_message("weixin", weixin_message("switch", text="/switch " + target))
    gateway.store.accept([switch])
    assert desktop.store.get("remote-route", gateway.route_key(switch, 0)) == target
    gateway.store.accept([normalize_message("weixin", weixin_message("task", text="Run on target"))])
    row = gateway.store.claim()
    worker = threading.Thread(target=gateway._execute, args=(row, Path(config.state_directory) / "cancel"))
    worker.start()
    try:
        pending = until(lambda: next(iter(desktop.sessions.approvals.values()), None))
        assert pending["sessionId"] == target
        gateway.current = row
        gateway.store.accept([normalize_message("weixin", weixin_message("new-blocked", text="/new"))])
        assert gateway.store.get(row["id"])["status"] == "running"
        desktop.sessions.abort(target)
    finally:
        worker.join(timeout=10)
    assert gateway.store.get(row["id"])["status"] == "cancelled"
    gateway.store.accept([normalize_message("weixin", weixin_message("new", text="/new"))])
    gateway.store.accept([normalize_message("weixin", weixin_message("next", text="New context task"))])
    row = gateway.store.claim()
    worker = threading.Thread(target=gateway._execute, args=(row, Path(config.state_directory) / "cancel-next"))
    worker.start()
    try:
        pending = until(lambda: next(iter(desktop.sessions.approvals.values()), None))
        child = desktop.sessions.get(pending["sessionId"])
        assert pending["sessionId"] not in (root, target)
        assert child["meta"]["model"] == desktop.sessions.get(target)["meta"]["model"]
        assert child["permissionPolicy"] == "confirm" and len(child["messages"]) <= 2
        desktop.sessions.abort(pending["sessionId"])
    finally:
        worker.join(timeout=10)


def test_channel_split_preserves_legacy_cursor_without_replaying_unfinished_work(routed_desktop):
    desktop, _ = routed_desktop
    connection = desktop.remote_channels.connection("weixin")
    legacy = ChannelStore(connection.directory)
    message = normalize_message("weixin", weixin_message("old-running"))
    legacy.accept([message], account="weixin", cursor="committed-cursor")
    legacy.claim()
    destination = connection.directory / "weixin"
    connection.migrate_journal(destination)
    restored = ChannelStore(destination)
    assert restored.cursor("weixin") == "committed-cursor"
    assert restored.get(message.key)["status"] == "interrupted"
    assert restored.claim() is None and restored.pending_reply({"weixin"}) is None
    restored.accept([message], account="weixin", cursor="next-cursor")
    assert restored.status()["tasks"] == {"interrupted": 1}
    connection.migrate_journal(destination)
    assert restored.cursor("weixin") == "next-cursor"


def test_feishu_sdk_switch_and_new_commands_route_task_to_selected_workspace(routed_desktop):
    pytest.importorskip("lark_oapi")
    desktop, (root, target, _) = routed_desktop
    events = [
        feishu_event("list", text="/sessions"),
        feishu_event("switch", text="/switch " + target),
        feishu_event("new", text="/new"),
        feishu_event("task", text="Execute in the selected workspace"),
    ]
    with feishu_socket(events) as socket, provider_service(ws_url=socket["url"]) as peer:
        connection = desktop.remote_channels.connection("feishu")
        config = ChannelConfig(
            workspace=Path(desktop.sessions.get(root)["meta"]["cwd"]),
            state_directory=connection.directory / "feishu",
            accounts={"feishu": AccountConfig(channel="feishu", api_base=peer["base_url"], allowed_users=["owner"])},
        )
        gateway = DesktopChannelGateway(config, desktop, root)
        gateway.credentials.save(
            "feishu", {"app_id": "local-app", "app_secret": "local-secret", "allowed_users": ["owner"]}
        )
        connection.gateway = gateway
        connection.thread = threading.Thread(target=connection._serve, args=(gateway,), daemon=True)
        connection.thread.start()
        try:
            pending = until(lambda: next(iter(desktop.sessions.approvals.values()), None))
            child = desktop.sessions.get(pending["sessionId"])
            assert child["meta"]["sessionId"] not in (root, target)
            assert child["meta"]["cwd"] == desktop.sessions.get(target)["meta"]["cwd"]
            assert child["permissionPolicy"] == "confirm"
            desktop.sessions.respond({"requestId": pending["id"], "sessionId": pending["sessionId"], "answer": "allow"})
            until(lambda: gateway.store.status()["tasks"].get("completed") == 1)
            until(lambda: any("已切换到" in json.loads(reply["content"])["text"] for reply in peer["replies"]))
            assert (Path(child["meta"]["cwd"]) / "bridge-proof.txt").read_text() == "once\n"
            assert not (Path(desktop.sessions.get(root)["meta"]["cwd"]) / "bridge-proof.txt").exists()
            assert gateway.store.status()["tasks"]["command"] == 3
        finally:
            connection.stop()
            connection.thread.join(timeout=10)
            assert not connection.thread.is_alive()
