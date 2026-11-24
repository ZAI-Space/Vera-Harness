"""Fetch GitHub revisions and copy bounded, portable plugin snapshots without running them."""

import os
import re
import shutil
import subprocess
import tarfile
from contextlib import contextmanager
from dataclasses import dataclass
from enum import Enum
from pathlib import Path, PurePosixPath, PureWindowsPath
from tempfile import TemporaryDirectory
from urllib.parse import urlsplit


class PluginError(ValueError):
    """An invalid package, unavailable source or failed plugin management operation."""


class PluginSource(str, Enum):
    """The two supported public repository hosts; no custom host configuration."""

    github = "github"
    gitee = "gitee"


def filesystem_path(path: Path) -> Path:
    """Use Windows extended paths so versioned packages work without the long-path OS setting."""
    path = path.expanduser().resolve()
    value = str(path)
    if os.name == "nt" and not value.startswith("\\\\?\\"):
        value = "\\\\?\\UNC\\" + value[2:] if value.startswith("\\\\") else "\\\\?\\" + value
    return Path(value)


def relative_path(value: str) -> str:
    """Normalize a package-relative POSIX path; reject traversal and Windows aliases."""
    if not isinstance(value, str):
        raise PluginError("Package paths must be strings.")
    path = PurePosixPath(value)
    if not value or path.is_absolute() or PureWindowsPath(value).drive or "\\" in value:
        raise PluginError(f"Expected a package-relative path: {value!r}.")
    for part in path.parts:
        if (
            part == ".."
            or part.rstrip(" .") != part
            or re.search(r'[<>:"|?*\x00-\x1f]', part)
            or part.lower() == ".git"
            or re.fullmatch(r"(?i:con|prn|aux|nul|com[1-9]|lpt[1-9])(?:\..*)?", part)
        ):
            raise PluginError(f"Unsafe package path: {value!r}.")
    return path.as_posix()


def package_path(root: Path, value: str) -> Path:
    """Resolve an existing or prospective path inside a package without following links."""
    candidate = root / relative_path(value)
    if candidate.resolve() != candidate.absolute():
        raise PluginError(f"Package paths cannot traverse links: {value!r}.")
    return candidate


def normalize_source(source: str, host: PluginSource = PluginSource.github) -> str:
    """Resolve owner/repo or local paths; URL-form sources always remain remote."""
    if not isinstance(source, str):
        raise PluginError("Plugin sources must be strings.")
    if "://" not in source and Path(source).expanduser().is_dir():
        return str(Path(source).expanduser().resolve())
    if re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", source):
        source = f"https://{PluginSource(host).value}.com/{source.removesuffix('.git')}.git"
    try:
        url = urlsplit(source)
    except ValueError:
        raise PluginError("Invalid source URL; use a GitHub or Gitee HTTPS clone URL.") from None
    if (
        url.scheme != "https"
        or url.netloc not in {"github.com", "gitee.com"}
        or not re.fullmatch(r"/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+/?", url.path)
        or url.query
        or url.fragment
    ):
        raise PluginError("Use owner/repo on GitHub/Gitee, a credential-free HTTPS clone URL, or a local package.")
    return f"https://{url.netloc}/{url.path.strip('/').removesuffix('.git')}.git"


def _git(directory: Path, *arguments: str, binary: bool = False, input: bytes | None = None) -> str | bytes:
    if shutil.which("git") is None:
        raise PluginError("Git is required for GitHub sources. Install Git (Git for Windows on Windows).")
    environment = {name: value for name, value in os.environ.items() if not name.startswith("GIT_")} | {
        "GIT_TERMINAL_PROMPT": "0",
        "GCM_INTERACTIVE": "never",
    }
    try:
        result = subprocess.run(
            ["git", "-c", "core.hooksPath=", "-c", "protocol.ext.allow=never", *arguments],
            input=input,
            cwd=directory,
            env=environment,
            capture_output=True,
            **({} if binary else {"encoding": "utf-8", "errors": "replace"}),
            timeout=120,
        )
    except subprocess.TimeoutExpired:
        raise PluginError("Git operation timed out after 120 seconds.") from None
    if result.returncode:
        detail = result.stderr.decode("utf-8", errors="replace") if binary else result.stderr
        raise PluginError(f"Git operation failed: {detail.strip()[-1200:]}")
    return result.stdout if binary else result.stdout.strip()


