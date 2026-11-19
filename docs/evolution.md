[English](evolution.md) · [简体中文](zh/evolution.md)

# Versioned source evolution

Evolution is an external experiment controller. A historical VERA runtime edits a
new generation of VERA source, required checks and fixed evaluations run, and an
accepted generation becomes the optimizer and source base for the next iteration.
The installed package, developer worktree, `dev`, and `main` are never updated by
experiment selection. No agent loop changes are required by this module.

## Upstream provenance and deliberate differences

* [SICA runner, ed8275d](https://github.com/MaximeRobeyns/self_improving_coding_agent/blob/ed8275dca4d3c5dbf77229964351fe9b424797dc/runner.py): archived generations, historical optimizer editing a separate next generation, read-only optimizer and writable target, repeated evaluation. VERA uses an independent Git archive and detached worktrees instead of directory copies. Optimizer and target base are recorded separately; this implementation selects the accepted best for both, rather than SICA's confidence-bound base selection.
* [auto-harness, 52360db](https://github.com/neosigmaai/auto-harness/blob/52360dbbeb8cea8886d90778e634a145c51da735/program_templates/base.md): one hypothesis per iteration, training evidence, protected evaluation infrastructure, regression suite, result history and stagnation stop. VERA requires positive validation gain, rather than accepting equal scores, and evaluates holdout only on explicit request.
* `evolution/auto_harness.py` can load the **unchanged pinned upstream** `BenchmarkRunner` and execute a benchmark-specific factory. The source controller and generic command-verifier path are adaptations of those designs, not claims that the complete upstream applications were embedded or their public benchmark results reproduced.

## Initialize without model calls

Install this source checkout and test dependencies in a Python environment. Git is
required. Commit the intended baseline first. Keep the experiment directory,
evaluation manifest, verifiers and held-out data outside the source repository.
Use an external YAML file such as:

```yaml
objective: Improve task completion while preserving existing tool behavior.
sandbox: auto
docker_image: vera-evolution-runtime:local
credential_env: [DEEPSEEK_API_KEY]
editable: [src/vera/agents/, src/vera/tools/]
optimizer:
  model:
    model_class: litellm
    model_name: deepseek/deepseek-flash
    model_kwargs:
      max_tokens: 4096
      timeout: 60
      num_retries: 0
  agent:
    agent_class: stateful
    step_limit: 30
checks:
  - ['{python}', '-m', ruff, check, src]
  - ['{python}', '-m', compileall, '-q', src]
tasks:
  - id: existing-file-tool
    split: train
    command: ['{python}', '/absolute/trusted/evaluate.py', '--candidate', '{candidate}', '--task', '{task_id}', '--result', '{result}']
    scoring: json
    max_cost: 0.02
  - id: unseen-file-tool
    split: validation
    command: ['{python}', '/absolute/trusted/evaluate.py', '--candidate', '{candidate}', '--task', '{task_id}', '--result', '{result}']
    scoring: json
    max_cost: 0.02
  - id: final-acceptance
    split: holdout
    command: ['{python}', '/absolute/trusted/evaluate.py', '--candidate', '{candidate}', '--task', '{task_id}', '--result', '{result}']
    scoring: json
    max_cost: 0.02
repeats: 3
max_iterations: 10
patience: 5
min_gain: 0.02
regression_threshold: 1.0
cost_limit: 5.0
optimizer_cost_limit: 0.25
optimizer_timeout: 600
```

Replace the external verifier with your actual task implementation. An exit-code
verifier uses `scoring: exit` (the default), `max_cost: 0`, and scores exit 0 as 1.
A JSON verifier writes `{"score": 0.8, "cost": 0.01}`. Missing results, nonzero exit
status and timeouts score zero. Task IDs and repetitions remain the denominator.
Malformed scores stop the run; no candidate is promoted from incomplete evidence.

Commands use argument arrays, so Windows paths with spaces require no shell
quoting inside YAML. Use absolute Windows paths for external scripts on Windows.
The CLI below works in PowerShell, Git Bash and Linux shells:

```bash
vera-extra evolution prepare-runtime --source .
vera-extra evolution init ../vera-experiment --source . -c ../evolution.yaml
vera-extra evolution baseline ../vera-experiment
vera-extra evolution run ../vera-experiment --iterations 3
vera-extra evolution status ../vera-experiment
vera-extra evolution cancel ../vera-experiment
vera-extra evolution run ../vera-experiment --resume
vera-extra evolution holdout ../vera-experiment
vera-extra evolution rollback ../vera-experiment baseline
vera-extra evolution export ../vera-experiment candidate.patch
```

`prepare-runtime` is optional for Docker users: it downloads build dependencies and
builds only committed source/dependency files, never `.env` or untracked files.
Initialization freezes the resulting image **content ID**. Linux Bubblewrap uses
the installed interpreter/dependencies read-only and does not need this image.
`auto` tries Bubblewrap, then an available Docker image, and fails if neither is
available. `sandbox: local` explicitly permits trusted development without either.
For machine-readable stdout set `VERA_SILENT_STARTUP=1` before starting Python,
as for the other `vera-extra` commands.

## Version, recovery and evaluation boundaries

* Each generation records its optimizer, base, source SHA, changed paths, checks,
  per-task/repetition results, cost and decision. Every check, trial and optimizer
  gets a fresh checkout of the recorded SHA; dirty/ignored optimizer files cannot
  affect later generations. The source repository must be clean at initialization.
  The optimizer process imports its historical version; Bash child processes use
  the candidate's `src` directory so self-checks test the code being edited.
* `state.json` is replaced atomically. An OS lock rejects concurrent controllers.
  Cancellation reaps the active subprocess tree. Recovery identifies previously
  owned processes by PID **and creation time**, reaps them and cleans up owned
  Docker containers before creating another candidate. Interrupted candidates are
  retained, never resumed or silently promoted.
* Reserve an optimizer/verifier cost bound before invoking it. Unknown or killed
  requests retain their full reservation; completed operations report usage. A
  reported overrun stops further work. These are accounting reservations, not
  provider-enforced spending caps: evolved runtime code can break its own usage
  counters. Use a provider quota or an external model gateway when a hard monetary
  cap is required. In-flight API completion may remain unknown after cancellation.
* Controller installation source, installed host dependency versions and external verifier files are fingerprinted.
  Changing them requires a new experiment. Docker optimizer dependencies are bound
  by the image ID. Dependency manifest, controller and test-definition changes are
  excluded from evolved source in this version; source runtime, tools, context,
  memory adapters and Subagent implementations can evolve within `editable`.
* Only train evidence is supplied to the optimizer. Validation drives selection;
  holdout never enters automatic search feedback. Newly passing train tasks join
  the regression suite. Equal validation scores do not promote a new version.
* Evolution experience is the explicit attempt history. Automatic Hindsight recall
  is disabled for optimizer runs, so a mutable global bank cannot contaminate
  comparisons. Task verifiers must supply their own fixed memory/data fixtures.
* Docker/Bubblewrap isolate the **whole optimizer Python process**, not just Bash.
  Only its `worker/` output directory is writable; controller logs, leases and
  verifier artifacts stay outside that mount. Atomic writes use exclusive random
  temporary files. Worker-provided process leases are ignored; result symlinks are rejected.
  Provider network access remains available. Local mode has no host security
  boundary. Trusted check/verifier commands execute on the host and must isolate
  untrusted candidate execution themselves (as benchmark sandbox backends do).
  A verifier importing arbitrary candidate Python into its own process is suitable
  only for trusted development, not adversarial benchmark integrity.
* Experimental rollback changes future version selection only. Existing runs and
  task databases are independent. This module does not migrate production data or
  deploy an evolved version. Export the reviewed diff onto a task branch from
  `dev`, then follow the normal PR/release process.

## Use an existing auto-harness benchmark

Clone auto-harness outside all candidate workspaces and check out `52360dbbeb8cea8886d90778e634a145c51da735`.
Provide a trusted absolute `factory.py:create` that accepts `(upstream, candidate,
split)` and returns an `upstream.BenchmarkRunner`. The factory must connect the
benchmark to the supplied candidate's **real VERA runtime**, rather than leaving
the upstream example agent in place. Provider-specific environments and datasets
are provisioned using upstream instructions.

Use this adapter as a JSON task command:

```text
python -m vera.evolution.auto_harness --checkout /trusted/auto-harness --factory /trusted/factory.py:create --candidate CANDIDATE --split train --task-id TASK_ID --result RESULT_JSON --cost-bound 0.05
```

In the manifest replace `CANDIDATE`, `TASK_ID`, `RESULT_JSON` with the documented
placeholders. Launch the adapter by its installed absolute script path if the
candidate baseline predates Evolution. The adapter verifies the upstream commit
and clean checkout, uses its Runner API and charges the conservative declared cost
bound because upstream runners do not provide a common actual-cost interface.
Backend task omissions still count as zero. The included integration test can use
`VERA_AUTO_HARNESS_CHECKOUT` to exercise this API against the real upstream source.
