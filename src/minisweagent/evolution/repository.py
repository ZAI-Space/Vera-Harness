"""Archive source generations without changing the developer's branches or index."""

import os
import subprocess
from pathlib import Path

from minisweagent.evolution.config import EvolutionConfig, EvolutionError


def git(directory: Path, *arguments: str) -> str:
    """Execute Git with explicit paths and raise on failure, preserving NUL output."""
    return subprocess.check_output(
        ["git", "-C", str(directory), *arguments],
        text=True,
        encoding="utf-8",
        stderr=subprocess.PIPE,
        env=os.environ | {"GIT_TERMINAL_PROMPT": "0"},
    )


def source_patch(archive: Path, baseline: str, candidate: str) -> bytes:
    """Preserve binary patches and CRLF context exactly; never decode diff output."""
    return subprocess.check_output(
        ["git", "-C", str(archive), "diff", "--binary", "--no-ext-diff", "--no-textconv", baseline, candidate],
        stderr=subprocess.PIPE,
    )


def create_archive(source: Path, root: Path) -> str:
    """Copy a clean committed source tree into an independent Git object database."""
    if git(source, "status", "--porcelain").strip():
        raise EvolutionError("Commit the source baseline before creating an experiment.")
    commit = git(source, "rev-parse", "HEAD").strip()
    subprocess.run(
        ["git", "clone", "--no-hardlinks", "--no-local", str(source), str(root / "archive")],
        check=True,
        capture_output=True,
    )
    archive = root / "archive"
    git(archive, "config", "user.name", "Vera Evolution")
    git(archive, "config", "user.email", "evolution@localhost")
    git(archive, "config", "commit.gpgsign", "false")
    git(archive, "config", "core.hooksPath", "")
    git(archive, "remote", "remove", "origin")
    git(archive, "update-ref", "refs/vera/baseline", commit)
    return commit


def checkout(root: Path, name: str, commit: str) -> Path:
    """Create and retain a detached worktree in the experiment-owned directory."""
    destination = root / "workspaces" / name
    destination.parent.mkdir(exist_ok=True)
    if destination.exists():
        raise EvolutionError(f"Workspace already exists: {destination}")
    git(root / "archive", "worktree", "add", "--detach", str(destination), commit)
    return destination


def commit_candidate(workspace: Path, base: str, config: EvolutionConfig) -> tuple[str, list[str]]:
    """Check the complete diff against the immutable base, including optimizer commits.

    Symlinks and submodules cannot enter an evolved version. Ignored artifacts are
    excluded from snapshots; all evaluations use a fresh checkout of the commit.
    """
    common = Path(git(workspace, "rev-parse", "--git-common-dir").strip())
    common = common if common.is_absolute() else workspace / common
    if common.resolve() != (workspace.parent.parent / "archive" / ".git").resolve():
        raise EvolutionError("Candidate Git metadata no longer belongs to this experiment archive.")
    paths = set(git(workspace, "diff", "--name-only", "-z", base).split("\0"))
    paths.update(git(workspace, "ls-files", "--others", "--exclude-standard", "-z").split("\0"))
    paths.discard("")
    if not paths:
        raise EvolutionError("Candidate made no source changes.")
    if forbidden := sorted(name for name in paths if not config.can_edit(name)):
        raise EvolutionError("Candidate changed protected paths: " + ", ".join(forbidden))
    if any((workspace / name).is_symlink() for name in paths):
        raise EvolutionError("Candidate source cannot contain symlinks.")
    git(workspace, "add", "--all")
    if any(line.startswith(("120000 ", "160000 ")) for line in git(workspace, "ls-files", "--stage").splitlines()):
        raise EvolutionError("Source snapshots cannot contain symlinks or submodules.")
    if git(workspace, "diff", "--cached", "--name-only").strip():
        git(workspace, "-c", "core.hooksPath=", "commit", "-m", "feat(evolution): capture source candidate")
    commit = git(workspace, "rev-parse", "HEAD").strip()
    git(workspace, "update-ref", f"refs/vera/candidates/{workspace.name}", commit)
    return commit, sorted(paths)
