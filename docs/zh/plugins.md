[English](../plugins.md) · [简体中文](plugins.md)

# 插件

独立插件模块把能力包适配到 Skill、MCP 和 Subagent，不修改循环。预置市场仅 GitHub 与 Gitee，管理命令不需要模型密钥。安装与启用分开，安装不运行下载仓库中的钩子或任意初始化脚本。

## 市场和安装

GitHub 使用 openai/plugins 市场，Gitee 使用已固定的镜像快照。国内快照与 GitHub 的内容/版本可以不同；GitHub 市场来自 `openai/plugins` 当前 HEAD（`openai-curated`）；Gitee 来源为 `https://gitee.com/mirrors/claude-code`，固定提交 `1718a574950cd8979b27b3e21f5e82760b10e8e0`（tag `v2.1.45`，市场名 `claude-code-plugins`）。此快照的目录和插件包均从 Gitee 下载，refresh 只刷新固定快照，不自动升级版本；更新预置快照需修改 `plugins/manager.py`。选择只影响后续搜索/安装，不改变已启用插件。外部仓库按安装时的提交固定，同仓库子目录按目录所在提交固定。

市场支持已声明的相对目录、local、url、git-subdir、github，以及 GitHub/Gitee HTTPS Git 来源；不支持的 npm 等条目可见但不能安装。NOT_AVAILABLE 明确不可用，不自动回退。刷新目录和更新插件是两项操作。更新或回滚改变内容后禁用该版本，用户重新启用才加载；移除市场不删除已安装包。

## 运行时与包格式

默认加载用户插件库中明确启用的包，`plugins.names` 进一步选择，不能批准禁用包；`plugins.enabled: false` 关闭。配置冲突直接报错，不覆盖现有能力。插件 Skill 仍受 enabled/disabled 约束，运行中的快照不因设置变更改变。轨迹与恢复指纹记录插件摘要，版本变化会阻止不兼容恢复。

包使用 plugin.json、skills/、可选 mcp.json 和 subagents.json；也接受受支持的兼容 manifest 布局。VERA 扩展通过 extensions.vera 引用角色定义。角色模型/工具限制沿用既有模块。插件权限声明不能替代宿主对工具、远程服务和沙箱的授权。

## 来源与存储边界

远程下载需要 Git，使用用户已有凭据助手，不保存 URL 密钥，不运行子模块和 Git hooks。只接受支持主机的 HTTPS 或开发测试的本地包，不提供任意自建市场配置流程。库使用内容摘要记录、固定版本、锁和原子更新；拒绝越界路径、链接、大小超限及不便携文件。启用包仍代表信任其提供的指令/能力，需检查来源。命令、完整包示例和当前固定市场版本保留在下方。

## 配置、命令与源码示例

```shell
vera-extra plugins marketplace use github
vera-extra plugins marketplace search remotion
vera-extra plugins install remotion
vera-extra plugins show remotion
vera-extra plugins enable remotion
vera --skill remotion-remotion-best-practices
```

```shell
vera-extra plugins marketplace use gitee
vera-extra plugins marketplace search frontend
vera-extra plugins install frontend-design
vera-extra plugins enable frontend-design
vera --skill frontend-design-frontend-design
```

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

```shell
vera-extra plugins install owner/repository --path plugins/example --ref v1.0.0
vera-extra plugins install owner/repository --source gitee --path plugins/example
vera-extra plugins --directory ./my-plugin-store list
```

```yaml
plugins:
  enabled: true
  # directory: /absolute/path/to/my-plugin-store
  names: [review-kit]
```

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

```shell
python -m pytest tests/run/test_plugins.py
```
