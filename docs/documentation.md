[English](documentation.md) · [简体中文](zh/documentation.md)

# Documentation maintenance

!!! abstract "Two language editions, one implementation"

    English guides keep the existing paths. Chinese guides mirror them under `zh/`. Every page links to its counterpart. API symbols and generated source docstrings retain their implementation language; localized API guidance surrounds the same directives. Config names, commands and security boundaries must agree.

## Per-page review

The table below records the concrete review scope for every existing page. It is a maintenance map, not a claim that optional services or every provider have been live-tested. Source includes and API directives are resolved by the strict documentation build. `scripts/check_docs.py` checks pairs, local file links and obsolete branding.

| Page | Review/update |
| --- | --- |
| [web-tools.md](web-tools.md) | Checked registry dispatch, provider settings, search/extraction limits and confirm-mode authorization. |
| [frontend-integration.md](frontend-integration.md) | Documents the authenticated desktop transport, Python service boundary and actual UI acceptance scope. |
| [SECURITY.md](SECURITY.md) | Removed upstream personal support contacts; documented VERA ownership and actual execution/data boundaries. |
| [_footer.md](_footer.md) | Replaced upstream community/support links with the VERA repository. |
| [advanced/control_flow.md](advanced/control_flow.md) | Checked DefaultAgent run/query/actions/stop handling; documented registry routing and outer controllers. |
| [advanced/cookbook.md](advanced/cookbook.md) | Replaced incomplete Agent constructors and ad-hoc Bash dispatch with required templates and ToolSpec. |
| [advanced/environments.md](advanced/environments.md) | Separated low-level Environment factories, sandbox policies and optional backend prerequisites. |
| [advanced/global_configuration.md](advanced/global_configuration.md) | Checked environment lookup, config precedence, paths, retry and accounting variables. |
| [advanced/v2_migration.md](advanced/v2_migration.md) | Replaced obsolete upstream installation guidance with explicit VERA naming/data migration. |
| [advanced/yaml_configuration.md](advanced/yaml_configuration.md) | Checked merge order, complete templates, supported classes and module-specific path ownership. |
| [agent-state.md](agent-state.md) | Checked state/event names, immutable observation and original loop counters. |
| [channels.md](channels.md) | Provided English counterpart; checked QR/Feishu pairing, allowlists, event prerequisites and outbox uncertainty. |
| [contributing.md](contributing.md) | Aligned Gitflow, local checks and paired-document maintenance with current collaboration rules. |
| [evolution.md](evolution.md) | Checked pinned source references, train/validation/holdout, source fingerprints and no deployment claims. |
| [faq.md](faq.md) | Corrected capabilities, permissions versus sandbox, fresh-shell behavior and evidence limits. |
| [hindsight-memory.md](hindsight-memory.md) | Checked banks, recall/reflect, conflict provenance, compaction and absence of automatic transcript ingestion. |
| [index.md](index.md) | Replaced inherited score/adoption and Bash-only claims with the current module map and transport boundary. |
| [markets-and-modes.md](markets-and-modes.md) | Checked market adapters, explicit selection, confined planning and persistent bounded goal controller. |
| [mcp.md](mcp.md) | Added markets, optional stdio env and HTTP header variables; no OAuth/SSE claim. |
| [models/local_models.md](models/local_models.md) | Verified api_base, model registry and cost-error behavior against the current Config class. |
| [models/quickstart.md](models/quickstart.md) | Removed frozen provider model catalog, corrected Responses shortcut and current adapter mapping. |
| [models/troubleshooting.md](models/troubleshooting.md) | Removed stale provider-specific examples; retained concrete authentication/accounting/format diagnostics. |
| [plugins.md](plugins.md) | Checked preset GitHub/Gitee source commits, install/enable, digests, rollback and capability boundaries. |
| [quickstart.md](quickstart.md) | Source install, current extras, three shell environments, secret input and unpublished package boundary. |
| [reference/agents/default.md](reference/agents/default.md) | Checked current source inclusions and API directives; localized guidance and retained exact public symbols. |
| [reference/agents/interactive.md](reference/agents/interactive.md) | Checked current source inclusions and API directives; localized guidance and retained exact public symbols. |
| [reference/environments/bubblewrap.md](reference/environments/bubblewrap.md) | Checked current source inclusions and API directives; localized guidance and retained exact public symbols. |
| [reference/environments/contree.md](reference/environments/contree.md) | Checked current source inclusions and API directives; localized guidance and retained exact public symbols. |
| [reference/environments/docker.md](reference/environments/docker.md) | Checked current source inclusions and API directives; localized guidance and retained exact public symbols. |
| [reference/environments/local.md](reference/environments/local.md) | Checked current source inclusions and API directives; localized guidance and retained exact public symbols. |
| [reference/environments/singularity.md](reference/environments/singularity.md) | Checked current source inclusions and API directives; localized guidance and retained exact public symbols. |
| [reference/environments/swerex_docker.md](reference/environments/swerex_docker.md) | Checked current source inclusions and API directives; localized guidance and retained exact public symbols. |
| [reference/environments/swerex_modal.md](reference/environments/swerex_modal.md) | Checked current source inclusions and API directives; localized guidance and retained exact public symbols. |
| [reference/index.md](reference/index.md) | Checked current source inclusions and API directives; localized guidance and retained exact public symbols. |
| [reference/models/extra.md](reference/models/extra.md) | Checked current source inclusions and API directives; localized guidance and retained exact public symbols. |
| [reference/models/litellm.md](reference/models/litellm.md) | Checked current source inclusions and API directives; localized guidance and retained exact public symbols. |
| [reference/models/litellm_response.md](reference/models/litellm_response.md) | Checked current source inclusions and API directives; localized guidance and retained exact public symbols. |
| [reference/models/openrouter.md](reference/models/openrouter.md) | Checked current source inclusions and API directives; localized guidance and retained exact public symbols. |
| [reference/models/overview.md](reference/models/overview.md) | Checked current source inclusions and API directives; localized guidance and retained exact public symbols. |
| [reference/models/portkey.md](reference/models/portkey.md) | Checked current source inclusions and API directives; localized guidance and retained exact public symbols. |
| [reference/models/portkey_response.md](reference/models/portkey_response.md) | Checked current source inclusions and API directives; localized guidance and retained exact public symbols. |
| [reference/models/requesty.md](reference/models/requesty.md) | Checked current source inclusions and API directives; localized guidance and retained exact public symbols. |
| [reference/models/test_models.md](reference/models/test_models.md) | Checked current source inclusions and API directives; localized guidance and retained exact public symbols. |
| [reference/models/utils.md](reference/models/utils.md) | Checked current source inclusions and API directives; localized guidance and retained exact public symbols. |
| [reference/run/config.md](reference/run/config.md) | Checked current source inclusions and API directives; localized guidance and retained exact public symbols. |
| [reference/run/hello_world.md](reference/run/hello_world.md) | Checked current source inclusions and API directives; localized guidance and retained exact public symbols. |
| [reference/run/inspector.md](reference/run/inspector.md) | Checked current source inclusions and API directives; localized guidance and retained exact public symbols. |
| [reference/run/cli.md](reference/run/cli.md) | Checked current source inclusions and API directives; localized guidance and retained exact public symbols. |
| [reference/run/extra.md](reference/run/extra.md) | Checked current source inclusions and API directives; localized guidance and retained exact public symbols. |
| [reference/run/programbench.md](reference/run/programbench.md) | Checked current source inclusions and API directives; localized guidance and retained exact public symbols. |
| [reference/run/swebench.md](reference/run/swebench.md) | Checked current source inclusions and API directives; localized guidance and retained exact public symbols. |
| [reference/run/swebench_single.md](reference/run/swebench_single.md) | Checked current source inclusions and API directives; localized guidance and retained exact public symbols. |
| [sandbox.md](sandbox.md) | Checked saved profiles, user installation, availability/disabled picker and no silent downgrade. |
| [scheduler.md](scheduler.md) | Checked schedule formats, durable claims, manual/finite runs, daemon limits, recovery and local-only results. |
| [skills.md](skills.md) | Added market provenance and removal behavior; retained exact discovery, paging and support-file rules. |
| [storage.md](storage.md) | Checked tool receipts, checkpoints, resume fingerprints, unknown outcomes and migration. |
| [subagents.md](subagents.md) | Checked role schemas, independent context, shared environment and parent budget/approval rules. |
| [terminal.md](terminal.md) | Added plan/goal and explicit market operations, reviewed file limits and next-task selection. |
| [usage/config.md](usage/config.md) | Checked setup/set/unset/edit, secret prompting and editor requirements. |
| [usage/inspector.md](usage/inspector.md) | Checked command entry, Textual bindings and read-only artifact inspection. |
| [usage/cli.md](usage/cli.md) | Rebuilt current option table and explicit modes; removed old-brand screenshots. |
| [usage/output_files.md](usage/output_files.md) | Checked serialized schema/version, final exit message, sensitive content and prediction boundary. |
| [usage/programbench.md](usage/programbench.md) | Removed inherited performance implications; documented current runner versus optional evaluator prerequisites. |
| [usage/python_bindings.md](usage/python_bindings.md) | Replaced invalid template-free constructor with current open_agent_runtime example. |
| [usage/swebench.md](usage/swebench.md) | Corrected partial trajectory saving, selected-task accounting and inference versus external scoring. |
| [windows.md](windows.md) | Checked bootstrap, Git Bash detection, download verification and platform-specific execution; removed stale acceptance counts. |

## Validation

```bash
python scripts/check_docs.py
python -m mkdocs build --strict
python -m ruff check src tests
python -m pytest -n 2 -ra
```

Check the actual installed CLI, fresh wheel, startup display and rendered README/docs. Preserve failures and unavailable prerequisites in the delivery evidence. For future behavioral changes, update both language pages and the relevant examples in the same branch.
