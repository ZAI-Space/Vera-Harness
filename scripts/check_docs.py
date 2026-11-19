"""Check bilingual VERA documentation, local links, source includes and public naming.

Run from any directory: python scripts/check_docs.py. This does not fetch remote
links or claim optional-service validation; mkdocs --strict resolves API symbols.
"""

import re
from pathlib import Path
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"


def check() -> list[str]:
    """Return actionable file-scoped failures without modifying documentation."""
    errors = []
    english = sorted(path for path in DOCS.rglob("*.md") if "zh" not in path.relative_to(DOCS).parts)
    for source in english:
        translated = DOCS / "zh" / source.relative_to(DOCS)
        if not translated.is_file():
            errors.append(f"{source.relative_to(ROOT)}: missing Chinese counterpart")
        elif not re.search(r"[\u4e00-\u9fff]", translated.read_text(encoding="utf-8")):
            errors.append(f"{translated.relative_to(ROOT)}: missing Chinese content")
        else:
            original_api = set(re.findall(r"^::: (\S+)", source.read_text(encoding="utf-8"), re.M))
            translated_api = set(re.findall(r"^::: (\S+)", translated.read_text(encoding="utf-8"), re.M))
            if original_api != translated_api:
                errors.append(f"{translated.relative_to(ROOT)}: API references differ from English")
    for translated in (DOCS / "zh").rglob("*.md"):
        if not (DOCS / translated.relative_to(DOCS / "zh")).is_file():
            errors.append(f"{translated.relative_to(ROOT)}: missing English counterpart")
    pages = [
        *DOCS.rglob("*.md"),
        *DOCS.rglob("*.html"),
        ROOT / "README.md",
        ROOT / "README.en.md",
        *(ROOT / "src").rglob("README.md"),
    ]
    for source in pages:
        text = source.read_text(encoding="utf-8")
        relative = source.relative_to(ROOT).as_posix()
        if (
            source.suffix == ".md"
            and source.name != "_footer.md"
            and relative.startswith("docs/")
            and "[English]" not in text
        ):
            errors.append(f"{relative}: missing language switch")
        if (
            "<img" in text
            and source.name.startswith("README")
            and source.parent == ROOT
            and "vera-logo.png" not in text
        ):
            errors.append(f"{relative}: missing VERA logo")
        # Historical names belong only to the explicit migration guide or cache explanation.
        if any(
            word in text
            for word in (
                "mini-swe-agent.com",
                "github.com/SWE-agent/mini-swe-agent",
                "minimal-agent.com",
                "mini-swe-agent-banner",
                "mini_square.svg",
                "klieret.short.gy",
            )
        ):
            errors.append(f"{relative}: obsolete public branding/link")
        without_code = re.sub(r"```.*?```", "", text, flags=re.S)
        links = re.findall(r"\[[^\]]*\]\(([^)]+)\)", without_code)
        links += re.findall(r'(?:src|href)="([^"{}]+)"', without_code)
        for raw in links:
            target = raw.strip().strip("<>").split(' "', 1)[0]
            address = urlsplit(target)
            if address.netloc.lower() == "github.com":
                repository_path = re.fullmatch(r"/zml-mis/Vera-Harness/(?:blob|tree)/(?:dev|main)/(.+)", address.path)
                if repository_path and not (ROOT / unquote(repository_path[1])).exists():
                    errors.append(f"{relative}: obsolete repository link {target}")
            if address.scheme or address.netloc or not address.path or address.path.startswith("/"):
                continue
            resolved = (source.parent / unquote(address.path)).resolve()
            if not resolved.is_relative_to(ROOT) or not resolved.exists():
                errors.append(f"{relative}: broken local link {target}")
        for target in re.findall(r'--8<-- "([^"]+)"', text):
            if not (ROOT / target).is_file():
                errors.append(f"{relative}: missing source include {target}")
    return errors


if __name__ == "__main__":
    issues = check()
    if issues:
        print("\n".join(issues))
        raise SystemExit(1)
    count = len([path for path in DOCS.rglob("*.md") if "zh" not in path.relative_to(DOCS).parts])
    print(f"Documentation checks passed: {count} English/Chinese pairs, README editions and local links.")
