"""Exercise package lifecycle, hostile sources, real MCP dispatch and CLI market installation."""

import json
import os
import shutil
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread

import pytest

from minisweagent.plugins import PluginError, PluginManager, load_plugins
from minisweagent.plugins.manifest import load_bundle
from minisweagent.plugins.source import PluginSource, Source, filesystem_path, normalize_source, relative_path
from minisweagent.storage import RunStore
from minisweagent.tools import ToolRegistry
from minisweagent.tools.mcp import mcp_tool_name, open_mcp_tools, parse_mcp_servers
from tests.run.test_skill_tools import run_cli, write_skill
from tests.run.test_storage import _write_config
from tests.run.test_web_tools import FINISH_CALL, _model_response


def write_plugin(root: Path, name: str = "review-kit", *, layout: str = "portable") -> Path:
    """Create a real skill package in each supported manifest layout."""
    manifest = root / ("plugin.json" if layout == "portable" else f".{layout}-plugin/plugin.json")
    manifest.parent.mkdir(parents=True, exist_ok=True)
    manifest.write_text(json.dumps({"name": name, "version": "1.0.0", "description": "Review changes."}))
    write_skill(root / "skills", "review", "Plugin workflow body.")
    return root


def write_market(root: Path, entries: list[dict], name: str = "team-market") -> Path:
    """Create the actual Codex repository marketplace layout."""
    catalog = root / ".agents/plugins/marketplace.json"
    catalog.parent.mkdir(parents=True, exist_ok=True)
    catalog.write_text(json.dumps({"name": name, "plugins": entries}))
    return root


def test_market_lifecycle_update_rollback_integrity_and_failure_atomicity(tmp_path):
    source = write_plugin(tmp_path / "market/plugins/review")
    root = write_market(
        tmp_path / "market", [{"name": "review-kit", "source": {"source": "local", "path": "./plugins/review"}}]
    )
    manager = PluginManager(tmp_path / "store")
    assert manager.list_plugins() == manager.list_marketplaces() == {}
    assert not manager.directory.exists()
    assert manager.add_marketplace(str(root))["plugins"]["review-kit"]["path"] == "plugins/review"
    first = manager.install_from_marketplace("review-kit", "team-market")
    assert not first["enabled"]
    assert load_plugins({"plugins": {"directory": manager.directory}}).skills == {}
    manager.set_enabled("review-kit", True)
    original = {"plugins": {"directory": manager.directory}, "model": {"model_name": "unchanged"}}
    loaded = load_plugins(original)
    assert list(loaded.skills) == ["review-kit-review"]
    assert loaded.skills["review-kit-review"].view()["content"] == "Plugin workflow body."
    assert original.keys() == {"plugins", "model"}
    assert manager.update("review-kit")["enabled"]
    (source / "skills/review/SKILL.md").write_text("invalid metadata")
    with pytest.raises(PluginError, match="frontmatter"):
        manager.update("review-kit")
    assert manager.show("review-kit")["enabled"]
    assert manager.show("review-kit")["digest"] == first["digest"]
    shutil.rmtree(source / "skills")
    write_skill(source / "skills", "review", "Updated workflow body.")
    second = manager.update("review-kit")
    assert not second["enabled"] and second["digest"] != first["digest"]
    assert len(manager.show("review-kit")["versions"]) == 2
    manager.set_enabled("review-kit", True)
    manager.rollback("review-kit", first["digest"])
    assert not manager.show("review-kit")["enabled"]
    assert manager.show("review-kit")["digest"] == first["digest"]
    manager.set_enabled("review-kit", True)
    manager.remove_marketplace("team-market")
    assert "review-kit-review" in load_plugins(original).skills
    with pytest.raises(PluginError, match="marketplace is unavailable"):
        manager.update("review-kit")
    manager.uninstall("review-kit")
    assert manager.list_plugins() == {}
    assert loaded.skills["review-kit-review"].view()["content"] == "Plugin workflow body."


