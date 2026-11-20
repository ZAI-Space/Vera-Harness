// @vitest-environment happy-dom
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { SUBAGENT_STORAGE_KEY, type SubagentDraft, useSubagentDraftsStore } from "./subagent-drafts";

const draft: SubagentDraft = {
	id: "",
	name: "reviewer",
	description: "Inspect changes",
	instructions: "Inspect without editing.",
	tools: ["bash"],
	skills: [],
	step_limit: 12,
	cost_limit: 0.5,
	wall_time_limit_seconds: 180,
	enabled: true,
};
beforeEach(() => {
	localStorage.clear();
	useSubagentDraftsStore.setState({ drafts: [], storageError: false });
});
afterEach(() => vi.unstubAllGlobals());

it("persists edits by stable id, prevents duplicates and restores local drafts", async () => {
	const store = useSubagentDraftsStore.getState();
	expect(store.saveDraft({ ...draft, tools: ["bash", "bash"] })).toBeNull();
	const id = useSubagentDraftsStore.getState().drafts[0]?.id ?? "";
	expect(id).not.toBe("");
	expect(store.saveDraft(draft)).toBe("duplicate");
	expect(store.saveDraft({ ...draft, name: "renamed" }, id)).toBeNull();
	store.toggleDraft(id);
	vi.resetModules();
	const restored = (await import("./subagent-drafts")).useSubagentDraftsStore;
	expect(restored.getState().drafts).toEqual([{ ...draft, id, name: "renamed", enabled: false }]);
	restored.getState().removeDraft(id);
	expect(JSON.parse(localStorage.getItem(SUBAGENT_STORAGE_KEY) ?? "null")).toEqual([]);
});

it.each([
	{ name: "Bad Name" },
	{ name: "1role" },
	{ description: " " },
	{ description: "a".repeat(321) },
	{ instructions: "" },
	{ instructions: "a".repeat(16_001) },
	{ tools: ["subagent_run"] },
	{ tools: ["skill_view"] },
	{ tools: ["bad tool"] },
	{ skills: ["bad skill"] },
	{ step_limit: 0 },
	{ step_limit: 201 },
	{ step_limit: 1.5 },
	{ cost_limit: 0 },
	{ cost_limit: Infinity },
	{ wall_time_limit_seconds: 0 },
	{ wall_time_limit_seconds: 3601 },
])("invalid role never changes the saved directory: %j", (patch) => {
	expect(useSubagentDraftsStore.getState().saveDraft({ ...draft, ...patch })).not.toBeNull();
	expect(useSubagentDraftsStore.getState().drafts).toEqual([]);
	expect(localStorage.getItem(SUBAGENT_STORAGE_KEY)).toBeNull();
});

it("keeps the editor retryable when storage fails, including toggle and removal", () => {
	const originalStorage = localStorage;
	const store = useSubagentDraftsStore.getState();
	expect(store.saveDraft(draft)).toBeNull();
	const before = useSubagentDraftsStore.getState().drafts;
	vi.stubGlobal("localStorage", {
		getItem: originalStorage.getItem.bind(originalStorage),
		setItem: () => {
			throw Error("quota");
		},
	});
	expect(store.saveDraft({ ...draft, name: "second" })).toBe("storage");
	store.toggleDraft(before[0]?.id ?? "");
	store.removeDraft(before[0]?.id ?? "");
	expect(useSubagentDraftsStore.getState().drafts).toBe(before);
	vi.unstubAllGlobals();
	expect(store.saveDraft({ ...draft, name: "second" })).toBeNull();
	expect(useSubagentDraftsStore.getState().drafts).toHaveLength(2);
	expect(useSubagentDraftsStore.getState().storageError).toBe(false);
});

it("bounds the role catalog and rejects missing edits", async () => {
	const saved = Array.from({ length: 66 }, (_, index) => ({
		...draft,
		id: `id-${index}`,
		name: `role-${index}`,
	}));
	localStorage.setItem(
		SUBAGENT_STORAGE_KEY,
		JSON.stringify([null, { ...draft, id: "bad", tools: null }, ...saved, saved[0]]),
	);
	vi.resetModules();
	const store = (await import("./subagent-drafts")).useSubagentDraftsStore.getState();
	expect(store.drafts).toHaveLength(64);
	expect(store.saveDraft(draft)).toBe("limit");
	expect(store.saveDraft(draft, "missing")).toBe("missing");
});
