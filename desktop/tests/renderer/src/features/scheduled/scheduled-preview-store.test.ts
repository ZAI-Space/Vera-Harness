import { beforeEach, expect, it } from "vitest";
import {
	isValidScheduledDraft,
	type ScheduledDraft,
} from "../../../../../src/renderer/src/features/scheduled/model";
import { useScheduledPreviewStore } from "../../../../../src/renderer/src/features/scheduled/scheduled-preview-store";
import {
	resolveSelectedRun,
	runsForTask,
} from "../../../../../src/renderer/src/features/scheduled/scheduled-runs";

const draft: ScheduledDraft = {
	title: "Daily review",
	prompt: "Inspect changes",
	cadence: "weekly",
	schedule: { hour: 9, minute: 30, weekday: 0, weekdays: [0, 4] },
	workspacePath: "/project",
	permissionMode: "confirm",
	sessionMode: "perRun",
	modelRef: "",
	thinkingLevel: "inherit",
};
beforeEach(() => useScheduledPreviewStore.setState({ tasks: [], runs: [], selectedTaskId: null }));

it.each([
	{ ...draft, title: " " },
	{ ...draft, schedule: { ...draft.schedule, hour: 24, minute: 0, weekday: 0 } },
	{ ...draft, schedule: { hour: 9, minute: 0, weekday: 0, weekdays: [] } },
	{ ...draft, schedule: { hour: 9, minute: 0, weekday: 0, weekdays: [0, 0] } },
	{
		...draft,
		cadence: "interval" as const,
		schedule: { hour: 9, minute: 0, weekday: 0, intervalMinutes: 4 },
	},
	{
		...draft,
		cadence: "interval" as const,
		schedule: { hour: 9, minute: 0, weekday: 0, intervalMinutes: 1441 },
	},
])("rejects invalid schedule intents without creating a task: %j", (invalid) => {
	expect(isValidScheduledDraft(invalid)).toBe(false);
	expect(useScheduledPreviewStore.getState().saveDraft(null, invalid)).toBe(false);
	expect(useScheduledPreviewStore.getState().tasks).toEqual([]);
});

it("creates detached drafts, preserves identity while editing and never fabricates a run or next execution", () => {
	const store = useScheduledPreviewStore.getState();
	expect(store.saveDraft(null, draft)).toBe(true);
	const task = useScheduledPreviewStore.getState().tasks[0];
	if (!task) throw new Error("Missing task");
	expect(task.schedule?.weekdays).not.toBe(draft.schedule?.weekdays);
	expect(task.enabled).toBe(false);
	expect(store.saveDraft(task.id, { ...draft, title: "Edited" })).toBe(true);
	store.setEnabled(task.id, true);
	const changed = useScheduledPreviewStore.getState();
	expect(changed.tasks).toHaveLength(1);
	expect(changed.tasks[0]?.id).toBe(task.id);
	expect(changed.tasks[0]?.createdAt).toBe(task.createdAt);
	expect(changed.tasks[0]?.nextRunAt).toBeUndefined();
	expect(changed.runs).toEqual([]);
	expect(store.saveDraft("removed-task", draft)).toBe(false);
});

it("task history selection stays within the chosen task and falls back after the selected run disappears", () => {
	const runs = [
		{
			id: "old",
			taskId: "a",
			sessionId: null,
			status: "completed" as const,
			errorCode: null,
			startedAt: "2026-11-18T01:00:00Z",
			endedAt: "2026-11-18T01:01:00Z",
		},
		{
			id: "new",
			taskId: "a",
			sessionId: null,
			status: "error" as const,
			errorCode: "failure",
			startedAt: "2026-11-19T01:00:00Z",
			endedAt: "2026-11-19T01:01:00Z",
		},
		{
			id: "other",
			taskId: "b",
			sessionId: null,
			status: "running" as const,
			errorCode: null,
			startedAt: "2026-11-19T02:00:00Z",
			endedAt: null,
		},
	];
	const scoped = runsForTask(runs, "a");
	expect(scoped.map((run) => run.id)).toEqual(["new", "old"]);
	expect(resolveSelectedRun(scoped, "old")?.id).toBe("old");
	expect(resolveSelectedRun(scoped, "other")?.id).toBe("new");
});
