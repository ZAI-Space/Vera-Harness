"""Keep the distributed examples loadable without network services or credentials."""

from pathlib import Path

from vera.config import get_config_from_spec
from vera.plugins.manifest import load_bundle
from vera.runtime import open_agent_runtime

EXAMPLES = Path(__file__).resolve().parents[2] / "examples"


def test_offline_runtime_example_finishes_without_tools(tmp_path):
    config = get_config_from_spec(str(EXAMPLES / "basic.yaml"))
    config["environment"] = {"cwd": str(tmp_path)}
    with open_agent_runtime(config) as runtime:
        assert runtime.agent.run("Complete the offline demonstration.")["exit_status"] == "Submitted"
        assert runtime.agent.n_calls == 1
    assert not list(tmp_path.iterdir())


def test_bundled_plugin_examples_validate_without_starting_mcp():
    review = load_bundle(EXAMPLES / "plugins/review-kit")
    assert review.manifest.name == "review-kit" and review.skills and review.roles
    github = load_bundle(EXAMPLES / "plugins/github")
    assert github.manifest.name == "github" and github.servers
