import type { SlashCommandInfo } from "@vera/contracts";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";
import { slashInvocationName, withDesktopSlashCommands } from "./desktop-slash-commands";
import { SlashMenu } from "./SlashMenu";
import { filterCommands } from "./slash-filter";

vi.mock("../../i18n", () => ({ useT: () => (key: string) => key }));

const command = (name: string, source: SlashCommandInfo["source"] = "extension"): SlashCommandInfo => ({
	name,
	source,
	description: name,
	supported: true,
});

describe("桌面斜杠菜单资源", () => {
	it("内置区只保留 new/settings，未注册分类保留禁用入口", () => {
		const commands = withDesktopSlashCommands([
			command("compact", "builtin"),
			command("export", "builtin"),
			command("settings", "builtin"),
		]);
		expect(commands.filter((entry) => entry.source === "builtin").map((entry) => entry.name)).toEqual([
			"new",
			"settings",
		]);
		for (const name of ["sandbox", "subagen", "plugin", "mcp", "skill"]) {
			expect(commands.find((entry) => entry.name === name)?.supported).toBe(false);
		}
	});

	it("检测到命令后替代该分类占位，保留 skill 身份与 MCP 调用", () => {
		const skill = { ...command("skill:bmad", "skill"), skillId: "skill-identity" };
		const mcp = command("mcp");
		const commands = withDesktopSlashCommands([
			command("sandbox:local"),
			command("subagen:reviewer"),
			skill,
			mcp,
		]);
		expect(commands.find((entry) => entry.name === "sandbox")).toBeUndefined();
		expect(commands.find((entry) => entry.name === "subagen")).toBeUndefined();
		expect(commands.find((entry) => entry.name === "skill:bmad")).toBe(skill);
		expect(commands.find((entry) => entry.name === "mcp")).toBe(mcp);
	});

	it("插件别名可搜索、唯一，并还原正确执行标识", () => {
		const commands = withDesktopSlashCommands([command("review"), command("plugin:review")]);
		const matches = filterCommands(commands, "plugin:");
		expect(matches.map((entry) => entry.name)).toEqual(["plugin:review:2", "plugin:review"]);
		expect(slashInvocationName(commands, "plugin:review:2")).toBe("review");
		expect(slashInvocationName(commands, "plugin:review")).toBe("plugin:review");
		expect(new Set(commands.map((entry) => entry.name)).size).toBe(commands.length);
	});

	it("实际 DOM 的禁用属性阻止点击，data-index 与过滤后的键盘顺序一致", () => {
		const commands = withDesktopSlashCommands([command("review"), command("skill:bmad", "skill")]);
		const html = renderToStaticMarkup(
			createElement(SlashMenu, {
				commands,
				query: "",
				selectedIndex: 0,
				onSelectedIndexChange: () => {},
				onPick: () => {},
			}),
		);
		const rows = [...html.matchAll(/<button[^>]*data-index="(\d+)"[^>]*>(.*?)<\/button>/gs)];
		expect(rows).toHaveLength(commands.length);
		for (const [index, row] of rows.entries()) {
			const entry = commands[index];
			if (!entry) throw new Error("菜单索引超出命令清单");
			expect(row[1]).toBe(String(index));
			expect(row[2]).toContain(`/${entry.name}`);
			expect(row[0].includes('disabled=""')).toBe(!entry.supported);
		}
	});
});
