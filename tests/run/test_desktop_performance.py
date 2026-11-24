"""Exercise real local statistics persistence, request cohorts and task observation."""

import time

import pytest

from vera.desktop.events import assistant_message
from vera.desktop.performance import TaskObservation
from vera.desktop.store import DesktopStore
from vera.desktop.usage import UsageStats


def record_usage(usage, identifier, request, timestamp=None):
    message = assistant_message(
        {"content": "", "usage": {"prompt_tokens": 100, "completion_tokens": 10, "prompt_cache_hit_tokens": 40}},
        {"provider": "local", "modelId": "alpha"},
    )
    message.update(requestId=request, timestamp=timestamp or int(time.time() * 1000))
    usage.record(identifier, message, "project")


def test_request_cohorts_are_persistent_and_independent_of_the_date_window(tmp_path):
    usage = UsageStats(DesktopStore(tmp_path))
    usage.begin_request("old-request", "existing-chat", "old-task")
    record_usage(usage, "old-usage", "old-request", int((time.time() - 40 * 86400) * 1000))
    usage.begin_request("next-request", "existing-chat", "next-task")
    usage.begin_request("first-request", "new-chat", "new-task")
    usage.begin_request("child-request", "new-chat", "new-task", delegated=True)
    usage.begin_request("legacy-request", "legacy-chat", "legacy-task", has_history=True)
    for name in ("next", "first", "child", "legacy"):
        record_usage(usage, name + "-usage", name + "-request")
    record_usage(usage, "first-usage", "first-request")
    record_usage(usage, "unknown", None)
    restored = UsageStats(DesktopStore(tmp_path))
    assert restored.query({"days": 7})["totals"]["requests"] == 5
    assert restored.query({"days": 7, "cacheGroup": "first"})["totals"]["requests"] == 1
    result = restored.query({"days": 7, "cacheGroup": "continued"})
    assert result["totals"]["requests"] == 2
    assert result["trend"][-1]["cacheHitRate"] == 0.4
    assert result["trend"][-2]["cacheHitRate"] is None
    with pytest.raises(ValueError, match="首次"):
        restored.query({"cacheGroup": "unsupported"})


def test_task_receipts_exclude_abnormal_response_times_and_keep_retry_outliers_visible(tmp_path):
    usage = UsageStats(DesktopStore(tmp_path))
    now = int(time.time() * 1000)
    for index in range(20):
        usage.performance.record(
            str(index),
            now,
            "project",
            "local",
            "alpha",
            {
                "status": "Submitted",
                "normalResponse": True,
                "firstResponseMs": 200,
                "retries": 10000 if index == 19 else 0,
                "tools": [],
                "errors": {},
            },
        )
    observation = TaskObservation(
        usage,
        "abnormal",
        {"sessionId": "chat", "cwd": "project", "model": {"provider": "local", "modelId": "alpha"}},
        time.monotonic() - 10,
        now,
    )
    observation.observe({"type": "model_request", "id": "attempt"})
    observation.observe({"type": "stream_delta", "update": {"type": "text_delta", "delta": "hello"}})
    observation.observe({"type": "model_failure", "category": "APIConnectionError"})
    observation.observe({"type": "retry", "reason": "model"})
    observation.observe({"type": "tool_start", "toolCallId": "read", "toolName": "project_read"})
    observation.observe(
        {"type": "tool_end", "toolCallId": "read", "toolName": "project_read", "result": {"returncode": 1}}
    )
    observation.finish("Submitted")
    observation.finish("Submitted")
    observation.identifier = "cancelled"
    observation.finish("Cancelled")
    observation.identifier = "failed"
    observation.finish("WorkerFailed")
    result = usage.query({"days": 7})["performance"]
    assert result["tasks"] == 23 and result["completed"] == 21
    assert result["completionRate"] == 21 / 23
    assert result["firstResponseMeanMs"] == 200 and result["firstResponseExcluded"] == 3
    assert result["retryMean"] < result["retryRawMean"] and result["retryExcluded"] == 2
    assert result["tools"][0]["failures"] == 3 and result["tools"][0]["calls"] == 3
    assert result["errors"][0]["count"] == 3
    assert usage.query({"project": "other"})["performance"]["tasks"] == 0
    assert usage.query({"model": "local/other"})["performance"]["firstResponseMeanMs"] is None
    assert b"hello" not in usage.store.path.read_bytes()
