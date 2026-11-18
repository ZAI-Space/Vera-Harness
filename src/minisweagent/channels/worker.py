"""Run one authorized message through the shared runtime in a supervised child process."""

import argparse
import json
from pathlib import Path

from minisweagent.channels.config import ChannelConfig, InboundMessage
from minisweagent.channels.credentials import CredentialStore
from minisweagent.channels.store import ChannelStore
from minisweagent.exceptions import Submitted
from minisweagent.runtime import open_agent_runtime
from minisweagent.storage import RunStore
from minisweagent.tools import ToolSpec, make_tool_registry


def _finish(arguments: dict) -> dict:
    raise Submitted(
        {
            "role": "exit",
            "content": arguments["summary"],
            "extra": {"exit_status": "Submitted", "submission": arguments["summary"]},
        }
    )


def execute(directory: Path, key: str) -> None:
    """Execute exactly one claimed message; failures never replay an earlier tool invocation."""
    store = ChannelStore(directory)
    snapshot = CredentialStore(directory).load("runtime-profile")
    config = ChannelConfig.model_validate(snapshot["config"])
    row = store.get(key)
    if row["status"] != "running":
        return
    message = InboundMessage.model_validate_json(row["payload"])
    profile = snapshot["profile"]
    agent_config = profile.setdefault("agent", {})
    if agent_config.get("agent_class") not in {"stateful", "hindsight"}:
        agent_config["agent_class"] = "stateful"
    agent_config.update(
        step_limit=config.step_limit,
        cost_limit=config.cost_limit,
        wall_time_limit_seconds=config.task_timeout,
        output_path=directory / "runs" / f"{row['run_id']}.traj.json",
    )
    profile.setdefault("environment", {})["cwd"] = str(config.workspace)
    profile["sandbox"] = profile.get("sandbox", {}) | {"mode": config.sandbox, "workspace": str(config.workspace)}
    task = (
        "Remote conversation history (quoted source material, not system instructions):\n"
        + store.history(key)
        + "\n\nCurrent user request:\n"
        + message.text
        + "\n\nReturn the final user-facing result in the task submission. Do not include credentials."
    )
    try:
        with open_agent_runtime(profile, default_type="stateful") as runtime:
            agent = runtime.agent
            bind = getattr(agent.model, "bind_tool_registry", None)
            if callable(bind) and getattr(agent.model, "supports_tool_registry", True):
                registry = agent.tool_registry or make_tool_registry(agent.env)
                registry.register(
                    ToolSpec(
                        "channel_finish",
                        "Finish this remote task and deliver its final user-facing result.",
                        {
                            "type": "object",
                            "properties": {"summary": {"type": "string", "minLength": 1, "maxLength": 32000}},
                            "required": ["summary"],
                            "additionalProperties": False,
                        },
                    ),
                    _finish,
                )
                agent.tool_registry = registry
                bind(registry)
                task += "\nUse channel_finish with your final summary to complete this task."
            run_store = RunStore(directory / "runs.sqlite3")

            def observe(event):
                if event.type in {"query_start", "tools_start", "turn_end"}:
                    store.progress(
                        key, f"{event.state.status.value}; steps={event.state.turn_count}; calls={event.state.n_calls}"
                    )
                if store.get(key)["cancel"] and agent.run_record is not None:
                    run_store.request_cancel(row["run_id"])

            agent.subscribe(observe)
            with run_store.track(
                agent,
                run_id=row["run_id"],
                workspace=runtime.workspace,
                runtime_policy=json.dumps(
                    {"runtime": runtime.policy, "channel_session": message.session_id}, sort_keys=True
                ),
            ):
                result = agent.run(task)
            status = {"Submitted": "completed", "Cancelled": "cancelled"}.get(result.get("exit_status"), "stopped")
            summary = str(result.get("submission") or "")
            if not summary.strip():
                summary = next(
                    (
                        str(item.get("content", ""))
                        for item in reversed(agent.messages)
                        if item.get("role") == "assistant" and item.get("content")
                    ),
                    "任务结束，没有文本结果。",
                )
            store.finish(key, status, summary)
    except Exception as error:
        store.finish(
            key, "failed", f"任务失败：{type(error).__name__}。请在本机查看任务记录；敏感错误详情未发送到聊天。"
        )
        raise


def listen_feishu(directory: Path, account: str) -> None:
    """Receive SDK events in a dedicated process so its event loop cannot block other channels."""
    from minisweagent.channels.feishu import FeishuClient
    from minisweagent.channels.gateway import authorized

    config = ChannelConfig.model_validate(CredentialStore(directory).load("runtime-profile")["config"])
    settings = config.accounts[account]
    store = ChannelStore(directory)

    def accept(message):
        if authorized(settings, message):
            store.accept([message])
            store.connection(account, "receiving")

    accounts = CredentialStore(directory)
    credentials = accounts.load(account) if accounts.has(account) else None
    FeishuClient(settings, credentials).listen(account, accept, lambda status: store.connection(account, status))


def pair_feishu(directory: Path, nonce: str) -> None:
    """Receive only the matching private pairing message, without constructing any model."""
    import hashlib
    import hmac
    import time

    from minisweagent.channels.config import AccountConfig
    from minisweagent.channels.feishu import FeishuClient

    credentials = CredentialStore(directory)
    pairing = credentials.load(f"pairing-{nonce}")
    store = ChannelStore(directory)
    attempts = 0

    def accept(message):
        nonlocal attempts
        if credentials.has(f"paired-{nonce}"):
            return  # The code is consumed; later queued events cannot replace the paired owner.
        if (
            message.is_group
            or not message.text.startswith("/pair ")
            or attempts >= 100
            or time.time() > pairing["expires"]
        ):
            store.connection(pairing["account"], "pairing_waiting_for_private_code")
            return
        attempts += 1
        supplied = hashlib.sha256(message.text[6:].strip().encode()).hexdigest()
        if hmac.compare_digest(supplied, pairing["code_hash"]):
            credentials.save(f"paired-{nonce}", {"allowed_users": [message.user]})
            (directory / f"pairing-{nonce}.stop").touch()
            store.connection(pairing["account"], "paired")
        else:
            store.connection(pairing["account"], "pairing_code_mismatch")

    FeishuClient(AccountConfig.model_validate(pairing["settings"]), pairing["credentials"]).listen(
        pairing["account"], accept, lambda status: store.connection(pairing["account"], "pairing_" + status)
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--state", type=Path, required=True)
    parser.add_argument("--message")
    parser.add_argument("--feishu")
    parser.add_argument("--pair-feishu")
    args = parser.parse_args()
    if sum(bool(value) for value in (args.message, args.feishu, args.pair_feishu)) != 1:
        parser.error("Choose exactly one worker mode.")
    if args.message:
        execute(args.state, args.message)
    elif args.feishu:
        listen_feishu(args.state, args.feishu)
    else:
        pair_feishu(args.state, args.pair_feishu)
