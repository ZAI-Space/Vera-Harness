"""Environment implementations for VERA."""

import copy
import importlib

from vera import Environment

_ENVIRONMENT_MAPPING = {
    "docker": "vera.environments.docker.DockerEnvironment",
    "singularity": "vera.environments.singularity.SingularityEnvironment",
    "local": "vera.environments.local.LocalEnvironment",
    "swerex_docker": "vera.environments.extra.swerex_docker.SwerexDockerEnvironment",
    "swerex_modal": "vera.environments.extra.swerex_modal.SwerexModalEnvironment",
    "bubblewrap": "vera.environments.extra.bubblewrap.BubblewrapEnvironment",
    "contree": "vera.environments.extra.contree.ContreeEnvironment",
}


def get_environment_class(spec: str) -> type[Environment]:
    """Resolve a short name or dotted import path to an environment class.

    Unknown names raise ``ValueError``. Import and attribute errors are reported
    as configuration errors; class-loading errors propagate from the import.
    """
    full_path = _ENVIRONMENT_MAPPING.get(spec, spec)
    try:
        module_name, class_name = full_path.rsplit(".", 1)
        module = importlib.import_module(module_name)
        return getattr(module, class_name)
    except (ValueError, ImportError, AttributeError):
        msg = f"Unknown environment type: {spec} (resolved to {full_path}, available: {_ENVIRONMENT_MAPPING})"
        raise ValueError(msg)


def get_environment(config: dict, *, default_type: str = "") -> Environment:
    """Construct the selected environment from a copied configuration.

    ``environment_class`` takes precedence over ``default_type``. Construction
    can allocate a local, container or remote resource, and its errors propagate.
    """
    config = copy.deepcopy(config)
    environment_class = config.pop("environment_class", default_type)
    return get_environment_class(environment_class)(**config)
