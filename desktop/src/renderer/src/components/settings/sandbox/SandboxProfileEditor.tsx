import { useState } from "react";
import { harness, isHarnessConnected, reportHarnessFailure } from "../../../harness-api";
import { useT } from "../../../i18n";
import {
	type SandboxDraftError,
	type SandboxProfileDraft,
	useBehaviorPreferencesStore,
	validateSandboxProfile,
} from "../../../stores/behavior-preferences";
import { Button } from "../../ui/Button";
import { Select } from "../../ui/Select";
import { Switch } from "../../ui/Switch";
import { BehaviorSettingRow } from "../BehaviorSettingRow";

const INPUT_CLASS =
	"w-full min-w-0 rounded-lg border border-border bg-transparent px-3 py-2 text-ui-12 text-ink outline-none focus:border-ink-faint";
const EMPTY_PROFILE: SandboxProfileDraft = {
	name: "",
	mode: "docker",
	docker_image: "python:3.12-slim",
	workspace_access: "read-write",
	timeout: 30,
	allow_web_tools: false,
	host_mcp_servers: [],
	remote_mcp_servers: [],
};
const serverNames = (value: string) => value.split(/[\s,，]+/).filter(Boolean);

/** 编辑 Harness 已有配置字段；表单提交只保存本机前端草稿，不执行命令。 */
export function SandboxProfileEditor({
	profile,
	onClose,
}: {
	profile?: SandboxProfileDraft;
	onClose: () => void;
}) {
	const t = useT();
	const [draft, setDraft] = useState<SandboxProfileDraft>(() => ({ ...EMPTY_PROFILE, ...profile }));
	const [hostServers, setHostServers] = useState(profile?.host_mcp_servers.join(", ") ?? "");
	const [remoteServers, setRemoteServers] = useState(profile?.remote_mcp_servers.join(", ") ?? "");
	const [error, setError] = useState<SandboxDraftError | null>(null);
	const save = useBehaviorPreferencesStore((s) => s.saveSandbox);
	const update = (patch: Partial<SandboxProfileDraft>) => setDraft((current) => ({ ...current, ...patch }));
	const value = {
		...draft,
		host_mcp_servers: serverNames(hostServers),
		remote_mcp_servers: serverNames(remoteServers),
	};
	return (
		<form
			aria-label={t(profile ? "behavior.sandbox.edit" : "behavior.sandbox.add")}
			onSubmit={async (event) => {
				event.preventDefault();
				if (isHarnessConnected()) {
					const current = useBehaviorPreferencesStore.getState().sandboxProfiles;
					const profiles = [...current.filter((item) => item.name !== profile?.name), value];
					try {
						await harness("saveSandboxProfiles", { profiles });
					} catch (error) {
						setError("storage");
						await reportHarnessFailure(error);
						return;
					}
				}
				const failure = save(value, profile?.name);
				if (failure) {
					setError(failure);
					return;
				}
				onClose();
			}}
			className="flex flex-col gap-4 rounded-xl bg-hover/30 p-4"
		>
			<div className="flex flex-wrap items-center justify-between gap-2">
				<h3 className="text-ui-13 font-medium text-ink">
					{t(profile ? "behavior.sandbox.edit" : "behavior.sandbox.add")}
				</h3>
				<Button size="sm" onClick={onClose}>
					{t("common.cancel")}
				</Button>
			</div>
			<label className="flex flex-col gap-2 text-ui-12 text-ink-dim" htmlFor="sandbox-name">
				{t("behavior.sandbox.name")}
				<input
					id="sandbox-name"
					className={INPUT_CLASS}
					value={draft.name}
					required
					maxLength={48}
					placeholder="python-dev"
					onChange={(event) => update({ name: event.target.value })}
				/>
			</label>
			<BehaviorSettingRow title={t("behavior.sandbox.engine")} hint={t("behavior.sandbox.engineHint")}>
				<Select
					variant="ghost"
					ariaLabel={t("behavior.sandbox.engine")}
					value={draft.mode}
					onChange={(mode) => update({ mode: mode as SandboxProfileDraft["mode"] })}
					options={[
						{ value: "docker", label: "Docker" },
						{ value: "bubblewrap", label: "Bubblewrap / WSL" },
					]}
				/>
			</BehaviorSettingRow>
			{draft.mode === "docker" && (
				<label className="flex flex-col gap-2 text-ui-12 text-ink-dim" htmlFor="sandbox-image">
					{t("behavior.sandbox.image")}
					<input
						id="sandbox-image"
						className={INPUT_CLASS}
						value={draft.docker_image}
						required
						onChange={(event) => update({ docker_image: event.target.value })}
					/>
					<span className="text-ui-11 leading-relaxed text-ink-faint">{t("behavior.sandbox.imageHint")}</span>
				</label>
			)}
			{draft.mode === "bubblewrap" && (
				<p className="text-ui-11 leading-relaxed text-ink-faint">{t("behavior.sandbox.bubblewrapHint")}</p>
			)}
			<BehaviorSettingRow title={t("behavior.sandbox.workspaceAccess")}>
				<Select
					variant="ghost"
					ariaLabel={t("behavior.sandbox.workspaceAccess")}
					value={draft.workspace_access}
					onChange={(workspace_access) =>
						update({ workspace_access: workspace_access as SandboxProfileDraft["workspace_access"] })
					}
					options={(["read-write", "read-only"] as const).map((access) => ({
						value: access,
						label: t(`behavior.sandbox.access.${access}`),
					}))}
				/>
			</BehaviorSettingRow>
			<label
				className="flex items-center justify-between gap-3 text-ui-12 text-ink-dim"
				htmlFor="sandbox-timeout"
			>
				{t("behavior.sandbox.timeout")}
				<input
					id="sandbox-timeout"
					className={`${INPUT_CLASS} max-w-24`}
					type="number"
					required
					min={1}
					max={3600}
					step={1}
					value={draft.timeout}
					onChange={(event) => update({ timeout: Number(event.target.value) })}
				/>
			</label>
			<details className="rounded-lg">
				<summary className="cursor-pointer py-2 text-ui-12 font-medium text-ink-dim">
					{t("behavior.sandbox.externalTools")}
				</summary>
				<div className="mt-3 flex flex-col gap-4">
					<BehaviorSettingRow
						title={t("behavior.sandbox.allowWeb")}
						hint={t("behavior.sandbox.allowWebHint")}
					>
						<Switch
							checked={draft.allow_web_tools}
							aria-label={t("behavior.sandbox.allowWeb")}
							onCheckedChange={(allow_web_tools) => update({ allow_web_tools })}
						/>
					</BehaviorSettingRow>
					<label className="flex flex-col gap-2 text-ui-12 text-ink-dim" htmlFor="sandbox-host-mcp">
						{t("behavior.sandbox.hostMcp")}
						<input
							id="sandbox-host-mcp"
							className={INPUT_CLASS}
							value={hostServers}
							onChange={(event) => setHostServers(event.target.value)}
						/>
					</label>
					<label className="flex flex-col gap-2 text-ui-12 text-ink-dim" htmlFor="sandbox-remote-mcp">
						{t("behavior.sandbox.remoteMcp")}
						<input
							id="sandbox-remote-mcp"
							className={INPUT_CLASS}
							value={remoteServers}
							onChange={(event) => setRemoteServers(event.target.value)}
						/>
					</label>
					<p className="text-ui-11 leading-relaxed text-ink-faint">{t("behavior.sandbox.mcpHint")}</p>
				</div>
			</details>
			{error && (
				<p role="alert" className="text-ui-12 text-danger">
					{t(`behavior.sandbox.errors.${error}`)}
				</p>
			)}
			<div className="flex justify-end gap-2">
				<Button onClick={onClose}>{t("common.cancel")}</Button>
				<Button type="submit" disabled={!!validateSandboxProfile(value)} className="font-medium">
					{t("behavior.sandbox.save")}
				</Button>
			</div>
		</form>
	);
}
