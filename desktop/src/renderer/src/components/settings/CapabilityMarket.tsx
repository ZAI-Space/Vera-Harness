import { useCallback, useEffect, useRef, useState } from "react";
import { getDesktopApi } from "../../api";
import { PluginIcon } from "../../features/plugins/PluginIcon";
import { harness } from "../../harness-api";
import { useI18nStore } from "../../i18n";
import { errText } from "../../lib/error-text";
import { Button } from "../ui/Button";

interface MarketRow {
	name: string;
	description: string;
	descriptionZh?: string;
	version: string;
	title: string;
	icon?: string;
	repository: string;
	transport: string;
	toolCount: number;
}
interface MarketPlan {
	name: string;
	version: string;
	config: Record<string, unknown>;
	required_inputs: string[];
	missing_environment: string[];
	prerequisites: string[];
}

/** Official registry browser. Inspect configuration before saving; new services stay disabled. */
export function CapabilityMarket({
	onInstalled,
	onConfigure,
}: {
	onInstalled: () => Promise<void>;
	onConfigure: (config: Record<string, unknown>) => void;
}) {
	const zh = useI18nStore((state) => state.language === "zh");
	const [query, setQuery] = useState("");
	const [rows, setRows] = useState<MarketRow[]>([]);
	const [updatedAt, setUpdatedAt] = useState("");
	const [selection, setSelection] = useState<MarketRow | null>(null);
	const [detail, setDetail] = useState<MarketPlan | null>(null);
	const [error, setError] = useState<string | null>(null);
	const [loading, setLoading] = useState(false);
	const [busy, setBusy] = useState(false);
	const generation = useRef(0);
	const search = useCallback(async (value: string, refresh = false) => {
		const request = ++generation.current;
		setLoading(true);
		setError(null);
		try {
			const result = await harness<{ entries: MarketRow[]; updatedAt: string }>("searchMcpMarket", {
				query: value,
				refresh,
			});
			if (request === generation.current) {
				setRows(result.entries);
				setUpdatedAt(result.updatedAt);
			}
		} catch (failure) {
			if (request === generation.current) setError(errText(failure) ?? String(failure));
		} finally {
			if (request === generation.current) setLoading(false);
		}
	}, []);
	useEffect(() => {
		void search("");
		return () => {
			generation.current++;
		};
	}, [search]);
	const inspect = async (row: MarketRow) => {
		const request = ++generation.current;
		setSelection(row);
		setDetail(null);
		setError(null);
		setLoading(true);
		try {
			const plan = await harness<MarketPlan>("inspectMcpMarket", { identifier: row.name });
			if (request === generation.current) setDetail(plan);
		} catch (failure) {
			if (request === generation.current) setError(errText(failure) ?? String(failure));
		} finally {
			if (request === generation.current) setLoading(false);
		}
	};
	if (selection)
		return (
			<div className="flex flex-col gap-4">
				<Button
					onClick={() => {
						generation.current++;
						setSelection(null);
						setDetail(null);
						setError(null);
						setLoading(false);
					}}
				>
					{zh ? "返回市场" : "Back to marketplace"}
				</Button>
				<div className="flex items-center gap-3">
					<PluginIcon name={selection.title} icon={selection.icon} />
					<h3 className="break-words text-ui-16 font-semibold text-ink">{selection.title}</h3>
				</div>
				<p className="text-ui-13 text-ink-dim">{(zh && selection.descriptionZh) || selection.description}</p>
				<Button onClick={() => void getDesktopApi().openExternal({ url: selection.repository })}>
					{zh ? "官方项目与使用说明" : "Project and documentation"}
				</Button>
				{loading && <p role="status">{zh ? "正在读取配置…" : "Reading configuration…"}</p>}
				{detail && (
					<>
						<p className="text-ui-12 text-ink-faint">
							{detail.version} · {detail.prerequisites.join(", ") || "HTTP"}
						</p>
						<pre className="max-h-64 overflow-auto whitespace-pre-wrap rounded-lg bg-hover p-4 text-ui-12 text-ink">
							{JSON.stringify({ mcpServers: { [detail.name]: detail.config } }, null, 2)}
						</pre>
						{detail.required_inputs.length > 0 && (
							<p className="text-ui-12 text-ink-dim">
								{zh ? "需要补充参数：" : "Required arguments: "}
								{detail.required_inputs.join(", ")}
							</p>
						)}
						{detail.missing_environment.length > 0 && (
							<p className="text-ui-12 text-ink-dim">
								{zh ? "启用前请设置环境变量：" : "Set environment variables before enabling: "}
								{detail.missing_environment.join(", ")}
							</p>
						)}
						<div className="flex justify-end gap-2">
							<Button
								disabled={busy}
								onClick={() => onConfigure({ mcpServers: { [detail.name]: detail.config } })}
							>
								{zh ? "编辑 JSON" : "Edit JSON"}
							</Button>
							<Button
								variant="primary"
								disabled={busy || detail.required_inputs.length > 0}
								onClick={async () => {
									setBusy(true);
									setError(null);
									try {
										await harness("addMcpMarket", { identifier: selection.name, version: detail.version });
										await onInstalled();
									} catch (failure) {
										setError(errText(failure) ?? String(failure));
									} finally {
										setBusy(false);
									}
								}}
							>
								{zh ? "添加服务" : "Add service"}
							</Button>
						</div>
					</>
				)}
				{error && (
					<p role="alert" className="text-ui-12 text-err">
						{error}
					</p>
				)}
			</div>
		);
	return (
		<section aria-label="MCP marketplace" className="flex flex-col gap-4">
			<p className="text-ui-12 text-ink-dim">
				{zh
					? "Docker 官方 MCP 目录 · 优先展示常用成熟服务。容器服务需要 Docker Engine；新增服务默认停用。"
					: "Docker official MCP catalog · Established services first. Container services require Docker Engine. New services remain disabled."}
			</p>
			<div className="flex items-center justify-between text-ui-11 text-ink-faint">
				<span>
					{zh ? "本机目录 · 更新于 " : "Local catalog · Updated "}
					{updatedAt}
				</span>
				<Button disabled={loading} onClick={() => void search(query, true)}>
					{zh ? "更新目录" : "Refresh catalog"}
				</Button>
			</div>
			<form
				className="flex gap-2"
				onSubmit={(event) => {
					event.preventDefault();
					void search(query);
				}}
			>
				<input
					aria-label="MCP search"
					placeholder={zh ? "搜索 MCP 服务" : "Search MCP services"}
					className="min-w-0 flex-1 rounded-lg border border-border bg-canvas px-3 py-2 text-ui-13 text-ink"
					value={query}
					onChange={(event) => setQuery(event.target.value)}
				/>
				<Button type="submit" disabled={loading}>
					{zh ? "搜索" : "Search"}
				</Button>
			</form>
			{loading && (
				<p role="status" className="text-ui-12 text-ink-faint">
					{zh ? "正在加载…" : "Loading…"}
				</p>
			)}
			{error && (
				<p role="alert" className="text-ui-12 text-err">
					{error}
				</p>
			)}
			<ul className="divide-y divide-border rounded-xl border border-border">
				{rows.map((row) => (
					<li key={row.name} className="flex items-center gap-3 p-4">
						<PluginIcon name={row.title} icon={row.icon} />
						<button type="button" className="min-w-0 flex-1 text-left" onClick={() => void inspect(row)}>
							<span className="block truncate text-ui-13 font-medium text-ink">{row.title}</span>
							<span className="mt-1 block line-clamp-2 text-ui-12 text-ink-dim">
								{(zh && row.descriptionZh) || row.description}
							</span>
							<span className="mt-1 block text-ui-11 text-ink-faint">
								{row.transport}
								{row.toolCount ? ` · ${row.toolCount} ${zh ? "个工具" : "tools"}` : ""}
							</span>
						</button>
						<Button
							aria-label={`${zh ? "查看详情" : "Details"} ${row.name}`}
							onClick={() => void inspect(row)}
						>
							+
						</Button>
					</li>
				))}
			</ul>
			{!loading && !error && rows.length === 0 && (
				<p className="text-ui-12 text-ink-faint">{zh ? "没有找到匹配的服务。" : "No matching services."}</p>
			)}
		</section>
	);
}
