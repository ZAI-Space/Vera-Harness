import { create } from "zustand";
import { harness, isHarnessConnected, reportHarnessFailure } from "../harness-api";

/** Harness 角色字段与本机列表元数据；不注册到执行服务，也不包含模型凭据。 */
export interface SubagentDraft {
	id: string;
	name: string;
	description: string;
	instructions: string;
	tools: string[];
	skills: string[];
	step_limit: number;
	cost_limit: number;
	wall_time_limit_seconds: number;
	enabled: boolean;
	model?: { provider: string; modelId: string };
}

export type SubagentDraftError =
	| "name"
	| "description"
	| "instructions"
	| "tools"
	| "skills"
	| "steps"
	| "cost"
	| "timeout"
	| "duplicate"
	| "limit"
	| "missing"
	| "storage";

const RESERVED_TOOLS = new Set([
	"subagents_list",
	"subagent_run",
	"subagent_finish",
	"skills_list",
	"skill_view",
]);
export const SUBAGENT_STORAGE_KEY = "vera.subagent-drafts.v1";

/** 只校验角色结构及预算；工具和技能是否已安装需由后续执行桥接检查。 */
export function validateSubagentDraft(draft: SubagentDraft): SubagentDraftError | null {
	if (!/^[a-z][a-z0-9-]{0,47}$/.test(draft.name)) return "name";
	if (!draft.description.trim() || draft.description.length > 320) return "description";
	if (!draft.instructions.trim() || draft.instructions.length > 16_000) return "instructions";
	if (draft.tools.some((tool) => !tool.trim() || /\s/.test(tool) || RESERVED_TOOLS.has(tool))) return "tools";
	if (draft.skills.some((skill) => !skill.trim() || /\s/.test(skill))) return "skills";
	if (!Number.isInteger(draft.step_limit) || draft.step_limit < 1 || draft.step_limit > 200) return "steps";
	if (!Number.isFinite(draft.cost_limit) || draft.cost_limit <= 0) return "cost";
	if (
		!Number.isInteger(draft.wall_time_limit_seconds) ||
		draft.wall_time_limit_seconds < 1 ||
		draft.wall_time_limit_seconds > 3600
	)
		return "timeout";
	return null;
}

function isDraft(value: unknown): value is SubagentDraft {
	if (!value || typeof value !== "object") return false;
	const draft = value as Record<string, unknown>;
	return (
		typeof draft.id === "string" &&
		!!draft.id &&
		typeof draft.name === "string" &&
		typeof draft.description === "string" &&
		typeof draft.instructions === "string" &&
		typeof draft.enabled === "boolean" &&
		typeof draft.step_limit === "number" &&
		typeof draft.cost_limit === "number" &&
		typeof draft.wall_time_limit_seconds === "number" &&
		Array.isArray(draft.tools) &&
		draft.tools.every((tool) => typeof tool === "string") &&
		Array.isArray(draft.skills) &&
		draft.skills.every((skill) => typeof skill === "string")
	);
}

function loadDrafts(): SubagentDraft[] {
	try {
		const saved: unknown = JSON.parse(localStorage.getItem(SUBAGENT_STORAGE_KEY) ?? "null");
		if (!Array.isArray(saved)) return [];
		const drafts: SubagentDraft[] = [];
		for (const item of saved) {
			if (
				drafts.length < 64 &&
				isDraft(item) &&
				!validateSubagentDraft(item) &&
				!drafts.some((draft) => draft.id === item.id || draft.name === item.name)
			)
				drafts.push(item);
		}
		return drafts;
	} catch {
		return [];
	}
}

interface SubagentDraftsStore {
	drafts: SubagentDraft[];
	storageError: boolean;
	/** 创建或按稳定 id 编辑；失败返回原因并保持原列表，便于表单重试。 */
	saveDraft: (
		draft: SubagentDraft,
		originalId?: string,
	) => SubagentDraftError | null | Promise<SubagentDraftError | null>;
	removeDraft: (id: string) => void;
	toggleDraft: (id: string) => void;
}

/** 应用本机的角色草稿目录；所有修改先落盘，失败时不伪造成功状态。 */
export const useSubagentDraftsStore = create<SubagentDraftsStore>((set, get) => {
	const update = (
		drafts: SubagentDraft[],
	): SubagentDraftError | null | Promise<SubagentDraftError | null> => {
		if (isHarnessConnected())
			return harness<SubagentDraft[]>("saveSubagentRoles", { roles: drafts }).then(
				(saved) => {
					set({ drafts: saved, storageError: false });
					return null;
				},
				(error) => {
					set({ storageError: true });
					void reportHarnessFailure(error);
					return "storage" as const;
				},
			);
		try {
			localStorage.setItem(SUBAGENT_STORAGE_KEY, JSON.stringify(drafts));
			set({ drafts, storageError: false });
			return null;
		} catch {
			set({ storageError: true });
			return "storage";
		}
	};
	return {
		drafts: loadDrafts(),
		storageError: false,
		saveDraft: (draft, originalId) => {
			const normalized = {
				...draft,
				name: draft.name.trim(),
				description: draft.description.trim(),
				instructions: draft.instructions.trim(),
				tools: [...new Set(draft.tools.map((tool) => tool.trim()))],
				skills: [...new Set(draft.skills.map((skill) => skill.trim()))],
			};
			const failure = validateSubagentDraft(normalized);
			if (failure) return failure;
			const existing = get().drafts;
			if (originalId && !existing.some((item) => item.id === originalId)) return "missing";
			if (!originalId && existing.length >= 64) return "limit";
			if (existing.some((item) => item.name === normalized.name && item.id !== originalId))
				return "duplicate";
			const record = { ...normalized, id: originalId ?? crypto.randomUUID() };
			return update(
				originalId ? existing.map((item) => (item.id === originalId ? record : item)) : [...existing, record],
			);
		},
		removeDraft: (id) => update(get().drafts.filter((draft) => draft.id !== id)),
		toggleDraft: (id) =>
			update(get().drafts.map((draft) => (draft.id === id ? { ...draft, enabled: !draft.enabled } : draft))),
	};
});
