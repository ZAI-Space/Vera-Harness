#!/usr/bin/env bash
# Own the local service lifecycle outside Electron; preserve the terminal entry point.
set -euo pipefail
project_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
if [[ "${OS:-}" == Windows_NT ]]; then
    exec powershell.exe -NoProfile -File "$(cygpath -w "$project_root/scripts/start-desktop.ps1")" "$@"
fi
python_path="${VERA_PYTHON:-$project_root/.venv/bin/python}"
connection_dir="$(mktemp -d)"
chmod 700 "$connection_dir"
export VERA_SILENT_STARTUP=1
"$python_path" -m vera.desktop.server --port 0 --connection-file "$connection_dir/connection.json" "$@" >"$connection_dir/service.log" 2>&1 &
service_pid=$!
cleanup() { kill "$service_pid" 2>/dev/null || true; wait "$service_pid" 2>/dev/null || true; rm -f -- "$connection_dir/connection.json"; }
trap cleanup EXIT INT TERM
for _ in {1..150}; do
    [[ -f "$connection_dir/connection.json" ]] && break
    kill -0 "$service_pid" 2>/dev/null || { cat "$connection_dir/service.log"; exit 1; }
    sleep 0.2
done
[[ -f "$connection_dir/connection.json" ]] || { echo 'VERA service startup timed out' >&2; exit 1; }
export VERA_DESKTOP_CONNECTION_FILE="$connection_dir/connection.json"
cd "$project_root/desktop"
[[ -d node_modules ]] || npm ci
[[ -f out/main/index.js ]] || npm run build
npm start
