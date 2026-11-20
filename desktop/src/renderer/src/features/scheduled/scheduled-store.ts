import { create } from "zustand";
import { harness, isHarnessConnected, reportHarnessFailure } from "../../harness-api";
import {
	isValidScheduledDraft,
	type ScheduledDraft,
	type ScheduledTask,
	type ScheduledTaskRun,
} from "./model";

interface ScheduledStore {
	tasks: ScheduledTask[];
	runs: ScheduledTaskRun[];
	selectedTaskId: string | null;
	selectTask: (id: string) => void;
	refresh: () => Promise<void>;
	saveDraft: (id: string | null, draft: ScheduledDraft) => boolean | Promise<boolean>;
	setEnabled: (id: string, enabled: boolean) => void;
	remove: (id: string) => void;
	run: (id: string) => void;
}
type Snapshot = { tasks: ScheduledTask[]; runs: ScheduledTaskRun[] };

/** 已连接时只接受真实调度器确认；未连接时保留明确标注的界面草稿。 */
export const useScheduledPreviewStore = create<ScheduledStore>((set, get) => {
	const action = (id: string, action: string) => {
		void harness<Snapshot>("scheduledAction", { id, action }).then(set).catch(reportHarnessFailure);
	};
	return {
		tasks: [],
		runs: [],
		selectedTaskId: null,
		selectTask: (selectedTaskId) => set({ selectedTaskId }),
		refresh: async () => {
			if (isHarnessConnected()) set(await harness<Snapshot>("getScheduledTasks"));
		},
		saveDraft: (id, draft) => {
			if (!isValidScheduledDraft(draft) || (id !== null && !get().tasks.some((task) => task.id === id)))
				return false;
			if (isHarnessConnected())
				return harness<Snapshot>("saveScheduledTask", {
					id,
					draft: { ...draft, timezone: Intl.DateTimeFormat().resolvedOptions().timeZone },
				}).then(
					(snapshot) => {
						set(snapshot);
						return true;
					},
					(error) => {
						void reportHarnessFailure(error);
						return false;
					},
				);
			const now = new Date().toISOString();
			const taskId = id ?? crypto.randomUUID();
			const existing = get().tasks.find((task) => task.id === taskId);
			const task: ScheduledTask = {
				...existing,
				...draft,
				title: draft.title.trim(),
				prompt: draft.prompt.trim(),
				schedule: draft.schedule
					? {
							...draft.schedule,
							weekdays: draft.schedule.weekdays ? [...draft.schedule.weekdays] : undefined,
						}
					: null,
				id: taskId,
				enabled: existing?.enabled ?? false,
				createdAt: existing?.createdAt ?? now,
				updatedAt: now,
			};
			set((state) => ({
				tasks: existing ? state.tasks.map((row) => (row.id === taskId ? task : row)) : [...state.tasks, task],
				selectedTaskId: taskId,
			}));
			return true;
		},
		setEnabled: (id, enabled) =>
			isHarnessConnected()
				? action(id, enabled ? "enable" : "disable")
				: set((state) => ({
						tasks: state.tasks.map((task) => (task.id === id ? { ...task, enabled } : task)),
					})),
		remove: (id) =>
			isHarnessConnected()
				? action(id, "remove")
				: set((state) => {
						const tasks = state.tasks.filter((task) => task.id !== id);
						return {
							tasks,
							runs: state.runs.filter((run) => run.taskId !== id),
							selectedTaskId: state.selectedTaskId === id ? (tasks[0]?.id ?? null) : state.selectedTaskId,
						};
					}),
		run: (id) => action(id, "run"),
	};
});
