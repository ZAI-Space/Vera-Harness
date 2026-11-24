"""Exercise global context and usage persistence with real workers and local stores."""

import time
from datetime import datetime, timedelta, timezone

import pytest

from vera.desktop.events import assistant_message
from vera.desktop.service import DesktopService
from vera.desktop.store import DesktopStore
from vera.desktop.usage import UsageStats, token_usage
from vera.user_context import UserContext


def test_global_rules_refresh_existing_conversation_and_are_literal(tmp_path):
    config = {
        "model": {
            "model_class": "deterministic",
            "model_name": "fixture",
            "cost_per_call": 0,
            "outputs": [
                {
                    "role": "assistant",
                    "content": "done",
                    "extra": {"actions": [{"command": "echo COMPLETE_TASK_AND_SUBMIT_FINAL_OUTPUT; echo verified"}]},
                }
            ],
        },
        "agent": {"system_template": "Use Bash.", "instance_template": "{{task}}", "mode": "yolo", "cost_limit": 1},
    }
    service = DesktopService(tmp_path / "state", config)
    try:
        first = service.invoke(
            "saveUserContextEntry",
            {"entry": {"kind": "rule", "title": "Global", "content": "FIRST_RULE {{ 7 * 7 }}", "enabled": True}},
        )
        service.invoke(
            "saveUserContextEntry",
            {"entry": {"kind": "memory", "title": "Preference", "content": "GLOBAL_FACT", "enabled": True}},
        )
        meta = service.invoke("createSession", {"options": {"cwd": str(tmp_path)}})
        key = meta["sessionId"]
        service.invoke("setSessionSelections", {"sessionId": key, "permissionPolicy": "yolo", "selections": {}})

        def run():
            service.invoke("prompt", {"sessionId": key, "text": "Complete task"})
            deadline = time.monotonic() + 30
            while service.sessions.baseline(key)["transcript"]["agentActive"] and time.monotonic() < deadline:
                time.sleep(0.05)
            assert not service.sessions.baseline(key)["transcript"]["agentActive"]
            return service.sessions.get(key)["runtimeMessages"]

        messages = run()
        assert "FIRST_RULE {{ 7 * 7 }}" in messages[0]["content"]
        assert "GLOBAL_FACT" in messages[0]["content"]
        service.invoke("saveUserContextEntry", {"entry": first | {"content": "SECOND_RULE"}})
        messages = run()
        system = [row for row in messages if row["role"] == "system"]
        assert len(system) == 1 and "SECOND_RULE" in system[0]["content"] and "FIRST_RULE" not in system[0]["content"]
        assert len([row for row in messages if row["role"] == "user"]) >= 2
        other = UserContext(service.user_context.directory)
        assert "SECOND_RULE" in other.render()
        service.invoke("saveUserContextEntry", {"entry": first | {"enabled": False}})
        assert "FIRST_RULE" not in other.render()
        service.invoke("removeUserContextEntry", {"id": first["id"]})
        assert len(other.entries()) == 1
        with pytest.raises(ValueError):
            other.save(first)
    finally:
        service.close()


@pytest.mark.parametrize(
    ("raw", "incoming", "cached", "reported"),
    [
        (
            {"prompt_tokens": 100, "completion_tokens": 10, "prompt_tokens_details": {"cached_tokens": 40}},
            100,
            40,
            True,
        ),
        ({"input_tokens": 100, "output_tokens": 10, "input_tokens_details": {"cached_tokens": 0}}, 100, 0, True),
        (
            {"input_tokens": 30, "output_tokens": 10, "cache_read_input_tokens": 40, "cache_creation_input_tokens": 30},
            100,
            40,
            True,
        ),
        ({"prompt_tokens": 100, "completion_tokens": 10, "prompt_cache_hit_tokens": 40}, 100, 40, True),
        ({"prompt_tokens": 100, "completion_tokens": 10}, 100, 0, False),
        (
            {"prompt_tokens": 100, "completion_tokens": 10, "prompt_tokens_details": {"cached_tokens": None}},
            100,
            0,
            False,
        ),
        (
            {
                "prompt_tokens": 100,
                "completion_tokens": 10,
                "prompt_tokens_details": {"cached_tokens": None},
                "prompt_cache_hit_tokens": 40,
            },
            100,
            40,
            True,
        ),
        ({"input_tokens": 30, "output_tokens": 10, "cache_creation_input_tokens": 70}, 100, 0, False),
    ],
)
def test_usage_formats_preserve_cache_reporting(raw, incoming, cached, reported):
    usage = token_usage(raw)
    assert (usage["input"], usage["cacheRead"], usage["cacheReported"]) == (incoming, cached, reported)
    assert usage["totalTokens"] == incoming + 10


def test_statistics_are_durable_filtered_idempotent_and_do_not_invent_cache(tmp_path):
    usage = UsageStats(DesktopStore(tmp_path))

    def record(identifier, project, model, cache, timestamp=None):
        raw = {"prompt_tokens": 100, "completion_tokens": 10}
        if cache is not None:
            raw["prompt_tokens_details"] = {"cached_tokens": cache}
        message = assistant_message({"content": "private text", "usage": raw}, {"provider": "local", "modelId": model})
        if timestamp is not None:
            message["timestamp"] = timestamp
        usage.record(identifier, message, project)

    record("a", "project-one", "alpha", 40)
    record("a", "project-one", "alpha", 40)
    record("b", "project-two", "beta", None)
    record("c", "project-one", "alpha", 20, int((datetime.now(timezone.utc) - timedelta(days=40)).timestamp() * 1000))
    restored = UsageStats(DesktopStore(tmp_path))
    result = restored.query({"days": 7, "timezone": "Asia/Shanghai"})
    assert len(result["heatmap"]) == 180 and len(result["trend"]) == 7
    assert result["totals"]["requests"] == 2 and result["totals"]["totalTokens"] == 220
    assert result["totals"]["cacheHitRate"] == 0.4 and result["totals"]["cacheResponses"] == 1
    assert restored.query({"model": "local/beta"})["totals"]["cacheHitRate"] is None
    assert restored.query({"project": "project-one", "days": 90})["totals"]["requests"] == 2
    assert restored.query({"project": "missing"})["totals"]["requests"] == 0
    assert b"private text" not in (tmp_path / "desktop.sqlite3").read_bytes()


def test_cache_hit_rate_weights_tokens_and_excludes_unreported_counters(tmp_path):
    usage = UsageStats(DesktopStore(tmp_path))
    for identifier, incoming, cached in (
        ("small", 100, 90),
        ("large", 900, 90),
        ("miss", 1000, 0),
        ("unknown", 9000, None),
    ):
        usage.record(
            identifier,
            assistant_message(
                {
                    "content": "",
                    "usage": {
                        "prompt_tokens": incoming,
                        "completion_tokens": 10,
                        "prompt_tokens_details": {"cached_tokens": cached},
                    },
                },
                {"provider": "local", "modelId": "alpha"},
            ),
            "project",
        )
    totals = usage.query({"days": 7})["totals"]
    assert totals["cacheHitRate"] == 0.09
    assert (totals["cacheRead"], totals["cacheInput"], totals["cacheResponses"]) == (180, 2000, 3)
    assert (totals["input"], totals["requests"]) == (11000, 4)
