# VERA Harness

Start the VERA desktop app and its authenticated local Python service:

```bash
npx vera-harness
```

Requires Node.js 22–25 (24 LTS recommended), Python 3.10–3.13 (3.12 recommended),
and Bash for local tools. Windows uses Git for Windows Bash. First launch
downloads Electron and Python dependencies into a private runtime. System Python
is not modified. Configure a model in the app before running tasks.

This Alpha desktop launcher is distributed through npm for Windows and Linux.

```bash
npx vera-harness --doctor
npm install -g vera-harness
vera-harness
```

`VERA_PYTHON` selects Python; `VERA_RUNTIME_DIR` selects the runtime cache.
`--setup-only` prepares the runtime without opening the app. Close the app or
press Ctrl+C to stop the local service. Credentials and history stay in the
normal VERA configuration directories, outside the npm package and runtime cache.

[中文文档](https://github.com/ZAI-Space/Vera-Harness/blob/main/docs/zh/releases.md) ·
[English guide](https://github.com/ZAI-Space/Vera-Harness/blob/main/docs/releases.md) ·
[Source](https://github.com/ZAI-Space/Vera-Harness)

Frontend source, build configuration and patches are included under `source/`.
VERA core is MIT; reused frontend portions retain their MIT and LGPL-3.0 terms.
See `THIRD_PARTY_NOTICES.md` and `third_party/`.
