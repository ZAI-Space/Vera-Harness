import type { SlashCommandInfo } from "@vera/contracts";
import { describe, expect, it } from "vitest";
import { filterCommands } from "../../../../../src/renderer/src/components/composer/slash-filter";
import { orderSlashCommands } from "../../../../../src/renderer/src/components/composer/slash-groups";

function cmd(name: string, source: SlashCommandInfo["source"]): SlashCommandInfo {
	return { name, description: "", source, supported: true };
}

describe("filterCommands", () => {
	const commands: SlashCommandInfo[] = [
		cmd("compact", "builtin"),
		cmd("rename", "builtin"),
		cmd("skill:mindmap", "skill"),
		cmd("skill:research", "skill"),
		cmd("help", "extension"),
	];

	it("空 query 返回全部，按新菜单分类排序", () => {
		expect(filterCommands(commands, "")).toEqual(orderSlashCommands(commands));
		expect(filterCommands(commands, "").map((command) => command.name)).toEqual([
			"compact",
			"rename",
			"help",
			"skill:mindmap",
			"skill:research",
		]);
	});
	it("非 skill 命令维持前缀匹配，不误伤 skill", () => {
		expect(filterCommands(commands, "comp")).toEqual([cmd("compact", "builtin")]);
		expect(filterCommands(commands, "hel")).toEqual([cmd("help", "extension")]);
		expect(filterCommands(commands, "compact")).toEqual([cmd("compact", "builtin")]);
	});
	it("skill: 前缀可命中", () => {
		expect(filterCommands(commands, "skill:m")).toEqual([cmd("skill:mindmap", "skill")]);
	});
	it("去前缀后前缀命中 skill", () => {
		expect(filterCommands(commands, "mind")).toEqual([cmd("skill:mindmap", "skill")]);
		expect(filterCommands(commands, "mindmap")).toEqual([cmd("skill:mindmap", "skill")]);
	});
	it("去前缀后子串命中（前缀命中在前，子串在后）", () => {
		expect(filterCommands(commands, "indmap")).toEqual([cmd("skill:mindmap", "skill")]);
		const more: SlashCommandInfo[] = [cmd("skill:game-map", "skill"), cmd("skill:mindmap", "skill")];
		expect(filterCommands(more, "map")).toEqual([
			cmd("skill:game-map", "skill"),
			cmd("skill:mindmap", "skill"),
		]);
		expect(filterCommands(more, "m")).toEqual([
			cmd("skill:mindmap", "skill"),
			cmd("skill:game-map", "skill"),
		]);
	});
	it("无匹配返回空", () => {
		expect(filterCommands(commands, "zzzz")).toEqual([]);
	});
	it("顺序与菜单分组一致：Enter/Tab 按下标取到的就是高亮的那条", () => {
		const mixed: SlashCommandInfo[] = [
			cmd("skill:sync-docs", "skill"),
			cmd("skill:easy", "skill"),
			cmd("sync", "extension"),
		];
		const result = filterCommands(mixed, "sy");
		expect(result).toEqual([
			cmd("sync", "extension"),
			cmd("skill:sync-docs", "skill"),
			cmd("skill:easy", "skill"),
		]);
		// 菜单与 hook 共用分类顺序，确保键盘索引与可见行一致。
		expect(result).toEqual(orderSlashCommands(result));
	});
});
