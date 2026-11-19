"""Run scheduled work through real subprocesses, Bash, HTTP model protocols and saved sandboxes."""

import json
import time

import pytest

from minisweagent.environments.sandbox import SandboxConfig, _docker
from minisweagent.environments.sandbox_profiles import SandboxProfiles
from minisweagent.runtime import open_agent_runtime
from minisweagent.scheduler.engine import Scheduler
from minisweagent.scheduler.store import JobStore
from minisweagent.storage import RunStore
from tests.run.test_scheduler import BASE, job_definition
from tests.run.test_skill_tools import write_skill
from tests.run.test_terminal_runtime import terminal_model as terminal_model


def test_due_task_executes_in_fresh_process_with_durable_result_and_skill_context(tmp_path):
    store = JobStore(tmp_path / "scheduler")
    write_skill(tmp_path / ".agents/skills", "review", "PRIVATE SCHEDULED SKILL")
    definition = job_definition(tmp_path, schedule="1s", skills=["review"])
    job = store.create(definition, now=BASE)
    with Scheduler(store.directory).owned() as scheduler:
        execution = scheduler.tick(now=BASE + 1)[0]
        scheduler.wait()
        assert scheduler.tick(now=BASE + 100) == []
    receipt = store.history(job["id"])[0]
    assert receipt["status"] == "completed", receipt
    assert receipt["result"]["summary"] == "scheduled-ok\n"
    trace = RunStore(store.directory / "runs.sqlite3").get_run(execution)
    assert trace["status"] == "completed" and trace["cost"] == 0
    trajectory = json.loads((store.directory / "artifacts" / execution / "trajectory.json").read_text(encoding="utf-8"))
    assert "PRIVATE SCHEDULED SKILL" in json.dumps(trajectory["messages"])
    assert len(store.history()) == 1 and (store.directory / "artifacts" / execution / "process.process.json").exists()


def test_native_tool_finish_model_override_and_no_scheduler_tool_in_worker(tmp_path, terminal_model):
    store = JobStore(tmp_path / "jobs")
    definition = job_definition(tmp_path, schedule="1s")
    definition["config"]["model"] = {
        "model_class": "tests.run.test_terminal_runtime.TerminalFixtureModel",
        "model_name": "scheduled-model",
        "api_url": terminal_model["url"],
    }
    definition["config"]["scheduler"] = {"enabled": True, "directory": str(tmp_path / "other-jobs")}
    terminal_model["actions"]["scheduled-model"] = [("schedule_finish", {"summary": "native scheduled result"})]
    store.create(definition, now=BASE)
    with Scheduler(store.directory).owned() as scheduler:
        scheduler.tick(now=BASE + 1)
        scheduler.wait()
    assert store.history()[0]["result"]["summary"] == "native scheduled result"
    assert len(terminal_model["requests"]) == 1
    assert "cronjob_manage" not in {row["function"]["name"] for row in terminal_model["requests"][0]["tools"]}
    assert not (tmp_path / "other-jobs").exists()


def test_one_missing_project_does_not_block_other_due_jobs(tmp_path):
    store = JobStore(tmp_path / "jobs")
    missing = tmp_path / "deleted-project"
    missing.mkdir()
    bad = store.create(job_definition(missing, schedule="1s"), now=BASE)
    good = store.create(job_definition(tmp_path, schedule="1s"), now=BASE)
    missing.rmdir()
    with Scheduler(store.directory).owned() as scheduler:
        assert len(scheduler.tick(now=BASE + 1)) == 2
        scheduler.wait()
    assert store.history(bad["id"])[0]["status"] == "failed"
    assert store.history(good["id"])[0]["status"] == "completed"


def test_running_cancellation_and_timeout_reap_background_descendants(tmp_path):
    store = JobStore(tmp_path / "jobs")
    value = job_definition(tmp_path, schedule="1s", timeout=2)
    value["config"]["model"]["outputs"][0]["extra"]["actions"][0]["command"] = (
        "printf started > started.txt; (sleep 8; touch leaked.txt) & sleep 30"
    )
    job = store.create(value, now=BASE)
    with Scheduler(store.directory).owned() as scheduler:
        execution = scheduler.tick(now=BASE + 1)[0]
        deadline = time.monotonic() + 12
        while not (tmp_path / "started.txt").exists() and time.monotonic() < deadline:
            time.sleep(0.05)
        assert (tmp_path / "started.txt").exists()
        store.cancel(execution)
        scheduler.wait()
    assert store.history(job["id"])[0]["status"] == "cancelled"
    assert not (tmp_path / "leaked.txt").exists()
    (tmp_path / "started.txt").unlink()
    another = store.create(value, now=BASE)
    with Scheduler(store.directory).owned() as scheduler:
        scheduler.tick(now=BASE + 1)
        scheduler.wait()
    assert store.history(another["id"])[0]["status"] == "timeout"
    time.sleep(2)
    assert not (tmp_path / "leaked.txt").exists()


