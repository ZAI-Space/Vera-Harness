"""Official MCP Registry discovery, transport previews and explicit local service registration."""

import os
import re
from copy import deepcopy
from pathlib import Path
from urllib.parse import quote

from vera import global_config_dir
from vera.channels.credentials import private_directory
from vera.evolution.process import experiment_lock, read_json, write_json
from vera.markets.http import catalog_json
from vera.tools import ToolError
from vera.tools.mcp import parse_mcp_servers

DEFAULT_DIRECTORY = global_config_dir / "mcp-services"
_ENV_NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")


class MCPServices:
    """Persist service configurations; adding never activates or starts a service.

    Saved values contain references to environment variables, not credentials.
    Explicit config entries take precedence over saved services of the same name.
    """

    def __init__(self, directory: Path = DEFAULT_DIRECTORY):
        self.directory = Path(directory).expanduser().resolve()
        self.path = self.directory / "services.json"

    def list(self) -> dict:
        """Read installed metadata/configuration; absent stores cause no filesystem writes."""
        return read_json(self.path) if self.path.exists() else {}

    def add(self, plan: dict) -> dict:
        """Save one inspected plan without overwriting an existing name or running commands."""
        if plan["required_inputs"]:
            raise ToolError("Provide required inputs before adding: " + ", ".join(plan["required_inputs"]))
        parse_mcp_servers({plan["name"]: plan["config"]})
        private_directory(self.directory)
        with experiment_lock(self.directory):
            services = self.list()
            if plan["name"] in services:
                raise ToolError("This MCP name is already installed; remove it explicitly before replacing it.")
            services[plan["name"]] = deepcopy(plan)
            write_json(self.path, services)
        return deepcopy(plan)

    def remove(self, name: str) -> None:
        """Remove settings only; running sessions retain their existing connections."""
        private_directory(self.directory)
        with experiment_lock(self.directory):
            services = self.list()
            if name not in services:
                raise ToolError("Unknown installed MCP service.")
            del services[name]
            write_json(self.path, services)

    @classmethod
    def from_config(cls, config: dict):
        """Use the default user store, or the host's explicit mcp_services.directory."""
        return cls(config.get("mcp_services", {}).get("directory", DEFAULT_DIRECTORY))


def merge_services(config: dict, *, catalog: bool = False) -> dict:
    """Make saved services available only to a catalog or an explicit mcp_selection."""
    config = deepcopy(config)
    selected = config.get("mcp_selection", [])
    servers = config.setdefault("mcp_servers", {})
    if not catalog and not selected:
        return config
    installed = MCPServices.from_config(config).list()
    for name, entry in installed.items():
        if catalog or name in selected:
            servers.setdefault(name, deepcopy(entry["config"]))
    return config


