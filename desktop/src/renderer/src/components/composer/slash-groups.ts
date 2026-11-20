import type { SlashCommandInfo } from "@vera/contracts";

export const SLASH_GROUP_ORDER = [
	"builtin",
	"sandbox",
	"subagen",
	"plugin",
	"mcp",
	"skill",
	"template",
] as const;
export type SlashGroup = (typeof SLASH_GROUP_ORDER)[number];
const RESOURCE_GROUPS = ["sandbox", "subagen", "plugin", "mcp"] as const;

/** 按已注册命令的命名空间分组；skill 保留现有资源身份，普通扩展归入插件。 */
export function slashGroup(command: SlashCommandInfo): SlashGroup {
	if (command.name === "subagent" || command.name.startsWith("subagent:")) return "subagen";
	if (command.source === "skill") return "skill";
	for (const group of RESOURCE_GROUPS) {
		if (command.name === group || command.name.startsWith(`${group}:`)) return group;
	}
	return command.source === "extension" ? "plugin" : command.source;
}

/** 所有菜单、过滤和键盘索引共用同一顺序，不修改原数组。 */
export function orderSlashCommands(commands: SlashCommandInfo[]): SlashCommandInfo[] {
	return SLASH_GROUP_ORDER.flatMap((group) => commands.filter((command) => slashGroup(command) === group));
}
