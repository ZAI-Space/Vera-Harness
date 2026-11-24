"""Bound catalog metadata reads and recover from malformed optional/worker output."""

import errno
import json
import os
from pathlib import Path
from types import SimpleNamespace

import pytest

from tests.run.test_plugins import write_market, write_plugin
from vera.desktop.store import DesktopStore
from vera.evolution.config import EvolutionError
from vera.evolution.engine import Experiment
from vera.markets.docker import DockerCatalog
from vera.plugins import PluginManager
from vera.plugins.presentation import marketplace_presentations
from vera.plugins.source import PluginError, Source
from vera.tools import ToolError


def fixture_catalog(tmp_path, **changes):
    """Use the shipped snapshot for initialization and a single pinned fixture row."""
    catalog = DockerCatalog(DesktopStore(tmp_path))
    catalog.data = {
        "registry": {"fixture": {"image": "mcp/fixture@sha256:" + "a" * 64, **changes}},
        "recommended": ["fixture"],
        "updatedAt": "2026-11-24",
    }
    return catalog


@pytest.mark.parametrize(
    "variables",
    [
        None,
        {},
        "VALUE",
        [None],
        ["VALUE"],
        [{}],
        [{"name": "VALUE"}],
        [{"name": "VALUE", "value": None}],
        [{"name": "BAD-NAME", "value": "text"}],
        [{"name": "VALUE", "value": {}}],
    ],
)
def test_docker_invalid_environment_reports_configuration_error(tmp_path, variables):
    with pytest.raises(ToolError, match="环境变量格式"):
        fixture_catalog(tmp_path, env=variables).preview("fixture")


def test_docker_environment_keeps_supported_scalar_conversion(tmp_path):
    plan = fixture_catalog(tmp_path, env=[{"name": "PORT", "value": 8080}]).preview("fixture")
    assert "PORT=8080" in plan["config"]["args"]


@pytest.mark.parametrize("metadata", [None, "category", [], 1])
def test_docker_cosmetic_metadata_does_not_hide_catalog(tmp_path, metadata):
    result = fixture_catalog(tmp_path, metadata=metadata).search()
    assert result["entries"][0]["category"] == ""
    assert result["entries"][0]["name"] == "fixture"


@pytest.mark.parametrize(
    "cache",
    [
        [],
        {"registry": {}},
        {"registry": None, "recommended": [], "updatedAt": "date"},
        {"registry": {"bad": None}, "recommended": ["bad"], "updatedAt": "date"},
        {"registry": {}, "recommended": [1], "updatedAt": "date"},
    ],
)
def test_docker_bad_cache_falls_back_to_shipped_snapshot(tmp_path, cache):
    store = DesktopStore(tmp_path)
    store.save("market-cache", "docker", cache)
    catalog = DockerCatalog(store)
    assert catalog.search()["entries"][0]["name"] == "playwright"
    assert "@sha256:" in catalog.preview("playwright")["config"]["args"][-1]


def test_docker_refresh_rejects_invalid_rows_without_replacing_cache(tmp_path, monkeypatch):
    class Reply:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def raise_for_status(self):
            pass

        def iter_content(self, size):
            yield b"registry:\n  fixture: null\n"

    catalog = fixture_catalog(tmp_path)
    previous = catalog.data
    monkeypatch.setattr("vera.markets.docker.requests.get", lambda *args, **kwargs: Reply())
    with pytest.raises(ToolError, match="invalid service entries"):
        catalog.refresh()
    assert catalog.data is previous
    assert catalog.store.get("market-cache", "docker") is None


def test_local_metadata_stops_reading_at_aggregate_limit(tmp_path, monkeypatch):
    paths = [f"manifest-{number:02d}.json" for number in range(32)]
    block = b"m" * (1024 * 1024)
    for name in paths:
        (tmp_path / name).write_bytes(block)
    consumed = []
    original_open = Path.open

    class Reader:
        def __init__(self, stream):
            self.stream = stream

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return self.stream.__exit__(*args)

        def read(self, size=-1):
            content = self.stream.read(size)
            consumed.append(len(content))
            return content

    def tracked_open(path, *args, **kwargs):
        stream = original_open(path, *args, **kwargs)
        return Reader(stream) if path.parent == tmp_path else stream

    monkeypatch.setattr(Path, "open", tracked_open)
    with pytest.raises(PluginError, match="16 MiB"):
        Source(str(tmp_path), tmp_path, None).read_files(paths)
    assert sum(consumed) <= 16 * 1024 * 1024 + 1
    assert len(consumed) == 17


@pytest.mark.parametrize("failure", [PluginError("batch unavailable"), OSError("file unavailable")])
def test_optional_manifest_batch_failure_degrades_presentation(tmp_path, monkeypatch, failure):
    root = write_plugin(tmp_path)

    def failed_read(self, *args, **kwargs):
        raise failure

    monkeypatch.setattr(Source, "read_files", failed_read)
    assert marketplace_presentations(Source(str(root), root, None), ["."], {"plugin.json"}) == {".": {}}


def test_optional_artwork_failure_retains_manifest_description(tmp_path, monkeypatch):
    root = write_plugin(tmp_path)
    manifest = root / "plugin.json"
    content = json.loads(manifest.read_text())
    content["interface"] = {"composerIcon": "logo.png"}
    manifest.write_text(json.dumps(content))
    (root / "logo.png").write_bytes(b"fixture")
    original_read = Source.read_files

    def read_manifest_only(self, paths, **kwargs):
        if "logo.png" in paths:
            raise PluginError("Optional artwork unavailable")
        return original_read(self, paths, **kwargs)

    monkeypatch.setattr(Source, "read_files", read_manifest_only)
    row = marketplace_presentations(Source(str(root), root, None), ["."], {"plugin.json", "logo.png"})["."]
    assert row["description"] == "Review changes."
    assert "icon" not in row


