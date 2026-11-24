"""Build repository documentation into an existing landing page's docs directory.

Use the current Python environment with the project's documentation dependencies.
The same module is a MkDocs hook: it groups inherited navigation without copying
page content or changing the regular documentation site's configuration.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from mkdocs.config.defaults import MkDocsConfig

ROOT = Path(__file__).resolve().parents[1]
BUILD_MARKER = ".vera-website-docs"
MARKER_CONTENT = "VERA generated website documentation\n"
MAINTENANCE_PAGES = {
    "architecture.md",
    "contributing.md",
    "desktop-api.md",
    "desktop-streaming.md",
    "documentation.md",
    "frontend-integration.md",
    "licenses.md",
    "repository-structure.md",
    "SECURITY.md",
    "taskboard.md",
    "testing.md",
    "website.md",
}


def on_config(config: MkDocsConfig) -> MkDocsConfig:
    """Group the inherited bilingual navigation by reader task, retaining pages.

    This hook changes only the website build. Existing feature subgroups and API
    groups retain their labels, ordering and targets from ``mkdocs.yml``.
    """
    navigation = []
    for language in config.nav:
        title, sections = next(iter(language.items()))
        is_chinese = title == "简体中文"
        usage, maintenance, reference = [], [], []
        for section in sections:
            section_title, pages = next(iter(section.items()))
            if section_title in {"API Reference", "API 参考"}:
                reference.extend(pages)
                continue
            for item in pages:
                target = next(iter(item.values())) if isinstance(item, dict) else item
                if isinstance(target, str) and target.removeprefix("zh/") in MAINTENANCE_PAGES:
                    maintenance.append(item)
                else:
                    usage.append(item)
        labels = (
            ("使用文档", "维护文档", "接口参考") if is_chinese else ("Usage docs", "Maintenance docs", "API reference")
        )
        navigation.append({title: [{labels[0]: usage}, {labels[1]: maintenance}, {labels[2]: reference}]})
    config.nav = navigation
    return config


def checked_output(landing_dir: Path) -> Path:
    """Return a safe docs target, or raise before MkDocs can clean any files.

    Require an existing landing ``index.html`` outside this repository.
    Refuse redirected directories and unmarked output.
    Only the returned directory may be cleaned by MkDocs.
    """
    landing_dir = landing_dir.expanduser().resolve()
    if not (landing_dir / "index.html").is_file():
        raise ValueError(f"Landing index.html is missing: {landing_dir}")
    output = landing_dir / "docs"
    if output.resolve() != output:
        raise ValueError(f"Documentation output must not redirect to another path: {output}")
    if output.is_relative_to(ROOT) or ROOT.is_relative_to(output):
        raise ValueError(f"Documentation output is restricted to an external landing directory: {output}")
    if output.exists():
        if not output.is_dir():
            raise ValueError(f"Documentation output is not a directory: {output}")
        marker = output / BUILD_MARKER
        has_marker = marker.is_file() and marker.read_text(encoding="utf-8") == MARKER_CONTENT
        if any(output.iterdir()) and not has_marker:
            raise ValueError(f"Refusing to clean unrecognized documentation output: {output}")
    return output


def main() -> int:
    """Build with the active interpreter; return MkDocs' status on build failure.

    No packages are installed. The landing page's source files remain unchanged.
    On success, stdout reports source counts and the absolute output directory.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--landing-dir", type=Path, required=True, help="Existing external landing page directory")
    args = parser.parse_args()
    try:
        output = checked_output(args.landing_dir)
    except ValueError as error:
        parser.error(str(error))
    print(f"Checked documentation output: {output}", flush=True)
    output.mkdir(parents=True, exist_ok=True)
    (output / BUILD_MARKER).write_text(MARKER_CONTENT, encoding="utf-8")
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "mkdocs",
            "build",
            "--strict",
            "--config-file",
            str(ROOT / "mkdocs.website.yml"),
            "--site-dir",
            str(output),
        ],
        cwd=ROOT,
        check=False,
    )
    if result.returncode:
        return result.returncode
    english = [path for path in (ROOT / "docs").rglob("*.md") if "zh" not in path.relative_to(ROOT / "docs").parts]
    chinese = list((ROOT / "docs" / "zh").rglob("*.md"))
    print(f"Built {len(english)} English and {len(chinese)} Chinese Markdown sources into {output}")
    print(f"Chinese entry: {output / 'zh' / 'index.html'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
