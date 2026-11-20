// Adapted from PI-Desktop ScheduledPage.tsx and ScheduledTaskRail, LGPL-3.0-only.
import { environmentEntityRef } from "@vera/contracts";
import { useEffect, useState } from "react";
import { ClockIcon, PlusIcon } from "../../components/icons";
import { ConfirmDialog } from "../../components/ui/ConfirmDialog";
import {
	WorkspaceButton,
	WorkspaceEmpty,
	WorkspacePage,
	WorkspaceSearch,
} from "../../components/workspace/WorkspacePage";
import { useT } from "../../i18n";
import { selectActiveCwd } from "../../lib/active-cwd";
import { useSessionsStore } from "../../stores/sessions";
import { matchesQuery } from "../plugins/model";
import type { ScheduledTask } from "./model";
import { ScheduledEditor } from "./ScheduledEditor";
import { ScheduledTaskDetail } from "./ScheduledTaskDetail";
import { scheduleLabel } from "./scheduled-labels";
import { useScheduledPreviewStore } from "./scheduled-preview-store";
import { resolveSelectedTaskId } from "./scheduled-runs";

/** 任务列与详情页复用原工作区布局；编辑表单独占内容区，取消不会提交。 */
export function ScheduledPage() {
	useEffect(() => {
		const refresh = () => {
			void useScheduledPreviewStore.getState().refresh().catch(console.error);
		};
		refresh();
		const timer = setInterval(refresh, 3000);
		return () => clearInterval(timer);
	}, []);
	const t = useT();
	const tasks = useScheduledPreviewStore((s) => s.tasks);
	const runs = useScheduledPreviewStore((s) => s.runs);
	const selectedId = useScheduledPreviewStore((s) => s.selectedTaskId);
	const selectTask = useScheduledPreviewStore((s) => s.selectTask);
	const saveDraft = useScheduledPreviewStore((s) => s.saveDraft);
	const setEnabled = useScheduledPreviewStore((s) => s.setEnabled);
	const remove = useScheduledPreviewStore((s) => s.remove);
	const cwd = useSessionsStore(selectActiveCwd);
	const [editor, setEditor] = useState<ScheduledTask | "new" | null>(null);
	const [query, setQuery] = useState("");
	const [deleting, setDeleting] = useState<ScheduledTask | null>(null);
	const filtered = tasks.filter((task) => matchesQuery(query, task.title, task.prompt, task.workspacePath));
	const selected = filtered.find((task) => task.id === resolveSelectedTaskId(filtered, selectedId, true));
	return (
		<WorkspacePage
			title={t("scheduled.title")}
			description={t("scheduled.description")}
			actions={
				<WorkspaceButton className="bg-hover" onClick={() => setEditor("new")}>
					<PlusIcon />
					{t("scheduled.create")}
				</WorkspaceButton>
			}
		>
			{editor ? (
				<ScheduledEditor
					key={editor === "new" ? "new" : editor.id}
					task={editor === "new" ? undefined : editor}
					workspacePath={cwd ? environmentEntityRef(cwd).id : ""}
					onCancel={() => setEditor(null)}
					onSave={async (draft) => {
						const saved = await saveDraft(editor === "new" ? null : editor.id, draft);
						if (saved) {
							setEditor(null);
							setQuery("");
						}
						return saved;
					}}
				/>
			) : (
				<>
					<div className="flex flex-wrap items-center justify-between gap-4">
						<p className="text-ui-12 text-ink-faint">{t("scheduled.taskCount", { count: tasks.length })}</p>
						<WorkspaceSearch value={query} onChange={setQuery} label={t("scheduled.search")} />
					</div>
					{tasks.length === 0 ? (
						<WorkspaceEmpty title={t("scheduled.empty")} description={t("scheduled.emptyHint")}>
							<WorkspaceButton onClick={() => setEditor("new")}>
								<PlusIcon />
								{t("scheduled.create")}
							</WorkspaceButton>
						</WorkspaceEmpty>
					) : filtered.length === 0 ? (
						<WorkspaceEmpty title={t("scheduled.noMatches")}>
							<WorkspaceButton onClick={() => setQuery("")}>{t("scheduled.clearSearch")}</WorkspaceButton>
						</WorkspaceEmpty>
					) : (
						<div className="grid min-w-0 gap-5 min-[1000px]:grid-cols-[220px_minmax(0,1fr)]">
							<nav aria-label={t("scheduled.taskList")} className="flex flex-col gap-2">
								{filtered.map((task) => (
									<button
										key={task.id}
										type="button"
										aria-current={task.id === selected?.id ? "true" : undefined}
										className={`rounded-xl p-4 text-left outline-none transition-colors focus-visible:ring-2 focus-visible:ring-ink-faint ${task.id === selected?.id ? "bg-hover text-ink" : "text-ink-2 hover:bg-hover"}`}
										onClick={() => selectTask(task.id)}
									>
										<div className="flex items-center gap-2">
											<ClockIcon size={14} />
											<span className="min-w-0 truncate text-ui-13 font-medium">{task.title}</span>
										</div>
										<p className="mt-2 text-ui-11 text-ink-dim">{scheduleLabel(task, t)}</p>
										<p className="mt-1 text-ui-11 text-ink-faint">
											{t(task.enabled ? "scheduled.enabledDraft" : "scheduled.pausedDraft")}
										</p>
									</button>
								))}
							</nav>
							{selected && (
								<ScheduledTaskDetail
									key={selected.id}
									task={selected}
									runs={runs}
									onEdit={() => setEditor(selected)}
									onDelete={() => setDeleting(selected)}
									onToggle={(enabled) => setEnabled(selected.id, enabled)}
								/>
							)}
						</div>
					)}
				</>
			)}
			{deleting && (
				<ConfirmDialog
					title={t("scheduled.deleteTitle")}
					description={t("scheduled.deleteHint", { title: deleting.title })}
					confirmLabel={t("common.delete")}
					cancelLabel={t("common.cancel")}
					danger
					onCancel={() => setDeleting(null)}
					onConfirm={() => {
						remove(deleting.id);
						setDeleting(null);
					}}
				/>
			)}
		</WorkspacePage>
	);
}