@pytest.mark.parametrize("layout", ["portable", "vera", "codex", "claude"])
def test_manifest_formats_namespace_mcp_and_role_permissions(tmp_path, layout):
    pytest.importorskip("mcp")
    package = write_plugin(tmp_path / layout, layout=layout)
    shutil.copy(Path(__file__).with_name("mcp_fixture.py"), package / "server.py")
    server = {
        "fixture": {
            "type": "stdio",
            "command": sys.executable,
            "args": ["${PLUGIN_ROOT}/server.py"],
            "allow_tools": ["echo"],
        }
    }
    (package / ("mcp.json" if layout == "portable" else ".mcp.json")).write_text(json.dumps({"mcpServers": server}))
    roles = {
        "reviewer": {
            "description": "Review",
            "instructions": "Use the workflow",
            "skills": ["review"],
            "tools": ["mcp:fixture/echo"],
        }
    }
    manifest = package / ("plugin.json" if layout == "portable" else f".{layout}-plugin/plugin.json")
    content = json.loads(manifest.read_text())
    content.update({"extensions": {"vera": {"subagents": roles}}} if layout == "portable" else {"subagents": roles})
    manifest.write_text(json.dumps(content))
    manager = PluginManager(tmp_path / "store")
    record = manager.install(str(package))
    manager.set_enabled("review-kit", True)
    loaded = load_plugins({"plugins": {"directory": manager.directory}})
    role = loaded.config["subagents"]["roles"]["review-kit-reviewer"]
    assert role["skills"] == ["review-kit-review"]
    assert role["tools"] == [mcp_tool_name("review-kit-fixture", "echo")]
    assert loaded.versions == {"review-kit": record["digest"]}
    registry = ToolRegistry()
    with open_mcp_tools(registry, parse_mcp_servers(loaded.config["mcp_servers"])):
        result = registry.execute({"tool": role["tools"][0], "arguments": {"text": "installed MCP"}})
        assert result["returncode"] == 0 and "installed MCP" in result["output"]
        assert len(registry.definitions()) == 1
    (manager.package(record) / "skills/review/SKILL.md").write_text("tampered")
    with pytest.raises(PluginError, match="integrity"):
        load_plugins({"plugins": {"directory": manager.directory}})
    manager.set_enabled("review-kit", False)
    assert load_plugins({"plugins": {"directory": manager.directory}}).skills == {}


@pytest.mark.parametrize(
    "path", ["../outside", "/absolute", "C:/outside", "a\\b", "dir/NUL.txt", "dir/file:stream", "name.", ".git/config"]
)
def test_reject_nonportable_or_escaping_package_paths(path):
    with pytest.raises(PluginError):
        relative_path(path)


@pytest.mark.parametrize(
    "source",
    [
        "http://github.com/a/b",
        "https://token@github.com/a/b",
        "https://example.com/a/b",
        "https://github.com/a/b/tree/main",
        "https://github.com/a/b?token=secret",
        "git@github.com:a/b.git",
    ],
)
def test_reject_ambiguous_or_credential_bearing_sources(source):
    with pytest.raises(PluginError):
        normalize_source(source)
    assert normalize_source("openai/plugins") == "https://github.com/openai/plugins.git"
    assert normalize_source("team/plugins", PluginSource.gitee) == "https://gitee.com/team/plugins.git"
    assert normalize_source("https://gitee.com/team/plugins") == "https://gitee.com/team/plugins.git"


def test_unsupported_capabilities_bad_metadata_and_first_install_failure(tmp_path):
    manager = PluginManager(tmp_path / "store")
    package = write_plugin(tmp_path / "source", layout="codex")
    manifest = package / ".codex-plugin/plugin.json"
    content = json.loads(manifest.read_text()) | {"hooks": "./hooks/hooks.json"}
    manifest.write_text(json.dumps(content))
    with pytest.raises(PluginError, match="Unsupported plugin capability"):
        manager.install(str(package))
    assert manager.list_plugins() == {}
    content.pop("hooks")
    manifest.write_text(json.dumps(content | {"skills": "../outside"}))
    with pytest.raises(PluginError, match="Unsafe package path"):
        manager.install(str(package))
    manifest.write_text(
        json.dumps(
            content
            | {
                "mcpServers": {
                    "private": {"url": "https://example.com/mcp", "headers": {"Authorization": "Bearer literal-secret"}}
                }
            }
        )
    )
    with pytest.raises(PluginError, match="Authorization: Bearer"):
        manager.install(str(package))
    manifest.write_text(
        json.dumps(
            content
            | {
                "mcpServers": {
                    "private": {"url": "https://example.com/mcp", "headers": {"Authorization": "Bearer ${TEST_TOKEN}"}}
                }
            }
        )
    )
    bundle = load_bundle(package.resolve())
    assert bundle.servers["review-kit-private"].bearer_token_env == "TEST_TOKEN"
    manifest.write_text(json.dumps(content | {"name": 123}))
    with pytest.raises(PluginError, match="Invalid plugin"):
        manager.install(str(package))


