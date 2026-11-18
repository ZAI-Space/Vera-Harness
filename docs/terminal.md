# Terminal file context and commands

Run `mini` (or `start.cmd` in Windows, `./scripts/start.sh` in Bash) inside
the project. The initial prompt accepts tasks, project file references and commands.
Use Tab to complete a file or command; use Esc followed by Enter to submit the
multiline prompt. Existing `/h`, `/m`, `/u`, `/c` and `/y` controls remain available
at the agent's confirmation prompts.

## Project files

Type `@` to choose files inside the current workspace:

```text
Review @src/main.py and @"docs/design notes.md"
```

Completion matches filenames and paths without regard to case. Git projects
respect ignore rules when listing files. Paths use forward slashes, including
on Windows. Absolute paths, traversal, escaping links, dependency directories
and common credential files are rejected. Only UTF-8 text is accepted, with
limits of 10 files, 32 KiB per file and 128 KiB per message. Repeated references
are deduplicated. The complete selection is validated before submitting a task.
Quoted file contents are context and grant no additional execution permissions.
Use `\@` to keep a literal mention; email addresses are left alone.

`mini -t 'Review @src/main.py'` supports the same references. A resumed run uses
its saved task instead of re-reading files.

## Session commands

Commands affect this terminal session, without writing global configuration.
Use a command without arguments to list configured choices.

| Command | Behavior |
| --- | --- |
| `/skill review,testing` | Add selected skill instructions to subsequent tasks. |
| `/mcp docs,issues` | Select configured MCP services for subsequent runtimes. |
| `/plugin review-kit` | Select installed, already enabled plugins for subsequent runtimes. |
| `/model fast` | Select a named model profile for subsequent tasks. |
| `/subagent reviewer [task]` | Request delegation to a configured role; an optional task submits immediately. |
| `/permissions confirm` | Require action confirmation (subject to the existing Bash whitelist). |
| `/permissions yolo` | Execute without per-action confirmation. |
| `/permissions human` | Execute commands entered by the user. |
| `/sandbox NAME` | Choose a saved, available isolated environment for the next task. |
| `/new` | End the current conversation and return to task entry. |
| `/stop` | Stop at the current user-input boundary; exit when entered at idle. |
| `/help` | Show commands and file selection syntax. |

`/skill`, `/mcp` and `/plugin` accept comma-separated names, `all` or `none`.
`/subagent none` clears delegation. `/sandbox` refreshes availability and returns
configured/disabled state for the picker. `/sandbox none` explicitly chooses
local host execution. See [sandbox settings](sandbox.md) to add profiles. Installed
plugins still require approval through plugin management before selection here.
Disabling an MCP service also removes its tools from delegated roles.

Configuration changes at an in-task prompt apply to the **next task**. Submit the
current result or enter `/new` before starting with the new settings. A task
entered at the existing finish-confirmation prompt continues the current
conversation; `/new` explicitly starts a fresh context. Separate runs preserve
their trajectories and storage records.

While a model or tool is running, Ctrl+C opens the existing interruption prompt;
enter `/stop` there. Commands are interpreted only from user input. To submit a
task starting with a literal slash, prefix it with another slash (`//...`).

The previous `/permissions auto`, `/permissions readonly` and optional backend
argument remain accepted for compatibility; the mode picker exposes only
`confirm`, `yolo` and `human`. Execution environment selection is independent.
There is no automatic risk classification or delegated approval mode.

The optional read-only restriction retains file context, skill reads, configured web reads,
delegation, and run logging. They use `task_finish` instead of Bash to finish.
They require a model adapter supporting registered tools and do not replace
operating-system isolation. Local mode otherwise has host access; confirmation
asks permission and does not isolate a command.

## Named models

Add profiles to your existing configuration; keep credentials in environment
variables as required by each model adapter:

```yaml
terminal:
  models:
    fast:
      model_class: litellm
      model_name: openai/your-fast-model
    reasoning:
      model_class: litellm
      model_name: openai/your-reasoning-model
```

`/model` lists safe profile names and model names, never model credentials.
`/model current` keeps the currently selected model. Each profile supplies the
complete model configuration, following the existing provider schema.

## Shared integration boundary

`minisweagent.terminal.session.TerminalSession` handles catalogs, input parsing,
per-task configuration and explicit context preparation without prompt-toolkit
or model requests. `InputResult` distinguishes messages, tasks, new conversations
and stop requests. `ProjectFiles` supplies workspace file completion and bounded
context. `terminal.ui` adapts those interfaces to the existing prompts, while
`open_agent_runtime` enforces capabilities. A desktop transport can reuse these
interfaces when its frontend is ready.
