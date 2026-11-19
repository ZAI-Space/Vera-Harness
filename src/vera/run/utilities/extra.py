#!/usr/bin/env python3

"""This is the central entry point to the vera-extra script. Use subcommands
to invoke other command line utilities like running on benchmarks, editing config,
inspecting trajectories, etc.
"""

import sys
from importlib import import_module

from rich.console import Console

subcommands = [
    ("vera.run.utilities.config", ["config"], "Manage the global config file"),
    ("vera.run.utilities.memory", ["memory"], "Retain and recall project notes in Hindsight"),
    ("vera.run.utilities.skills", ["skills"], "List and inspect local Agent Skills"),
    ("vera.run.utilities.mcp", ["mcp"], "Find and add MCP services from the official Registry"),
    ("vera.run.utilities.plugins", ["plugins"], "Install plugins from GitHub and plugin marketplaces"),
    ("vera.run.utilities.sandboxes", ["sandboxes"], "Manage user-configured sandbox environments"),
    ("vera.run.utilities.cron", ["cron"], "Manage scheduled tasks and the scheduler service"),
    ("vera.run.utilities.channels", ["channels"], "Connect Weixin and Feishu to the agent runtime"),
    ("vera.run.utilities.runs", ["runs"], "Inspect and cancel recorded agent runs"),
    ("vera.run.utilities.evolution", ["evolution"], "Evaluate and evolve versioned Vera source"),
    ("vera.run.utilities.inspector", ["inspect", "i", "inspector"], "Run inspector (browse trajectories)"),
    ("vera.run.benchmarks.swebench", ["swebench"], "Evaluate on SWE-bench (batch mode)"),
    ("vera.run.benchmarks.swebench_single", ["swebench-single"], "Evaluate on SWE-bench (single instance)"),
    ("vera.run.benchmarks.programbench", ["programbench"], "Run on ProgramBench (batch mode)"),
]


def get_docstring() -> str:
    lines = [
        "[bold cyan]VERA[/bold cyan] utilities: configure and manage agent capabilities.",
        "",
        "Available sub-commands:",
        "",
    ]
    for _, aliases, description in subcommands:
        alias_text = " or ".join(f"[bold green]{alias}[/bold green]" for alias in aliases)
        lines.append(f"  {alias_text}: {description}")
    return "\n".join(lines)


def main():
    args = sys.argv[1:]

    if len(args) == 0 or len(args) == 1 and args[0] in ["-h", "--help"]:
        return Console().print(get_docstring())

    for module_path, aliases, _ in subcommands:
        if args[0] in aliases:
            return import_module(module_path).app(args[1:], prog_name=f"vera-extra {aliases[0]}")

    return Console().print(get_docstring())


if __name__ == "__main__":
    main()