def test_catalog_identity_policies_refresh_and_atomic_rejection(tmp_path):
    root = write_market(
        tmp_path / "market",
        [
            {
                "name": "review-kit",
                "source": {
                    "source": "git-subdir",
                    "url": "https://github.com/example/plugins",
                    "path": "./plugins/review",
                    "sha": "f" * 40,
                },
            },
            {"name": "npm-only", "source": {"source": "npm", "package": "example"}},
            {"name": "blocked", "source": "./plugins/blocked", "policy": {"installation": "NOT_AVAILABLE"}},
        ],
    )
    manager = PluginManager(tmp_path / "store")
    market = manager.add_marketplace(str(root))
    assert market["plugins"]["review-kit"]["ref"] == "f" * 40
    for plugin in ("npm-only", "blocked"):
        with pytest.raises(PluginError):
            manager.install_from_marketplace(plugin, "team-market")
    write_market(root, [{"name": "escape", "source": "../outside"}])
    with pytest.raises(PluginError, match="Unsafe package path"):
        manager.refresh_marketplace("team-market")
    assert "review-kit" in manager.list_marketplaces()["team-market"]["plugins"]
    write_market(root, [{"name": "review-kit", "source": "./plugins/review"}])
    write_plugin(root / "plugins/review", name="wrong-identity")
    manager.refresh_marketplace("team-market")
    with pytest.raises(PluginError, match="Expected plugin"):
        manager.install_from_marketplace("review-kit", "team-market")
    assert manager.list_plugins() == {}


def test_claude_catalog_fallback_and_only_two_public_hosts(tmp_path):
    root = tmp_path / "market"
    (root / ".claude-plugin").mkdir(parents=True)
    catalog = root / ".claude-plugin/marketplace.json"
    catalog.write_text(
        json.dumps(
            {
                "name": "domestic",
                "plugins": [
                    {
                        "name": "gitee-package",
                        "source": {
                            "source": "git-subdir",
                            "url": "https://gitee.com/team/plugins.git",
                            "path": "./plugins/review",
                        },
                    },
                    {"name": "github-package", "source": {"source": "github", "repo": "team/plugins"}},
                ],
            }
        )
    )
    manager = PluginManager(tmp_path / "store")
    record = manager.add_marketplace(str(root), host=PluginSource.gitee)
    assert record["catalog"] == ".claude-plugin/marketplace.json"
    assert record["plugins"]["gitee-package"]["source"].startswith("https://gitee.com/")
    assert record["plugins"]["github-package"]["source"].startswith("https://github.com/")
    assert set(PluginSource) == {PluginSource.github, PluginSource.gitee}
    with pytest.raises(PluginError):
        normalize_source("https://gitcode.com/team/plugins.git")
    with pytest.raises(PluginError):
        normalize_source("https://[invalid/owner/repo")
    with pytest.raises(PluginError, match="Choose a source first"):
        manager.install_named("gitee-package")
    # Persist a saved catalog selection directly to exercise the same on-disk transition offline.
    with manager._state(write=True) as state:
        state["selected_marketplace"] = "domestic"
    assert manager.selected_marketplace() == "domestic"
    manager.remove_marketplace("domestic")
    assert manager.selected_marketplace() is None


