"""Exercise real LAN HTTP authentication, projections, revocation and runtime commands."""

import json
import socket
import threading
import time
from urllib.parse import urlsplit

import pytest
import requests

from vera.desktop.service import DesktopService


def test_lan_pairing_readonly_scoped_writes_and_revocation(tmp_path):
    service = DesktopService(tmp_path / "data")
    try:
        assert not service.invoke("lanGetStatus")["enabled"]
        session = service.invoke("createSession", {"options": {"cwd": str(tmp_path)}})
        key = session["sessionId"]
        service.providers.save_key("private-provider", "local-private-provider-secret")
        status = service.invoke("lanSetEnabled", {"enabled": True})
        assert status["enabled"] and status["urls"] and not status["remoteControl"]
        address = f"http://127.0.0.1:{status['port']}"
        token = urlsplit(status["urls"][0]).fragment.removeprefix("token=")
        headers = {"Authorization": "Bearer " + token}
        assert requests.get(address + "/", timeout=3).status_code == 200
        assert requests.get(address + "/api/snapshot", timeout=3).status_code == 401
        snapshot = requests.get(address + "/api/snapshot", headers=headers, timeout=3)
        assert snapshot.status_code == 200 and snapshot.json()["sessionId"] == key
        assert "local-private-provider-secret" not in snapshot.text
        assert (
            requests.get(
                address + "/api/snapshot", headers=headers | {"Origin": "https://example.com"}, timeout=3
            ).status_code
            == 401
        )
        assert (
            requests.get(
                address + "/api/snapshot", headers=headers | {"Host": "attacker.example"}, timeout=3
            ).status_code
            == 401
        )
        assert (
            requests.post(
                address + "/api/action", headers=headers, json={"method": "abort", "sessionId": key}, timeout=3
            ).status_code
            == 403
        )
        service.invoke("lanSetRemoteControl", {"enabled": True})
        assert (
            requests.post(
                address + "/api/action",
                headers=headers,
                json={"method": "removeCredential", "sessionId": key},
                timeout=3,
            ).status_code
            == 403
        )
        assert (
            requests.post(
                address + "/api/action",
                headers=headers,
                json={"method": "prompt", "sessionId": key, "text": "/yolo"},
                timeout=3,
            ).status_code
            == 400
        )
        service.invoke("setSessionSelections", {"sessionId": key, "permissionPolicy": "human"})
        response = requests.post(
            address + "/api/action",
            headers=headers,
            json={"method": "prompt", "sessionId": key, "text": "printf lan-ok > lan.txt"},
            timeout=5,
        )
        assert response.status_code == 200
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline and service.sessions.baseline(key)["transcript"]["agentActive"]:
            time.sleep(0.1)
        assert (tmp_path / "lan.txt").read_text() == "lan-ok"
        assert service.invoke("lanGetStatus")["clients"] == 1
        service.invoke("lanSetRemoteControl", {"enabled": False})
        assert (
            requests.post(
                address + "/api/action", headers=headers, json={"method": "abort", "sessionId": key}, timeout=3
            ).status_code
            == 403
        )
        service.invoke("lanSetEnabled", {"enabled": False})
        assert not service.invoke("lanGetStatus")["urls"]
        restarted = service.invoke("lanSetEnabled", {"enabled": True})
        assert restarted["urls"][0] != status["urls"][0]
        assert (
            requests.get(f"http://127.0.0.1:{restarted['port']}/api/snapshot", headers=headers, timeout=3).status_code
            == 401
        )
    finally:
        service.close()


def test_remote_control_requires_an_active_listener(tmp_path):
    service = DesktopService(tmp_path)
    try:
        with pytest.raises(ValueError, match="先开启"):
            service.invoke("lanSetRemoteControl", {"enabled": True})
    finally:
        service.close()


def test_incomplete_lan_body_cannot_block_revocation_or_dispatch_after_disable(tmp_path):
    """The owner can revoke an accepted slow client before it finishes its action."""
    service = DesktopService(tmp_path / "data")
    client = None
    stopped = threading.Event()
    closer = None
    try:
        key = service.invoke("createSession", {"options": {"cwd": str(tmp_path)}})["sessionId"]
        status = service.invoke("lanSetEnabled", {"enabled": True})
        service.invoke("lanSetRemoteControl", {"enabled": True})
        token = urlsplit(status["urls"][0]).fragment.removeprefix("token=")
        body = json.dumps({"method": "abort", "sessionId": key}).encode()
        client = socket.create_connection(("127.0.0.1", status["port"]), timeout=3)
        client.sendall(
            (
                f"POST /api/action HTTP/1.0\r\nHost: 127.0.0.1:{status['port']}\r\n"
                f"Authorization: Bearer {token}\r\nContent-Length: {len(body)}\r\n\r\n"
            ).encode()
            + body[:1]
        )
        time.sleep(0.1)

        def disable():
            service.lan.close()
            stopped.set()

        closer = threading.Thread(target=disable)
        closer.start()
        assert stopped.wait(2), "An incomplete remote body blocked owner revocation"
        client.sendall(body[1:])
        assert b"401" in client.recv(4096).split(b"\r\n", 1)[0]
        assert not service.lan.status()["enabled"]
    finally:
        if client:
            client.close()
        if closer:
            closer.join(timeout=3)
        service.close()
