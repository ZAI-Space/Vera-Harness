import type { McpServerView } from "@vera/contracts";
import { useState } from "react";
import { harness } from "../../../harness-api";
import { useT } from "../../../i18n";
import { errText } from "../../../lib/error-text";
import { Button } from "../../ui/Button";

interface LocalConfig {
	id: string;
	path: string;
	names: string[];
	error?: string;
}

/** Submit the complete JSON atomically; preserve transport options when editing. */
export function McpJsonEditor({
	server,
	cwd,
	initialConfig,
	onSaved,
	onCancel,
}: {
	server?: McpServerView;
	cwd?: string;
	initialConfig?: Record<string, unknown>;
	onSaved: () => Promise<void>;
	onCancel: () => void;
}) {
	const t = useT();
	const [value, setValue] = useState(() =>
		initialConfig
			? JSON.stringify(initialConfig, null, 2)
			: server
				? JSON.stringify(
						{
							mcpServers: {
								[server.name]:
									server.config ??
									(server.transport.kind === "stdio"
										? { command: server.transport.command, args: server.transport.args ?? [] }
										: server.transport.kind === "url"
											? { url: server.transport.url }
											: {}),
							},
						},
						null,
						2,
					)
				: "",
	);
	const [error, setError] = useState<string | null>(null);
	const [busy, setBusy] = useState(false);
	const [localConfigs, setLocalConfigs] = useState<LocalConfig[] | null>(null);
	const save = async () => {
		setError(null);
		let config: unknown;
		try {
			config = JSON.parse(value);
		} catch {
			setError(t("settings.mcp.jsonInvalid"));
			return;
		}
		setBusy(true);
		try {
			await harness("saveMcpJson", { config });
			await onSaved();
		} catch (failure) {
			setError(errText(failure) ?? String(failure));
		} finally {
			setBusy(false);
		}
	};
	return (
		<div className="flex flex-col gap-4">
			<p className="text-ui-12 leading-relaxed text-ink-dim">{t("settings.mcp.jsonHint")}</p>
			{!server && (
				<div className="flex flex-col gap-2">
					<Button
						disabled={busy}
						onClick={async () => {
							setBusy(true);
							setError(null);
							try {
								setLocalConfigs(await harness<LocalConfig[]>("discoverLocalMcpConfigs", { cwd }));
							} catch (failure) {
								setError(errText(failure) ?? String(failure));
							} finally {
								setBusy(false);
							}
						}}
					>
						{t("settings.mcp.scanLocal")}
					</Button>
					{localConfigs?.length === 0 && (
						<p className="text-ui-12 text-ink-dim">{t("settings.mcp.scanEmpty")}</p>
					)}
					{localConfigs?.map((config) => (
						<button
							key={config.id}
							type="button"
							disabled={busy || !!config.error}
							className="rounded-lg bg-hover px-3 py-2 text-left text-ui-12 text-ink-dim disabled:opacity-50"
							onClick={async () => {
								setBusy(true);
								setError(null);
								try {
									setValue(
										JSON.stringify(await harness("loadLocalMcpConfig", { cwd, id: config.id }), null, 2),
									);
								} catch (failure) {
									setError(errText(failure) ?? String(failure));
								} finally {
									setBusy(false);
								}
							}}
						>
							{config.names.join(", ")}
							<span className="block break-all text-ink-faint">{config.path}</span>
							{config.error}
						</button>
					))}
				</div>
			)}
			<textarea
				aria-label="MCP JSON"
				className="min-h-80 w-full resize-y rounded-lg border border-border bg-canvas p-4 font-mono text-ui-12 text-ink outline-none focus:border-ink-faint"
				spellCheck={false}
				value={value}
				onChange={(event) => {
					setValue(event.target.value);
					setError(null);
				}}
				placeholder={
					'{\n  "mcpServers": {\n    "time": {\n      "command": "uvx",\n      "args": ["mcp-server-time"]\n    }\n  }\n}'
				}
			/>
			{error && (
				<p role="alert" className="text-ui-12 text-err">
					{error}
				</p>
			)}
			<div className="flex justify-end gap-2">
				<Button disabled={busy} onClick={onCancel}>
					{t("common.cancel")}
				</Button>
				<Button variant="primary" disabled={busy || !value.trim()} onClick={() => void save()}>
					{t("common.save")}
				</Button>
			</div>
		</div>
	);
}
