"""Validate real schedule calendars, transactional occurrences and cross-process ownership."""

import json
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

import pytest
from pydantic import ValidationError

from vera.scheduler.config import JobSpec, next_occurrence, parse_schedule
from vera.scheduler.engine import Scheduler
from vera.scheduler.store import JobStore
from vera.tools import ToolError

BASE = datetime(2026, 11, 19, tzinfo=timezone.utc).timestamp()


def job_definition(workspace: Path, **changes) -> dict:
    """A real deterministic model runs Bash; no paid API or mocked method is used."""
    return {
        "name": "Project check",
        "prompt": "Perform the scheduled check",
        "schedule": "every 1h",
        "workspace": str(workspace),
        "config": {
            "agent": {"mode": "yolo"},
            "model": {
                "model_class": "deterministic",
                "model_name": "fixture",
                "cost_per_call": 0,
                "outputs": [
                    {
                        "role": "assistant",
                        "content": "Complete",
                        "extra": {
                            "actions": [{"command": "echo COMPLETE_TASK_AND_SUBMIT_FINAL_OUTPUT; echo scheduled-ok"}]
                        },
                    }
                ],
            },
        },
        **changes,
    }


def test_four_schedule_formats_timezone_and_bounded_invalid_inputs():
    assert parse_schedule("30m", "UTC", BASE) == {"kind": "once", "seconds": 1800, "next": BASE + 1800}
    every = parse_schedule("every 2h", "Asia/Shanghai", BASE)
    assert every["kind"] == "interval" and next_occurrence(every, "UTC", BASE + 7200, BASE + 25000) == BASE + 28800
    assert parse_schedule("0 9 * * *", "Asia/Shanghai", BASE)["next"] == BASE + 3600
    assert parse_schedule("2026-11-19T09:00:00", "Asia/Shanghai", BASE)["next"] == BASE + 3600
    assert parse_schedule("2026-11-19T01:00:00Z", "UTC", BASE)["next"] == BASE + 3600
    assert next_occurrence({"kind": "once"}, "UTC", BASE, BASE) is None
    for value, zone in (
        ("0s", "UTC"),
        ("every 0h", "UTC"),
        ("0 0 31 2 *", "UTC"),
        ("0 0 * * * *", "UTC"),
        ("yesterday", "UTC"),
        ("2020-01-01", "UTC"),
        ("30m", "Unknown/Zone"),
        ("2027-03-14T02:30:00", "America/New_York"),
    ):
        with pytest.raises(ToolError):
            parse_schedule(value, zone, BASE)


def test_cron_observes_dst_while_intervals_are_elapsed_time():
    before = datetime(2027, 3, 13, 15, tzinfo=timezone.utc).timestamp()
    schedule = parse_schedule("0 9 * * *", "America/New_York", before)
    assert schedule["next"] == datetime(2027, 3, 14, 13, tzinfo=timezone.utc).timestamp()
    assert (
        next_occurrence(schedule, "America/New_York", schedule["next"], schedule["next"])
        == datetime(2027, 3, 15, 13, tzinfo=timezone.utc).timestamp()
    )


def test_background_policy_limits_and_read_queries_do_not_create_state(tmp_path):
    store = JobStore(tmp_path / "absent")
    assert store.list() == [] and store.history() == [] and not store.directory.exists()
    for override in (
        {"config": {"agent": {"mode": "confirm"}}},
        {"config": {"agent": {"mode": "human"}}},
        {"timezone": "fake"},
        {"cost_limit": 0},
        {"timeout": 0},
    ):
        with pytest.raises(ValidationError):
            JobSpec.model_validate(job_definition(tmp_path, **override))
    with pytest.raises(ToolError, match="workspace"):
        store.create(job_definition(tmp_path / "not-created"))
    assert not store.directory.exists()


