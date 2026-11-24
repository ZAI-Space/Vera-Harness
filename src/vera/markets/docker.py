"""Docker's curated MCP catalog with an offline snapshot and pinned transport previews."""

import json
import os
import re
import threading
from datetime import datetime, timezone
from pathlib import Path

import requests
import yaml

from vera.tools import ToolError
from vera.tools.mcp import parse_mcp_servers

CATALOG_URL = "https://desktop.docker.com/mcp/catalog/v3/catalog.yaml"
CATALOG_REPOSITORY = "https://github.com/docker/mcp-registry"
SNAPSHOT = Path(__file__).resolve().parents[1] / "config/markets/docker.json"

# Summaries of the publishers' declared tools; original descriptions remain intact.
SUMMARIES_ZH = {
    "playwright": "浏览器自动化：访问网页、定位元素、填写表单、执行交互并获取页面快照和截图。",
    "github-official": "GitHub 官方服务：搜索仓库代码，管理 Issue、分支和 Pull Request，读取提交与发布记录。",
    "context7": "获取软件库和框架的最新版本文档与代码示例，为开发任务补充准确上下文。",
    "brave": "通过 Brave Search 搜索网页、图片、新闻和视频，获取搜索结果与页面内容。",
    "firecrawl": "搜索、抓取和遍历网站，将网页转换为 Markdown 或结构化数据，支持网页交互。",
    "tavily": "面向 AI 的网页搜索与内容提取，为调研和问答提供网络资料。",
    "exa": "语义网页搜索与内容检索，查找相关网页并提取可用于研究的内容。",
    "mongodb": "连接 MongoDB，查看数据库和集合结构、执行查询并辅助数据库管理。",
    "stripe": "连接 Stripe，查询和管理客户、支付、订阅等业务资源；需要配置对应 API 权限。",
    "notion": "Notion 官方服务：搜索、读取和更新页面、数据源与内容块，管理工作区知识。",
    "elasticsearch": "连接 Elasticsearch，探索索引结构、搜索文档并分析检索数据。",
    "grafana": "连接 Grafana，查询仪表盘、指标和日志，辅助监控分析与故障排查。",
    "neon": "管理 Neon PostgreSQL 项目与数据库分支，探索表结构并执行 SQL 操作。",
    "dockerhub": "搜索 Docker Hub 镜像仓库，查看镜像标签与仓库信息。",
}


