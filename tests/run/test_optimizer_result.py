"""Validate the trusted controller's handling of optimizer-owned filesystem results."""

import json
import os

import pytest

from tests.conftest import create_symlink
from vera.evolution.config import EvolutionError
from vera.evolution.process import read_optimizer_result


def test_optimizer_result_accepts_only_bounded_regular_json(tmp_path):
    path = tmp_path / "optimizer-result.json"
    path.write_text(json.dumps({"cost": 0, "status": "Submitted"}), encoding="utf-8")
    assert read_optimizer_result(path) == {"cost": 0, "status": "Submitted"}
    path.write_bytes(b" " * (1024 * 1024 + 1))
    with pytest.raises(EvolutionError, match="1 MiB"):
        read_optimizer_result(path)
    path.write_text("[]", encoding="utf-8")
    with pytest.raises(EvolutionError, match="JSON object"):
        read_optimizer_result(path)
    path.write_text("{", encoding="utf-8")
    with pytest.raises(json.JSONDecodeError):
        read_optimizer_result(path)
    with pytest.raises(EvolutionError, match="regular"):
        read_optimizer_result(tmp_path)


@pytest.mark.skipif(not hasattr(os, "mkfifo"), reason="POSIX FIFO required")
def test_optimizer_result_rejects_fifo_without_opening_it(tmp_path):
    path = tmp_path / "optimizer-result.json"
    os.mkfifo(path)
    with pytest.raises(EvolutionError, match="regular"):
        read_optimizer_result(path)


def test_optimizer_result_rejects_links(tmp_path):
    original = tmp_path / "report.json"
    original.write_text('{"status":"Submitted","cost":0}', encoding="utf-8")
    symbolic = tmp_path / "symbolic.json"
    create_symlink(symbolic, original)
    with pytest.raises(EvolutionError, match="regular"):
        read_optimizer_result(symbolic)
    linked = tmp_path / "hard.json"
    os.link(original, linked)
    with pytest.raises(EvolutionError, match="regular"):
        read_optimizer_result(linked)
