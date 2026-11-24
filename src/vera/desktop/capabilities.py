"""Adapt existing capability managers to desktop settings and picker DTOs."""

from pathlib import Path

from vera.agents.subagents import SubagentConfig
from vera.environments.sandbox_profiles import SandboxProfiles
from vera.markets.docker import DockerCatalog
from vera.plugins import PluginManager, load_plugins
from vera.plugins.source import PluginSource
from vera.terminal.session import COMMANDS
from vera.tools.mcp import parse_mcp_servers
from vera.tools.skills import SkillConfig, discover_skills


class Capabilities:
    """Safe views and explicit mutations; discovery never implies enable/execute."""

    methods = {
        "listProviders",
        "listModels",
        "saveApiKey",
        "removeCredential",
        "addCustomProvider",
        "updateCustomProvider",
        "removeCustomProvider",
        "setProviderBaseUrl",
        "testProvider",
        "listUpstreamModels",
        "getModelPrefs",
        "setModelHidden",
        "setModelsHidden",
        "setProviderModelsHidden",
        "setSubagentModel",
        "setSubagentThinking",
        "setSubagentPreferBuiltin",
        "listSubagents",
        "getBehaviorSettings",
        "getCommandShells",
        "saveBehaviorSettings",
        "getSubagentRoles",
        "saveSubagentRoles",
        "getSandboxProfiles",
        "saveSandboxProfiles",
        "mcpConfigList",
        "mcpConfigUpsert",
        "saveMcpJson",
        "discoverLocalMcpConfigs",
        "loadLocalMcpConfig",
        "mcpConfigRemove",
        "mcpConfigReload",
        "probeMcpServer",
        "listSlashCommands",
        "listSlashCommandsForCwd",
        "getLoadedResources",
        "getPlugins",
        "pluginAction",
        "pluginMarket",
        "getPluginRepositories",
        "addPluginRepository",
        "searchMcpMarket",
        "inspectMcpMarket",
        "addMcpMarket",
        "getScheduledTasks",
        "saveScheduledTask",
        "scheduledAction",
        "getCapabilityStatus",
    }

    def __init__(self, service):
        self.service = service
        self.store = service.store
        self.profiles = SandboxProfiles(self.store.directory / "sandboxes.sqlite3")
        self.plugins = PluginManager(self.store.directory / "plugins")
        self.mcp_market = DockerCatalog(self.store)

    def preferences(self):
        return self.store.get(
            "settings",
            "modelPrefs",
            {"hiddenModels": {}, "subagentModels": {}, "subagentThinking": {}, "subagentPreferBuiltin": True},
        )

    def invoke(self, method: str, args: dict):
        if method in {"discoverLocalMcpConfigs", "loadLocalMcpConfig"}:
            from vera.desktop.mcp_discovery import discover, load

            workspace = Path(args.get("cwd") or self.store.directory).expanduser().resolve(strict=True)
            return discover(workspace) if method == "discoverLocalMcpConfigs" else load(workspace, args["id"])
        providers = self.service.providers
        if method == "getCapabilityStatus":
            return {
                "protocolVersion": 1,
                "permissions": ["confirm", "yolo", "human"],
                "features": {
                    "chat": True,
                    "files": True,
                    "models": True,
                    "approval": True,
                    "skills": True,
                    "mcp": True,
                    "plugins": True,
                    "subagents": True,
                    "sandbox": True,
                    "scheduler": True,
                    "plan": True,
                    "goal": True,
                    "ssh": False,
                    "manualCompaction": False,
                    "lanControl": True,
                },
            }
        if method == "listProviders":
            return providers.list()
        if method == "listModels":
            return providers.models()
        if method in {"saveApiKey", "removeCredential"}:
            return providers.save_key(args["providerId"], args.get("key") if method == "saveApiKey" else None)
        if method in {"addCustomProvider", "updateCustomProvider"}:
            return providers.configure(args["input"])
        if method == "removeCustomProvider":
            values = self.store.get("settings", "providers", {})
            values.pop(args["providerId"], None)
            self.store.save("settings", "providers", values)
            return providers.save_key(args["providerId"], None)
        if method == "setProviderBaseUrl":
            provider = next((item for item in providers.list() if item["id"] == args["providerId"]), None)
            if provider is None:
                raise ValueError("Unknown provider.")
            return providers.configure(
                {
                    "id": provider["id"],
                    "name": provider["name"],
                    "baseUrl": args["baseUrl"],
                    "api": provider.get("api", "openai-completions"),
                    "models": provider["models"],
                    "apiKey": args.get("apiKey"),
                }
            )
        if method == "listUpstreamModels":
            return providers.upstream(args)
        if method == "testProvider":
            from vera.models import get_model

            provider = next((item for item in providers.list() if item["id"] == args["providerId"]), None)
            model_id = args.get("modelId") or (provider["models"][0]["id"] if provider and provider["models"] else None)
            if not model_id:
                return {"ok": False, "error": "Choose a configured model first."}
            config = providers.model_config({"provider": args["providerId"], "modelId": model_id})
            config["model_kwargs"].update(max_tokens=8, timeout=20)
            try:
                model = get_model(config=config)
                model._query([{"role": "user", "content": "Reply OK."}])
                return {"ok": True, "modelId": model_id}
            except Exception:
                return {"ok": False, "error": "Provider request failed. Verify URL, credentials and model access."}
        if method == "getModelPrefs":
            return self.preferences()
        if method.startswith("set") and method in {
            "setModelHidden",
            "setModelsHidden",
            "setProviderModelsHidden",
            "setSubagentModel",
            "setSubagentThinking",
            "setSubagentPreferBuiltin",
        }:
            value = self.preferences()
            if method == "setSubagentPreferBuiltin":
                value["subagentPreferBuiltin"] = args["preferBuiltin"]
            elif method in {"setSubagentModel", "setSubagentThinking"}:
                field = "subagentModels" if method == "setSubagentModel" else "subagentThinking"
                selected = args.get("modelRef", args.get("level"))
                if selected is None:
                    value.setdefault(field, {}).pop(args["agent"], None)
                else:
                    value.setdefault(field, {})[args["agent"]] = selected
            else:
                provider = args["provider"]
                providers_hidden = set(value.get("hiddenProviders", []))
                ids = args.get("modelIds", [args["modelId"]] if "modelId" in args else [])
                if method == "setProviderModelsHidden":
                    providers_hidden.add(provider) if args["hidden"] else providers_hidden.discard(provider)
                    value["hiddenModels"].pop(provider, None)
                    value.setdefault("visibleModels", {}).pop(provider, None)
                    value["hiddenProviders"] = sorted(providers_hidden)
                else:
                    default_hidden = provider in providers_hidden
                    mapping = value.setdefault("visibleModels", {}) if default_hidden else value["hiddenModels"]
                    selected = set(mapping.get(provider, []))
                    for model in ids:
                        selected.add(model) if args["hidden"] != default_hidden else selected.discard(model)
                    if selected:
                        mapping[provider] = sorted(selected)
                    else:
                        mapping.pop(provider, None)
                for optional in ("hiddenProviders", "visibleModels"):
                    if not value.get(optional):
                        value.pop(optional, None)
            self.store.save("settings", "modelPrefs", value)
            return value
        if method == "getBehaviorSettings":
            return self.store.get(
                "settings",
                "behavior",
                {
                    "defaultMode": "agent",
                    "permissionPolicy": "confirm",
                    "commandShell": "git-bash" if __import__("os").name == "nt" else "bash",
                    "defaultSandbox": None,
                },
            )
        if method == "getCommandShells":
            from vera.desktop.shells import command_shells

            return [
                {key: value for key, value in row.items() if key != "command"}
                for row in command_shells(refresh=args.get("refresh", False))
            ]
        if method == "saveBehaviorSettings":
            value = args["settings"]
            if value.get("permissionPolicy") not in {"confirm", "human", "yolo"}:
                raise ValueError("Choose confirm, human or yolo.")
            from vera.desktop.shells import shell_command

            shell_command(value.get("commandShell", "system"))
            self.store.save("settings", "behavior", value)
            return value
        if method in {"getSubagentRoles", "listSubagents"}:
            roles = self.store.get("settings", "roleDrafts", [])
            return (
                roles
                if method == "getSubagentRoles"
                else [
                    {"name": row["name"], "description": row["description"], "source": "user", "model": None}
                    for row in roles
                    if row["enabled"]
                ]
            )
        if method == "saveSubagentRoles":
            roles = {}
            models = {}
            for row in args["roles"]:
                if row["enabled"]:
                    roles[row["name"]] = {
                        key: row[key]
                        for key in (
                            "description",
                            "instructions",
                            "tools",
                            "skills",
                        )
                    }
                    if row.get("model"):
                        providers.model_config(row["model"])
                        models[row["name"]] = row["model"]
            SubagentConfig.model_validate({"roles": roles})
            self.store.save("settings", "roles", roles)
            self.store.save("settings", "roleModels", models)
            self.store.save("settings", "roleDrafts", args["roles"])
            return args["roles"]
        if method == "getSandboxProfiles":
            return {
                "profiles": [
                    {"name": name, **profile.model_dump(mode="json")}
                    for name, profile in self.profiles.list_profiles().items()
                ],
                "status": self.profiles.status(Path(args.get("cwd") or self.store.directory)),
            }
        if method == "saveSandboxProfiles":
            profiles = args["profiles"]
            from vera.environments.sandbox import SandboxConfig

            for row in profiles:
                SandboxConfig.model_validate({key: value for key, value in row.items() if key != "name"})
            existing = self.profiles.list_profiles()
            for row in profiles:
                self.profiles.save(
                    row["name"], {key: value for key, value in row.items() if key != "name"}, replace=True
                )
            for name in existing.keys() - {row["name"] for row in profiles}:
                self.profiles.remove(name)
            return self.invoke("getSandboxProfiles", args)
        if method == "mcpConfigList":
            entries = self.store.get("settings", "mcp", {})
            rows = [
                {
                    "name": name,
                    "source": "user",
                    "enabled": row["enabled"],
                    "exposure": "direct",
                    "tools": [],
                    "description": row.get("description", ""),
                    "verification": self.store.get("mcp-verification", name),
                    "config": row["config"],
                    "transport": {"kind": "url", "url": row["config"]["url"]}
                    if row["config"].get("url")
                    else {"kind": "stdio", "command": row["config"]["command"], "args": row["config"].get("args", [])},
                }
                for name, row in entries.items()
            ]
            return {
                "global": rows,
                "project": [],
                "errors": [],
                "projectTrusted": True,
                "globalPath": str(self.store.path),
            }
        if method == "saveMcpJson":
            from vera.plugins.manifest import _servers

            value = args.get("config")
            if not isinstance(value, dict) or not value:
                raise ValueError("请提供非空的 mcpServers JSON 对象。")
            # Reuse the plugin transport normalizer for standard type/env/header
            # syntax. All entries are validated before any configuration is saved.
            parsed = _servers(self.store.directory, value)
            if not parsed:
                raise ValueError("配置中没有 MCP 服务。")
            entries = self.store.get("settings", "mcp", {})
            for name, config in parsed.items():
                previous = entries.get(name, {})
                entries[name] = {
                    "config": config.model_dump(exclude_none=True),
                    "enabled": previous.get("enabled", False),
                    "description": previous.get("description", ""),
                }
            self.store.save("settings", "mcp", entries)
            for name in parsed:
                self.store.delete("mcp-verification", name)
            return self.mcp_mutation()
        if method == "mcpConfigUpsert":
            row = args.get("input", args)
            if row.get("scope") == "project":
                raise ValueError("Save this MCP service at user scope; project overrides are not supported here.")
            if row.get("exposure", "direct") != "direct":
                raise ValueError("VERA uses direct tools with explicit service selection. Choose direct exposure.")
            entries = self.store.get("settings", "mcp", {})
            config = {key: row[key] for key in ("url", "command", "args") if row.get(key) is not None}
            config = config or entries.get(row["name"], {}).get("config", {})
            parse_mcp_servers({row["name"]: config})
            entries[row["name"]] = {
                "config": config,
                "enabled": row.get("enabled", entries.get(row["name"], {}).get("enabled", False)),
                "description": row.get("description", entries.get(row["name"], {}).get("description", "")),
            }
            self.store.save("settings", "mcp", entries)
            self.store.delete("mcp-verification", row["name"])
            return self.mcp_mutation()
        if method == "mcpConfigRemove":
            if args.get("scope") == "project":
                raise ValueError("Project MCP configuration is not managed by this desktop.")
            entries = self.store.get("settings", "mcp", {})
            entries.pop(args["name"], None)
            self.store.delete("mcp-verification", args["name"])
            self.store.save("settings", "mcp", entries)
            return self.mcp_mutation()
        if method == "mcpConfigReload":
            return self.mcp_mutation()
        if method == "probeMcpServer":
            from vera.desktop.mcp import probe_server

            entry = self.store.get("settings", "mcp", {}).get(args["name"])
            if entry is None:
                raise ValueError("Unknown MCP server.")
            result = probe_server(args["name"], entry["config"])
            if self.store.get("settings", "mcp", {}).get(args["name"]) == entry:
                self.store.save("mcp-verification", args["name"], result)
            return result
        if method in {"listSlashCommands", "listSlashCommandsForCwd", "getLoadedResources"}:
            cwd = (
                Path(self.service.sessions.get(args["sessionId"])["meta"]["cwd"])
                if args.get("sessionId")
                else Path(args.get("cwd") or self.store.directory)
            )
            skills = discover_skills(SkillConfig(directories=[self.store.directory / "skills"]), cwd)
            plugin_config = {"directory": str(self.store.directory / "plugins")}
            if args.get("sessionId"):
                selections = self.service.sessions.get(args["sessionId"])["selections"]
                if "plugins" in selections:
                    plugin_config["names"] = selections["plugins"]
            plugins = load_plugins(
                {"plugins": plugin_config, "subagents": {"roles": self.store.get("settings", "roles", {})}}
            )
            plugin_skills = plugins.skills
            skills.update(plugin_skills)
            if method == "getLoadedResources":
                return {
                    "skills": [
                        {
                            "name": name,
                            "description": skill.description,
                            "scope": "project"
                            if skill.directory.is_relative_to(cwd / ".agents" / "skills")
                            else "user",
                            "source": "plugin" if name in plugin_skills else "VERA",
                            "path": str(skill.directory / "SKILL.md"),
                            "disableModelInvocation": False,
                        }
                        for name, skill in skills.items()
                    ],
                    "extensions": [],
                    "skillDiagnostics": [],
                    "extensionErrors": [],
                }
            availability = self.profiles.status(cwd)
            return (
                [
                    {
                        "name": name.removeprefix("/"),
                        "description": description,
                        "source": "builtin",
                        "supported": name != "/sandbox" or availability["enabled"],
                    }
                    for name, description in COMMANDS.items()
                    if name not in {"/model", "/permissions", "/subagent"}
                ]
                + [
                    {
                        "name": "sandbox:" + row["name"],
                        "invocationName": "sandbox " + row["name"],
                        "description": row["reason"],
                        "source": "builtin",
                        "supported": row["available"],
                    }
                    for row in availability["choices"]
                ]
                + [
                    {
                        "name": "subagent:" + name,
                        "invocationName": "subagent " + name,
                        "description": role["description"],
                        "argumentHint": "<task>",
                        "source": "builtin",
                        "supported": True,
                    }
                    for name, role in sorted(plugins.config.get("subagents", {}).get("roles", {}).items())
                ]
                + [
                    {
                        "name": "skill:" + name,
                        "skillId": name,
                        "description": skill.description,
                        "source": "skill",
                        "supported": True,
                    }
                    for name, skill in skills.items()
                ]
            )
        if method == "searchMcpMarket":
            return self.mcp_market.search(args.get("query", ""), refresh=bool(args.get("refresh")))
        if method == "inspectMcpMarket":
            return self.mcp_market.preview(args["identifier"])
        if method == "addMcpMarket":
            plan = self.mcp_market.preview(args["identifier"])
            if args.get("version") and args["version"] != plan["version"]:
                raise ValueError("目录已更新，请重新查看此服务的配置后添加。")
            if plan["required_inputs"]:
                raise ValueError("Configure the required arguments before adding this service.")
            entries = self.store.get("settings", "mcp", {})
            if plan["name"] in entries:
                raise ValueError("An MCP service already uses this name.")
            entries[plan["name"]] = {"config": plan["config"], "enabled": False, "description": plan["source"]}
            self.store.save("settings", "mcp", entries)
            return self.invoke("mcpConfigList", {})
        if method == "getPlugins":
            rows = [(name, self.plugins.show(name)) for name in self.plugins.list_plugins()]
            return [
                {
                    "id": name,
                    "name": row.get("displayName", name),
                    "description": row.get("description", ""),
                    "longDescription": row.get("longDescription", ""),
                    "icon": row.get("icon", ""),
                    "version": row.get("version", row.get("commit", ""))[:12],
                    "author": row.get("author", {}).get("name", "")
                    if isinstance(row.get("author", {}), dict)
                    else str(row["author"]),
                    "category": "development",
                    "capabilities": [
                        *["skill:" + skill for skill in row.get("skills", [])],
                        *["mcp:" + server for server in row.get("mcp_servers", {})],
                        *["subagent:" + role for role in row.get("subagents", [])],
                    ],
                    "source": row.get("source", ""),
                    "enabled": row["enabled"],
                    "status": "ready",
                }
                for name, row in rows
            ]
        if method == "getPluginRepositories":
            return [
                {"id": "anthropic", "name": "Anthropic 官方 · GitHub"},
                {"id": "github", "name": "Codex 官方 · GitHub"},
                {"id": "gitee", "name": "Claude Code · Gitee"},
                *[
                    {"id": name, "name": name, "source": row["source"]}
                    for name, row in self.plugins.list_marketplaces().items()
                    if name not in {"claude-plugins-official", "openai-curated", "claude-code-plugins"}
                ],
            ]
        if method == "addPluginRepository":
            from vera.plugins.source import normalize_source

            source = normalize_source(args["source"])
            existing = next(
                ((name, row) for name, row in self.plugins.list_marketplaces().items() if row["source"] == source), None
            )
            if existing:
                name, catalog = existing
            else:
                catalog = self.plugins.add_marketplace(source)
                name = catalog["name"]
            alias = {
                "claude-plugins-official": "anthropic",
                "openai-curated": "github",
                "claude-code-plugins": "gitee",
            }.get(name, name)
            return {"id": alias, "name": name, "source": catalog["source"]}
        if method == "pluginMarket":
            source = args.get("source", "anthropic")
            if source in {"github", "gitee"}:
                selected = self.plugins.use_marketplace(PluginSource(source), refresh=bool(args.get("refresh")))
                name = selected["marketplace"]
            elif source == "anthropic":
                name = "claude-plugins-official"
                if name not in self.plugins.list_marketplaces():
                    name = self.plugins.add_marketplace("anthropics/claude-plugins-official")["name"]
                elif args.get("refresh"):
                    self.plugins.refresh_marketplace(name)
            else:
                name = source
                if name not in self.plugins.list_marketplaces():
                    raise ValueError("插件仓库已不存在，请刷新仓库列表后重新选择。")
                if args.get("refresh"):
                    self.plugins.refresh_marketplace(name)
            marketplace_name = name
            catalog = self.plugins.list_marketplaces()[marketplace_name]
            if catalog.get("presentation_version") != 1:
                self.plugins.refresh_marketplace(marketplace_name)
                catalog = self.plugins.list_marketplaces()[marketplace_name]
            return [
                {
                    "id": name,
                    "name": entry.get("displayName", name),
                    "marketplace": marketplace_name,
                    "description": entry.get("description") or entry.get("shortDescription", ""),
                    "longDescription": entry.get("longDescription", ""),
                    "compatibility": entry.get("unsupported", ""),
                    "source": catalog["source"],
                    "version": entry.get("version") or (catalog["commit"] or "local")[:12],
                    "author": entry.get("author", {}).get("name", source)
                    if isinstance(entry.get("author", {}), dict)
                    else entry["author"],
                    "category": str(entry.get("category", "development")).lower()
                    if str(entry.get("category", "development")).lower() in {"development", "design", "productivity"}
                    else "development",
                    "capabilities": (
                        entry.get("capabilities")
                        or [
                            capability
                            for capability, marker in (
                                ("skills", entry.get("skills")),
                                ("mcp", entry.get("mcpServers", entry.get("mcp_servers"))),
                                ("subagents", entry.get("subagents")),
                            )
                            if marker
                        ]
                        or [str(entry.get("category", "development")).lower()]
                    ),
                    "icon": entry.get("icon")
                    or (
                        "skills"
                        if entry.get("skills")
                        else "mcp"
                        if entry.get("mcpServers", entry.get("mcp_servers"))
                        else "subagents"
                        if entry.get("subagents")
                        else str(entry.get("category", "development")).lower()
                    ),
                    "enabled": False,
                    "status": "error" if entry.get("unsupported") else "ready",
                }
                for name, entry in catalog["plugins"].items()
            ]
        if method == "pluginAction":
            action, name = args["action"], args["name"]
            if action == "install":
                if args.get("marketplace"):
                    self.plugins.install_from_marketplace(name, args["marketplace"])
                elif args.get("source"):
                    self.plugins.install(args["source"])
                else:
                    self.plugins.install_named(name)
            elif action in {"enable", "disable"}:
                self.plugins.set_enabled(name, action == "enable")
            elif action == "remove":
                self.plugins.uninstall(name)
            elif action == "update":
                self.plugins.update(name)
            else:
                raise ValueError("Unknown plugin action.")
            return self.invoke("getPlugins", {})
        if method in {"getScheduledTasks", "saveScheduledTask", "scheduledAction"}:
            from vera.desktop.scheduling import ScheduledTasks

            return ScheduledTasks(self.service).invoke(method, args)
        raise ValueError("Unknown capability method.")

    def mcp_mutation(self):
        """Configured services apply at the next runtime; busy sessions keep their snapshot."""
        return {
            "config": self.invoke("mcpConfigList", {}),
            "reload": {
                "reloaded": 0,
                "skipped": [{"sessionId": key, "reason": "streaming"} for key in self.service.sessions.running],
            },
        }
