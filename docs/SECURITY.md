[English](SECURITY.md) · [简体中文](zh/SECURITY.md)

# Security policy

## Reporting a vulnerability

Report VERA issues to this repository's maintainers through the available repository contact/security channels. Do not send VERA support requests to upstream authors or publish live credentials, customer data or an exploit against another user's service. Provide the affected commit, configuration with secrets removed, reproducible steps and expected boundary.

## Execution boundaries

Local mode runs with the current user's permissions. `confirm` is approval, not isolation; `yolo` is explicit unattended execution. Configure a sandbox when isolation is required, including opt-ins for host MCP and web providers. Treat downloaded plugin code, Skill instructions and external MCP replies as untrusted inputs. See [sandbox behavior](sandbox.md) and [frontend transport boundaries](frontend-integration.md).

Stored tasks, trajectories and private settings may contain sensitive project data. The channels credential store provides its documented platform protection, but unrelated job/config snapshots are not a universal encrypted credential vault. Verify scopes and keep store files out of Git.
