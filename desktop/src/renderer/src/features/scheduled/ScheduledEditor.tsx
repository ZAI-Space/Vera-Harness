// Adapted from PI-Desktop features/scheduled/ScheduledEditor.tsx, LGPL-3.0-only.
// Retains cadence/calendar/interval editing; uses VERA controls and draft storage.
import { useState } from "react";
import { Select } from "../../components/ui/Select";
import {
	WORKSPACE_INPUT_CLASS,
	WorkspaceButton,
	WorkspaceField,
} from "../../components/workspace/WorkspacePage";
import { isHarnessConnected } from "../../harness-api";
import { useT } from "../../i18n";
import { useSessionsStore } from "../../stores/sessions";
import {
	isValidScheduledDraft,
	type ScheduledCadence,
	type ScheduledDraft,
	type ScheduledTask,
} from "./model";
import { convertInterval, intervalAmount } from "./scheduled-format";

/** 编辑完整的任务执行意图；保存只调用传入的草稿接口，不触发执行。 */
export function ScheduledEditor({
	task,
	workspacePath,
	onSave,
	onCancel,
}: {
	task?: ScheduledTask;
	workspacePath: string;
	onSave: (draft: ScheduledDraft) => boolean | Promise<boolean>;
	onCancel: () => void;
}) {
	const t = useT();
	const models = useSessionsStore((s) => s.models);
	const [title, setTitle] = useState(task?.title ?? "");
	const [prompt, setPrompt] = useState(task?.prompt ?? "");
	const [workspace, setWorkspace] = useState(task?.workspacePath ?? workspacePath);
	const [cadence, setCadence] = useState<ScheduledCadence>(task?.cadence ?? "daily");
	const [time, setTime] = useState(
		`${String(task?.schedule?.hour ?? 9).padStart(2, "0")}:${String(task?.schedule?.minute ?? 0).padStart(2, "0")}`,
	);
	const [weekdays, setWeekdays] = useState(task?.schedule?.weekdays ?? [task?.schedule?.weekday ?? 0]);
	const initialInterval = intervalAmount(task?.schedule?.intervalMinutes) ?? {
		value: 30,
		unit: "minutes" as const,
	};
	const [intervalValue, setIntervalValue] = useState(String(initialInterval.value));
	const [intervalUnit, setIntervalUnit] = useState<"minutes" | "hours">(initialInterval.unit);
	const [permission, setPermission] = useState<ScheduledDraft["permissionMode"]>(
		task?.permissionMode ?? "confirm",
	);
	const [sessionMode, setSessionMode] = useState<ScheduledDraft["sessionMode"]>(
		task?.sessionMode ?? "perRun",
	);
	const [modelRef, setModelRef] = useState(task?.modelRef ?? "");
	const [thinking, setThinking] = useState(task?.thinkingLevel ?? "inherit");
	const [error, setError] = useState(false);
	const [hour, minute] = time.split(":").map(Number);
	const draft: ScheduledDraft = {
		title,
		prompt,
		workspacePath: workspace,
		cadence,
		permissionMode: permission,
		sessionMode,
		modelRef,
		thinkingLevel: thinking,
		schedule:
			cadence === "manual" || cadence === "hourly"
				? null
				: {
						hour: hour ?? -1,
						minute: minute ?? -1,
						weekday: weekdays[0] ?? 0,
						weekdays: [...weekdays].sort(),
						intervalMinutes: intervalUnit === "hours" ? Number(intervalValue) * 60 : Number(intervalValue),
					},
	};
	const valid = isValidScheduledDraft(draft);
	return (
		<form
			aria-label={t(task ? "scheduled.edit" : "scheduled.create")}
			className="rounded-xl bg-surface p-5 shadow-soft"
			onSubmit={async (event) => {
				event.preventDefault();
				if (!valid || !(await onSave(draft))) setError(true);
			}}
		>
			<h2 className="mb-6 text-ui-19 font-medium text-ink">
				{t(task ? "scheduled.edit" : "scheduled.create")}
			</h2>
			<div className="flex flex-col gap-5">
				<WorkspaceField label={t("scheduled.taskTitle")} htmlFor="scheduled-title">
					<input
						id="scheduled-title"
						className={WORKSPACE_INPUT_CLASS}
						maxLength={100}
						required
						value={title}
						placeholder={t("scheduled.titlePlaceholder")}
						onChange={(event) => setTitle(event.target.value)}
					/>
				</WorkspaceField>
				<WorkspaceField label={t("scheduled.prompt")} htmlFor="scheduled-prompt">
					<textarea
						id="scheduled-prompt"
						className={`${WORKSPACE_INPUT_CLASS} min-h-32 resize-y leading-relaxed`}
						maxLength={20000}
						required
						value={prompt}
						placeholder={t("scheduled.promptPlaceholder")}
						onChange={(event) => setPrompt(event.target.value)}
					/>
				</WorkspaceField>
				<WorkspaceField label={t("scheduled.workspace")} htmlFor="scheduled-workspace">
					<input
						id="scheduled-workspace"
						className={WORKSPACE_INPUT_CLASS}
						value={workspace}
						placeholder={t("scheduled.workspacePlaceholder")}
						onChange={(event) => setWorkspace(event.target.value)}
					/>
				</WorkspaceField>
				<div className="grid gap-5 sm:grid-cols-2">
					<div>
						<p className="mb-2 text-ui-13 font-medium text-ink-2">{t("scheduled.cadence")}</p>
						<Select
							ariaLabel={t("scheduled.cadence")}
							value={cadence}
							onChange={(value) => setCadence(value as ScheduledCadence)}
							options={(["manual", "hourly", "interval", "daily", "weekly"] as const).map((id) => ({
								value: id,
								label: t(`scheduled.cadences.${id}`),
							}))}
						/>
					</div>
					{(cadence === "daily" || cadence === "weekly") && (
						<WorkspaceField label={t("scheduled.time")} htmlFor="scheduled-time">
							<input
								id="scheduled-time"
								type="time"
								className={WORKSPACE_INPUT_CLASS}
								required
								value={time}
								onChange={(event) => setTime(event.target.value)}
							/>
						</WorkspaceField>
					)}
					{cadence === "interval" && (
						<WorkspaceField label={t("scheduled.interval")} htmlFor="scheduled-interval">
							<div className="flex gap-2">
								<input
									id="scheduled-interval"
									type="number"
									className={WORKSPACE_INPUT_CLASS}
									min={intervalUnit === "hours" ? 1 : 5}
									max={intervalUnit === "hours" ? 24 : 1440}
									step={1}
									required
									value={intervalValue}
									onChange={(event) => setIntervalValue(event.target.value)}
								/>
								<Select
									value={intervalUnit}
									ariaLabel={t("scheduled.intervalUnit")}
									onChange={(value) => {
										const unit = value as "minutes" | "hours";
										setIntervalValue(String(convertInterval(Number(intervalValue), intervalUnit, unit)));
										setIntervalUnit(unit);
									}}
									options={(["minutes", "hours"] as const).map((id) => ({
										value: id,
										label: t(`scheduled.units.${id}`),
									}))}
								/>
							</div>
						</WorkspaceField>
					)}
				</div>
				{cadence === "weekly" && (
					<fieldset>
						<legend className="mb-3 text-ui-13 font-medium text-ink-2">{t("scheduled.weekdays")}</legend>
						<div className="flex flex-wrap gap-2">
							{[0, 1, 2, 3, 4, 5, 6].map((day) => (
								<button
									key={day}
									type="button"
									aria-pressed={weekdays.includes(day)}
									className={`rounded-lg px-3 py-2 text-ui-13 outline-none focus-visible:ring-2 focus-visible:ring-ink-faint ${weekdays.includes(day) ? "bg-hover font-medium text-ink" : "text-ink-dim hover:bg-hover"}`}
									onClick={() =>
										setWeekdays((current) =>
											current.includes(day) ? current.filter((value) => value !== day) : [...current, day],
										)
									}
								>
									{t(`scheduled.days.${day as 0 | 1 | 2 | 3 | 4 | 5 | 6}`)}
								</button>
							))}
						</div>
					</fieldset>
				)}
				<p className="text-ui-12 text-ink-faint">
					{t("scheduled.timezone", { zone: Intl.DateTimeFormat().resolvedOptions().timeZone })}
				</p>
				<div className="grid gap-5 sm:grid-cols-2">
					<div>
						<p className="mb-2 text-ui-13 font-medium text-ink-2">{t("scheduled.model")}</p>
						<Select
							ariaLabel={t("scheduled.model")}
							value={modelRef}
							onChange={setModelRef}
							options={[
								{ value: "", label: t("scheduled.inheritModel") },
								...models.map((model) => ({
									value: `${model.provider}/${model.id}`,
									label: `${model.providerName} · ${model.label}`,
								})),
								...(modelRef && !models.some((model) => `${model.provider}/${model.id}` === modelRef)
									? [{ value: modelRef, label: modelRef }]
									: []),
							]}
						/>
					</div>
					<div>
						<p className="mb-2 text-ui-13 font-medium text-ink-2">{t("scheduled.thinking")}</p>
						<Select
							ariaLabel={t("scheduled.thinking")}
							value={thinking}
							onChange={setThinking}
							options={[
								{ value: "inherit", label: t("scheduled.inheritModel") },
								...(["off", "minimal", "low", "medium", "high", "xhigh", "max"] as const).map((level) => ({
									value: level,
									label: t(`thinkingLevels.${level}`),
								})),
							]}
						/>
					</div>
					<div>
						<p className="mb-2 text-ui-13 font-medium text-ink-2">{t("scheduled.permissions")}</p>
						<Select
							ariaLabel={t("scheduled.permissions")}
							value={permission}
							onChange={(value) => setPermission(value as ScheduledDraft["permissionMode"])}
							options={(["human", "confirm", "yolo"] as const).map((id) => ({
								value: id,
								label: t(`composer.permissionPolicies.${id}.title`),
								disabled: isHarnessConnected() && id !== "yolo",
							}))}
						/>
					</div>
					<div>
						<p className="mb-2 text-ui-13 font-medium text-ink-2">{t("scheduled.sessionMode")}</p>
						<Select
							ariaLabel={t("scheduled.sessionMode")}
							value={sessionMode}
							onChange={(value) => setSessionMode(value as ScheduledDraft["sessionMode"])}
							options={(["perRun", "reuse"] as const).map((id) => ({
								value: id,
								label: t(`scheduled.sessionModes.${id}`),
								disabled: isHarnessConnected() && id !== "perRun",
							}))}
						/>
					</div>
				</div>
				{error && (
					<p role="alert" className="text-ui-12 text-danger">
						{t("scheduled.invalidDraft")}
					</p>
				)}
				<div className="flex justify-end gap-2">
					<WorkspaceButton onClick={onCancel}>{t("common.cancel")}</WorkspaceButton>
					<WorkspaceButton type="submit" disabled={!valid} className="bg-hover">
						{t("scheduled.saveDraft")}
					</WorkspaceButton>
				</div>
			</div>
		</form>
	);
}
