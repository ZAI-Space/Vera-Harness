"""Context projection preserves provider protocol groups and user steering."""

from copy import deepcopy

import pytest

from minisweagent.agents.hindsight import HindsightAgent
from minisweagent.environments.local import LocalEnvironment
from minisweagent.memory.context import compact_context
from minisweagent.models.test_models import DeterministicModel, make_output


@pytest.mark.parametrize("responses_api", [False, True])
def test_compaction_keeps_tool_pairs_and_preserves_full_history(responses_api):
    history = [{"role": "system", "content": "System"}, {"role": "user", "content": "Task"}]
    for index in range(4):
        call_id = f"call_{index}"
        if responses_api:
            history.extend(
                [
                    {"object": "response", "output": [{"type": "function_call", "call_id": call_id}]},
                    {"type": "function_call_output", "call_id": call_id, "output": f"Result {index} " + "x" * 1000},
                ]
            )
        else:
            history.extend(
                [
                    {"role": "assistant", "tool_calls": [{"id": call_id}]},
                    {"role": "tool", "tool_call_id": call_id, "content": f"Result {index} " + "x" * 1000},
                ]
            )
    original = deepcopy(history)
    compacted = compact_context(history, 3200)
    assert compacted[0] == history[0]
    assert compacted[1]["content"].startswith("Task\n\nOlder session history")
    assert "Result 1" in compacted[1]["content"]
    assert compacted[2:] == history[-4:]
    assert history == original


def test_compaction_preserves_first_user_followup_and_everything_after_it():
    history = [{"role": "system", "content": "System"}, {"role": "user", "content": "Task"}]
    for index in range(4):
        history.extend([{"role": "assistant", "content": str(index)}, {"role": "tool", "content": "x" * 1500}])
        if index == 1:
            history.append({"role": "user", "content": "Keep the build configuration untouched."})
    compacted = compact_context(history, 3000)
    assert compacted[2:] == history[4:]


class RecordingModel(DeterministicModel):
    """Capture the actual model inputs during a deterministic run."""

    def __init__(self, outputs):
        super().__init__(outputs=outputs)
        self.inputs = []

    def query(self, messages, **kwargs):
        self.inputs.append(deepcopy(messages))
        return super().query(messages, **kwargs)


def test_agent_compacts_provider_input_without_pruning_saved_trajectory():
    outputs = [
        make_output(f"Step {index}", [{"command": f"echo 'Result {index} {'x' * 1000}'"}], cost=0) for index in range(4)
    ]
    outputs.append(make_output("Done", [{"command": "echo COMPLETE_TASK_AND_SUBMIT_FINAL_OUTPUT"}], cost=0))
    model = RecordingModel(outputs)
    agent = HindsightAgent(
        model,
        LocalEnvironment(),
        memory_mode="disabled",
        context_budget_chars=3200,
        system_template="Use Bash.",
        instance_template="{{ task }}",
    )
    assert agent.run("Verify the full transcript")["exit_status"] == "Submitted"
    assert "Older session history" in model.inputs[-1][1]["content"]
    assert len(model.inputs[-1]) < len(agent.messages) - 2
    assert agent.serialize()["messages"][1]["content"] == "Verify the full transcript"
    assert "Result 0" in agent.serialize()["messages"][3]["content"]
