import type { SlashCommandInfo } from "@vera/contracts";
import { orderSlashCommands, slashGroup } from "./slash-groups";

interface DesktopSlashCommand extends SlashCommandInfo {
	/** 插件展示别名对应的真实命令，发送时还原，避免更改已有扩展协议。 */
	invocationName?: string;
}

/** 将插件显示别名还原为后端已注册命令；禁用项不参与执行映射。 */
export function slashInvocationName(commands: SlashCommandInfo[], name: string): string {
	const command = commands.find((candidate) => candidate.name === name && candidate.supported) as
		| DesktopSlashCommand
		| undefined;
	return command?.invocationName ?? name;
}

/** 桌面菜单保留 new/settings；其余显示服务端已注册资源，缺失分类提供禁用项。 */
export function withDesktopSlashCommands(
	commands: SlashCommandInfo[],
	runtimeConnected = false,
): SlashCommandInfo[] {
	const builtin: SlashCommandInfo[] = [
		{ name: "new", description: "Create a new conversation", source: "builtin", supported: true },
		{ name: "settings", description: "Open settings", source: "builtin", supported: true },
		...(runtimeConnected
			? [
					{
						name: "export",
						description: "Export this conversation",
						source: "builtin" as const,
						supported: true,
					},
				]
			: []),
	];
	const reserved = new Set(builtin.map((command) => command.name));
	const taken = new Set([...reserved, ...commands.map((command) => command.name)]);
	const resources = commands
		.filter((command) => (runtimeConnected || command.source !== "builtin") && !reserved.has(command.name))
		.map((command): DesktopSlashCommand => {
			if (
				command.source !== "extension" ||
				slashGroup(command) !== "plugin" ||
				command.name === "plugin" ||
				command.name.startsWith("plugin:")
			)
				return command;
			const base = `plugin:${command.name}`;
			let name = base;
			for (let suffix = 2; taken.has(name); suffix++) name = `${base}:${suffix}`;
			taken.add(name);
			return { ...command, name, invocationName: command.name };
		});
	const emptyGroups = (["sandbox", "subagen", "plugin", "mcp", "skill"] as const)
		.filter((group) => !resources.some((command) => slashGroup(command) === group))
		.map(
			(group): SlashCommandInfo => ({
				name: group,
				description: "",
				source: group === "skill" ? "skill" : "extension",
				supported: false,
			}),
		);
	return orderSlashCommands([...builtin, ...resources, ...emptyGroups]);
}
