"""Validate immutable experiment inputs and explicit optimization boundaries."""

import re
from pathlib import Path, PurePosixPath
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class EvolutionError(RuntimeError):
    """An experiment cannot continue without changing or inspecting its inputs."""


class BudgetError(EvolutionError):
    """Stop search when the next cost cannot be covered or reconciled safely."""


class EvaluationError(EvolutionError):
    """A broken scoring contract must stop search rather than consume more attempts."""


class TaskSpec(BaseModel):
    """Run a trusted verifier outside the editable code, with a fixed task ID.

    Commands are argument arrays, never shell strings. Placeholders are limited to
    {python}, {candidate}, {result}, {task_id}. Exit status scores binary tasks;
    json tasks must write {"score": 0..1, "cost": nonnegative USD} to {result}.
    max_cost reserves the declared upper bound before each verifier invocation.
    """

    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    id: str = Field(pattern=r"^[a-zA-Z0-9][a-zA-Z0-9_-]{0,63}$")
    split: Literal["train", "validation", "holdout"]
    command: list[str] = Field(min_length=1)
    scoring: Literal["exit", "json"] = "exit"
    timeout: int = Field(default=120, ge=1, le=86400)
    max_cost: float = Field(default=0, ge=0)


class EvolutionConfig(BaseModel):
    """Freeze the search program, evaluation manifest and installed dependencies.

    The optimizer receives only train evidence. Holdout tasks run only through
    explicit final evaluation. Source changes are committed into a private Git
    archive; dependency manifest and controller changes are intentionally blocked.
    """

    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    objective: str = Field(min_length=1)
    optimizer: dict = Field(default_factory=dict)
    sandbox: Literal["auto", "docker", "bubblewrap", "local"] = "auto"
    docker_image: str = "vera-evolution-runtime:local"
    credential_env: list[str] = Field(
        default_factory=lambda: ["OPENAI_API_KEY", "ANTHROPIC_API_KEY", "DEEPSEEK_API_KEY"]
    )
    editable: list[str] = Field(default_factory=lambda: ["src/minisweagent/"])
    checks: list[list[str]] = Field(min_length=1)
    tasks: list[TaskSpec] = Field(min_length=2)
    repeats: int = Field(default=1, ge=1, le=20)
    max_iterations: int = Field(default=10, ge=1, le=1000)
    patience: int = Field(default=5, ge=1)
    min_gain: float = Field(default=0.01, gt=0, le=1)
    regression_threshold: float = Field(default=1, gt=0, le=1)
    pass_score: float = Field(default=1, gt=0, le=1)
    cost_limit: float = Field(default=5, gt=0)
    optimizer_cost_limit: float = Field(default=0.5, gt=0)
    optimizer_timeout: int = Field(default=600, ge=1, le=86400)
    check_timeout: int = Field(default=300, ge=1, le=86400)

    @field_validator("editable")
    @classmethod
    def check_editable(cls, paths: list[str]) -> list[str]:
        """Use literal repository-relative files or directory prefixes, not globs."""
        if not paths or any(
            not path
            or "\\" in path
            or ":" in path
            or "*" in path
            or PurePosixPath(path).is_absolute()
            or any(part in {".", "..", ".git"} for part in path.split("/") if part)
            for path in paths
        ):
            raise ValueError("editable must contain relative files or directory prefixes ending in '/'.")
        return paths

    @field_validator("credential_env")
    @classmethod
    def check_credential_names(cls, names: list[str]) -> list[str]:
        """Persist variable names only, never their values."""
        if any(not re.fullmatch(r"[A-Z][A-Z0-9_]*", name) for name in names):
            raise ValueError("credential_env must contain environment variable names.")
        return names

    @model_validator(mode="after")
    def check_manifest(self):
        """Reject ambiguous denominators, shell commands and persisted credentials."""
        if len({task.id for task in self.tasks}) != len(self.tasks):
            raise ValueError("Task IDs must be unique across all splits.")
        if not {"train", "validation"}.issubset({task.split for task in self.tasks}):
            raise ValueError("Include both train and validation tasks.")
        if any(not command or any(not isinstance(arg, str) or not arg for arg in command) for command in self.checks):
            raise ValueError("checks must contain nonempty argument arrays.")
        if any(task.scoring == "exit" and task.max_cost for task in self.tasks):
            raise ValueError("Paid verifiers need json scoring to report their actual cost.")

        def reject_secrets(value):
            if isinstance(value, dict):
                for key, item in value.items():
                    if re.search(r"(^|_)(api_key|token|password|authorization)$", key, re.I) and item:
                        raise ValueError(
                            "Reference credentials through provider environment variables, not config values."
                        )
                    reject_secrets(item)
            elif isinstance(value, list):
                for item in value:
                    reject_secrets(item)

        reject_secrets(self.optimizer)
        if not self.optimizer.get("model", {}).get("model_name"):
            raise ValueError("Pin optimizer.model.model_name explicitly; global model defaults are not reproducible.")
        return self

    def can_edit(self, name: str) -> bool:
        """Keep experiment infrastructure, test definitions and dependencies fixed."""
        protected = ("src/minisweagent/evolution/", "src/minisweagent/run/utilities/evolution.py", "tests/", ".git")
        manifests = {"pyproject.toml", "uv.lock", "setup.py", "setup.cfg", "requirements.txt"}
        if name.startswith(protected) or Path(name).name in manifests:
            return False
        return any(name == path or path.endswith("/") and name.startswith(path) for path in self.editable)
