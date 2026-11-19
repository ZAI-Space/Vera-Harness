"""Execute one occurrence in a fresh, bounded agent process; never modify scheduling decisions."""

import argparse
import json
from pathlib import Path

from minisweagent.config import get_config_from_spec
from minisweagent.evolution.process import write_json
from minisweagent.exceptions import Submitted
from minisweagent.runtime import open_agent_runtime
from minisweagent.scheduler.config import JobSpec
from minisweagent.scheduler.store import JobStore
from minisweagent.storage import RunStore
from minisweagent.terminal.session import TerminalSession
from minisweagent.tools import ToolSpec, make_tool_registry
from minisweagent.utils.serialize import recursive_merge


def execute(directory: Path, key: str) -> None:
    """Run an already fenced occurrence and atomically publish its terminal result.

    The supervisor handles timeout/cancellation and publishes database state. Each
    occurrence gets fresh messages, a normal RunStore record, and its own output.
    Credentials are resolved by normal provider adapters; no shell argv contains them.
    """
    store = JobStore(directory)
    row = store.execution(key)
    if row["status"] != "running":
        raise RuntimeError("The scheduled occurrence is not running.")
    output = directory / "artifacts" / key
    try:
        spec = JobSpec.model_validate_json(row["snapshot"])
        config = recursive_merge(get_config_from_spec("mini.yaml"), spec.config)
        config["scheduler"] = {"enabled": False}
        config.setdefault("environment", {})["cwd"] = str(spec.workspace)
        if "sandbox" in config:
            config["sandbox"]["workspace"] = str(spec.workspace)
        agent = config.setdefault("agent", {})
        agent.update(
            mode="yolo",
            confirm_exit=False,
            output_path=output / "trajectory.json",
            wall_time_limit_seconds=spec.timeout,
            step_limit=spec.step_limit,
            cost_limit=spec.cost_limit,
        )
        if agent.get("agent_class") in {None, "default", "interactive"}:
            agent["agent_class"] = "stateful"
        for role in config.get("subagents", {}).get("roles", {}).values():
            role["tools"] = [name for name in role.get("tools", []) if name != "cronjob_manage"]
        session = TerminalSession(config, spec.workspace)
        session.skills = list(spec.skills)
        task = session.prepare_task(spec.prompt)
        with open_agent_runtime(config, default_type="stateful") as runtime:
            agent = runtime.agent
            if callable(getattr(agent.model, "bind_tool_registry", None)) and getattr(
                agent.model, "supports_tool_registry", True
            ):
                registry = agent.tool_registry or make_tool_registry(agent.env)

                def finish(arguments):
                    raise Submitted(
                        {
                            "role": "exit",
                            "content": arguments["summary"],
                            "extra": {"exit_status": "Submitted", "submission": arguments["summary"]},
                        }
                    )

                registry.register(
                    ToolSpec(
                        "schedule_finish",
                        "Complete this scheduled task with its final result.",
                        {
                            "type": "object",
                            "properties": {"summary": {"type": "string"}},
                            "required": ["summary"],
                            "additionalProperties": False,
                        },
                    ),
                    finish,
                )
                agent.tool_registry = registry
                agent.model.bind_tool_registry(registry)
                task += "\nUse schedule_finish with the final result to finish this scheduled task."
            with RunStore(directory / "runs.sqlite3").track(
                agent,
                run_id=key,
                workspace=runtime.workspace,
                runtime_policy=json.dumps({"runtime": runtime.policy, "job": row["job_id"]}, sort_keys=True),
            ):
                result = agent.run(task)
            status = {"Submitted": "completed", "Cancelled": "cancelled"}.get(result.get("exit_status"), "failed")
            write_json(
                output / "result.json",
                {
                    "status": status,
                    "summary": str(result.get("submission") or ""),
                    "exit_status": result.get("exit_status"),
                    "run_id": key,
                    "cost": agent.cost,
                    "trajectory": str(output / "trajectory.json"),
                },
            )
    except Exception as error:
        write_json(output / "result.json", {"status": "failed", "error_type": type(error).__name__, "run_id": key})
        raise


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    parser.add_argument("execution")
    arguments = parser.parse_args()
    execute(arguments.directory, arguments.execution)
