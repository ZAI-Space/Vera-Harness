"""Exercise source rewriting, selection and recovery with real Git/CLI processes.

Uses the repository's existing deterministic model, not mocks or paid model calls.
Each optimizer executes the normal Vera Agent Loop and real Bash file operations.
"""

import json
import os
import shlex
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest

from vera.evolution.config import EvolutionConfig, EvolutionError
from vera.evolution.engine import Experiment
from vera.evolution.process import _process_stamp, experiment_lock, read_json, run_process, write_json
from vera.evolution.repository import checkout, commit_candidate, create_archive, git
from vera.evolution.runtime import select_runtime
from vera.plugins.source import filesystem_path

CLI = "vera.run.utilities.evolution"


@pytest.fixture
def source_repo(tmp_path):
    """Clone a committed real runtime; no fixture replaces an agent or model method."""
    source = tmp_path / "Vera source"
    subprocess.run(
        ["git", "clone", "--no-local", str(Path(__file__).resolve().parents[2]), str(source)],
        check=True,
        capture_output=True,
    )
    git(source, "config", "user.name", "Evolution tests")
    git(source, "config", "user.email", "tests@localhost")
    (source / "src/vera/evolution_example.py").write_bytes(b"VALUE = 0\r\n")
    with (source / ".gitattributes").open("a", encoding="utf-8") as stream:
        stream.write("\nsrc/vera/evolution_example.py -text\n")
    git(source, "add", "src/vera/evolution_example.py", ".gitattributes")
    git(source, "commit", "-m", "test(evolution): create baseline problem")
    return source