def test_optional_cron_tool_is_project_scoped_and_confirm_mode_cannot_escalate(tmp_path):
    from tests.run.test_terminal_runtime import runtime_profile

    config = runtime_profile(tmp_path)
    config["scheduler"] = {"enabled": True, "directory": str(tmp_path / "jobs")}
    with open_agent_runtime(config) as runtime:
        assert '"scheduler"' in runtime.policy
        registry = runtime.agent.tool_registry
        created = registry.execute(
            {
                "tool": "cronjob_manage",
                "arguments": {
                    "action": "create",
                    "name": "Daily review",
                    "prompt": "Review project",
                    "schedule": "every 1d",
                },
            }
        )
        assert created["returncode"] == 0
        key = json.loads(created["output"])["result"]["id"]
        assert (
            registry.execute({"tool": "cronjob_manage", "arguments": {"action": "pause", "job_id": key}})["returncode"]
            == 0
        )
    config["agent"]["mode"] = "confirm"
    with open_agent_runtime(config) as runtime:
        rejected = runtime.agent.tool_registry.execute(
            {
                "tool": "cronjob_manage",
                "arguments": {"action": "create", "prompt": "Do not silently authorize", "schedule": "30m"},
            }
        )
        assert rejected["returncode"] == 1
    assert len(JobStore(tmp_path / "jobs").list()) == 1
    other_project = tmp_path / "other-project"
    other_project.mkdir()
    foreign = JobStore(tmp_path / "jobs").create(job_definition(other_project))
    with open_agent_runtime(config) as runtime:
        registry = runtime.agent.tool_registry
        assert (
            registry.execute({"tool": "cronjob_manage", "arguments": {"action": "run", "job_id": foreign["id"]}})[
                "returncode"
            ]
            == 1
        )
        assert (
            foreign["id"] not in registry.execute({"tool": "cronjob_manage", "arguments": {"action": "list"}})["output"]
        )
    config["scheduler"]["enabled"] = False
    with open_agent_runtime(config) as runtime:
        assert runtime.agent.tool_registry is None
        assert '"scheduler"' not in runtime.policy


@pytest.mark.parametrize(("backend",), [("local",), ("docker",)])  # noqa: PT006 - repository test convention
def test_scheduled_job_uses_shared_subagent_runtime(tmp_path, terminal_model, backend):
    if backend == "docker" and _docker(SandboxConfig()) is None:
        pytest.skip("Local Linux Docker engine/image unavailable")
    store = JobStore(tmp_path / "jobs")
    definition = job_definition(tmp_path, schedule="1s", timeout=45)
    model = {
        "model_class": "tests.run.test_terminal_runtime.TerminalFixtureModel",
        "model_name": "parent",
        "api_url": terminal_model["url"],
    }
    definition["config"].update(
        model=model,
        subagents={
            "roles": {
                "writer": {
                    "description": "Scoped child",
                    "instructions": "Write the requested file",
                    "tools": ["bash"],
                    "model": model | {"model_name": "child"},
                }
            }
        },
    )
    if backend == "docker":
        definition["config"].update(
            sandbox_profile="scheduled-env", sandbox_profiles={"path": str(tmp_path / "profiles.sqlite3")}
        )
        SandboxProfiles.from_config(definition["config"]).save("scheduled-env", {"mode": "docker"})
    terminal_model["actions"]["parent"] = [
        ("subagent_run", {"role": "writer", "task": "Write scheduled child artifact"}),
        ("schedule_finish", {"summary": "scheduled Docker success"}),
    ]
    terminal_model["actions"]["child"] = [
        ("bash", {"command": "printf scheduled-child-ok > child.txt"}),
        ("subagent_finish", {"summary": "child done"}),
    ]
    job = store.create(definition, now=BASE)
    with Scheduler(store.directory).owned() as scheduler:
        scheduler.tick(now=BASE + 1)
        scheduler.wait()
    result = store.history(job["id"])[0]
    assert result["status"] == "completed", result
    assert result["result"]["summary"] == "scheduled Docker success"
    assert (tmp_path / "child.txt").read_text() == "scheduled-child-ok"
    runs = RunStore(store.directory / "runs.sqlite3").list_runs()
    assert len(runs) == 2 and all(row["status"] == "completed" for row in runs)
