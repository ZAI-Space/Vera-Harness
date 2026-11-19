// Adapted from PI-Desktop features/plugins/model.ts, LGPL-3.0-only.
// Source and license: third_party/pi-desktop/NOTICE.md.
import type { Translate } from "../../i18n";
/** 插件页的显示契约，与 Pi 的 UI 插件和未来 Harness 管理接口分开。 */
export interface WorkspacePlugin {
	id: string;
	name: string;
	description: string;
	exampleDescription?: "review" | "design" | "notes";
	version: string;
	author: string;
	category: "development" | "productivity" | "design";
	capabilities: string[];
	source?: string;
	enabled: boolean;
	status: "preview" | "ready" | "error" | "load_error";
	updateAvailable?: boolean;
}

export const GROUP_ORDER = ["attention", "updates", "active", "disabled"] as const;
export type PluginGroup = (typeof GROUP_ORDER)[number];

/** 复用原页面的多字段查询语义，不区分大小写。 */
export function matchesQuery(query: string, ...fields: Array<string | undefined>): boolean {
	const needle = query.trim().toLocaleLowerCase();
	if (!needle) return true;
	return fields.some((field) => field?.toLocaleLowerCase().includes(needle));
}

/** 问题和更新优先展示；开关表示草稿中的启用意图，不启动插件。 */
export function groupOf(plugin: WorkspacePlugin): PluginGroup {
	if (plugin.status === "error" || plugin.status === "load_error") return "attention";
	if (plugin.updateAvailable) return "updates";
	return plugin.enabled ? "active" : "disabled";
}

/** 示例说明随语言切换，真实插件描述保留原文，未读取的来源使用当前语言提示。 */
export function pluginDescription(plugin: WorkspacePlugin, t: Translate): string {
	return plugin.exampleDescription
		? t(`plugins.examples.${plugin.exampleDescription}`)
		: plugin.description || t("plugins.sourceDraft");
}
