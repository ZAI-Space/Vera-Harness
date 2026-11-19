import { useState } from "react";
import {
	WORKSPACE_INPUT_CLASS,
	WorkspaceButton,
	WorkspaceField,
} from "../../components/workspace/WorkspacePage";
import { useT } from "../../i18n";
import type { WorkspacePlugin } from "./model";

/** 先编辑来源草稿，不请求仓库或解析远端清单；真实安装留给后续接口。 */
export function PluginSourceForm({
	onSave,
	onCancel,
}: {
	onSave: (plugin: WorkspacePlugin) => void;
	onCancel: () => void;
}) {
	const t = useT();
	const [source, setSource] = useState("");
	const [name, setName] = useState("");
	const [error, setError] = useState(false);
	return (
		<form
			className="rounded-xl bg-surface p-5 shadow-soft"
			onSubmit={(event) => {
				event.preventDefault();
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
					!name.trim()
				) {
					setError(true);
					return;
				}
				onSave({
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
			}}
		>
			<h2 className="mb-5 text-ui-16 font-medium text-ink">{t("plugins.fromSource")}</h2>
			<div className="grid gap-4 sm:grid-cols-2">
				<WorkspaceField label={t("plugins.name")} htmlFor="plugin-name">
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
					<input
						id="plugin-source"
						className={WORKSPACE_INPUT_CLASS}
						type="url"
						required
						placeholder="https://github.com/owner/plugin"
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
			<div className="mt-5 flex justify-end gap-2">
				<WorkspaceButton onClick={onCancel}>{t("common.cancel")}</WorkspaceButton>
				<WorkspaceButton type="submit" className="bg-hover">
					{t("plugins.saveSource")}
				</WorkspaceButton>
			</div>
		</form>
	);
}
