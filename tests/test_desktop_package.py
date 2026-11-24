"""Protect clean-checkout desktop packaging from ignored local assets."""

import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("build_desktop_package", ROOT / "scripts/build_desktop_package.py")
builder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)


def test_staging_uses_tracked_logo_without_a_local_build_directory(tmp_path, monkeypatch):
    """A fresh checkout produces both app and corresponding-source icons."""
    for name in ("out/main", "src/main", "third_party", "patches", "scripts"):
        (tmp_path / "desktop" / name).mkdir(parents=True)
    (tmp_path / "desktop/out/main/index.js").write_text("export {};", encoding="utf-8")
    for name in (
        "package.json",
        "package-lock.json",
        "electron.vite.config.ts",
        "tsconfig.base.json",
        "tsconfig.node.json",
        "tsconfig.web.json",
        "vitest.config.ts",
    ):
        (tmp_path / "desktop" / name).write_text("{}", encoding="utf-8")
    source = tmp_path / "packages/desktop-launcher"
    (source / "bin").mkdir(parents=True)
    (source / "bin/vera-harness.mjs").write_text("// launcher", encoding="utf-8")
    (source / "package.json").write_text(
        json.dumps({"name": "vera-harness", "version": "0.1.0-alpha.1"}), encoding="utf-8"
    )
    for name in ("LICENSE.md", "THIRD_PARTY_NOTICES.md"):
        (tmp_path / name).write_text("license", encoding="utf-8")
    (tmp_path / "docs/assets").mkdir(parents=True)
    (tmp_path / "docs/assets/vera-logo.png").write_bytes(b"tracked-logo")

    def build_wheel(command, *, check):
        assert check and command[1:4] == ["-m", "build", "--wheel"]
        wheel_dir = Path(command[command.index("--outdir") + 1])
        wheel_dir.mkdir(parents=True)
        (wheel_dir / "vera_harness-0.1.0a1-py3-none-any.whl").write_bytes(b"fixture-wheel")

    monkeypatch.setattr(builder, "ROOT", tmp_path)
    monkeypatch.setattr(builder.subprocess, "run", build_wheel)
    builder.main()
    assert not (tmp_path / "desktop/build").exists()
    output = tmp_path / "dist/npm"
    assert (output / "build/icon.png").read_bytes() == b"tracked-logo"
    assert (output / "source/build/icon.png").read_bytes() == b"tracked-logo"
    assert (output / "source/tsconfig.base.json").is_file()
