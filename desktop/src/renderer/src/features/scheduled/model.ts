// Frontend shapes adapted from PI-Desktop shared/types/platform.ts, LGPL-3.0-only.
/** 定时任务页面的显示契约；草稿与执行服务尚未连接。 */
export type ScheduledCadence = "manual" | "hourly" | "interval" | "daily" | "weekly";
export interface ScheduledTaskSchedule {
	hour: number;
	minute: number;
	weekday: number;
	weekdays?: number[];
	intervalMinutes?: number;
}

export interface ScheduledDraft {
	title: string;
	prompt: string;
	cadence: ScheduledCadence;
	schedule: ScheduledTaskSchedule | null;
	workspacePath: string;
	permissionMode: "human" | "confirm" | "yolo";
	sessionMode: "perRun" | "reuse";
	modelRef: string;
	thinkingLevel: string;
}

export interface ScheduledTask extends ScheduledDraft {
	id: string;
	enabled: boolean;
	createdAt: string;
	updatedAt: string;
	lastRunAt?: string;
	nextRunAt?: string;
}

export interface ScheduledTaskRun {
	id: string;
	taskId: string;
	sessionId: string | null;
	status: "running" | "completed" | "aborted" | "error";
	errorCode: string | null;
	startedAt: string;
	endedAt: string | null;
	output?: string;
}

/** 在展示层提交前校验调度意图；失败不会修改草稿集合。 */
export function isValidScheduledDraft(draft: ScheduledDraft): boolean {
	if (!draft.title.trim() || !draft.prompt.trim()) return false;
	if (draft.cadence === "manual" || draft.cadence === "hourly") return true;
	const schedule = draft.schedule;
	if (!schedule) return false;
	if (draft.cadence === "interval")
		return (
			Number.isInteger(schedule.intervalMinutes) &&
			(schedule.intervalMinutes ?? 0) >= 5 &&
			(schedule.intervalMinutes ?? 0) <= 1440
		);
	if (
		!Number.isInteger(schedule.hour) ||
		schedule.hour < 0 ||
		schedule.hour > 23 ||
		!Number.isInteger(schedule.minute) ||
		schedule.minute < 0 ||
		schedule.minute > 59
	)
		return false;
	if (draft.cadence === "daily") return true;
	const weekdays = schedule.weekdays ?? [schedule.weekday];
	return (
		draft.cadence === "weekly" &&
		weekdays.length > 0 &&
		new Set(weekdays).size === weekdays.length &&
		weekdays.every((day) => Number.isInteger(day) && day >= 0 && day <= 6)
	);
}
