"""Exercise the real settings CLI, detached daemon and crash recovery without patching clock or processes."""

import json
import os
import subprocess
import sys
import time

import yaml

from tests.run.test_scheduler import BASE, job_definition
from tests.run.test_skill_tools import run_cli
from vera.evolution.process import _process_stamp
from vera.scheduler.engine import Scheduler, service_status, start_service, stop_service
from vera.scheduler.store import JobStore


def wait_until(predicate, timeout=15):
    """Bound real-process waits and fail with the last state available to the caller."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if value := predicate():
            return value
        time.sleep(0.05)
    raise AssertionError("Scheduled process did not reach the expected state")


def test_cli_create_edit_pause_resume_run_and_result_listing(tmp_path):
    root = tmp_path / "scheduler state"
    definition = tmp_path / "job.yaml"
    value = job_definition(tmp_path)
    definition.write_text(yaml.safe_dump(value), encoding="utf-8")
    prefix = ("cron", "--state", str(root))
    created = json.loads(run_cli(tmp_path, "vera.run.utilities.extra", *prefix, "create", str(definition)).stdout)
    key = created["id"]
    assert json.loads(run_cli(tmp_path, "vera.run.utilities.extra", *prefix, "status").stdout)["running"] is False
    for action, expected in (("pause", "paused"), ("resume", "scheduled")):
        assert (
            json.loads(run_cli(tmp_path, "vera.run.utilities.extra", *prefix, action, key).stdout)["state"] == expected
        )
    value["name"] = "Updated scheduled check"
    definition.write_text(yaml.safe_dump(value), encoding="utf-8")
    assert (
        json.loads(run_cli(tmp_path, "vera.run.utilities.extra", *prefix, "update", key, str(definition)).stdout)[
            "name"
        ]
        == value["name"]
    )
    run_cli(tmp_path, "vera.run.utilities.extra", *prefix, "run", key)
    run_cli(tmp_path, "vera.run.utilities.extra", *prefix, "tick")
    result = json.loads(run_cli(tmp_path, "vera.run.utilities.extra", *prefix, "history", "--job", key).stdout)[0]
    assert result["status"] == "completed" and result["result"]["summary"] == "scheduled-ok\n"
    run_cli(tmp_path, "vera.run.utilities.extra", *prefix, "remove", key)
    assert json.loads(run_cli(tmp_path, "vera.run.utilities.extra", *prefix, "list").stdout) == []


def test_detached_daemon_survives_starting_cli_and_executes_a_due_job(tmp_path):
    store = JobStore(tmp_path / "service")
    key = store.create(job_definition(tmp_path, schedule="2s"))["id"]
    result = run_cli(tmp_path, "vera.run.utilities.extra", "cron", "--state", str(store.directory), "start")
    status = json.loads(result.stdout)
    assert status["running"] and status["pid"] != os.getpid()
    try:
        assert start_service(store.directory)["pid"] == status["pid"]
        records = wait_until(
            lambda: rows if (rows := store.history(key)) and rows[0]["status"] == "completed" else None
        )
        assert records[0]["result"]["summary"] == "scheduled-ok\n"
        assert store.get(key)["state"] == "completed"
        assert service_status(store.directory)["running"]
    finally:
        stop_service(store.directory)
        wait_until(lambda: not service_status(store.directory)["running"])


def test_restart_recovers_known_result_without_rerunning_or_losing_summary(tmp_path):
    from vera.evolution.process import write_json

    store = JobStore(tmp_path / "jobs")
    job = store.create(job_definition(tmp_path, schedule="1s"), now=BASE)
    execution = store.claim_due(1, now=BASE + 1)[0]
    assert store.start(execution)
    output = store.directory / "artifacts" / execution
    output.mkdir(parents=True)
    write_json(output / "result.json", {"status": "completed", "summary": "worker finished before controller exit"})
    with Scheduler(store.directory).owned() as scheduler:
        assert scheduler.tick(now=BASE + 3) == []
    assert store.history(job["id"])[0]["result"]["summary"] == "worker finished before controller exit"
    unknown = store.control(job["id"], "run")["execution_id"]
    assert store.start(unknown)
    corrupt = store.directory / "artifacts" / unknown
    corrupt.mkdir()
    (corrupt / "result.json").write_text("{broken")
    with Scheduler(store.directory).owned():
        assert store.execution(unknown)["status"] == "interrupted"


def test_stopping_daemon_cancels_active_work_and_unknown_pid_file_is_not_running(tmp_path):
    store = JobStore(tmp_path / "service")
    value = job_definition(tmp_path, schedule="1s", timeout=40)
    value["config"]["model"]["outputs"][0]["extra"]["actions"][0]["command"] = "printf started > active.txt; sleep 30"
    job = store.create(value)
    start_service(store.directory)
    try:
        wait_until(lambda: (tmp_path / "active.txt").exists())
        stop_service(store.directory)
        wait_until(lambda: rows if (rows := store.history(job["id"])) and rows[0]["status"] == "cancelled" else None)
        wait_until(lambda: not service_status(store.directory)["running"])
    finally:
        stop_service(store.directory)
    (store.directory / "service.json").write_text(json.dumps({"pid": os.getpid(), "stamp": "wrong-identity"}))
    assert service_status(store.directory)["running"] is False


def test_controller_crash_reaps_recorded_child_and_does_not_replay(tmp_path):
    store = JobStore(tmp_path / "crash-state")
    value = job_definition(tmp_path, schedule="1s", timeout=40)
    value["config"]["model"]["outputs"][0]["extra"]["actions"][0]["command"] = (
        "printf started > crash-started.txt; sleep 30"
    )
    key = store.create(value)["id"]
    environment = os.environ | {"VERA_SILENT_STARTUP": "1"}
    with (tmp_path / "controller.log").open("wb") as log:
        process = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "vera.run.utilities.cron",
                "--state",
                str(store.directory),
                "serve",
                "--interval",
                "0.1",
            ],
            stdout=log,
            stderr=log,
            env=environment,
        )
    try:
        wait_until(lambda: (tmp_path / "crash-started.txt").exists())
        row = store.history(key)[0]
        lease = json.loads((store.directory / "artifacts" / row["id"] / "process.process.json").read_text())
        assert _process_stamp(lease["pid"]) == lease["stamp"]
        process.kill()
        process.wait(timeout=10)
        with Scheduler(store.directory).owned() as recovered:
            assert recovered.tick() == []
        assert store.history(key)[0]["status"] == "interrupted"
        assert _process_stamp(lease["pid"]) != lease["stamp"]
        assert len(store.history(key)) == 1
    finally:
        if process.poll() is None:
            process.kill()
            process.wait(timeout=10)
