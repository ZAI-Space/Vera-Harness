"""Fork exact assistant replies and recall user attachments without losing context."""

import pytest

from vera.desktop.service import DesktopService


@pytest.mark.parametrize(("indexed",), [(False,), (True,)])  # noqa: PT006 - AGENTS.md requires tuple parameter names.
def test_fork_retains_selected_answer_and_recall_restores_images(tmp_path, indexed):
    service = DesktopService(tmp_path / "state")
    try:
        meta = service.invoke("createSession", {"options": {"cwd": str(tmp_path)}})
        key = meta["sessionId"]
        value = service.sessions.get(key)
        image = {"mimeType": "image/png", "data": "aW1hZ2U="}
        value["meta"].update(name="History", thinkingLevel="high")
        value["permissionPolicy"] = "yolo"
        value["runtimeMessages"] = [{"role": "system", "content": "Context"}]
        for turn in range(3):
            value["messages"].extend(
                [
                    {
                        "kind": "user",
                        "entryId": f"user-{turn}",
                        "text": f"Question {turn}",
                        "images": [image],
                        "runtimeIndex": 1 + 2 * turn,
                    },
                    {
                        "kind": "assistant",
                        "entryId": f"answer-{turn}",
                        "text": "Repeated answer",
                        "tools": [],
                        **({"runtimeIndex": 2 + 2 * turn} if indexed else {}),
                    },
                ]
            )
            value["runtimeMessages"].extend(
                [{"role": "user", "content": f"Question {turn}"}, {"role": "assistant", "content": "Repeated answer"}]
            )
        service.save_session(value)
        fork = service.invoke("forkSession", {"sessionId": key, "ref": {"entryId": "answer-1"}})
        child = service.sessions.get(fork["sessionId"])
        assert child["messages"] == value["messages"][:4]
        assert child["runtimeMessages"] == value["runtimeMessages"][:5]
        assert child["permissionPolicy"] == "yolo" and child["meta"]["thinkingLevel"] == "high"
        assert service.sessions.get(key)["messages"] == value["messages"]
        recalled = service.invoke("recallMessage", {"sessionId": key, "ref": {"entryId": "user-2"}})
        assert recalled["images"] == [image] and recalled["text"] == "Question 2"
        assert service.sessions.get(key)["messages"] == value["messages"][:4]
        assert service.sessions.get(key)["runtimeMessages"] == value["runtimeMessages"][:5]
        service.invoke("deleteSession", {"sessionId": fork["sessionId"]})
        assert service.invoke("closeSession", {"sessionId": fork["sessionId"]}) == {"closed": True}
        assert service.sessions.get(key)["messages"] == value["messages"][:4]
    finally:
        service.close()
