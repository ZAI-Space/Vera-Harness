import type { Language, MessageKey } from "./index";

/** Connected product copy replaces extraction-preview wording without changing preview mode. */
export const runtimeCopy: Record<Language, Partial<Record<MessageKey, string>>> = {
	zh: {
		"settings.mcp.advancedHint":
			"配置由本机后端保存。参数可使用 JSON 字符串数组，含空格的路径作为一个数组项。",
		"settings.mcp.summary": "已配置 {total} 台服务器 · 已发现 {tools} 个工具",
		"settings.mcp.state.idle": "待任务连接",
		"settings.mcp.toolWrite": "按当前权限模式执行",
		"settings.mcp.toolReadOnly": "标记为只读；按当前权限模式执行",
		"settings.mcp.noActiveSession": "服务在任务开始时连接，结束后关闭。可先测试连接并查看工具清单。",
		"settings.mcp.reloadApplied": "配置已保存，下次任务生效",
		"settings.mcp.reconnect": "重新读取配置",
		"settings.mcp.configFiles": "配置存储",
		"settings.mcp.reloadExplain": "配置由本机后端管理。保存和启停对下次任务生效；连接测试不会执行工具。",
		"workspace.preview": "配置与运行记录保存在本机。安装、启用和执行分别确认。",
		"behavior.frontendNotice": "配置保存到本机后端，从下一次任务开始生效。",
		"behavior.shellHint": "本地命令使用 Bash；Windows 使用 Git Bash，隔离环境使用自身的 Shell。",
		"subagents.frontendNotice": "角色由本机 Runtime 执行，使用独立上下文；模板中的读写工具已适配当前能力。",
		"modelAdvanced.frontendHint": "参数在下一次任务请求中生效；不支持的参数由服务商明确报错。",
		"modelAdvanced.testPending": "保存后可在配置列表中测试。",
		"plugins.addPreview": "安装插件",
		"plugins.addHint": "下载并安装“{name}”。安装后需单独启用，才会参与后续任务。",
		"plugins.removeTitle": "卸载插件",
		"plugins.removeHint": "卸载“{name}”并停止后续加载？正在运行的任务保留已加载版本。",
		"plugins.emptyHint": "选择 GitHub 或 Gitee 市场，查看后安装所需插件。",
		"plugins.exampleCatalog": "市场内容按所选来源加载；安装与启用分开。",
		"plugins.groups.active": "已启用",
		"plugins.toggle": "启用 {name}",
		"plugins.saveSource": "安装来源插件",
		"plugins.sourceDraft": "未提供能力说明",
		"scheduled.saveDraft": "保存任务",
		"scheduled.taskCount": "{count} 个任务",
		"scheduled.enabledDraft": "已启用",
		"scheduled.pausedDraft": "已暂停",
		"scheduled.toggle": "启用此任务",
		"scheduled.emptyHint":
			"安排频率、内容和工作目录，保存后再启用。后台执行需明确选择 YOLO，每次使用独立上下文。",
		"scheduled.noRuns": "暂无运行记录，启用任务或选择立即运行。",
		"scheduled.deleteTitle": "删除任务",
		"scheduled.deleteHint": "删除“{title}”并取消后续调度？已有运行记录保留。",
		"scheduled.invalidDraft": "检查任务内容与时间。后台任务需选择 YOLO 和每次新建会话，并配置可用模型。",
	},
	en: {
		"settings.mcp.advancedHint":
			"Saved by the local backend. Arguments accept a JSON string array; keep paths with spaces in one item.",
		"settings.mcp.summary": "{total} configured servers · {tools} discovered tools",
		"settings.mcp.state.idle": "Connects during tasks",
		"settings.mcp.toolWrite": "Uses the current permission policy",
		"settings.mcp.toolReadOnly": "Marked read-only; uses the current permission policy",
		"settings.mcp.noActiveSession":
			"Tasks open and close their own connections. Test a service to inspect its tools first.",
		"settings.mcp.reloadApplied": "Saved; applies to the next task",
		"settings.mcp.reconnect": "Reload configuration",
		"settings.mcp.configFiles": "Configuration storage",
		"settings.mcp.reloadExplain":
			"Managed by the local backend. Saving affects the next task; connection tests do not execute tools.",
		"workspace.preview":
			"Configuration and run history stay on this computer. Install, enable and execute are separate actions.",
		"behavior.frontendNotice": "Saved by the local backend; applies to the next task.",
		"behavior.shellHint":
			"Local commands use Bash, including Git Bash on Windows. Sandboxes use their own shell.",
		"subagents.frontendNotice":
			"Roles run in the shared Runtime with independent contexts. Template tools are adapted to available capabilities.",
		"modelAdvanced.frontendHint":
			"Options apply to the next task. Providers report unsupported parameters explicitly.",
		"modelAdvanced.testPending": "Save first, then test from the configuration list.",
		"plugins.addPreview": "Install plugin",
		"plugins.addHint": "Download and install “{name}”. Enable it separately before using it in future tasks.",
		"plugins.removeTitle": "Uninstall plugin",
		"plugins.removeHint": "Uninstall “{name}” for future tasks? Active runs retain their loaded version.",
		"plugins.emptyHint": "Choose GitHub or Gitee, inspect the marketplace and install a plugin.",
		"plugins.exampleCatalog":
			"Packages come from the selected marketplace. Installation does not enable a plugin.",
		"plugins.groups.active": "Enabled",
		"plugins.toggle": "Enable {name}",
		"plugins.saveSource": "Install source plugin",
		"plugins.sourceDraft": "No capability description provided",
		"scheduled.saveDraft": "Save task",
		"scheduled.taskCount": "{count} tasks",
		"scheduled.enabledDraft": "Enabled",
		"scheduled.pausedDraft": "Paused",
		"scheduled.toggle": "Enable task",
		"scheduled.emptyHint":
			"Choose the schedule, prompt and project, then enable the saved task. Unattended execution requires explicit YOLO and a fresh context per run.",
		"scheduled.noRuns": "No runs yet. Enable the task or choose Run now.",
		"scheduled.deleteTitle": "Delete task",
		"scheduled.deleteHint":
			"Delete “{title}” and stop future scheduling? Existing run receipts remain available.",
		"scheduled.invalidDraft":
			"Check the prompt and schedule. Background tasks require YOLO, a fresh context and a configured model.",
	},
};
