"""Bridge an unchanged, pinned auto-harness BenchmarkRunner to Vera's verifier API.

Run this trusted adapter outside the candidate repository. A benchmark-specific
factory receives (upstream_benchmark_module, candidate_path, split) and must return
an upstream BenchmarkRunner actually bound to that candidate. Dataset provisioning,
model credentials and benchmark environment selection remain upstream concerns.
"""

import argparse
import importlib.util
import json
import math
import sys
from pathlib import Path

from vera.evolution.repository import git

UPSTREAM_REVISION = "52360dbbeb8cea8886d90778e634a145c51da735"


def _load(name: str, path: Path):
    specification = importlib.util.spec_from_file_location(name, path)
    if specification is None or specification.loader is None:
        raise ValueError(f"Cannot load {path}")
    module = importlib.util.module_from_spec(specification)
    sys.modules[name] = module
    specification.loader.exec_module(module)
    return module


def main() -> None:
    """Run one fixed task through the upstream API, with explicit conservative cost."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--checkout", type=Path, required=True)
    parser.add_argument("--factory", required=True, help="Absolute trusted factory.py:function")
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--split", required=True)
    parser.add_argument("--task-id", required=True)
    parser.add_argument("--result", type=Path, required=True)
    parser.add_argument("--cost-bound", type=float, required=True)
    args = parser.parse_args()
    if (
        git(args.checkout, "rev-parse", "HEAD").strip() != UPSTREAM_REVISION
        or git(args.checkout, "status", "--porcelain").strip()
    ):
        raise ValueError("auto-harness must be clean and pinned to " + UPSTREAM_REVISION)
    if not math.isfinite(args.cost_bound) or args.cost_bound < 0:
        raise ValueError("cost-bound must be finite and nonnegative.")
    upstream = _load("vera_upstream_benchmark", args.checkout / "benchmark.py")
    factory_path, function = args.factory.rsplit(":", 1)
    runner = getattr(_load("vera_benchmark_factory", Path(factory_path)), function)(
        upstream, args.candidate, args.split
    )
    if not isinstance(runner, upstream.BenchmarkRunner):
        raise TypeError("Factory must return an upstream BenchmarkRunner.")
    results = runner.run(task_ids=[args.task_id])
    reward = results.get(args.task_id)
    # Keep the requested task as the denominator even if the backend drops it.
    score = upstream.BenchmarkRunner.val_score(runner, {args.task_id: reward})
    if not math.isfinite(score) or not 0 <= score <= 1:
        raise ValueError("Invalid upstream reward.")
    args.result.write_text(
        json.dumps({"score": score, "cost": args.cost_bound, "cost_is_reserved_bound": True}), encoding="utf-8"
    )


if __name__ == "__main__":
    main()
