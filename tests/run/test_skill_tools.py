"""Exercise skill discovery, local CLI commands and Agent Loop tool dispatch."""

import json
import os
import subprocess
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread

import pytest

from tests.conftest import create_symlink
from tests.run.test_web_tools import FINISH_CALL, _model_response
from vera.tools import ToolError, ToolRegistry
from vera.tools.skills import SkillConfig, discover_skills, register_skill_tools


def write_skill(root: Path, name: str, body: str) -> Path:
    """Create a test workflow with one companion file."""
    directory = root / name
    (directory / "references").mkdir(parents=True)
    (directory / "SKILL.md").write_text(
        f"---\nname: {name}\ndescription: Workflow for {name}.\n---\n{body}", encoding="utf-8"
    )
    (directory / "references" / "guide.md").write_text("Reference instructions.", encoding="utf-8")
    return directory


def test_catalog_discovery_precedence_search_and_pagination(tmp_path):
    project = tmp_path / ".agents" / "skills"
    instructions = "main workflow step\n" * 300
    write_skill(project / "development", "review-work", instructions)
    write_skill(tmp_path / "external", "review-work", "shadowed instructions")
    write_skill(tmp_path / "external", "ignore-me", "disabled instructions")
    for index in range(8):
        write_skill(project, f"sample-{index}", "sample instructions")
    config = SkillConfig(directories=[Path("external")], disabled=["ignore-me"])
    registry = ToolRegistry()
    catalog = discover_skills(config, tmp_path)
    register_skill_tools(registry, catalog)

    def call(tool, **arguments):
        result = registry.execute({"tool": tool, "arguments": arguments})
        assert result["returncode"] == 0
        return json.loads(result["output"])

    listing = call("skills_list", query="sample")
    remainder = call("skills_list", query="sample", offset=listing["next_offset"])
    assert len(listing["skills"] + remainder["skills"]) == 8
    assert call("skills_list", query="ignore-me")["skills"] == []
    assert call("skills_list", query="review-work")["skills"] == [
        {"name": "review-work", "description": "Workflow for review-work."}
    ]
    first = call("skill_view", name="review-work")
    second = call("skill_view", name="review-work", offset=first["next_offset"])
    assert first["content"] + second["content"] == instructions
    assert first["files"] == ["references/guide.md"]
    assert call("skill_view", name="review-work", file_path=first["files"][0])["content"] == "Reference instructions."
    for path in ("references/../../SKILL.md", "C:/sensitive.md", "references/.env", "references/file.txt:hidden"):
        assert (
            registry.execute({"tool": "skill_view", "arguments": {"name": "review-work", "file_path": path}})[
                "returncode"
            ]
            == 1
        )


def test_linked_attachments_stay_in_skill_directory(tmp_path):
    skill_dir = write_skill(tmp_path / ".agents" / "skills", "review-work", "workflow")
    outside = tmp_path / "outside.md"
    outside.write_text("Do not expose this file", encoding="utf-8")
    create_symlink(skill_dir / "references" / "alias.md", outside)
    selected = discover_skills(SkillConfig(), tmp_path)["review-work"]
    assert selected.view()["files"] == ["references/guide.md"]
    with pytest.raises(ToolError, match="Skill file is unavailable"):
        selected.view("references/alias.md")


def run_cli(tmp_path, module, *arguments, **environment):
    """Run the actual CLI in a workspace with isolated user configuration."""
    repo_path = str(Path(__file__).resolve().parents[2])
    python_paths = [repo_path, os.environ.get("PYTHONPATH", "")]
    return subprocess.run(
        [sys.executable, "-m", module, *arguments],
        cwd=tmp_path,
        env=os.environ
        | {
            "VERA_CONFIGURED": "true",
            "VERA_GLOBAL_CONFIG_DIR": str(tmp_path / "user-config"),
            "VERA_SILENT_STARTUP": "1",
            "PYTHONIOENCODING": "utf-8",
            "PYTHONPATH": os.pathsep.join(filter(None, python_paths)),
        }
        | environment,
        capture_output=True,
        encoding="utf-8",
        timeout=30,
        check=True,
    )


def test_offline_inspection_finds_project_and_external_skills(tmp_path):
    project_skill = write_skill(tmp_path / ".agents" / "skills", "review-work", "Main workflow body.")
    write_skill(tmp_path / "extra", "another-workflow", "External workflow body.")
    write_skill(tmp_path / "user-config" / "skills", "shared-workflow", "User workflow body.")
    command = "vera.run.utilities.extra"
    listing = run_cli(tmp_path, command, "skills", "list", "-d", "extra").stdout
    assert "review-work\tWorkflow for review-work." in listing
    assert "another-workflow\tWorkflow for another-workflow." in listing
    assert "shared-workflow\tWorkflow for shared-workflow." in listing
    assert "Main workflow body." not in listing
    reference = project_skill / "references" / "guide.md"
    reference.write_text("Reference instructions ░", encoding="utf-8")
    result = run_cli(
        tmp_path, command, "skills", "show", "review-work", "references/guide.md", PYTHONIOENCODING="gbk"
    ).stdout
    assert result.strip() == "Reference instructions ░"


@pytest.mark.parametrize("explicit_skill", [[], ["--skill", "review-work"]])
def test_agent_discovers_and_loads_workflow_with_selected_model(tmp_path, explicit_skill):
    write_skill(tmp_path / ".agents" / "skills", "review-work", "Main workflow body.")
    actions = (
        [
            ("skills_list", {"query": "review"}),
            ("skill_view", {"name": "review-work"}),
            ("skill_view", {"name": "review-work", "file_path": "references/guide.md"}),
            FINISH_CALL,
        ]
        if not explicit_skill
        else [FINISH_CALL]
    )
    requests = []

    class ModelHandler(BaseHTTPRequestHandler):
        def do_POST(self):
            payload = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            action = actions[len(requests)]
            requests.append(payload)
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(_model_response([action], responses_api=False)).encode())

    with ThreadingHTTPServer(("127.0.0.1", 0), ModelHandler) as server:
        thread = Thread(target=server.serve_forever, daemon=True)
        thread.start()
        trajectory = tmp_path / "run.json"
        try:
            run_cli(
                tmp_path,
                "vera",
                *explicit_skill,
                "-t",
                "Review changes",
                "--model",
                "fixture",
                "--model-class",
                "tests.run.test_web_tools.LocalFixtureModel",
                "-y",
                "--exit-immediately",
                "-o",
                str(trajectory),
                VERA_TEST_MODEL_URL=f"http://127.0.0.1:{server.server_port}",
            )
        finally:
            server.shutdown()
            thread.join(timeout=5)
    assert json.loads(trajectory.read_text(encoding="utf-8"))["info"]["exit_status"] == "Submitted"
    assert [tool["function"]["name"] for tool in requests[0]["tools"]] == ["bash", "skills_list", "skill_view"]
    assert ("Main workflow body." in json.dumps(requests[0]["messages"])) == bool(explicit_skill)
    if not explicit_skill:
        assert "Workflow for review-work." in json.dumps(requests[1]["messages"])
        assert "Main workflow body." in json.dumps(requests[2]["messages"])
        assert "Reference instructions." in json.dumps(requests[3]["messages"])
