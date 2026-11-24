"""Project removal confirms one unchanged catalog and preserves unrelated source and chats."""

import time

import pytest

from tests.run.test_desktop import desktop, wait_until  # noqa: F401
from vera.desktop.service import DesktopService


# Value: protects=expired project deletion confirmations preserve all chats;
# fails_when=deletion accepts an expired token with an unchanged catalog;
# why_new=existing checks reject only changed catalogs and reused tokens; seam=none;
# no_claim=clock scheduling or actual ten-minute elapsed time.
def test_project_deletion_preview_is_single_use_and_fenced_against_catalog_changes(tmp_path):
    service = DesktopService(tmp_path / "state")
    project = tmp_path / "project"
    other = tmp_path / "other"
    project.mkdir()
    other.mkdir()
    source = project / "source.txt"
    source.write_text("PRESERVE_SOURCE")
    try:
        first = service.invoke("createSession", {"options": {"cwd": str(project)}})
        protected = service.invoke("createSession", {"options": {"cwd": str(other)}})
        args = {"cwd": str(project.resolve())}
        preview = service.invoke("previewSessionProjectDeletion", args)
        assert preview["sessionCount"] == 1
        _, cwd, rows = service.project_deletion.previews[preview["token"]]
        service.project_deletion.previews[preview["token"]] = (time.monotonic() - 1, cwd, rows)
        with pytest.raises(ValueError, match="过期"):
            service.invoke("deleteSessionProject", args | {"token": preview["token"]})
        assert {row["sessionId"] for row in service.metas()} == {first["sessionId"], protected["sessionId"]}
        assert source.read_text() == "PRESERVE_SOURCE"
        preview = service.invoke("previewSessionProjectDeletion", args)
        service.invoke("setSessionName", {"sessionId": first["sessionId"], "name": "Changed after preview"})
        with pytest.raises(ValueError, match="过期"):
            service.invoke("deleteSessionProject", args | {"token": preview["token"]})
        preview = service.invoke("previewSessionProjectDeletion", args)
        child = service.store.create_session({"cwd": str(project)})
        child["meta"].update(parentSessionId=first["sessionId"], readOnly=True)
        service.store.delete("session", child["meta"]["sessionId"])
        service.store.save("delegated-session", child["meta"]["sessionId"], child)
        preview = service.invoke("previewSessionProjectDeletion", args)
        assert preview["sessionCount"] == 2
        assert service.invoke("deleteSessionProject", args | {"token": preview["token"]}) == {
            "deleted": sorted([first["sessionId"], child["meta"]["sessionId"]]),
            "failed": [],
        }
        assert source.read_text() == "PRESERVE_SOURCE"
        assert service.metas() == [protected]
        assert not service.store.list("delegated-session")
        with pytest.raises(ValueError, match="过期"):
            service.invoke("deleteSessionProject", args | {"token": preview["token"]})
    finally:
        service.close()


# Value: protects=running projects cannot be previewed or deleted;
# fails_when=project removal ignores an active worker awaiting approval;
# why_new=existing deletion coverage contains only idle sessions; seam=none;
# no_claim=paid provider behavior; the real worker uses a deterministic model.
def test_project_deletion_refuses_a_real_worker_waiting_for_approval(desktop, tmp_path):
    service, invoke, _, _ = desktop
    project = tmp_path / "active-project"
    project.mkdir()
    source = project / "source.txt"
    source.write_text("PRESERVE_SOURCE")
    key = invoke("createSession", options={"cwd": str(project)})["sessionId"]
    args = {"cwd": str(project.resolve())}
    preview = service.invoke("previewSessionProjectDeletion", args)
    invoke("prompt", sessionId=key, text="Wait for approval before modifying this project.")
    try:
        wait_until(lambda: service.sessions.approvals)
        for method in ("previewSessionProjectDeletion", "deleteSessionProject"):
            with pytest.raises(ValueError, match="先停止"):
                service.invoke(method, args | {"token": preview["token"]})
        assert service.sessions.get(key)["meta"]["sessionId"] == key
        assert source.read_text() == "PRESERVE_SOURCE"
        assert not (project / "actual.txt").exists()
    finally:
        invoke("abort", sessionId=key)
        wait_until(lambda: not service.sessions.baseline(key)["transcript"]["agentActive"])