def test_all_remote_marketplace_skips_unused_source_inventory(tmp_path, monkeypatch):
    root = write_market(
        tmp_path / "market", [{"name": "remote-kit", "source": {"source": "github", "repo": "team/plugins"}}]
    )

    def unexpected_inventory(self):
        pytest.fail("An all-remote catalog must not inventory its source tree")

    monkeypatch.setattr(Source, "files", unexpected_inventory)
    row = PluginManager(tmp_path / "store").add_marketplace(str(root))
    assert row["plugins"]["remote-kit"]["source"] == "https://github.com/team/plugins.git"


def test_marketplace_optional_inventory_failure_keeps_registration_and_package_limits(tmp_path):
    root = write_market(
        tmp_path / "market",
        [{"name": "review-kit", "source": "./plugins/review", "description": "Catalog description"}],
    )
    write_plugin(root / "plugins/review")
    with (root / "unrelated.bin").open("wb") as stream:
        stream.truncate(100 * 1024 * 1024 + 1)
    source = Source(str(root), root, None)
    with pytest.raises(PluginError, match="100 MiB"):
        source.files()
    manager = PluginManager(tmp_path / "store")
    row = manager.add_marketplace(str(root))
    assert row["plugins"]["review-kit"]["description"] == "Catalog description"
    assert manager.install_from_marketplace("review-kit", "team-market")["name"] == "review-kit"


@pytest.mark.parametrize(
    "report",
    [
        {"status": "Submitted"},
        {"cost": None, "status": "Submitted"},
        {"cost": "bad", "status": "Submitted"},
        {"cost": -1, "status": "Submitted"},
        {"cost": True, "status": "Submitted"},
        {"cost": "nan", "status": "Submitted"},
        {"cost": 10**400, "status": "Submitted"},
        {"cost": 0},
        {"cost": 0, "status": []},
    ],
)
def test_optimizer_malformed_fields_raise_candidate_error(tmp_path, monkeypatch, report):
    import vera.evolution.engine as engine

    experiment = object.__new__(Experiment)
    experiment.root = tmp_path
    experiment.state = {"id": "fixture", "runtime": {"mode": "local"}, "versions": []}
    experiment.config = SimpleNamespace(
        objective="fixture", editable=["src/vera/"], optimizer={}, optimizer_cost_limit=0.5, optimizer_timeout=1
    )
    experiment.cancel_path = tmp_path / "cancel"
    reservations, settlements = [], []
    experiment._reserve = reservations.append
    experiment._settle = lambda *values: settlements.append(values)
    experiment._environment = lambda source: {}
    monkeypatch.setattr(engine, "checkout", lambda *args: tmp_path)
    monkeypatch.setattr(engine, "optimizer_command", lambda *args, **kwargs: (["fixture"], {}))

    def finish_process(*args, **kwargs):
        result_path = tmp_path / "artifacts/generation/worker/optimizer-result.json"
        result_path.write_text(json.dumps(report), encoding="utf-8")
        return {"returncode": 0, "status": "completed"}

    monkeypatch.setattr(engine, "run_process", finish_process)
    with pytest.raises(EvolutionError, match="invalid cost/status"):
        experiment._optimize({"id": "generation", "workspace": str(tmp_path)}, {"sha": "baseline"}, {"results": {}})
    assert reservations == [0.5] and not settlements


@pytest.mark.parametrize(
    ("platform", "winerror", "error_number", "attempts"),
    [
        ("nt", 32, errno.EACCES, 3),
        ("nt", None, errno.EACCES, 3),
        ("nt", 87, errno.EACCES, 1),
        ("posix", 32, errno.EACCES, 1),
    ],
)
def test_optimizer_result_retries_only_windows_transient_open_failures(
    tmp_path, monkeypatch, platform, winerror, error_number, attempts
):
    import vera.evolution.process as process

    path = tmp_path / "result.json"
    path.write_text('{"cost": 0, "status": "Submitted"}', encoding="utf-8")
    calls, sleeps = [], []
    original_open = os.open

    def flaky_open(*args, **kwargs):
        calls.append(args)
        if len(calls) < 3:
            failure = PermissionError(error_number, "fixture sharing failure")
            failure.winerror = winerror
            raise failure
        return original_open(*args, **kwargs)

    monkeypatch.setattr(process, "os", SimpleNamespace(**(vars(os) | {"name": platform, "open": flaky_open})))
    monkeypatch.setattr(process, "time", SimpleNamespace(sleep=sleeps.append))
    if attempts == 3:
        assert process.read_optimizer_result(path) == {"cost": 0, "status": "Submitted"}
        assert sleeps == [0.01, 0.01]
    else:
        with pytest.raises(PermissionError):
            process.read_optimizer_result(path)
        assert not sleeps
    assert len(calls) == attempts


def test_optimizer_result_persistent_windows_lock_has_bounded_retries(tmp_path, monkeypatch):
    import vera.evolution.process as process

    calls, sleeps = [], []

    def unavailable(path):
        calls.append(path)
        raise PermissionError(errno.EACCES, "fixture persistent lock")

    monkeypatch.setattr(process, "os", SimpleNamespace(name="nt"))
    monkeypatch.setattr(process, "time", SimpleNamespace(sleep=sleeps.append))
    monkeypatch.setattr(process, "_read_optimizer_result_once", unavailable)
    with pytest.raises(PermissionError):
        process.read_optimizer_result(tmp_path / "result.json")
    assert len(calls) == 20 and len(sleeps) == 19