def test_resume_rejects_changed_plugin_content_before_any_new_action(tmp_path):
    package = write_plugin(tmp_path / "source")
    manager = PluginManager(tmp_path / "user-config/plugins")
    manager.install(str(package))
    manager.set_enabled("review-kit", True)
    config = tmp_path / "test.yaml"
    _write_config(config, "printf checkpoint", step_limit=1)
    # The deterministic adapter can use explicitly selected skills without a model tool protocol.
    database = tmp_path / "runs.sqlite3"
    run_cli(
        tmp_path,
        "minisweagent",
        "-c",
        str(config),
        "--storage",
        str(database),
        "-t",
        "Checkpoint task",
        "-o",
        str(tmp_path / "first.json"),
    )
    run_id = RunStore(database).list_runs()[0]["id"]
    (package / "skills/review/SKILL.md").write_text("---\nname: review\ndescription: changed\n---\nNew instructions.")
    manager.update("review-kit")
    manager.set_enabled("review-kit", True)
    with pytest.raises(subprocess.CalledProcessError) as failure:
        run_cli(
            tmp_path,
            "minisweagent",
            "-c",
            str(config),
            "--storage",
            str(database),
            "--resume",
            run_id,
            "-o",
            str(tmp_path / "second.json"),
        )
    assert "original workspace, execution configuration" in failure.value.stderr


def test_scoped_loading_collision_and_concurrent_registry_writes(tmp_path):
    manager = PluginManager(tmp_path / "store")
    for name in ("first", "second"):
        manager.install(str(write_plugin(tmp_path / name, name)))
    with ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(lambda name: manager.set_enabled(name, True), ["first", "second"]))
    assert all(plugin["enabled"] for plugin in manager.list_plugins().values())
    config = {"plugins": {"directory": manager.directory, "names": ["first"]}}
    assert list(load_plugins(config).skills) == ["first-review"]
    assert load_plugins({**config, "skills": {"disabled": ["first-review"]}}).skills == {}
    manager.set_enabled("first", False)
    with pytest.raises(PluginError, match="explicitly enabled"):
        load_plugins(config)
    assert load_plugins({"plugins": {"enabled": False, "directory": manager.directory}}).skills == {}
    package = write_plugin(tmp_path / "third", "third")
    (package / "mcp.json").write_text(json.dumps({"mcpServers": {"docs": {"url": "https://example.com/mcp"}}}))
    manager.install(str(package))
    manager.set_enabled("third", True)
    with pytest.raises(PluginError, match="collision"):
        load_plugins({"plugins": {"directory": manager.directory}, "mcp_servers": {"third-docs": {}}})


