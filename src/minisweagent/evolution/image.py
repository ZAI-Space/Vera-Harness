"""Build the optional optimizer image from committed, explicitly selected files."""

import io
import subprocess
import tarfile
import tempfile
from pathlib import Path

from minisweagent.evolution.config import EvolutionError
from minisweagent.evolution.repository import git

_DOCKERFILE = """FROM python:3.12-slim
RUN apt-get update && apt-get install -y --no-install-recommends git ca-certificates && rm -rf /var/lib/apt/lists/*
COPY . /opt/vera
RUN pip install --no-cache-dir '/opt/vera[mcp]' pytest ruff && rm -rf /opt/vera
ENV PYTHONUTF8=1 PYTHONDONTWRITEBYTECODE=1 HOME=/tmp
"""


def prepare_image(source: Path, image: str) -> str:
    """Build once before experiments; never include .env, local state or worktree dirt.

    Uses the committed project dependency declarations. The returned image ID,
    rather than its mutable tag, is persisted by experiment initialization.
    """
    source = source.resolve()
    commit = git(source, "rev-parse", "HEAD").strip()
    archive = subprocess.check_output(
        [
            "git",
            "-C",
            str(source),
            "archive",
            commit,
            "pyproject.toml",
            "README.md",
            "LICENSE.md",
            "src",
        ]
    )
    with tempfile.TemporaryDirectory(prefix="vera-evolution-image-") as temporary:
        context = Path(temporary)
        with tarfile.open(fileobj=io.BytesIO(archive)) as package:
            for member in package.getmembers():
                destination = context / member.name
                if not destination.resolve().is_relative_to(context) or not (member.isfile() or member.isdir()):
                    raise EvolutionError("The committed build context contains links or special files.")
                if member.isdir():
                    destination.mkdir(parents=True, exist_ok=True)
                else:
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    destination.write_bytes(package.extractfile(member).read())
        (context / "Dockerfile").write_text(_DOCKERFILE, encoding="utf-8")
        subprocess.run(["docker", "build", "--tag", image, str(context)], check=True)
    return subprocess.check_output(["docker", "image", "inspect", "--format", "{{.Id}}", image], text=True).strip()
