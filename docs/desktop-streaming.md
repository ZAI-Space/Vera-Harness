[English](desktop-streaming.md) · [简体中文](zh/desktop-streaming.md)

# Desktop streaming presentation

!!! abstract "Separate provider output from display animation"

    Provider deltas must arrive before completion. A smooth-text animation improves presentation of received text; it cannot turn a buffered response into real streaming. Visible reasoning is shown only when the provider supplies it.

## Design references

The presentation design references PI-Desktop revision `f589deec80b4be928146db0eca74e6f3f5e4e4b0`. Component sources and licenses are listed in the desktop's third-party notice.

| Upstream implementation | Observed behavior | VERA application |
| --- | --- | --- |
| [AssistantTurnParts](https://github.com/vastsa/PI-Desktop/blob/f589deec80b4be928146db0eca74e6f3f5e4e4b0/apps/desktop/src/features/chat/transcript/AssistantTurnParts.tsx) | Answer fragments and activity groups stay separate and ordered | Existing Markdown, MetaGroup and tool-card components |
| [Activity folding](https://github.com/vastsa/PI-Desktop/blob/f589deec80b4be928146db0eca74e6f3f5e4e4b0/apps/desktop/src/lib/activity-group-folding.ts) | Live reasoning opens; settled reasoning folds; reader choices take precedence | Automatic disclosure defaults until an explicit reader choice |
| [Thinking visibility](https://github.com/vastsa/PI-Desktop/blob/f589deec80b4be928146db0eca74e6f3f5e4e4b0/apps/desktop/src/lib/thinking-visibility.ts) | Reasoning visibility is a presentation preference, separate from process folding | Reasoning has a separate block; waiting for a response is not labelled as actual reasoning |
| [Smooth text](https://github.com/vastsa/PI-Desktop/blob/f589deec80b4be928146db0eca74e6f3f5e4e4b0/apps/desktop/src/hooks/useSmoothText.ts) | Adaptive release, bounded visual lag and reduced-motion support | Keep the existing incremental Markdown and pacing implementation |
| [Stream coalescer](https://github.com/vastsa/PI-Desktop/blob/f589deec80b4be928146db0eca74e6f3f5e4e4b0/packages/agent-runtime/src/stream-coalescer.ts) | Merge frequent updates; flush before semantic boundaries | Existing renderer EventConflator preserves boundaries and updates at frame cadence |
| [Transcript scrolling](https://github.com/vastsa/PI-Desktop/blob/f589deec80b4be928146db0eca74e6f3f5e4e4b0/apps/desktop/src/lib/transcript-scroll.ts) | User scrolling releases bottom-follow; returning to the tail restores it | Preserve the existing message-list reading-position behavior |

## Runtime event path

```text
Provider SSE → desktop streaming model adapter → worker JSON frames
→ authenticated loopback event buffer → Electron main/preload
→ EventConflator → transcript reducer → Markdown / reasoning / tool cards
```

The desktop selects streaming subclasses of the existing LiteLLM adapters. Chat Completions is normalized by LiteLLM for OpenAI-compatible, Anthropic and Gemini providers; Responses uses its native response events. Received chunks are assembled into the final provider response so the original action parser, cost accounting, tool validation and runtime receipts still apply. The Agent Loop is unchanged.

Desktop workers use token accounting and set `LITELLM_LOCAL_MODEL_COST_MAP=True` before importing the SDK. LiteLLM uses its bundled model metadata during startup instead of downloading the remote price table. Provider requests still require their configured connection.

Task performance receipts record milliseconds from task start: `runtimeReadyMs` marks the first root `tools_ready` frame, `modelRequestMs` the first root `model_request`, and `firstResponseMs` the first effective root output. `providerWaitMs` is `firstResponseMs - modelRequestMs`, or `null` if either value is unavailable. These timings separate runtime preparation from the observed wait for provider output; they do not guarantee a fixed response speed.

Each model reply starts a turn. Text and visible reasoning append to separate content blocks; tool argument fragments never execute. Complete tool calls are validated and, in confirm mode, wait for a scoped approval. Tool results precede turn completion. Stable UI identities avoid replaying a whole answer when it settles.

The backend keeps a live display projection for reconnect. If stopped, received text remains in history and partial tool arguments stay display-only. A missing completion receipt produces an error. Opaque signatures and encrypted reasoning are retained for provider context replay; the reasoning panel displays readable content supplied by the provider.

## Regression tests

- `tests/run/test_desktop_streaming.py`: a local HTTP SSE peer pauses before completion; the backend must already expose text and reasoning, then retain final tools/usage. A second test aborts before completion.
- `desktop/tests/contracts/transcript/harness.integration.test.ts`: a real Python worker executes Bash; TypeScript consumes its event trace and checks reasoning, answer, tool completion and idle state.

Run desktop interaction tests with `npm run test:ui` from `desktop/`. See [testing](testing.md) for environment setup and commands.