def test_real_git_archive_exports_pinned_tree_and_rejects_submodules(tmp_path):
    repository = tmp_path / "git-source"
    package = write_plugin(repository / "plugins/review")

    def git(*arguments):
        return subprocess.run(
            ["git", "-c", "user.name=Test", "-c", "user.email=test@example.invalid", *arguments],
            cwd=repository,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()

    git("init")
    git("add", ".")
    git("commit", "-m", "fixture")
    commit = git("rev-parse", "HEAD")
    source = Source(str(repository), repository, commit)
    snapshot = source.export("plugins/review", tmp_path / "exported")
    assert load_bundle(snapshot).manifest.name == "review-kit"
    (package / "skills/review/SKILL.md").write_text("uncommitted mutation")
    assert "Plugin workflow" in (snapshot / "skills/review/SKILL.md").read_text()
    git("update-index", "--add", "--cacheinfo", f"160000,{commit},plugins/review/submodule")
    git("commit", "-m", "submodule")
    with pytest.raises(PluginError, match="submodules"):
        Source(str(repository), repository, git("rev-parse", "HEAD")).export("plugins/review", tmp_path / "bad-export")


@pytest.mark.skipif(os.name == "nt", reason="Windows symlink creation requires developer mode")
def test_local_links_and_case_aliases_cannot_enter_packages(tmp_path):
    package = write_plugin(tmp_path / "source")
    (package / "escape").symlink_to(tmp_path, target_is_directory=True)
    manager = PluginManager(tmp_path / "store")
    with pytest.raises(PluginError, match="link"):
        manager.install(str(package))
    (package / "escape").unlink()
    (package / "FILE.txt").write_text("one")
    (package / "file.txt").write_text("two")
    with pytest.raises(PluginError, match="collision"):
        manager.install(str(package))


def test_long_windows_package_paths_remain_readable_after_versioning(tmp_path):
    package = write_plugin(filesystem_path(tmp_path / "source"))
    attachment = package / "skills/review/references" / ("nested-" * 12) / ("long-name-" * 10 + ".md")
    attachment.parent.mkdir(parents=True)
    attachment.write_text("Long path attachment.")
    manager = PluginManager(tmp_path / "deep-store" / ("directory-" * 6))
    record = manager.install(str(package))
    manager.set_enabled("review-kit", True)
    assert manager.show("review-kit")["digest"] == record["digest"]
    loaded = load_plugins({"plugins": {"directory": manager.directory}})
    relative = attachment.relative_to(package / "skills/review").as_posix()
    assert loaded.skills["review-kit-review"].view(relative)["content"] == "Long path attachment."


def test_actual_cli_market_install_parent_skill_mcp_and_subagent(tmp_path):
    pytest.importorskip("mcp")
    package = write_plugin(tmp_path / "market/plugins/review")
    shutil.copy(Path(__file__).with_name("mcp_fixture.py"), package / "server.py")
    (package / "mcp.json").write_text(
        json.dumps(
            {
                "mcpServers": {
                    "fixture": {
                        "command": sys.executable,
                        "args": ["${PLUGIN_ROOT}/server.py"],
                        "allow_tools": ["echo"],
                    }
                }
            }
        )
    )
    manifest = package / "plugin.json"
    manifest.write_text(
        json.dumps(
            json.loads(manifest.read_text())
            | {
                "extensions": {
                    "vera": {
                        "subagents": {
                            "reviewer": {
                                "description": "Review",
                                "instructions": "Independent plugin role.",
                                "skills": ["review"],
                                "tools": ["mcp:fixture/echo"],
                            }
                        }
                    }
                }
            }
        )
    )
    write_market(tmp_path / "market", [{"name": "review-kit", "source": "./plugins/review"}])
    module = "minisweagent.run.utilities.mini_extra"
    PluginManager(tmp_path / "user-config/plugins").add_marketplace(str(tmp_path / "market"))
    assert "review-kit@team-market" in run_cli(tmp_path, module, "plugins", "marketplace", "search", "review").stdout
    run_cli(tmp_path, module, "plugins", "install", "review-kit@team-market", "--enable")
    requests = []
    actions = iter(
        [
            ("skills_list", {}),
            ("skill_view", {"name": "review-kit-review"}),
            ("mcp_review-kit-fixture_echo", {"text": "parent echo"}),
            ("subagent_run", {"role": "review-kit-reviewer", "task": "child only task"}),
            ("skill_view", {"name": "review-kit-review"}),
            ("mcp_review-kit-fixture_echo", {"text": "child echo"}),
            ("subagent_finish", {"summary": "plugin child completed"}),
            FINISH_CALL,
        ]
    )

    class ModelHandler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def do_POST(self):
            payload = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            requests.append(payload)
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(_model_response([next(actions)], False)).encode())

    with ThreadingHTTPServer(("127.0.0.1", 0), ModelHandler) as server:
        thread = Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            run_cli(
                tmp_path,
                "minisweagent",
                "-t",
                "Plugin parent task",
                "-m",
                "fixture",
                "--model-class",
                "tests.run.test_web_tools.LocalFixtureModel",
                "-y",
                "--exit-immediately",
                "--storage",
                str(tmp_path / "runs.sqlite3"),
                "-o",
                str(tmp_path / "run.json"),
                MSWEA_TEST_MODEL_URL=f"http://127.0.0.1:{server.server_port}",
            )
        finally:
            server.shutdown()
            thread.join(timeout=5)
    trajectory = json.loads((tmp_path / "run.json").read_text())
    assert trajectory["info"]["exit_status"] == "Submitted"
    assert "review-kit" in trajectory["info"]["plugins"]
    assert len(requests) == 8
    assert "Plugin workflow body." in json.dumps(requests[2]["messages"])
    assert "parent echo" in json.dumps(requests[3]["messages"])
    assert "plugin child completed" in json.dumps(requests[-1]["messages"])
    child = requests[4]
    assert "child only task" in json.dumps(child["messages"])
    assert "Plugin parent task" not in json.dumps(child["messages"])
    assert {tool["function"]["name"] for tool in child["tools"]} == {
        "skills_list",
        "skill_view",
        "mcp_review-kit-fixture_echo",
        "subagent_finish",
    }
