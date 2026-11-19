[English](agent-state.md) · [简体中文](zh/agent-state.md)

# Agent state observation

State is an opt-in observation layer. The original `DefaultAgent.run()` loop,
`InteractiveAgent`, stop rules, exception handling, action order, budgets and
trajectory format are unchanged. The existing `default` and `interactive` factory
names still select the original classes.

The implementation borrows the separation of state snapshots and lifecycle
events from pi-agent, using this fixed reference:

- [pi-agent state types](https://github.com/badlogic/pi-mono/blob/4afe78de1e51162c01c946dcf080e6a266685a01/packages/agent/src/types.ts)
- [pi-agent state and lifecycle implementation](https://github.com/badlogic/pi-mono/blob/4afe78de1e51162c01c946dcf080e6a266685a01/packages/agent/src/agent.ts)

This is a Python observation adapter, not a port of Pi's asynchronous runtime.

## Enable

PowerShell/CMD:

```powershell
.\start.cmd --agent-class stateful_interactive
```

Git Bash/Linux Bash:

```bash
bash scripts/start.sh --agent-class stateful_interactive
```

The terminal keeps the existing interface. Applications can observe the agent
through Python, using `StatefulAgent` instead of `DefaultAgent`, or
`StatefulInteractiveAgent` instead of `InteractiveAgent`:

```python
from vera.agents.stateful import StatefulAgent

agent = StatefulAgent(model, environment, **agent_config)
unsubscribe = agent.subscribe(
    lambda event: print(event.type, event.state.status.value)
)
result = agent.run(task)
print(agent.state.status.value, agent.state.n_calls, agent.state.cost)
snapshot = agent.state.to_dict()
unsubscribe()
```

`model`, `environment`, `agent_config` and `task` are the same objects and values
used by the existing agent. State observation does not configure a model.

## State and events

| Status | Meaning |
| --- | --- |
| `idle` | No run observed yet |
| `running` | Inside the existing run/turn, between operations |
| `querying` | Inside the existing `query()` method, including interactive human-mode dispatch |
| `executing` | Inside an existing action batch |
| `waiting_for_input` | Inside the existing slash-command/confirmation input method |
| `completed` | The original run returned `Submitted` |
| `stopped` | The original run returned another stop result, including a budget limit |
| `failed` | Repeated format errors, or an exception escaped the original run |
| `cancelled` | An uncaught `KeyboardInterrupt` escaped the original run |

Snapshots include messages, cost, model-call count, consecutive-format-error
count, observed turn count, pending batch tool ids, exit status and error text.
Messages/counters are read from the original agent; the observer does not own or
reset them. As before, calling `run()` again replaces the transcript but retains
the original counters and wall-clock baseline. The observed turn count starts
again for each run. Direct low-level `step()` and `query()` calls are observed,
but `is_running` specifically describes a wrapped `run()` invocation.

Events are `agent_start`, `agent_end`, `turn_start`, `turn_end`, `query_start`,
`query_end`, `tools_start`, `tools_end`, `messages_added`, `input_requested`, and
`input_received`. Sequence numbers increase across runs. Notifications occur
after the corresponding phase update. Each subscriber receives a detached copy;
changing a snapshot cannot change live messages or another subscriber's event.
Ordinary listener errors are logged without changing execution. Listeners must
not mutate or advance the live agent. They run synchronously, so their elapsed
time is included in the existing wall-clock budget. Unsubscribe is idempotent.

Tool tracking is at batch boundaries because the underlying execution code is
unchanged. Pending ids include queued actions and actions awaiting confirmation;
they do not claim that every action is executing simultaneously. The original
limit-increase prompts use built-in `input()` inside `query()` and remain in the
`querying` phase. Temporary interrupts handled by `InteractiveAgent` do not mark
the whole run cancelled if that original loop continues.

State/event dictionaries can be saved by the caller, but are not automatically
added to existing trajectories. They are diagnostic snapshots, not restartable
checkpoints. This change adds no streaming, scheduler, concurrency guard,
pause/resume, steering queue or storage backend.

## Validation

On 2026-11-17, Windows/Python 3.12 regression checks passed 263 tests across the
agent implementations, saving, startup, inspector and configuration. Focused
state tests also cover setup/save failures, format-error recovery and charging,
budget stops, uncaught exceptions/interrupts, action batches, observer failures,
snapshot isolation, unsubscribe and equivalence with the original agents.

A Windows `start.cmd` run selected `stateful_interactive`, processed a deterministic
response, and saved a `Submitted` trajectory in the existing format. An
interactive human-mode terminal test observed `waiting_for_input`,
`executing` and `completed`, executed an actual Bash `echo`, and finished with
zero model calls. Ruff lint/format checks and the wheel build passed. No real
model/provider result, streaming support or durable recovery is claimed.
