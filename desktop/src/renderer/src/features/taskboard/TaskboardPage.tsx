import { useCallback, useEffect, useState } from "react";
import { getDesktopApi } from "../../api";
import { Button } from "../../components/ui/Button";
import { harness } from "../../harness-api";
import { useI18nStore } from "../../i18n";
import { errText } from "../../lib/error-text";
import { TaskboardExecution } from "./TaskboardExecution";

interface TaskboardStatus {
	installed: boolean;
	running: boolean;
	url: string | null;
	repository: string;
	nodeAvailable: boolean;
}

/** Reuse dashi-taskboard's original application in an isolated loopback frame. */
export function TaskboardPage() {
	const zh = useI18nStore((state) => state.language === "zh");
	const [status, setStatus] = useState<TaskboardStatus | null>(null);
	const [busy, setBusy] = useState(false);
	const [error, setError] = useState<string | null>(null);
	const load = useCallback(async () => {
		try {
			setStatus(await harness<TaskboardStatus>("getTaskboardStatus"));
			setError(null);
		} catch (failure) {
			setError(errText(failure) ?? String(failure));
		}
	}, []);
	useEffect(() => {
		void load();
	}, [load]);
	const act = async (method: string) => {
		setBusy(true);
		try {
			setStatus(await harness<TaskboardStatus>(method));
			setError(null);
		} catch (failure) {
			setError(errText(failure) ?? String(failure));
		} finally {
			setBusy(false);
		}
	};
	return (
		<section className="flex min-w-0 flex-1 flex-col" aria-label={zh ? "任务面板" : "Taskboard"}>
			<header className="flex flex-wrap items-center justify-between gap-3 border-b border-border px-5 py-3">
				<div>
					<h1 className="text-ui-16 font-semibold text-ink">{zh ? "任务面板" : "Taskboard"}</h1>
					<p className="mt-1 text-ui-11 text-ink-faint">
						dashi-taskboard · {zh ? "任务管理与 Agent 执行" : "Issue management and Agent execution"}
					</p>
				</div>
				<div className="flex gap-2">
					<Button
						onClick={() =>
							void getDesktopApi().openExternal({ url: "https://github.com/chuspeeism/dashi-taskboard" })
						}
					>
						{zh ? "项目说明" : "Documentation"}
					</Button>
					{status?.running && (
						<Button disabled={busy} onClick={() => void act("stopTaskboard")}>
							{zh ? "停止服务" : "Stop service"}
						</Button>
					)}
				</div>
			</header>
			{error && (
				<p role="alert" className="m-4 text-ui-12 text-err">
					{error}
				</p>
			)}
			{status?.running && status.url ? (
				<>
					<TaskboardExecution />
					<iframe
						title="dashi-taskboard"
						className="min-h-0 flex-1 border-0 bg-surface"
						src={`${status.url}?lang=${zh ? "zh-CN" : "en"}`}
						sandbox="allow-scripts allow-same-origin allow-forms allow-downloads"
						referrerPolicy="no-referrer"
					/>
				</>
			) : (
				<div className="flex flex-1 flex-col items-center justify-center gap-4 p-8 text-center">
					<p className="max-w-lg text-ui-13 leading-relaxed text-ink-dim">
						{zh
							? "使用原生看板管理项目、任务与进度，并通过 Agent 执行面板启动任务、查看过程与回写结果。"
							: "Manage projects and issues, start Agent execution, inspect progress and synchronize results."}
					</p>
					{status && !status.installed && (
						<p className="text-ui-12 text-ink-faint">
							{zh
								? "请先运行项目中的 scripts/setup-taskboard.ps1 安装本地任务面板。"
								: "Run scripts/setup-taskboard.ps1 to install the local board."}
						</p>
					)}
					<Button
						variant="primary"
						disabled={busy || !status?.installed || !status.nodeAvailable}
						onClick={() => void act("startTaskboard")}
					>
						{busy ? (zh ? "正在启动…" : "Starting…") : zh ? "启动任务面板" : "Start taskboard"}
					</Button>
				</div>
			)}
		</section>
	);
}
