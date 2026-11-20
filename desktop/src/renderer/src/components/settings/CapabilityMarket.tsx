import { useState } from "react";
import { harness, isHarnessConnected } from "../../harness-api";

interface MarketRow {
	id: string;
	name: string;
	description: string;
}

/** 发现、查看、安装分开；服务端验证必要参数和凭据，安装不等于启用。 */
export function CapabilityMarket({
	kind,
	onInstalled,
}: {
	kind: "mcp" | "skill";
	onInstalled?: () => Promise<void>;
}) {
	const [query, setQuery] = useState("");
	const [rows, setRows] = useState<MarketRow[]>([]);
	const [selection, setSelection] = useState<MarketRow | null>(null);
	const [detail, setDetail] = useState<unknown>(null);
	const [message, setMessage] = useState("");
	const [busy, setBusy] = useState(false);
	if (!isHarnessConnected()) return null;
	const search = async () => {
		setBusy(true);
		setMessage("");
		try {
			if (kind === "mcp") {
				const value = await harness<{
					entries: { name: string; description?: string }[];
				}>("searchMcpMarket", { query });
				setRows(
					value.entries.map((entry) => ({
						id: entry.name,
						name: entry.name,
						description: entry.description ?? "",
					})),
				);
			} else {
				const value = await harness<{
					packages: { name: string; description: string; installSource: string }[];
				}>("searchCatalog", { query });
				setRows(
					value.packages.map((entry) => ({
						id: entry.installSource,
						name: entry.name,
						description: entry.description,
					})),
				);
			}
		} catch (error) {
			setMessage(String(error));
		} finally {
			setBusy(false);
		}
	};
	return (
		<section className="mb-5 rounded-xl bg-hover/30 p-3" aria-label={`${kind} marketplace`}>
			<p className="mb-2 text-ui-12">{kind === "mcp" ? "MCP Registry" : "skills.sh"}</p>
			<form
				className="flex gap-2"
				onSubmit={(event) => {
					event.preventDefault();
					void search();
				}}
			>
				<input
					aria-label={`${kind} search`}
					className="min-w-0 flex-1 rounded border border-border bg-transparent p-2"
					value={query}
					onChange={(event) => setQuery(event.target.value)}
				/>
				<button disabled={busy} type="submit">
					Search
				</button>
			</form>
			{message && (
				<p role="status" className="my-2 break-words text-ui-12">
					{message}
				</p>
			)}
			<ul>
				{rows.map((row) => (
					<li className="my-2" key={row.id}>
						<button
							type="button"
							onClick={async () => {
								setSelection(row);
								setDetail(null);
								if (kind === "mcp") {
									try {
										setDetail(await harness("inspectMcpMarket", { identifier: row.id }));
									} catch (error) {
										setMessage(String(error));
									}
								}
							}}
						>
							{row.name}
						</button>
						<p className="text-ui-11 text-ink-dim">{row.description}</p>
					</li>
				))}
			</ul>
			{selection && (
				<div className="mt-3">
					<pre className="max-h-48 overflow-auto whitespace-pre-wrap text-ui-11">
						{detail ? JSON.stringify(detail, null, 2) : selection.id}
					</pre>
					<button
						disabled={busy || (kind === "mcp" && !detail)}
						type="button"
						onClick={async () => {
							setBusy(true);
							try {
								await harness(
									kind === "mcp" ? "addMcpMarket" : "installPackage",
									kind === "mcp" ? { identifier: selection.id } : { source: selection.id, scope: "user" },
								);
								await onInstalled?.();
								setMessage("Saved. Select and enable the capability before running it.");
							} catch (error) {
								setMessage(String(error));
							} finally {
								setBusy(false);
							}
						}}
					>
						Add {kind === "mcp" ? "service" : "skill"}
					</button>
				</div>
			)}
		</section>
	);
}
