import { useState } from "react";
import {
	WORKSPACE_INPUT_CLASS,
	WorkspaceButton,
	WorkspaceField,
} from "../../components/workspace/WorkspacePage";
import { useT } from "../../i18n";
import type { WorkspacePlugin } from "./model";

/** Add a repository catalog; package installation remains a separate explicit action. */
export function PluginSourceForm({
	onSave,
	onCancel,
	errorMessage,
}: {
	onSave: (plugin: WorkspacePlugin) => void | Promise<void>;
	onCancel: () => void;
	errorMessage?: string | null;
}) {
	const t = useT();
	const [source, setSource] = useState("");
	const [name, setName] = useState("");
	const [host, setHost] = useState<"github" | "gitee">("github");
	const [error, setError] = useState(false);
	const [saving, setSaving] = useState(false);
	return (
		<form
			className="rounded-xl bg-surface p-5 shadow-soft"
			onSubmit={async (event) => {
				event.preventDefault();
				setError(false);
				let url: URL;
				try {
					url = new URL(source);
				} catch {
					setError(true);
					return;
				}
				if (
					url.protocol !== "https:" ||
					url.username ||
					url.password ||
					url.search ||
					url.hash ||
					url.hostname !== `${host}.com` ||
					!name.trim()
				) {
					setError(true);
					return;
				}
				setSaving(true);
				try {
					await onSave({
						id: crypto.randomUUID(),
						name: name.trim(),
						description: "",
						source: url.href,
						version: "—",
						author: "—",
						category: "development",
						capabilities: [],
						enabled: false,
						status: "preview",
					});
				} finally {
					setSaving(false);
				}
			}}
		>
			<h2 className="mb-2 text-ui-16 font-medium text-ink">{t("plugins.addRepository")}</h2>
			<p className="mb-5 text-ui-12 text-ink-faint">{t("plugins.repositoryHint")}</p>
			<div className="grid gap-4 sm:grid-cols-2">
				<WorkspaceField label={t("plugins.repositoryName")} htmlFor="plugin-name">
					<input
						id="plugin-name"
						className={WORKSPACE_INPUT_CLASS}
						required
						maxLength={100}
						value={name}
						onChange={(event) => setName(event.target.value)}
					/>
				</WorkspaceField>
				<WorkspaceField label={t("plugins.source")} htmlFor="plugin-source">
					<select
						className={WORKSPACE_INPUT_CLASS}
						value={host}
						onChange={(event) => setHost(event.target.value as "github" | "gitee")}
					>
						<option value="github">GitHub</option>
						<option value="gitee">Gitee</option>
					</select>
					<input
						id="plugin-source"
						className={WORKSPACE_INPUT_CLASS}
						type="url"
						required
						placeholder={`https://${host}.com/owner/plugin`}
						value={source}
						onChange={(event) => setSource(event.target.value)}
					/>
				</WorkspaceField>
			</div>
			{error && (
				<p role="alert" className="mt-3 text-ui-12 text-danger">
					{t("plugins.invalidSource")}
				</p>
			)}
			{errorMessage && (
				<p role="alert" className="mt-3 text-ui-12 text-danger">
					{errorMessage}
				</p>
			)}
			<div className="mt-5 flex justify-end gap-2">
				<WorkspaceButton onClick={onCancel}>{t("common.cancel")}</WorkspaceButton>
				<WorkspaceButton type="submit" className="bg-hover" disabled={saving}>
					{t("plugins.saveRepository")}
				</WorkspaceButton>
			</div>
		</form>
	);
}
