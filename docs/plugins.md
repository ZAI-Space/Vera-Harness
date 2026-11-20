[English](plugins.md) · [简体中文](zh/plugins.md)

# Plugins

The independent `vera.plugins` module manages capability packages and two
marketplace sources: **GitHub and Gitee**. It adapts packages to Skills, MCP and Subagent modules;
it does not change Agent Loop. Commands do not need a model or API key.

## Choose a source and install

Run these commands from PowerShell, Git Bash or a Linux shell after activating the
project's Python environment:

```shell
vera-extra plugins marketplace use github
vera-extra plugins marketplace search remotion
vera-extra plugins install remotion
vera-extra plugins show remotion
vera-extra plugins enable remotion
vera --skill remotion-remotion-best-practices
```

For the domestic source, use:

```shell
vera-extra plugins marketplace use gitee
vera-extra plugins marketplace search frontend
vera-extra plugins install frontend-design
vera-extra plugins enable frontend-design
vera --skill frontend-design-frontend-design
```

No market URL or custom source configuration is needed. GitHub uses OpenAI's
`openai/plugins` marketplace at its current HEAD (`openai-curated`). Gitee uses
`gitee.com/mirrors/claude-code` at the verified commit
`1718a574950cd8979b27b3e21f5e82760b10e8e0` (tag `v2.1.45`, market `claude-code-plugins`).
This fixed older snapshot retains package files in Gitee; its newer catalog points
back to GitHub. The domestic selection therefore downloads catalog **and package**
from Gitee. Its contents and versions differ from the GitHub source; refreshing this
pinned market doesn't upgrade it beyond this snapshot. Changing the curated domestic
snapshot is a code change in `plugins/manager.py`, not a user configuration burden.

Selection affects subsequent name searches/installations. Previously enabled plugins
remain enabled. Add/install/enable are separate operations; `install --enable` combines
the latter two when explicitly requested. `NAME@MARKETPLACE` can select an already
downloaded catalog without changing the current selection.

Supported catalog sources are relative strings, `local`, `url`, `git-subdir`,
`github` (`repo: owner/repo`) and `git` with GitHub/Gitee HTTPS URLs. A local entry's
`path` is relative to the **repository root**. Same-repository entries are pinned to
the catalog's exact commit. External sources are resolved and pinned when installed.
Unsupported sources such as npm remain visible with an explanation; installing them
fails explicitly. `NOT_AVAILABLE` entries cannot be installed. Other catalog default
policies do not install or activate packages automatically.

Refresh and update are separate operations:

```shell
vera-extra plugins marketplace list
vera-extra plugins marketplace refresh openai-curated
vera-extra plugins update remotion
vera-extra plugins show remotion
vera-extra plugins enable remotion
vera-extra plugins disable remotion
vera-extra plugins rollback remotion FULL_DIGEST_FROM_SHOW
vera-extra plugins enable remotion
vera-extra plugins uninstall remotion
vera-extra plugins marketplace remove openai-curated
```

Updating changed files or rolling back disables the selected version until explicitly
enabled again. Failed downloads, malformed catalogs and invalid packages preserve
the previously registered versions. Uninstall removes registration/history; immutable
cached files remain so an already running session can still read its package. Removing
a marketplace leaves its installed plugins available, but updating them requires the
marketplace again. Restart a run to change its loaded plugin set.

## Direct packages and store selection

```shell
vera-extra plugins install owner/repository --path plugins/example --ref v1.0.0
vera-extra plugins install owner/repository --source gitee --path plugins/example
vera-extra plugins --directory ./my-plugin-store list
```

Repository downloads require Git, including Git for Windows on Windows. There is no
automatic Git installation. Private repositories use the existing Git credential
helper; credentials in source URLs are rejected and no token is saved in the registry.
Remote sources use only the selected committed tree and never checkout submodules
or run Git hooks. The developer Python API also supports local fixture packages for
testing; the marketplace CLI has no custom-host or self-hosting setup flow.

By default, `vera` loads explicitly enabled packages in the global config directory's
`plugins` store. Configuration can restrict this selection, but cannot approve a
disabled package:

```yaml
plugins:
  enabled: true
  # directory: /absolute/path/to/my-plugin-store
  names: [review-kit]
```

`plugins.enabled: false` disables plugin loading for this run. `skills.enabled` and
`skills.disabled` apply to plugin skills as well. Normal project/global skill discovery
continues to work. Capability collisions are errors instead of silent overrides.
Loaded digests are included in trajectory `info.plugins` and the stored run's runtime
fingerprint, so resuming with a changed plugin set is rejected.