def test_archive_preserves_binary_assets_in_deep_workspaces(source_repo, tmp_path):
    """A clean source stays clean and binary assets survive real Git checkouts."""
    # Keep archive metadata short enough for Git while tracked files exceed MAX_PATH.
    root = tmp_path / ("long-path-" * max(1, (160 - len(str(tmp_path))) // 10))
    root.mkdir()
    baseline = create_archive(source_repo, root)
    workspace = checkout(root, "generation-0001-improvement", baseline)
    asset = Path("desktop/src/renderer/src/assets/splash/vera-logo.png")
    source_file = Path("desktop/src/renderer/src/components/settings/providers/upstream-models-loader.test.ts")
    assert len(str(workspace / source_file)) > 260
    assert filesystem_path(workspace / source_file).read_bytes() == (source_repo / source_file).read_bytes()
    assert (workspace / asset).read_bytes() == (source_repo / asset).read_bytes()
    assert not git(workspace, "status", "--porcelain").strip()
    assert not git(source_repo, "status", "--porcelain").strip()


def _config(*commands, **changes):
    outputs = [
        {"role": "assistant", "content": "Improve the source", "extra": {"actions": [{"command": command}]}}
        for command in (*commands, "echo COMPLETE_TASK_AND_SUBMIT_FINAL_OUTPUT")
    ]
    verifier = (
        "from pathlib import Path;import sys;from vera.evolution_example import VALUE;"
        "assert not Path('verifier-isolation-marker').exists();Path('verifier-isolation-marker').touch();"
    )
    value = {
        "objective": "Improve the implementation and preserve existing behavior.",
        "sandbox": "local",
        "max_iterations": 4,
        "patience": 4,
        "optimizer_timeout": 40,
        "optimizer": {
            "model": {"model_class": "deterministic", "model_name": "fixture", "outputs": outputs, "cost_per_call": 0},
            "agent": {"agent_class": "default", "step_limit": 8},
        },
        "checks": [["{python}", "-m", "compileall", "-q", "src/vera"]],
        "tasks": [
            {"id": "existing", "split": "train", "command": ["{python}", "-c", verifier + "sys.exit(VALUE < 0)"]},
            {
                "id": "improvement",
                "split": "validation",
                "command": ["{python}", "-c", verifier + "sys.exit(VALUE < 1)"],
            },
            {
                "id": "secret_holdout",
                "split": "holdout",
                "command": ["{python}", "-c", verifier + "sys.exit(VALUE != 1)"],
            },
        ],
    }
    return EvolutionConfig.model_validate(value | changes)


def _cli(root, *arguments, check=True):
    return subprocess.run(
        [sys.executable, "-m", CLI, *arguments, str(root)],
        env=os.environ | {"PYTHONUTF8": "1", "VERA_SILENT_STARTUP": "1"},
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=check,
        timeout=120,
    )


def test_closed_loop_executes_evolved_optimizer_and_rejects_regression(source_repo, tmp_path):
    baseline = git(source_repo, "rev-parse", "HEAD")
    config = _config(
        "if grep -q 'VALUE = 0' src/vera/evolution_example.py; then printf 'VALUE = 1\\n' > src/vera/evolution_example.py; else printf 'VALUE = -1\\n' > src/vera/evolution_example.py; fi",
        "printf '\\n# Candidate import path: %s\\n' \"$PYTHONPATH\" >> src/vera/evolution_example.py",
        "printf '\\nprint(\"EVOLVED_OPTIMIZER_ACTIVE\")\\n' >> src/vera/run/cli.py",
        repeats=2,
    )
    experiment = Experiment.create(tmp_path / "experiment space", source_repo, config)
    state = experiment.run(iterations=2)
    original, accepted, rejected = state["versions"]
    assert state["best"] == accepted["id"]
    assert accepted["status"] == "accepted" and rejected["status"] == "rejected"
    assert "Regression" in rejected["reason"]
    assert rejected["optimizer"] == accepted["id"] == rejected["base"]
    assert rejected["base_sha"] == accepted["sha"] != original["sha"]
    assert str(Path(accepted["workspace"]) / "src") in (
        Path(accepted["workspace"]) / "src/vera/evolution_example.py"
    ).read_text(encoding="utf-8")
    assert "EVOLVED_OPTIMIZER_ACTIVE" in (experiment.root / "artifacts" / rejected["id"] / "optimizer.log").read_text(
        encoding="utf-8"
    )
    assert original["results"]["improvement"]["score"] == 0
    assert accepted["results"]["improvement"]["score"] == 1
    assert len(accepted["results"]["improvement"]["trials"]) == 2
    assert "secret_holdout" not in (experiment.root / "artifacts" / accepted["id"] / "request.json").read_text(
        encoding="utf-8"
    )
    assert "secret_holdout" not in accepted["results"]
    assert state["spent"] == 0
    assert json.loads(_cli(experiment.root, "status").stdout)["best"] == accepted["id"]
    assert experiment.holdout()["secret_holdout"]["score"] == 1
    assert Experiment(experiment.root).state["best"] == accepted["id"]
    patch = tmp_path / "accepted.patch"
    subprocess.run(
        [sys.executable, "-m", CLI, "export", str(experiment.root), str(patch)],
        check=True,
        capture_output=True,
        timeout=15,
    )
    assert "evolution_example.py" in patch.read_text(encoding="utf-8")
    git(source_repo, "apply", "--check", str(patch))
    experiment.rollback("baseline")
    assert Experiment(experiment.root).state["best"] == "baseline"
    assert git(source_repo, "rev-parse", "HEAD") == baseline
    assert not git(source_repo, "status", "--porcelain").strip()
    assert (source_repo / "src/vera/evolution_example.py").read_text(encoding="utf-8") == "VALUE = 0\n"


def test_protected_edits_and_unchanged_candidates_never_promote(source_repo, tmp_path):
    protected = Experiment.create(
        tmp_path / "protected",
        source_repo,
        _config("printf 'changed\\n' > pyproject.toml", editable=["pyproject.toml", "src/vera/"]),
    )
    state = protected.run(iterations=1)
    assert state["best"] == "baseline"
    assert "protected paths" in state["versions"][-1]["reason"]
    unchanged = Experiment.create(tmp_path / "unchanged", source_repo, _config("printf unchanged"))
    assert unchanged.run(iterations=1)["best"] == "baseline"
    assert "no source changes" in unchanged.state["versions"][-1]["reason"]


def test_resume_archives_unknown_generation_and_keeps_reserved_cost(source_repo, tmp_path):
    experiment = Experiment.create(
        tmp_path / "resume",
        source_repo,
        _config("printf 'VALUE = 1\\n' > src/vera/evolution_example.py"),
    )
    experiment.run(iterations=1)
    experiment.state["spent"] = 0.5
    experiment.state["versions"].append(
        {
            "id": "generation-0002",
            "status": "generating",
            "workspace": "interrupted-workspace",
            "base": experiment.state["best"],
            "optimizer": experiment.state["best"],
        }
    )
    write_json(experiment.root / "state.json", experiment.state)
    experiment.cancel_path.touch()
    with pytest.raises(EvolutionError, match="Cancellation"):
        Experiment(experiment.root).run(iterations=1)
    resumed = Experiment(experiment.root).run(iterations=1, resume=True)
    assert resumed["spent"] == 0.5
    assert resumed["versions"][2]["status"] == "interrupted"
    assert resumed["versions"][3]["base"] == "generation-0001"
    assert resumed["versions"][3]["status"] == "failed"
    assert "no source changes" in resumed["versions"][3]["reason"]


def test_budget_and_controller_lock_block_before_optimizer(source_repo, tmp_path):
    experiment = Experiment.create(tmp_path / "budget", source_repo, _config("printf never", cost_limit=0.1))
    with experiment_lock(experiment.root):
        result = _cli(experiment.root, "run", check=False)
        assert result.returncode != 0 and "Another evolution controller" in result.stderr
    with pytest.raises(EvolutionError, match="budget"):
        experiment.run(iterations=1)
    assert experiment.state["spent"] == 0
    assert experiment.state["best"] == "baseline"
    assert not (experiment.root / "artifacts/generation-0001/optimizer.log").exists()


def test_cli_cancellation_reaps_child_and_requires_explicit_resume(source_repo, tmp_path):
    experiment = Experiment.create(
        tmp_path / "cancel",
        source_repo,
        _config("printf started > optimizer-started; sleep 60; printf unexpected > optimizer-finished"),
    )
    log_path = experiment.root / "artifacts/generation-0001/optimizer.log"
    with (tmp_path / "controller.log").open("wb") as log:
        process = subprocess.Popen(
            [sys.executable, "-m", CLI, "run", str(experiment.root), "--iterations", "1"],
            env=os.environ | {"PYTHONUTF8": "1"},
            stdout=log,
            stderr=subprocess.STDOUT,
        )
        try:
            deadline = time.monotonic() + 40
            while not log_path.exists():
                assert process.poll() is None
                assert time.monotonic() < deadline
                time.sleep(0.05)
            while True:
                version = Experiment(experiment.root).state["versions"][-1]
                if (Path(version["workspace"]) / "optimizer-started").exists():
                    break
                assert process.poll() is None
                assert time.monotonic() < deadline
                time.sleep(0.05)
            _cli(experiment.root, "cancel")
            assert process.wait(timeout=20) != 0
        finally:
            if process.poll() is None:
                process.kill()
                process.wait(timeout=10)
    state = Experiment(experiment.root).state
    assert state["status"] == "cancelled"
    assert state["versions"][-1]["status"] == "interrupted"
    assert state["spent"] == experiment.config.optimizer_cost_limit
    assert not (Path(state["versions"][-1]["workspace"]) / "optimizer-finished").exists()
    assert _cli(experiment.root, "run", check=False).returncode != 0


@pytest.mark.skipif(os.name != "nt", reason="Windows MAX_PATH contracts")
def test_atomic_manifest_keeps_temporary_paths_within_windows_limits(tmp_path):
    """A valid destination must not fail because a temporary name repeats its basename."""
    directory = tmp_path
    while len(str(directory)) < 180:
        directory /= "manifest-directory"
    directory.mkdir(parents=True)
    path = directory / f"controller-state-{'s' * 30}.json"
    assert len(str(path)) < 260 < len(str(path)) + 42
    path.write_text('{"status":"old"}', encoding="utf-8")
    write_json(path, {"status": "published"})
    assert read_json(path) == {"status": "published"}
    assert not list(directory.glob("*.pending"))


@pytest.mark.skipif(os.name != "nt", reason="Windows exclusive file sharing contracts")
@pytest.mark.parametrize("is_transient", [True, False])
def test_state_reader_handles_real_windows_sharing_errors(tmp_path, is_transient):
    """Wait for short sharing conflicts; preserve persistent and JSON errors."""
    import ctypes
    from ctypes import wintypes

    path = tmp_path / "state.json"
    write_json(path, {"status": "running"})
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.CreateFileW.argtypes = [
        wintypes.LPCWSTR,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.LPVOID,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.HANDLE,
    ]
    kernel.CreateFileW.restype = wintypes.HANDLE
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    handle = kernel.CreateFileW(str(path), 0x80000000, 0, None, 3, 0x80, None)
    assert handle != wintypes.HANDLE(-1).value, ctypes.get_last_error()
    release = threading.Timer(0.05, kernel.CloseHandle, args=(handle,))
    try:
        if is_transient:
            release.start()
            assert read_json(path) == {"status": "running"}
        else:
            with pytest.raises(PermissionError):
                read_json(path)
    finally:
        if is_transient:
            release.join()
        else:
            kernel.CloseHandle(handle)
    path.write_text("invalid JSON", encoding="utf-8")
    with pytest.raises(json.JSONDecodeError):
        read_json(path)


def test_process_lease_failure_reaps_started_child(tmp_path):
    """An unpublishable process lease must not leave the worker running."""
    marker = tmp_path / "unexpected-completion"
    log = tmp_path / "worker.log"
    log.with_suffix(".process.json").mkdir()
    with pytest.raises(OSError):
        run_process(
            [
                sys.executable,
                "-c",
                "import time;from pathlib import Path;time.sleep(1);Path('unexpected-completion').touch()",
            ],
            cwd=tmp_path,
            env=os.environ.copy(),
            log=log,
            timeout=10,
            cancel=tmp_path / "cancel.request",
        )
    time.sleep(1.5)
    assert not marker.exists()


def test_controller_crash_reaps_previous_process_without_replaying(source_repo, tmp_path):
    experiment = Experiment.create(
        tmp_path / "crash",
        source_repo,
        _config("printf started > optimizer-started; sleep 60; printf unexpected > optimizer-finished"),
    )
    with (tmp_path / "controller-crash.log").open("wb") as output:
        process = subprocess.Popen(
            [sys.executable, "-m", CLI, "run", str(experiment.root), "--iterations", "1"],
            env=os.environ | {"PYTHONUTF8": "1"},
            stdout=output,
            stderr=subprocess.STDOUT,
        )
        try:
            deadline = time.monotonic() + 40
            while True:
                current = Experiment(experiment.root).state
                if (
                    len(current["versions"]) > 1
                    and (Path(current["versions"][-1]["workspace"]) / "optimizer-started").exists()
                ):
                    break
                assert process.poll() is None
                assert time.monotonic() < deadline
                time.sleep(0.05)
            lease_path = experiment.root / "artifacts/generation-0001/optimizer.process.json"
            lease = json.loads(lease_path.read_text(encoding="utf-8"))
            assert _process_stamp(lease["pid"]) == lease["stamp"]
            process.kill()
            process.wait(timeout=10)
            state = Experiment(experiment.root).run(iterations=0, resume=True)
            assert state["versions"][-1]["status"] == "interrupted"
            assert state["spent"] == experiment.config.optimizer_cost_limit
            deadline = time.monotonic() + 10
            while _process_stamp(lease["pid"]) == lease["stamp"]:
                assert time.monotonic() < deadline
                time.sleep(0.05)
            assert json.loads(lease_path.read_text(encoding="utf-8"))["status"] == "interrupted"
            assert not (Path(current["versions"][-1]["workspace"]) / "optimizer-finished").exists()
        finally:
            if process.poll() is None:
                process.kill()
                process.wait(timeout=10)


def test_timeout_missing_scores_and_noop_gains_keep_fixed_denominator(source_repo, tmp_path):
    config = _config("printf 'VALUE = 1\\n' > src/vera/evolution_example.py")
    config.tasks.append(
        type(config.tasks[0])(
            id="timeout",
            split="validation",
            timeout=1,
            command=["{python}", "-c", "import time;time.sleep(30)"],
        )
    )
    config.tasks.append(
        type(config.tasks[0])(
            id="missing",
            split="validation",
            scoring="json",
            command=["{python}", "-c", "pass"],
        )
    )
    experiment = Experiment.create(tmp_path / "denominator", source_repo, config)
    state = experiment.run(iterations=1)
    candidate = state["versions"][-1]
    assert candidate["status"] == "accepted"
    assert candidate["validation_gain"] == pytest.approx(1 / 3)
    assert candidate["results"]["timeout"]["score"] == candidate["results"]["missing"]["score"] == 0
    assert candidate["results"]["timeout"]["trials"][0]["status"] == "timeout"


def test_manifest_validation_and_dirty_source_fail_closed(source_repo, tmp_path):
    config = _config("printf never")
    (source_repo / "dirty.py").touch()
    with pytest.raises(EvolutionError, match="Commit the source baseline"):
        Experiment.create(tmp_path / "dirty experiment", source_repo, config)
    with pytest.raises(ValueError, match="unique"):
        EvolutionConfig.model_validate(config.model_dump() | {"tasks": [config.tasks[0], config.tasks[0]]})
    with pytest.raises(ValueError, match="credentials"):
        EvolutionConfig.model_validate(config.model_dump() | {"optimizer": {"model": {"api_key": "do-not-save"}}})
    with pytest.raises(ValueError, match="editable"):
        EvolutionConfig.model_validate(config.model_dump() | {"editable": ["../"]})


@pytest.mark.parametrize("backend", ["docker", "bubblewrap"])
def test_complete_optimizer_process_is_isolated(source_repo, tmp_path, backend):
    canary = tmp_path / "controller-owned-canary"
    canary.write_text("protected controller data", encoding="utf-8")
    config = _config(
        "test ! -w /optimizer/src/vera/run/cli.py && test ! -e /artifacts/../state.json && printf 'VALUE = 1\\n' > src/vera/evolution_example.py && python -c 'from vera.evolution_example import VALUE; assert VALUE == 1' || printf 'VALUE = 0\\n' > src/vera/evolution_example.py",
        f"ln -s {shlex.quote(str(canary))} /artifacts/check-0.log; ln -s {shlex.quote(str(canary))} /artifacts/optimizer.process.pending; printf '{{}}' > /artifacts/verifier.process.json",
        sandbox=backend,
    )
    try:
        select_runtime(config)
    except EvolutionError:
        pytest.skip(f"{backend} optimizer runtime is unavailable")
    experiment = Experiment.create(tmp_path / backend, source_repo, config)
    state = experiment.run(iterations=1)
    assert state["versions"][-1]["status"] == "accepted", json.dumps(state["versions"][-1], indent=2)
    assert state["runtime"]["mode"] == backend
    assert state["best"] == "generation-0001"
    assert canary.read_text(encoding="utf-8") == "protected controller data"
    if os.name != "nt":
        assert (experiment.root / "artifacts/generation-0001/worker/check-0.log").is_symlink()
    assert Experiment(experiment.root).run(iterations=0)["best"] == state["best"]
    if backend == "docker":
        assert not subprocess.check_output(
            ["docker", "ps", "-aq", "--filter", f"name=^/{state['versions'][-1]['container']}$"],
            text=True,
        ).strip()


def test_verifier_changes_and_equal_scores_cannot_promote(source_repo, tmp_path):
    verifier = tmp_path / "trusted-verifier.py"
    verifier.write_text("raise SystemExit(0)\n", encoding="utf-8")
    config = _config("printf 'VALUE = 0 # changed implementation\\n' > src/vera/evolution_example.py")
    config.tasks[0].command = ["{python}", str(verifier)]
    experiment = Experiment.create(tmp_path / "verifier", source_repo, config)
    state = experiment.run(iterations=1)
    assert state["best"] == "baseline"
    assert state["versions"][-1]["status"] == "rejected"
    assert state["versions"][-1]["validation_gain"] == 0
    verifier.write_text("raise SystemExit(1)\n", encoding="utf-8")
    with pytest.raises(EvolutionError, match="verifier files changed"):
        Experiment(experiment.root).run(iterations=1)


def test_upstream_auto_harness_runner_adapter(source_repo, tmp_path):
    checkout = os.getenv("VERA_AUTO_HARNESS_CHECKOUT")
    if not checkout:
        pytest.skip("Set VERA_AUTO_HARNESS_CHECKOUT to the pinned upstream repository")
    from vera.evolution import auto_harness

    factory = tmp_path / "factory.py"
    factory.write_text(
        """import ast
def create(upstream, candidate, split):
    class CandidateRunner(upstream.BenchmarkRunner):
        def run(self, task_ids=None):
            if split == 'drop':
                return {}
            value = ast.literal_eval((candidate / 'src/vera/evolution_example.py').read_text().split('=')[1].strip())
            return {task: float(value == 0) for task in task_ids}
    return CandidateRunner()
""",
        encoding="utf-8",
    )
    for split, expected in [("train", 1), ("drop", 0)]:
        result = tmp_path / f"{split}.json"
        subprocess.run(
            [
                sys.executable,
                str(Path(auto_harness.__file__)),
                "--checkout",
                checkout,
                "--factory",
                f"{factory}:create",
                "--candidate",
                str(source_repo),
                "--split",
                split,
                "--task-id",
                "fixed-task",
                "--result",
                str(result),
                "--cost-bound",
                "0.02",
            ],
            check=True,
            capture_output=True,
            timeout=30,
        )
        assert json.loads(result.read_text(encoding="utf-8")) == {
            "score": expected,
            "cost": 0.02,
            "cost_is_reserved_bound": True,
        }


def test_invalid_verifier_and_cost_overrun_stop_before_source_generation(source_repo, tmp_path):
    for identifier, result, message in [
        ("bad-score", {"score": 2, "cost": 0}, "invalid score"),
        ("bad-cost", {"score": 1, "cost": 1}, "exceeded its reserved bound"),
    ]:
        config = _config("printf never")
        config.tasks[0].scoring = "json"
        config.tasks[0].max_cost = 0.1
        config.tasks[0].command = [
            "{python}",
            "-c",
            "import json,sys;from pathlib import Path;Path(sys.argv[1]).write_text(json.dumps(" + repr(result) + "))",
            "{result}",
        ]
        experiment = Experiment.create(tmp_path / identifier, source_repo, config)
        with pytest.raises(EvolutionError, match=message):
            experiment.run(iterations=1)
        assert len(experiment.state["versions"]) == 1
        assert experiment.state["best"] == "baseline"
        assert experiment.state["spent"] == (0.1 if identifier == "bad-score" else 1)


def test_retargeted_git_metadata_cannot_mutate_the_source_repository(source_repo, tmp_path):
    config = _config("printf never")
    experiment = Experiment.create(tmp_path / "git-boundary", source_repo, config)
    workspace = checkout(experiment.root, "retargeted", experiment.state["baseline"])
    (workspace / "src/vera/evolution_example.py").write_text("VALUE = 1\n", encoding="utf-8")
    metadata = workspace / ".git"
    metadata.chmod(0o600)
    # Windows Git marks this file hidden; update in place rather than recreate it.
    with metadata.open("r+b") as stream:
        stream.write(f"gitdir: {source_repo / '.git'}\n".encode())
        stream.truncate()
    with pytest.raises(EvolutionError, match="experiment archive"):
        commit_candidate(workspace, experiment.state["baseline"], config)
    assert git(source_repo, "rev-parse", "HEAD").strip() == experiment.state["baseline"]
    assert not git(source_repo, "status", "--porcelain").strip()
