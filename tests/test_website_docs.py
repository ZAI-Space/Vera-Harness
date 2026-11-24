"""Check website navigation coverage and the build command's cleanup boundary."""

import importlib.util
from pathlib import Path

import pytest
from mkdocs.config import load_config

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("build_website_docs", ROOT / "scripts" / "build_website_docs.py")
website = importlib.util.module_from_spec(spec)
spec.loader.exec_module(website)


def page_targets(node):
    """Collect leaf targets from MkDocs' nested navigation."""
    if isinstance(node, str):
        return [node]
    children = node.values() if isinstance(node, dict) else node
    return [target for child in children for target in page_targets(child)]


def test_website_navigation_retains_all_pages():
    """Regrouping preserves every inherited page once in each language."""
    config = load_config(str(ROOT / "mkdocs.website.yml"))
    previous = page_targets(config.nav)
    website.on_config(config)
    assert sorted(page_targets(config.nav)) == sorted(previous)
    for language, labels in zip(
        config.nav,
        [("Usage docs", "Maintenance docs", "API reference"), ("使用文档", "维护文档", "接口参考")],
        strict=True,
    ):
        sections = next(iter(language.values()))
        assert tuple(next(iter(section)) for section in sections) == labels
        usage, maintenance, reference = [page_targets(section) for section in sections]
        assert any(target.endswith("quickstart.md") for target in usage)
        assert any(target.endswith("documentation.md") for target in maintenance)
        assert reference and all("reference/" in target for target in reference)


def test_output_accepts_new_and_recognized_generated_directory(tmp_path):
    (tmp_path / "index.html").write_text("landing", encoding="utf-8")
    output = website.checked_output(tmp_path)
    assert output == tmp_path / "docs"
    output.mkdir()
    (output / website.BUILD_MARKER).write_text(website.MARKER_CONTENT, encoding="utf-8")
    (output / "index.html").write_text("generated", encoding="utf-8")
    assert website.checked_output(tmp_path) == output


def test_output_refuses_unrecognized_files_without_touching_them(tmp_path):
    (tmp_path / "index.html").write_text("landing", encoding="utf-8")
    output = tmp_path / "docs"
    output.mkdir()
    keep = output / "notes.md"
    keep.write_text("keep this", encoding="utf-8")
    with pytest.raises(ValueError, match="unrecognized"):
        website.checked_output(tmp_path)
    assert keep.read_text(encoding="utf-8") == "keep this"


def test_output_refuses_repository_and_missing_landing(tmp_path, monkeypatch):
    with pytest.raises(ValueError, match="missing"):
        website.checked_output(tmp_path)
    monkeypatch.setattr(website, "ROOT", tmp_path)
    landing = tmp_path / "unrelated"
    landing.mkdir()
    (landing / "index.html").write_text("keep", encoding="utf-8")
    with pytest.raises(ValueError, match="restricted"):
        website.checked_output(landing)


def test_output_refuses_landing_inside_repository(tmp_path, monkeypatch):
    landing = tmp_path / "website"
    landing.mkdir()
    (landing / "index.html").write_text("landing", encoding="utf-8")
    monkeypatch.setattr(website, "ROOT", tmp_path)
    with pytest.raises(ValueError, match="external landing"):
        website.checked_output(landing)


def test_build_requires_an_explicit_external_landing_directory(monkeypatch, capsys):
    monkeypatch.setattr("sys.argv", ["build_website_docs.py"])
    with pytest.raises(SystemExit) as error:
        website.main()
    assert error.value.code == 2
    assert "--landing-dir" in capsys.readouterr().err


def test_output_refuses_redirected_docs_directory(tmp_path):
    (tmp_path / "index.html").write_text("landing", encoding="utf-8")
    elsewhere = tmp_path / "keep"
    elsewhere.mkdir()
    try:
        (tmp_path / "docs").symlink_to(elsewhere, target_is_directory=True)
    except OSError as error:
        if getattr(error, "winerror", None) == 1314:
            pytest.skip("Windows symlink privileges are unavailable")
        raise
    with pytest.raises(ValueError, match="redirect"):
        website.checked_output(tmp_path)
