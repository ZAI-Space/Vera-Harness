"""Verify queued input recovery and priority delivery with real isolated workers."""

import time
from copy import deepcopy

import pytest

from vera.desktop.service import DesktopService
from vera.utils.serialize import strip_sensitive


@pytest.fixture
def queued_desktop(tmp_path):
    service = DesktopService(
        tmp_path / "state",
        {
            "model": {
                "model_class": "deterministic",
                "model_name": "fixture",
                "cost_per_call": 0,
                "outputs": [
                    {
                        "role": "assistant",
                        "content": "Done",
                        "extra": {"actions": [{"command": "echo COMPLETE_TASK_AND_SUBMIT_FINAL_OUTPUT; echo done"}]},
                    }
                ],
            },
            "agent": {
                "system_template": "Use Bash.",
                "instance_template": "{{task}}",
                "mode": "confirm",
                "cost_limit": 0,
            },
        },
    )
    session_id = service.invoke("createSession", {"options": {"cwd": str(tmp_path)}})["sessionId"]
    yield service, session_id
    service.close()


def wait_for(predicate):
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        if result := predicate():
            return result
        time.sleep(0.02)
    pytest.fail("Queued desktop worker did not settle.")


def pending(service):
    return next(iter(list(service.sessions.approvals.values())), None)


def test_clear_queue_returns_complete_inputs_and_releases_capacity(queued_desktop):
    service, session_id = queued_desktop
    service.sessions.prompt(session_id, "first")
    wait_for(lambda: pending(service))
    document = {"version": 1, "parts": [{"type": "text", "text": "read "}, {"type": "file", "path": "note.txt"}]}
    images = [{"mimeType": "image/png", "data": "AQID"}]
    service.sessions.prompt(session_id, "read note.txt", document, images)
    for index in range(19):
        service.sessions.prompt(session_id, f"queued {index}")
    with pytest.raises(ValueError, match="full"):
        service.sessions.prompt(session_id, "over capacity")
    cleared = service.invoke("clearQueue", {"sessionId": session_id})
    assert cleared["followUp"] == ["read note.txt", *[f"queued {index}" for index in range(19)]]
    assert cleared["followUpInputs"][0] == {"document": document, "images": images}
    assert cleared["followUpInputs"][1]["document"]["parts"][0]["text"] == "queued 0"
    assert service.invoke("getFollowUpMessages", {"sessionId": session_id}) == []
    service.sessions.prompt(session_id, "accepted again")
    assert service.invoke("getFollowUpMessages", {"sessionId": session_id}) == ["accepted again"]


def test_failed_followup_start_retains_queue_and_does_not_publish_a_user_message(queued_desktop, monkeypatch):
    service, session_id = queued_desktop
    service.sessions.prompt(session_id, "first")
    wait_for(lambda: pending(service))
    service.sessions.prompt(session_id, "retain me")

    def fail_start(*args, **kwargs):
        raise OSError("Simulated worker launch failure")

    with monkeypatch.context() as patch:
        patch.setattr("vera.desktop.sessions.subprocess.Popen", fail_start)
        service.sessions.respond({"sessionId": session_id, "requestId": pending(service)["id"], "answer": "allow"})
        wait_for(lambda: any(row["method"] == "onExtensionNotify" for row in service.events.read(0, 0)["events"]))
    value = service.sessions.get(session_id)
    assert [row["text"] for row in value["messages"] if row["kind"] == "user"] == ["first"]
    assert service.invoke("getFollowUpMessages", {"sessionId": session_id}) == ["retain me"]
    assert any(row["method"] == "onExtensionNotify" for row in service.events.read(0, 0)["events"])
    service.invoke("clearQueue", {"sessionId": session_id})
    service.sessions.prompt(session_id, "retry")
    wait_for(lambda: pending(service))
    service.sessions.respond({"sessionId": session_id, "requestId": pending(service)["id"], "answer": "allow"})
    wait_for(lambda: session_id not in service.sessions.running)


def test_immediate_send_stops_current_worker_and_preserves_fifo_followups(queued_desktop):
    service, session_id = queued_desktop
    service.sessions.prompt(session_id, "first")
    wait_for(lambda: pending(service))
    first_process = service.sessions.running[session_id]
    service.sessions.prompt(session_id, "queued one")
    service.sessions.prompt(session_id, "queued two")
    service.invoke("prompt", {"sessionId": session_id, "text": "urgent", "interrupt": True})
    for expected in ("urgent", "queued one", "queued two"):
        wait_for(
            lambda: (
                pending(service)
                and [row["text"] for row in service.sessions.get(session_id)["messages"] if row["kind"] == "user"][-1]
                == expected
            )
        )
        users = [row["text"] for row in service.sessions.get(session_id)["messages"] if row["kind"] == "user"]
        assert users[-1] == expected
        service.sessions.respond({"sessionId": session_id, "requestId": pending(service)["id"], "answer": "allow"})
        wait_for(lambda: not pending(service))
    wait_for(lambda: session_id not in service.sessions.running)
    assert first_process.poll() is not None
    assert service.invoke("getFollowUpMessages", {"sessionId": session_id}) == []
    assert not service.sessions.interrupted
    assert [row["text"] for row in service.sessions.get(session_id)["messages"] if row["kind"] == "user"] == [
        "first",
        "urgent",
        "queued one",
        "queued two",
    ]


def test_image_only_followup_does_not_stall_later_messages(queued_desktop, monkeypatch):
    """Empty text with an image must dispatch a task and advance the same FIFO."""
    service, session_id = queued_desktop
    config = service.sessions.config(service.sessions.get(session_id))
    value = service.sessions.get(session_id)
    value["meta"]["model"] = {"provider": "fixture", "modelId": "image-model"}
    service.store.save("session", session_id, value)
    monkeypatch.setattr(service.sessions, "config", lambda _: deepcopy(config))
    monkeypatch.setattr(service.providers, "definition", lambda _: {"imageInput": True})
    # The real deterministic worker has no provider credentials to restore.
    monkeypatch.setattr(
        "vera.desktop.sessions.strip_sensitive",
        lambda payload: strip_sensitive(
            {name: item for name, item in payload.items() if name not in {"desktop_provider_ref", "desktop_state_dir"}}
        ),
    )
    image = {"mimeType": "image/png", "data": "AQID"}
    service.sessions.prompt(session_id, "first")
    wait_for(lambda: pending(service))
    service.sessions.prompt(session_id, "", images=[image])
    service.sessions.prompt(session_id, "after image")
    for _ in range(3):
        approval = wait_for(lambda: pending(service))
        service.sessions.respond({"sessionId": session_id, "requestId": approval["id"], "answer": "allow"})
        wait_for(lambda: not pending(service))
    wait_for(lambda: session_id not in service.sessions.running)
    users = [row for row in service.sessions.get(session_id)["messages"] if row["kind"] == "user"]
    assert [row["text"] for row in users] == ["first", "", "after image"]
    assert users[1]["images"] == [image]
    assert service.invoke("getFollowUpMessages", {"sessionId": session_id}) == []