def test_sqlite_claim_fence_and_nonoverlap_across_concurrent_callers(tmp_path):
    store = JobStore(tmp_path / "jobs")
    job = store.create(job_definition(tmp_path), now=BASE)
    with ThreadPoolExecutor(max_workers=4) as executor:
        claimed = list(executor.map(lambda _: store.claim_due(1, now=BASE + 3600), range(4)))
    keys = {key for batch in claimed for key in batch}
    assert len(keys) == 1 and len(store.history()) == 1
    key = keys.pop()
    with ThreadPoolExecutor(max_workers=4) as executor:
        assert sum(executor.map(lambda _: store.start(key), range(4))) == 1
    assert store.claim_due(2, now=BASE + 7200) == []
    store.finish(key, "completed", {"summary": "settled"})
    store.finish(key, "failed", {"summary": "stale writer"})
    assert store.history()[0]["result"]["summary"] == "settled"
    assert len(store.claim_due(2, now=BASE + 7200)) == 1
    assert store.get(job["id"])["fired"] == 2


def test_missed_slots_coalesce_or_skip_and_one_shots_expire(tmp_path):
    store = JobStore(tmp_path / "jobs")
    catch_up = store.create(job_definition(tmp_path, schedule="every 10s"), now=BASE)
    skip = store.create(job_definition(tmp_path, schedule="every 10s", catch_up=False), now=BASE)
    once = store.create(job_definition(tmp_path, schedule="10s"), now=BASE)
    assert len(store.claim_due(4, now=BASE + 500)) == 1
    assert store.get(catch_up["id"])["next_run_at"].startswith("2026-11-19T00:08:30")
    assert store.history(skip["id"])[0]["status"] == "skipped"
    assert store.history(once["id"])[0]["status"] == "skipped"
    assert store.get(once["id"])["state"] == "completed"
    assert len(store.history()) == 3


def test_pause_edit_remove_repeat_and_manual_runs_keep_snapshot_history(tmp_path):
    store = JobStore(tmp_path / "jobs")
    definition = job_definition(tmp_path, schedule="every 10s", repeat=1)
    key = store.create(definition, now=BASE)["id"]
    store.control(key, "pause")
    assert store.claim_due(1, now=BASE + 10) == []
    store.control(key, "resume")
    execution = store.claim_due(1, now=BASE + 10)[0]
    snapshot = store.execution(execution)["snapshot"]
    assert store.get(key)["state"] == "completed"
    with pytest.raises(ToolError, match="active"):
        store.control(key, "run")
    store.start(execution)
    store.finish(execution, "failed", {"reason": "failure does not retry side effects"})
    assert store.claim_due(1, now=BASE + 100) == []
    assert store.control(key, "run")["status"] == "queued"
    assert store.get(key)["next_run_at"] is None and store.get(key)["fired"] == 1
    revision = store.get(key)["revision"]
    updated = store.update(key, definition | {"prompt": "new prompt"}, revision=revision, now=BASE + 100)
    assert updated["revision"] == revision + 1 and store.execution(execution)["snapshot"] == snapshot
    with pytest.raises(ToolError, match="refresh"):
        store.update(key, definition, revision=1, now=BASE + 100)
    store.control(key, "remove")
    assert store.list() == [] and len(store.history(key)) == 2
    with pytest.raises(ToolError, match="Unknown"):
        store.get(key)


def test_concurrent_writers_do_not_lose_jobs_or_expose_provider_config(tmp_path):
    store = JobStore(tmp_path / "jobs")
    value = job_definition(tmp_path)
    value["config"]["model"]["model_kwargs"] = {"api_key": "private-fixture-key"}
    with ThreadPoolExecutor(max_workers=4) as executor:
        list(executor.map(lambda _: store.create(value, now=BASE), range(12)))
    assert len(store.list()) == 12 and "private-fixture-key" not in json.dumps(store.list())
    assert "private-fixture-key" in json.dumps(store.definition(store.list()[0]["id"]).model_dump(mode="json"))


def test_single_owner_lock_and_recovery_never_replays_unknown_occurrences(tmp_path):
    store = JobStore(tmp_path / "jobs")
    key = store.create(job_definition(tmp_path, schedule="1s"), now=BASE)["id"]
    execution = store.claim_due(1, now=BASE + 1)[0]
    store.start(execution)
    with Scheduler(store.directory).owned():
        assert store.history(key)[0]["status"] == "interrupted"
        with pytest.raises(ToolError, match="Another scheduler"):
            with Scheduler(store.directory).owned():
                pytest.fail("Two schedulers owned the same store")
    with Scheduler(store.directory).owned() as recovered:
        assert recovered.tick(now=BASE + 10) == []
    assert len(store.history(key)) == 1
