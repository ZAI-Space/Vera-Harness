[English](README.en.md) · [简体中文](README.md)

# VERA Desktop

An Electron + React desktop entry point sharing the VERA Python Runtime with the terminal.

Install the Python dependencies from the repository root, then run `npm ci` here. Node.js 24 LTS is recommended.

```powershell
# From the repository root: own both the local service and desktop lifetime
powershell -File scripts/start-desktop.ps1
```

Git Bash or Linux/macOS: `bash scripts/start-desktop.sh`. Local tools use Git Bash on Windows. Docker is optional; configured sandboxes are selected separately.

Use `npm run dev` for frontend-only development. Without a backend connection file this is a labelled preview and cannot execute agent tasks.

Checks: `npm run check:boundary`, `npm run lint`, `npm run typecheck`, `npm test`, `npm run build`. The cross-language integration test needs the root `.venv`, or `VERA_PYTHON` pointing to an interpreter with VERA installed.

[Backend contract and limits](../docs/frontend-integration.md) · [Streaming and reasoning presentation](../docs/desktop-streaming.md)

Source and licensing: [Percho MIT](third_party/percho-LICENSE), [PI-Desktop LGPL-3.0](third_party/pi-desktop/NOTICE.md). These notices retain each component's license and do not relicense LGPL code as MIT.
