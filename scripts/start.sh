#!/usr/bin/env bash
# Start the checkout with its virtual environment; provision dependencies once.
set -euo pipefail

project_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
case "$(uname -s)" in
    MINGW*|MSYS*)
        git_root="$(cygpath -m /)"
        export VERA_BASH_PATH="${VERA_BASH_PATH:-${git_root%/}/bin/bash.exe}"
        export PYTHONUTF8="${PYTHONUTF8:-1}"
        export PYTHONIOENCODING="${PYTHONIOENCODING:-utf-8}"
        venv_python="$project_root/.venv/Scripts/python.exe"
        # Mintty exposes a POSIX PTY; native Windows Python needs a console bridge.
        if [[ -t 0 && -t 1 ]] && ! "$venv_python" -c 'import sys; sys.exit(not sys.stdin.isatty())' 2>/dev/null; then
            use_winpty=true
        fi
        ;;
    *) venv_python="$project_root/.venv/bin/python" ;;
esac

if [[ ! -f "$venv_python" ]]; then
    bootstrap_python="${VERA_BOOTSTRAP_PYTHON:-}"
    if [[ -z "$bootstrap_python" ]]; then
        bootstrap_python="$(command -v python3 || command -v python || true)"
    fi
    if [[ -z "$bootstrap_python" ]] || ! "$bootstrap_python" -c 'import sys; sys.exit(sys.version_info < (3, 10))'; then
        echo 'Python 3.10 or newer is required. Install Python and retry.' >&2
        exit 1
    fi
    "$bootstrap_python" -m venv "$project_root/.venv"
fi

if ! "$venv_python" -c 'from importlib.metadata import distribution; distribution("vera-harness")' >/dev/null 2>&1; then
    if command -v uv >/dev/null 2>&1; then
        uv pip install --python "$venv_python" -e "$project_root"
    else
        "$venv_python" -m pip install -e "$project_root"
    fi
fi

if [[ "${use_winpty:-false}" == true ]]; then
    if ! command -v winpty >/dev/null 2>&1; then
        echo 'An interactive Mintty session requires winpty. Use Windows Terminal or reinstall full Git for Windows.' >&2
        exit 1
    fi
    exec winpty "$venv_python" -m vera "$@"
fi
exec "$venv_python" -m vera "$@"
