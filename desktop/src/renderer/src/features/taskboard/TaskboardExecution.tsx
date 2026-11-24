import type { SessionMeta } from "@vera/contracts";
import { useCallback, useEffect, useState } from "react";
import { Button } from "../../components/ui/Button";
import { ConfirmDialog } from "../../components/ui/ConfirmDialog";
import { Select } from "../../components/ui/Select";
import { harness } from "../../harness-api";
import { useI18nStore } from "../../i18n";
import { selectActiveCwd } from "../../lib/active-cwd";
import { errText } from "../../lib/error-text";
import { useProjectsStore } from "../../stores/projects";
import { useSessionsStore } from "../../stores/sessions";

interface BoardTask {
	id: string;
	identifier: string;
	title: string;
	status: string;
	version: number;
	archivedAt: string | null;
}
interface BoardRun {
	sessionId: string;
	taskId: string;
	title: string;
	status: string;
	error?: string;
	syncError?: string;
}
interface ExecutionSnapshot {
	tasks: BoardTask[];
	runs: BoardRun[];
}

/** Explicit board dispatch reuses normal chats, permissions and live execution inspection. */
export function TaskboardExecution() {
	const zh = useI18nStore((state) => state.language === "zh");
	const activeCwd = useSessionsStore(selectActiveCwd);
	const models = useSessionsStore((state) => state.models);
	const [snapshot, setSnapshot] = useState<ExecutionSnapshot>({ tasks: [], runs: [] });
	const [taskId, setTaskId] = useState("");
	const [cwd, setCwd] = useState(activeCwd ?? "");
	const [model, setModel] = useState("");
	const [permission, setPermission] = useState("confirm");
	const [warning, setWarning] = useState(false);
	const [busy, setBusy] = useState(false);
	const [error, setError] = useState<string | null>(null);
	const [loadError, setLoadError] = useState<string | null>(null);
	const refresh = useCallback(async () => {
		try {
			setSnapshot(await harness<ExecutionSnapshot>("getTaskboardExecution"));
			setLoadError(null);
		} catch (failure) {
			setLoadError(errText(failure) ?? String(failure));
		}
	}, []);
	useEffect(() => {
		void refresh();
		const timer = setInterval(() => void refresh(), 3000);
		return () => clearInterval(timer);
	}, [refresh]);
	const execute = async () => {
		const task = snapshot.tasks.find((row) => row.id === taskId);
		if (!task) return;
		setBusy(true);
		setError(null);
		try {
			const separator = model.indexOf("/");
			await harness("runTaskboardTask", {
				taskId,
				version: task.version,
				cwd,
				provider: model.slice(0, separator),
				modelId: model.slice(separator + 1),
				thinkingLevel: "default",
				permissionPolicy: permission,
			});
			await refresh();
		} catch (failure) {
			setError(errText(failure) ?? String(failure));
		} finally {
			setBusy(false);
		}
	};
	const open = async (sessionId: string) => {
		try {
			const sessions = await harness<SessionMeta[]>("listAllSessions");
			const session = sessions.find((row) => row.sessionId === sessionId);
			if (!session) throw new Error(zh ? "执行对话已删除。" : "Execution chat was deleted.");
			await useProjectsStore.getState().openSession(session);
		} catch (failure) {
			setError(errText(failure) ?? String(failure));
		}
	};
	const stop = async (sessionId: string) => {
		try {
			await harness("abort", { sessionId });
			await refresh();
		} catch (failure) {
			setError(errText(failure) ?? String(failure));
		}
	};
	return (
		<details className="shrink-0 border-b border-border px-5 py-3">
			<summary className="cursor-pointer text-ui-13 font-medium text-ink">
				{zh ? "Agent 执行" : "Agent execution"}
				{snapshot.runs.some((run) => run.status === "running") && (zh ? " · 执行中" : " · Running")}
			</summary>
			<div className="max-h-64 space-y-3 overflow-y-auto pt-3">
				<p className="text-ui-11 text-ink-faint">
					{zh
						? "选择任务后启动独立执行对话；完成后回写待审核。确认模式需在执行对话中批准工具操作。"
						: "Start a separate chat for the selected issue. Completed runs move to review; confirm mode requires tool approval in the execution chat."}
				</p>
				<div className="grid gap-3 sm:grid-cols-2">
					<Select
						ariaLabel={zh ? "执行任务" : "Issue"}
						value={taskId}
						onChange={setTaskId}
						options={[
							{ value: "", label: zh ? "选择看板任务" : "Select issue" },
							...snapshot.tasks
								.filter((row) => !row.archivedAt && !["done", "canceled"].includes(row.status))
								.map((row) => ({ value: row.id, label: `${row.identifier} · ${row.title}` })),
						]}
					/>
					<Select
						ariaLabel={zh ? "执行模型" : "Execution model"}
						value={model}
						onChange={setModel}
						options={[
							{ value: "", label: zh ? "选择模型" : "Select model" },
							...models.map((row) => ({
								value: `${row.provider}/${row.id}`,
								label: `${row.providerName} · ${row.label}`,
							})),
						]}
					/>
					<label className="text-ui-11 text-ink-dim">
						{zh ? "执行目录" : "Workspace"}
						<input
							className="mt-1 w-full rounded-md border border-border bg-canvas px-2 py-2 text-ui-12"
							value={cwd}
							onChange={(event) => setCwd(event.target.value)}
						/>
					</label>
					<Select
						ariaLabel={zh ? "执行权限" : "Execution permission"}
						value={permission}
						onChange={(value) => (value === "yolo" ? setWarning(true) : setPermission(value))}
						options={[
							{ value: "confirm", label: zh ? "确认模式" : "Confirm" },
							{ value: "yolo", label: zh ? "完全通过" : "Yolo" },
						]}
					/>
				</div>
				<div className="flex gap-2">
					<Button disabled={busy} onClick={() => void refresh()}>
						{zh ? "刷新任务" : "Refresh issues"}
					</Button>
					<Button
						variant="primary"
						disabled={
							busy ||
							!taskId ||
							!model ||
							!cwd.trim() ||
							snapshot.runs.some((run) => run.taskId === taskId && run.status === "running")
						}
						onClick={() => void execute()}
					>
						{zh ? "启动 Agent 执行" : "Run with Agent"}
					</Button>
				</div>
				{error && (
					<p role="alert" className="text-ui-12 text-err">
						{error}
					</p>
				)}
				{loadError && (
					<p role="alert" className="text-ui-12 text-err">
						{loadError}
					</p>
				)}
				{snapshot.runs.map((run) => (
					<div
						key={run.sessionId}
						className="flex flex-wrap items-center justify-between gap-2 border-t border-border py-2 text-ui-12"
					>
						<div className="min-w-0">
							<p className="break-words text-ink">
								{run.title} ·{" "}
								{run.status === "running"
									? zh
										? "执行中"
										: "Running"
									: run.status === "completed"
										? zh
											? "待审核"
											: "Ready for review"
										: zh
											? "执行失败"
											: "Failed"}
							</p>
							{run.error && <p className="text-err">{run.error}</p>}
							{run.syncError && (
								<p className="text-err">
									{zh ? "回写失败：" : "Sync failed: "}
									{run.syncError}
								</p>
							)}
						</div>
						<div className="flex gap-2">
							{run.status === "running" && (
								<Button onClick={() => void stop(run.sessionId)}>{zh ? "停止执行" : "Stop execution"}</Button>
							)}
							{run.syncError && (
								<Button
									onClick={() =>
										void harness("syncTaskboardRun", { sessionId: run.sessionId })
											.then(refresh)
											.catch((failure) => setError(String(failure)))
									}
								>
									{zh ? "重试回写" : "Retry sync"}
								</Button>
							)}
							<Button onClick={() => void open(run.sessionId)}>
								{zh ? "查看执行对话" : "Open execution chat"}
							</Button>
						</div>
					</div>
				))}
			</div>
			{warning && (
				<ConfirmDialog
					title={zh ? "允许 Agent 自动执行？" : "Allow automatic execution?"}
					description={
						zh
							? "完全通过会允许 Agent 在所选目录执行命令、修改文件和访问网络，不再逐项确认。请仅对可信任务和目录启用。"
							: "Yolo allows commands, file changes and network access without individual approval. Only use trusted tasks and workspaces."
					}
					confirmLabel={zh ? "启用完全通过" : "Enable Yolo"}
					cancelLabel={zh ? "取消" : "Cancel"}
					onConfirm={() => {
						setPermission("yolo");
						setWarning(false);
					}}
					onCancel={() => setWarning(false)}
				/>
			)}
		</details>
	);
}
