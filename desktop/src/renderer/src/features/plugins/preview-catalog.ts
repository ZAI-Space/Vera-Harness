import type { WorkspacePlugin } from "./model";

/** 明确标记的界面示例，不读取市场、不安装代码，也不推断本机已有插件。 */
export const PLUGIN_PREVIEW_CATALOG: WorkspacePlugin[] = [
	{
		id: "preview.review-kit",
		name: "Review Kit",
		description: "",
		exampleDescription: "review",
		version: "1.0.0",
		author: "VERA",
		category: "development",
		capabilities: ["skills", "subagents"],
		icon: "review",
		enabled: true,
		status: "preview",
	},
	{
		id: "preview.frontend-design",
		name: "Frontend Design",
		description: "",
		exampleDescription: "design",
		version: "1.0.0",
		author: "VERA",
		category: "design",
		capabilities: ["skills"],
		icon: "design",
		enabled: true,
		status: "preview",
	},
	{
		id: "preview.project-notes",
		name: "Project Notes",
		description: "",
		exampleDescription: "notes",
		version: "1.0.0",
		author: "VERA",
		category: "productivity",
		capabilities: ["skills", "mcp"],
		icon: "notes",
		enabled: true,
		status: "preview",
	},
];
