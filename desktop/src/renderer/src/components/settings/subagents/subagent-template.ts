// Adapted from PI-Desktop SubagentEditorSheet.tsx, LGPL-3.0-only.

import { isHarnessConnected } from "../../../harness-api";
import type { SubagentDraft } from "../../../stores/subagent-drafts";
import type { SubagentPreset } from "./subagent-presets";

/** 返回独立的空白草稿；模型跟随父代理，预算沿用 Harness 角色默认值。 */
export function createSubagentDraft(): SubagentDraft {
	return {
		id: "",
		name: "",
		description: "",
		instructions: "",
		tools: [],
		skills: [],
		step_limit: 12,
		cost_limit: 0.5,
		wall_time_limit_seconds: 180,
		enabled: true,
	};
}

/** 复用原模板完整内容与工具清单；名称用稳定 slug 适配 Harness，保留用户预算和技能。 */
export function applySubagentPreset(draft: SubagentDraft, preset: SubagentPreset): SubagentDraft {
	const mapping: Record<string, string> = {
		Read: "project_read",
		Glob: "project_files",
		Grep: "project_search",
		Bash: "bash",
	};
	return {
		...draft,
		name: preset.id,
		description: preset.description,
		instructions: preset.body,
		tools: isHarnessConnected()
			? [...new Set(preset.tools.flatMap((name) => (mapping[name] ? [mapping[name]] : [])))]
			: [...preset.tools],
	};
}

/** 清空模板负责的字段；切换起点不重置用户配置的预算、技能和启用状态。 */
export function resetSubagentTemplate(draft: SubagentDraft): SubagentDraft {
	return { ...draft, name: "", description: "", instructions: "", tools: [] };
}