def inventory(root: Path) -> dict[str, str]:
    """Hash up to 10,000 regular files / 100 MiB, rejecting links, aliases and special files."""
    from hashlib import sha256

    files = {}
    total = 0
    aliases = set()
    for directory, directories, names in os.walk(root, followlinks=False):
        directories[:] = sorted(name for name in directories if name != ".git")
        for name in [*directories, *sorted(names)]:
            path = Path(directory) / name
            relative = path.relative_to(root).as_posix()
            relative_path(relative)
            if path.resolve() != path.absolute() or (not path.is_dir() and not path.is_file()):
                raise PluginError(f"Plugin contains a link or special file: {relative!r}.")
            alias = relative.casefold()
            if alias in aliases:
                raise PluginError(f"Plugin contains a case-insensitive path collision: {relative!r}.")
            aliases.add(alias)
            if path.is_file():
                total += path.stat().st_size
                if total > 100 * 1024 * 1024 or len(files) >= 10_000:
                    raise PluginError("Plugin exceeds the 100 MiB / 10,000 file limit.")
                files[relative] = sha256(path.read_bytes()).hexdigest()
    return files


@dataclass(frozen=True)
class Source:
    """A fetched Git revision or local directory; exports never execute package code."""

    location: str
    root: Path
    commit: str | None

    def read_files(self, paths: list[str], *, limit: int = 1024 * 1024) -> dict[str, bytes]:
        """Read bounded metadata in two Git batches instead of launching Git for every file.

        Oversized/non-regular files are omitted; the complete batch is limited to
        16 MiB. Local packages retain the same path and symlink checks as read_file.
        """
        paths = sorted({relative_path(path) for path in paths})
        if not paths:
            return {}
        if self.commit is None:
            result = {}
            total = 0
            for path in paths:
                target = package_path(self.root, path)
                if target.is_file() and target.stat().st_size <= limit:
                    with target.open("rb") as stream:
                        content = stream.read(min(limit, 16 * 1024 * 1024 - total) + 1)
                    if len(content) > limit or total + len(content) > 16 * 1024 * 1024:
                        raise PluginError("Catalog metadata exceeds its file or 16 MiB batch limit.")
                    result[path] = content
                    total += len(content)
            return result
        queries = "".join(f"{self.commit}:{path}\n" for path in paths).encode()
        sizes = _git(self.root, "cat-file", "--batch-check", binary=True, input=queries).splitlines()
        selected = [
            (path, int(row.split()[2]))
            for path, row in zip(paths, sizes)
            if len(row.split()) == 3 and row.split()[1] == b"blob" and int(row.split()[2]) <= limit
        ]
        if sum(size for _, size in selected) > 16 * 1024 * 1024:
            raise PluginError("Catalog metadata exceeds 16 MiB.")
        if not selected:
            return {}
        payload = _git(
            self.root,
            "cat-file",
            "--batch",
            binary=True,
            input="".join(f"{self.commit}:{path}\n" for path, _ in selected).encode(),
        )
        result, offset = {}, 0
        for path, size in selected:
            start = payload.index(b"\n", offset) + 1
            result[path] = payload[start : start + size]
            offset = start + size + 1
        return result

    def read_file(self, path: str, *, limit: int = 1024 * 1024) -> bytes:
        """Read a bounded regular file at this exact revision without checking out code."""
        path = relative_path(path)
        if self.commit is None:
            target = package_path(self.root, path)
            size = target.stat().st_size
        else:
            target = f"{self.commit}:{path}"
            size = int(_git(self.root, "cat-file", "-s", target))
        if size > limit:
            raise PluginError("Catalog metadata file exceeds its size limit.")
        return target.read_bytes() if self.commit is None else _git(self.root, "show", target, binary=True)

    def files(self) -> list[str]:
        """List a bounded source tree for capability discovery without exporting or executing it."""
        if self.commit is None:
            return sorted(inventory(self.root))
        paths = _git(self.root, "ls-tree", "-r", "--name-only", self.commit).splitlines()
        if len(paths) > 20_000:
            raise PluginError("Source tree exceeds 20,000 files.")
        return paths

    def contains(self, path: str) -> bool:
        """Check a catalog path in the fetched revision without exporting the repository."""
        path = relative_path(path)
        if self.commit is None:
            return package_path(self.root, path).is_file()
        return path in _git(self.root, "ls-tree", "--name-only", self.commit, "--", path).splitlines()

    def export(self, path: str, destination: Path) -> Path:
        """Copy a subtree into a new destination; reject unsafe archive members before extracting."""
        path = relative_path(path)
        if self.commit is None:
            source = package_path(self.root, path)
            if not source.is_dir():
                raise PluginError(f"Source directory does not exist: {path!r}.")
            inventory(source)
            shutil.copytree(source, destination, ignore=shutil.ignore_patterns(".git"))
        else:
            archive = self.root / "package.tar"
            tree = self.commit if path == "." else f"{self.commit}:{path}"
            entries = _git(self.root, "ls-tree", "-r", tree).splitlines()
            if any(entry.startswith(("120000 ", "160000 ")) for entry in entries):
                raise PluginError("Plugin sources cannot contain symlinks or submodules.")
            _git(self.root, "archive", "--format=tar", f"--output={archive}", tree)
            if archive.stat().st_size > 110 * 1024 * 1024:
                raise PluginError("Plugin archive exceeds its size limit.")
            with tarfile.open(archive) as reader:
                members = reader.getmembers()
                if len(members) > 20_000 or sum(member.size for member in members) > 100 * 1024 * 1024:
                    raise PluginError("Plugin archive exceeds its size / entry limit.")
                for member in members:
                    relative_path(member.name)
                    if not member.isfile() and not member.isdir():
                        raise PluginError(f"Plugin archives cannot contain links or special files: {member.name!r}.")
                destination.mkdir()
                for member in members:
                    target = destination / member.name
                    if member.isdir():
                        target.mkdir(parents=True, exist_ok=True)
                    else:
                        target.parent.mkdir(parents=True, exist_ok=True)
                        with reader.extractfile(member) as content, target.open("xb") as output:
                            shutil.copyfileobj(content, output)
                        target.chmod(0o755 if member.mode & 0o111 else 0o644)
            inventory(destination)
        return destination


@contextmanager
def open_source(source: str, ref: str = "HEAD"):
    """Fetch one explicit revision into a disposable bare repo; local sources use current files.

    No checkout, submodules, installation hooks or dependency installers run. GitHub
    credentials use the user's existing Git credential helper; secrets aren't stored.
    """
    location = normalize_source(source)
    if not isinstance(ref, str) or not ref or ref.startswith("-") or any(character.isspace() for character in ref):
        raise PluginError("Use HEAD, a branch, tag or commit as --ref.")
    if not location.startswith("https://"):
        yield Source(location, filesystem_path(Path(location)), None)
        return
    with TemporaryDirectory(prefix="vera-plugin-source-") as temporary:
        root = Path(temporary).resolve()
        _git(root, "init", "--bare", "--template=", ".")
        _git(root, "fetch", "--depth=1", "--no-tags", "--", location, ref)
        commit = _git(root, "rev-parse", "FETCH_HEAD^{commit}")
        yield Source(location, root, commit)