class MCPRegistry:
    """Search official latest-version records and compile supported HTTP/npm/PyPI transports.

    Registry presence is publisher metadata, not a safety endorsement. Previews
    expose requirements before adding; package execution happens only on selection.
    """

    def __init__(self, endpoint: str = "https://registry.modelcontextprotocol.io/v0.1"):
        self.endpoint = endpoint.rstrip("/")

    def search(self, query: str = "", *, cursor: str = "", limit: int = 20) -> dict:
        """Return latest active metadata and a cursor; never guess latest from result ordering."""
        parameters = {"search": query, "version": "latest", "limit": min(max(limit, 1), 100)}
        if cursor:
            parameters["cursor"] = cursor
        value = catalog_json(self.endpoint + "/servers", params=parameters)
        entries = []
        for item in value.get("servers", []):
            metadata = item.get("_meta", {}).get("io.modelcontextprotocol.registry/official", {})
            if metadata.get("status", "active") != "active":
                continue
            server = item["server"]
            entries.append({key: server.get(key, "") for key in ("name", "description", "version", "repository")})
        return {"source": self.endpoint, "entries": entries, "next_cursor": value.get("metadata", {}).get("nextCursor")}

    def inspect(self, identifier: str, version: str = "latest") -> dict:
        """Retrieve the publisher's exact version, declared transports and input requirements."""
        value = catalog_json(f"{self.endpoint}/servers/{quote(identifier, safe='')}/versions/{quote(version, safe='')}")
        if (
            value.get("_meta", {}).get("io.modelcontextprotocol.registry/official", {}).get("status", "active")
            != "active"
        ):
            raise ToolError("This MCP registry entry is not active.")
        server = value.get("server")
        if not isinstance(server, dict) or server.get("name") != identifier:
            raise ToolError("The registry returned a different or invalid server.")
        return server

    def preview(
        self,
        identifier: str,
        *,
        name: str | None = None,
        version: str = "latest",
        inputs: dict[str, str] | None = None,
        header_env: dict[str, str] | None = None,
    ) -> dict:
        """Compile a pinned local config; missing non-secret arguments are returned as required_inputs.

        inputs supplies declared non-secret package arguments. header_env maps HTTP
        header names to local variable names. Secret values must never be passed here.
        """
        server = self.inspect(identifier, version)
        alias = name or re.sub(r"[^A-Za-z0-9_-]", "-", identifier.rsplit("/", 1)[-1])[:32]
        missing = []
        prerequisites = []
        remotes = [item for item in server.get("remotes", []) if item.get("type") == "streamable-http"]
        if remotes:
            remote = remotes[0]
            config = {"url": remote["url"]}
            for header in remote.get("headers", []):
                key = header["name"]
                variable = (header_env or {}).get(key)
                if not variable and not header.get("isRequired", False):
                    continue
                variable = variable or "MCP_" + alias.upper().replace("-", "_") + "_" + key.upper().replace("-", "_")
                if not _ENV_NAME.fullmatch(variable):
                    raise ToolError("Header credentials must reference a valid environment variable name.")
                if key.lower() == "authorization":
                    config["bearer_token_env"] = variable
                else:
                    config.setdefault("headers_from", {})[key] = variable
        else:
            packages = [
                item
                for item in server.get("packages", [])
                if item.get("registryType") in {"npm", "pypi"} and item.get("transport", {}).get("type") == "stdio"
            ]
            if not packages:
                raise ToolError("No supported Streamable HTTP, npm or PyPI stdio transport in this entry.")
            package = packages[0]
            kind, package_name, release = package["registryType"], package["identifier"], package.get("version", "")
            pattern = r"(?:@[a-z0-9_.-]+/)?[a-z0-9][a-z0-9_.-]*" if kind == "npm" else r"[A-Za-z0-9][A-Za-z0-9_.-]*"
            version_pattern = (
                r"v?[0-9]+\.[0-9]+\.[0-9]+(?:[-+][A-Za-z0-9.-]+)*" if kind == "npm" else r"[0-9][A-Za-z0-9.+_-]{0,100}"
            )
            expected_registry = "https://registry.npmjs.org" if kind == "npm" else "https://pypi.org"
            if (
                not re.fullmatch(pattern, package_name)
                or not re.fullmatch(version_pattern, release)
                or package.get("registryBaseUrl", expected_registry).rstrip("/") != expected_registry
            ):
                raise ToolError("Only explicitly versioned packages from npmjs.org or pypi.org are supported.")
            if package.get("runtimeArguments"):
                raise ToolError("This package requires custom runtime arguments; configure it manually.")
            config = {
                "command": "npx" if kind == "npm" else "uvx",
                "args": ["-y", f"{package_name}@{release}"] if kind == "npm" else [f"{package_name}=={release}"],
            }
            prerequisites = ["Node.js/npx" if kind == "npm" else "uv/uvx"]
            for argument in package.get("packageArguments", []):
                if argument.get("isSecret"):
                    raise ToolError(
                        "Secret command-line arguments are unsupported; use a service with environment authentication."
                    )
                value = (inputs or {}).get(argument.get("name"), argument.get("value", argument.get("default")))
                variables = argument.get("variables", {})
                if variables:
                    raise ToolError("Templated package arguments require manual configuration.")
                if value is None:
                    if argument.get("isRequired"):
                        missing.append(argument.get("name") or argument.get("valueHint") or "argument")
                    continue
                if argument.get("type") == "named":
                    config["args"].append(argument["name"])
                config["args"].append(str(value))
            for variable in package.get("environmentVariables", []):
                field = "env_from" if variable.get("isRequired", False) else "optional_env_from"
                config.setdefault(field, []).append(variable["name"])
        parse_mcp_servers({alias: config})
        return {
            "name": alias,
            "source": identifier,
            "version": server["version"],
            "config": config,
            "required_inputs": missing,
            "prerequisites": prerequisites,
            "missing_environment": [
                key
                for key in [
                    *config.get("env_from", []),
                    *config.get("headers_from", {}).values(),
                    *([config["bearer_token_env"]] if config.get("bearer_token_env") else []),
                ]
                if key not in os.environ
            ],
        }