## Author a package

Use the portable layout described in [OpenAI's packaging documentation](https://developers.openai.com/plugins/build/plugins):

```text
review-kit/
  plugin.json
  skills/review/SKILL.md
  mcp.json                 # optional
  subagents.json           # optional VERA extension
```

```json
{
  "name": "review-kit",
  "version": "1.0.0",
  "description": "Review a code change.",
  "extensions": {"vera": {"subagents": "./subagents.json"}}
}
```

Portable packages discover `skills/` and `mcp.json` at fixed root paths. Compatibility
manifests are also accepted at `.vera-plugin/plugin.json`, `.codex-plugin/plugin.json`
and `.claude-plugin/plugin.json`; those may declare `skills` (path/list) and `mcpServers`
(mapping/file), defaulting to `skills/` and `.mcp.json`. Root `plugin.json` takes
precedence. A portable `extensions.com.openai` object supplies OpenAI-specific
settings; otherwise a Codex overlay can supply them. These aren't merged.

An MCP file wraps entries in `mcpServers`. Existing VERA MCP settings apply, plus
portable `type: stdio` / `streamable-http` and compatible `http`. For example:

```json
{
  "mcpServers": {
    "docs": {
      "type": "stdio",
      "command": "python",
      "args": ["${PLUGIN_ROOT}/server.py"],
      "env_from": ["DOCS_API_KEY"],
      "allow_tools": ["search"]
    }
  }
}
```

The installed package directory is the default stdio `cwd`. `${PLUGIN_ROOT}`,
`${CLAUDE_PLUGIN_ROOT}` and `${CODEX_PLUGIN_ROOT}` expand in command, args and cwd.
Secrets use `env_from`, `env: {"NAME": "${NAME}"}` or `bearer_token_env` for HTTP.
The compatible HTTP `Authorization: Bearer ${ENV_NAME}` header is also supported.
Literal env mappings, arbitrary headers and OAuth/client-side input placeholders
require adaptation to these existing MCP settings.

The optional VERA `subagents` field is a role mapping or a relative JSON filename;
each value uses the existing SubagentRole schema. Roles declare local skill names
and can refer to bundled MCP tools as `mcp:SERVER/TOOL`. Ordinary registered tools
such as `bash` retain their runtime names. A role inherits the parent model unless
its complete `model` setting selects another one.

All exported skills, servers and roles get a plugin prefix: `review-kit-review`,
`review-kit-docs`, `review-kit-reviewer`. MCP tool names are generated by the existing
MCP naming function, for example `mcp_review-kit-docs_search`; long names use stable
hash suffixes. `show` reports the actual names and connection settings.

## Boundaries and verification

Downloaded code is never executed by add/install/update/show. Explicit activation
allows MCP commands/endpoints to connect on the next run. Normal confirmation and
sandbox external-tool policies still apply: plugin MCP processes run on the host,
and workspace Docker isolation does not isolate them. Install is not a sandbox.

Hooks, commands, hosted Codex Apps and agent Markdown formats are rejected rather
than silently ignored. This supports compatible capability packages, not every
Codex/Claude plugin or their account-specific OAuth/connector services. Native
Python tools can be distributed as MCP servers without importing downloaded code
into the host process. Dependencies are installed by the user; no package-manager
scripts run during plugin installation.

Snapshots reject traversal, symlinks, junctions, submodules, special files, Windows
reserved names and case-insensitive collisions. Limits are 100 MiB / 10,000 files
per package, 1 MiB per JSON object and 1,000 marketplace entries. SHA-256 inventories
are checked before loading. These detect accidental changes, not malicious changes
by someone who can rewrite the user's entire store. SQLite transactions serialize
registry writes. Windows extended paths support long package paths without changing
the machine's registry settings.

See the repository's `.agents/plugins/marketplace.json` and `examples/plugins/` for
working packages. `github` uses the [official GitHub remote MCP server](https://github.com/github/github-mcp-server)
with `GITHUB_TOKEN` supplied only through the process environment; it requires a PAT
and the existing MCP optional dependencies. The example isn't a GitHub credential.

```shell
python -m pytest tests/run/test_plugins.py
```

These tests use real filesystem snapshots, Git archives, CLI subprocesses, SQLite,
MCP stdio servers and an HTTP model protocol fixture. They don't call a paid model
or mutate GitHub repositories.
