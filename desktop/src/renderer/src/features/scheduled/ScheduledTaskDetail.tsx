// Adapted from PI-Desktop ScheduledTaskDetail.tsx, LGPL-3.0-only.
import { useState } from "react";
import { EditIcon, TrashIcon } from "../../components/icons";
import { Switch } from "../../components/ui/Switch";
import { Tooltip } from "../../components/ui/Tooltip";
import { WorkspaceButton } from "../../components/workspace/WorkspacePage";
import { isHarnessConnected } from "../../harness-api";
import { useI18nStore, useT } from "../../i18n";
import type { ScheduledTask, ScheduledTaskRun } from "./model";
import { formatDuration, formatMoment } from "./scheduled-format";
import { scheduleLabel } from "./scheduled-labels";
import { resolveSelectedRun, runDurationMs, runsForTask } from "./scheduled-runs";
import { useScheduledPreviewStore } from "./scheduled-store";

/** 任务详情与运行历史共用原页面的选择语义；没有真实运行记录时明确展示空态。 */
export function ScheduledTaskDetail({
	task,
	runs,
	onEdit,
	onDelete,
	onToggle,
}: {
	task: ScheduledTask;
	runs: ScheduledTaskRun[];
	onEdit: () => void;
	onDelete: () => void;
	onToggle: (enabled: boolean) => void;
}) {
	const t = useT();
	const language = useI18nStore((s) => s.language);
	const [selectedRunId, setSelectedRunId] = useState<string | null>(null);
	const history = runsForTask(runs, task.id);
	const selectedRun = resolveSelectedRun(history, selectedRunId);
	return (
		<section aria-label={task.title} className="min-w-0 rounded-xl bg-surface p-5 shadow-soft">
			<header className="flex flex-wrap items-start justify-between gap-4">
				<div className="min-w-0">
					<h2 className="break-words text-ui-19 font-semibold text-ink">{task.title}</h2>
					<p className="mt-2 text-ui-12 text-ink-dim">{scheduleLabel(task, t)}</p>
					<p className="mt-2 text-ui-11 text-ink-faint">
						{t(task.enabled ? "scheduled.enabledDraft" : "scheduled.pausedDraft")}
					</p>
				</div>
				<Switch
					checked={task.enabled}
					disabled={task.cadence === "manual"}
					aria-label={t("scheduled.toggle")}
					onCheckedChange={onToggle}
				/>
			</header>
			<div className="my-5 flex flex-wrap gap-2">
				<Tooltip label={t(isHarnessConnected() ? "scheduled.runNow" : "scheduled.executionUnavailable")}>
					<span>
						<WorkspaceButton
							disabled={!isHarnessConnected()}
							onClick={() => useScheduledPreviewStore.getState().run(task.id)}
						>
							{t("scheduled.runNow")}
						</WorkspaceButton>
					</span>
				</Tooltip>
				<WorkspaceButton onClick={onEdit}>
					<EditIcon />
					{t("scheduled.edit")}
				</WorkspaceButton>
				<WorkspaceButton onClick={onDelete}>
					<TrashIcon />
					{t("common.delete")}
				</WorkspaceButton>
			</div>
			<h3 className="mb-2 text-ui-13 font-medium text-ink-2">{t("scheduled.prompt")}</h3>
			<p className="whitespace-pre-wrap break-words text-ui-13 leading-relaxed text-ink-dim">{task.prompt}</p>
			<dl className="my-6 grid grid-cols-[auto_minmax(0,1fr)] gap-x-5 gap-y-3 text-ui-12">
				<dt className="text-ink-faint">{t("scheduled.workspace")}</dt>
				<dd className="break-all text-ink-dim">{task.workspacePath || t("scheduled.notSelected")}</dd>
				<dt className="text-ink-faint">{t("scheduled.model")}</dt>
				<dd className="break-all text-ink-dim">{task.modelRef || t("scheduled.inheritModel")}</dd>
				<dt className="text-ink-faint">{t("scheduled.permissions")}</dt>
				<dd className="text-ink-dim">{t(`composer.permissionPolicies.${task.permissionMode}.title`)}</dd>
				<dt className="text-ink-faint">{t("scheduled.sessionMode")}</dt>
				<dd className="text-ink-dim">{t(`scheduled.sessionModes.${task.sessionMode}`)}</dd>
			</dl>
			<h3 className="text-ui-14 font-medium text-ink">{t("scheduled.history")}</h3>
			{history.length === 0 ? (
				<p className="py-6 text-ui-13 text-ink-faint">{t("scheduled.noRuns")}</p>
			) : (
				<div className="mt-4 space-y-2">
					{history.map((run) => (
						<button
							key={run.id}
							type="button"
							aria-pressed={run.id === selectedRun?.id}
							className={`flex w-full flex-wrap justify-between gap-2 rounded-lg px-3 py-2 text-left text-ui-12 ${run.id === selectedRun?.id ? "bg-hover text-ink" : "text-ink-dim hover:bg-hover"}`}
							onClick={() => setSelectedRunId(run.id)}
						>
							<span>{formatMoment(run.startedAt, language)}</span>
							<span>
								{t(`scheduled.runStates.${run.status}`)} · {formatDuration(runDurationMs(run))}
							</span>
						</button>
					))}
				</div>
			)}
			{selectedRun && (
				<section className="mt-4 rounded-lg bg-hover p-4" aria-label={t("scheduled.runDetail")}>
					<h4 className="text-ui-13 font-medium text-ink-2">{t("scheduled.runDetail")}</h4>
					<pre className="mt-3 whitespace-pre-wrap break-words font-mono text-ui-12 leading-relaxed text-ink-dim">
						{selectedRun.output || selectedRun.errorCode || t("scheduled.noOutput")}
					</pre>
				</section>
			)}
		</section>
	);
}
