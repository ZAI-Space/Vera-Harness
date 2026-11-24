"""Create a self-contained npm staging tree from a built desktop and a Python wheel.

Run from the repository root after ``npm --prefix desktop run build``.
Only the generated ``dist/npm`` directory is replaced. No credentials or local
configuration are copied. The result is ready for ``npm pack ./dist/npm``.
"""

import hashlib
import importlib.util
import json
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    """Stage built assets, exact Python wheel, licenses and corresponding source."""
    frontend = ROOT / "desktop"
    if not (frontend / "out/main/index.js").is_file():
        raise SystemExit("Build the desktop first: npm --prefix desktop run build")
    output = ROOT / "dist/npm"
    if output.exists():
        if output.is_symlink() or output.resolve().parent != (ROOT / "dist").resolve():
            raise SystemExit("Refusing redirected package output")
        shutil.rmtree(output)
    shutil.copytree(ROOT / "packages/desktop-launcher", output)
    for name in ("out", "build", "third_party"):
        shutil.copytree(frontend / name, output / name)
    for name in ("LICENSE.md", "THIRD_PARTY_NOTICES.md"):
        shutil.copyfile(ROOT / name, output / name)
    source = output / "source"
    shutil.copytree(frontend / "src", source / "src")
    for name in (
        "package.json",
        "package-lock.json",
        "electron.vite.config.ts",
        "tsconfig.base.json",
        "vitest.config.ts",
        "tsconfig.node.json",
        "tsconfig.web.json",
    ):
        shutil.copyfile(frontend / name, source / name)
    shutil.copytree(frontend / "patches", source / "patches")
    for name in ("build", "scripts", "third_party"):
        shutil.copytree(frontend / name, source / name)
    command = [sys.executable, "-m", "build", "--wheel", "--outdir", str(output / "python")]
    if importlib.util.find_spec("pip") is None and shutil.which("uv"):
        command += ["--installer", "uv"]
    subprocess.run([*command, str(ROOT)], check=True)
    (wheel,) = (output / "python").glob("*.whl")
    runtime = {"wheel": wheel.name, "sha256": hashlib.sha256(wheel.read_bytes()).hexdigest()}
    (output / "runtime.json").write_text(json.dumps(runtime, indent=2) + "\n", encoding="utf-8")
    manifest = json.loads((output / "package.json").read_text(encoding="utf-8"))
    (output / "bin/vera-harness.mjs").chmod(0o755)
    print(f"Staged {manifest['name']}@{manifest['version']} at {output}")


if __name__ == "__main__":
    main()
