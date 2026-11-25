[English](environments.md) · [简体中文](../zh/advanced/environments.md)

# Environment classes

!!! abstract "Environment and sandbox are separate choices"

    An Environment executes tool commands. Sandbox configuration adds a policy for isolation, mounts and external capabilities. Choosing `--environment-class docker` is not the same interface as a saved `--sandbox-profile`.

| Factory name | Backend | Requirements |
| --- | --- | --- |
| `local` | Host commands; Git Bash on Windows | Bash and host permissions; no isolation |
| `docker` | Docker/Podman container | Running compatible engine and configured image |
| `bubblewrap` | Linux namespaces | Bubblewrap and usable user namespaces |
| `singularity` | Singularity/Apptainer | Installed runtime and compatible image |
| `swerex_docker` | SWE-ReX Docker | Optional SWE-ReX dependency and engine |
| `swerex_modal` | SWE-ReX on Modal | Modal dependencies, service credentials and network |
| `contree` | ConTree service | Optional compatible SDK and service access |

```bash
vera --environment-class local
vera --sandbox docker
vera --sandbox-profile python-dev
```

The local backend runs with the current user's host permissions. For isolation, install and configure a sandbox backend with its required engine and image.

Set low-level options under `environment`, and policy under `sandbox`. [Saved sandbox configuration](../sandbox.md) explains checks, selection, permissions, host MCP opt-ins and unavailable backends. User configuration manages engine/image installation; the Runtime does not silently downgrade an explicit isolation request.
