[English](storage.md) · [简体中文](zh/storage.md)

# Run storage

Enable SQLite run records by passing a database path.

```bash
vera --storage ./runs.sqlite3 -t "Run the unit tests"
vera-extra runs list --db ./runs.sqlite3
vera-extra runs show <run-id> --db ./runs.sqlite3
```

To use the default database in the global configuration directory, add `storage: {}` to a config overlay. A `storage.path` value or `--storage` selects a different database. Use a path outside the writable workspace when the database must be protected from shell commands in that workspace.

Each run has an ID, status, exit reason, model usage and a trajectory path. Delegated runs include their parent ID and role. Parent cost includes its children, and model call counts refer to each run's own calls. With storage enabled, the default trajectory filename includes the run ID. If you supply `-o`, choose a fresh path for each run to keep its earlier trajectory available.

Tool receipts store the tool name, requested action, provider call ID when available, timestamps and return code. A `returned` receipt means the runtime recorded a return value. The return code indicates whether execution reported success. An `unknown` receipt means the runtime cannot establish an outcome, such as after a crash during dispatch or a lost MCP response. A run in `running` state has an open record and may belong to an interrupted process.

SQLite stores the last completed conversation checkpoint, including the original task and model messages. Keep the database and trajectories private when they contain project data. The history commands open SQLite read-only.

```bash
vera-extra runs cancel <run-id> --db ./runs.sqlite3
vera --storage ./runs.sqlite3 --resume <run-id>
```

Cancellation stops at the next step or tool boundary, including during a delegated run. An in-flight operation can continue until it returns or reaches its own timeout. A resumed run gets its own ID, trajectory and budget. Start it from the same workspace with the same execution backend, model adapter and relevant config overlays. It reconnects its runtime resources and continues from the saved messages. Enable a writable workspace when you need changes to persist across runs. Temporary container state ends with the original run.

If a tool receipt is unknown or a tool ran after the checkpoint, check the workspace and tool receipts before resuming. Pass your findings through `--reconcile "The report was already written. Continue with validation."` VERA includes the findings in the resumed conversation and never dispatches calls from the old checkpoint. Each run can have one continuation, and an active process must release its run lock before resumption.

Version 1 run databases migrate automatically when opened for writing. Older runs remain queryable. Resumption requires a saved checkpoint.