class DockerCatalog:
    """Serve the saved catalog immediately; only an explicit refresh uses the network.

    Browsing/previewing never pulls images or starts Docker. Installation records
    immutable image digests; credentials remain environment variable references.
    """

    def __init__(self, store):
        self.store = store
        self.lock = threading.Lock()
        cached = store.get("market-cache", "docker")
        valid = (
            isinstance(cached, dict)
            and isinstance(cached.get("registry"), dict)
            and all(isinstance(row, dict) for row in cached["registry"].values())
            and isinstance(cached.get("recommended"), list)
            and all(isinstance(name, str) for name in cached["recommended"])
            and isinstance(cached.get("updatedAt"), str)
        )
        self.data = cached if valid else json.loads(SNAPSHOT.read_text(encoding="utf-8"))

    def refresh(self) -> None:
        """Replace the cache after a bounded, validated fetch; keep old data on failure."""
        with self.lock:
            try:
                with requests.get(CATALOG_URL, stream=True, timeout=(5, 20), allow_redirects=False) as response:
                    response.raise_for_status()
                    content = bytearray()
                    for chunk in response.iter_content(65536):
                        content.extend(chunk)
                        if len(content) > 2 * 1024 * 1024:
                            raise ToolError("Docker catalog exceeds 2 MiB.")
                value = yaml.safe_load(bytes(content))
            except (requests.RequestException, yaml.YAMLError):
                raise ToolError("Docker 目录更新失败，请检查网络后重试；已保留上次目录。") from None
            if not isinstance(value, dict) or not isinstance(value.get("registry"), dict):
                raise ToolError("Docker catalog returned an invalid registry.")
            entries = value["registry"]
            if any(not isinstance(row, dict) for row in entries.values()):
                raise ToolError("Docker catalog returned invalid service entries.")
            for name, row in entries.items():
                previous = self.data["registry"].get(name, {})
                if previous.get("icon") == row.get("icon") and previous.get("iconData"):
                    row["iconData"] = previous["iconData"]
            updated = {**self.data, "updatedAt": datetime.now(timezone.utc).date().isoformat(), "registry": entries}
            self.store.save("market-cache", "docker", updated)
            self.data = updated

    def search(self, query: str = "", *, refresh: bool = False) -> dict:
        """Prioritize established publishers; searches cover the complete Docker catalog locally."""
        if refresh:
            self.refresh()
        needle = query.strip().casefold()
        recommended = self.data["recommended"]
        names = recommended if not needle else [*recommended, *sorted(set(self.data["registry"]) - set(recommended))]
        rows = []
        for name in names:
            row = self.data["registry"].get(name)
            if (
                not row
                or needle
                not in " ".join(
                    [name, row.get("title", ""), row.get("description", ""), SUMMARIES_ZH.get(name, "")]
                ).casefold()
            ):
                continue
            rows.append(
                {
                    "name": name,
                    "title": row.get("title", name),
                    "description": row.get("description", ""),
                    "descriptionZh": SUMMARIES_ZH.get(name, ""),
                    "version": row.get("image", "").rsplit("@", 1)[-1][:19] or "HTTP",
                    "icon": row.get("iconData") or row.get("icon", ""),
                    "repository": row.get("upstream") or row.get("source") or CATALOG_REPOSITORY,
                    "category": row["metadata"].get("category", "") if isinstance(row.get("metadata"), dict) else "",
                    "toolCount": len(row.get("tools", [])),
                    "transport": "HTTP" if row.get("remote") else "Docker",
                    "recommended": name in recommended,
                }
            )
        return {
            "source": CATALOG_REPOSITORY,
            "updatedAt": self.data["updatedAt"],
            "entries": rows[:60],
            "total": len(rows),
        }

    def preview(self, identifier: str) -> dict:
        """Compile supported remote/container options and expose unresolved configuration explicitly."""
        row = self.data["registry"].get(identifier)
        if not row or not re.fullmatch(r"[a-z][a-z0-9-]{0,47}", identifier):
            raise ToolError("Unknown Docker MCP service.")
        required = []
        environment = set()
        if remote := row.get("remote"):
            if remote.get("transport_type") != "streamable-http":
                raise ToolError("此服务的远程协议尚不支持，请使用 JSON 配置。")
            config = {"url": remote["url"]}
            for name, value in remote.get("headers", {}).items():
                match = re.fullmatch(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}", value)
                if not match:
                    raise ToolError("此服务需要自定义请求头，请使用 JSON 配置。")
                config.setdefault("headers_from", {})[name] = match[1]
                environment.add(match[1])
            prerequisites = ["HTTP · API Key 或账号授权要求请参阅服务说明"]
        else:
            image = row.get("image", "")
            if not re.fullmatch(r"[a-z0-9./_-]+@sha256:[a-f0-9]{64}", image):
                raise ToolError("此服务没有固定摘要的镜像，请查看官方说明后配置 JSON。")
            arguments = ["run", "--rm", "-i"]
            environment = {secret["env"] for secret in row.get("secrets", []) if secret.get("env")}
            for key in sorted(environment):
                arguments.extend(["--env", key])
            variables = row.get("env", [])
            if not isinstance(variables, list):
                raise ToolError("此服务的环境变量格式无效，请参阅官方说明并使用 JSON 配置。")
            for variable in variables:
                if (
                    not isinstance(variable, dict)
                    or not isinstance(variable.get("name"), str)
                    or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", variable["name"])
                    or "value" not in variable
                    or not isinstance(variable["value"], (str, int, float, bool))
                ):
                    raise ToolError("此服务的环境变量格式无效，请参阅官方说明并使用 JSON 配置。")
                name, value = variable["name"], str(variable["value"])
                if "{{" in value:
                    # Optional settings (such as Firecrawl's self-host URL) retain upstream defaults.
                    if any(config.get("required") for config in row.get("config", [])):
                        required.append(name)
                    continue
                if "$" in value:
                    required.append(name)
                    continue
                arguments.extend(["--env", f"{name}={value}"])
            if row.get("volumes"):
                required.append("挂载目录（在 JSON 中指定 docker --mount）")
            arguments.append(image)
            for argument in row.get("command", []):
                if "$" in argument or "{{" in argument:
                    required.append("服务启动参数（请参阅官方说明）")
                else:
                    arguments.append(argument)
            config = {"command": "docker", "args": arguments, "env_from": sorted(environment)}
            prerequisites = ["Docker Engine（需已安装并运行，首次启动会拉取镜像）"]
        parse_mcp_servers({identifier: config})
        return {
            "name": identifier,
            "source": CATALOG_REPOSITORY,
            "version": row.get("image", "HTTP"),
            "config": config,
            "required_inputs": required,
            "missing_environment": sorted(key for key in environment if key not in os.environ),
            "prerequisites": prerequisites,
        }
