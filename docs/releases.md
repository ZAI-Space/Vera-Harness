[English](releases.md) · [简体中文](zh/releases.md)

# Releases and npm installation

## Start the desktop app

Install Node.js 24 LTS, Python 3.12 and Bash, then run:

```bash
npx vera-harness
```

Supported versions are Node.js 22–25 and Python 3.10–3.13. Windows uses Git for
Windows Bash. First launch downloads Electron and installs the bundled VERA
wheel and Python dependencies into a private environment. The desktop window
opens after its authenticated loopback service responds. Close the app to stop
that service. Configure a model in desktop settings before submitting a task.

Use `npm install -g vera-harness`, then `vera-harness`, for a global installation.
`npx` executes the same npm package; it is not a separate publishing destination.
The Alpha desktop launcher is distributed through npm for Windows and Linux.

## Configuration and recovery

| Setting or command | Purpose |
| --- | --- |
| `VERA_PYTHON` | Python executable path without arguments. |
| `VERA_RUNTIME_DIR` | Parent directory for versioned private environments. |
| `vera-harness --doctor` | Check Python availability and the bundled wheel checksum. |
| `vera-harness --setup-only` | Install the runtime without opening the app. |
| `vera-harness --version` | Print the npm desktop version. |

Windows caches environments under `%LOCALAPPDATA%/VERA/runtimes`. Other systems
use `$XDG_CACHE_HOME/vera-harness/runtimes` or `~/.cache/vera-harness/runtimes`.
Each version and wheel checksum has a separate environment. Failed setup does
not receive a ready marker; retry to complete installation. For an interrupted
setup lock, confirm no setup process is running before removing the reported
`.setup-lock` directory. [Configuration and history](storage.md) stay outside
this cache. The launcher does not modify system Python.

## Build and publish

From the repository root with the project Python environment:

```bash
python -m pip install build twine
npm --prefix desktop ci
npm --prefix desktop run build
python scripts/build_desktop_package.py
npm pack ./dist/npm --pack-destination ./dist
node dist/npm/bin/vera-harness.mjs --doctor
node --test tests/launcher/runtime.test.mjs
```

The package contains the desktop frontend build, corresponding source and patches
under `source/`, licenses, a VERA wheel and its SHA-256 checksum. Promotional
landing page source, local configuration and credentials are excluded. Keep
`dist/` out of Git. npm version `0.1.0-alpha.4` corresponds to Python `0.1.0a4`
and tag `v0.1.0-alpha.4`.

Create the release candidate on a temporary branch from `main`. Merge its PR
into protected `main` after all 10 required CI checks pass. The single-maintainer
policy requires zero human approvals. Delete the temporary branch after delivery.
Tag the landed `main` commit
and create an Alpha GitHub Release. Attach the reviewed npm tarball, Python wheel
and checksums. GitHub supplies the tagged source archive. The release workflow
also rebuilds and uploads artifacts from the released tag.

Publish the reviewed tarball with an authorized npm account:

```bash
npm whoami --registry=https://registry.npmjs.org/
npm publish ./dist/vera-harness-0.1.0-alpha.4.tgz --access public --tag latest --registry=https://registry.npmjs.org/
npm view vera-harness version --registry=https://registry.npmjs.org/
```

The published Alpha is the npm default so `npx vera-harness` starts it. Its version
remains explicitly Alpha. Complete any browser or two-factor confirmation locally.
Never commit npm credentials. The workflow does not publish to PyPI or store an
npm token. Verify a fresh npm installation and record the final SHA and hashes.
