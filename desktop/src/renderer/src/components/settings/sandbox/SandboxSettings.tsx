import { useEffect, useState } from "react";
import { harness, isHarnessConnected, reportHarnessFailure } from "../../../harness-api";
import { useT } from "../../../i18n";
import { type SandboxProfileDraft, useBehaviorPreferencesStore } from "../../../stores/behavior-preferences";
import { EditIcon, PlusIcon, ShieldIcon, TrashIcon } from "../../icons";
import { Button } from "../../ui/Button";
import { ConfirmDialog } from "../../ui/ConfirmDialog";
import { Select } from "../../ui/Select";
import { BehaviorSettingRow } from "../BehaviorSettingRow";
import { SandboxProfileEditor } from "./SandboxProfileEditor";

/** 命名配置列表与编辑器：参考 OpenHands 运行时选择和 Agent-Sandbox 配置管理的交互结构。 */
export function SandboxSettings() {
	const t = useT();
	const profiles = useBehaviorPreferencesStore((s) => s.sandboxProfiles);
	const defaultSandbox = useBehaviorPreferencesStore((s) => s.defaultSandbox);
	const setDefaultSandbox = useBehaviorPreferencesStore((s) => s.setDefaultSandbox);
	const removeSandbox = useBehaviorPreferencesStore((s) => s.removeSandbox);
	const [editor, setEditor] = useState<SandboxProfileDraft | "new" | null>(null);
	const [deleting, setDeleting] = useState<string | null>(null);
	const [status, setStatus] = useState<Record<string, { available: boolean; reason: string }>>({});
	useEffect(() => {
		if (!isHarnessConnected()) return;
		let current = true;
		void harness<{ status: { choices: { name: string; available: boolean; reason: string }[] } }>(
			"getSandboxProfiles",
		)
			.then((value) => {
				if (current)
					setStatus(
						Object.fromEntries(
							value.status.choices
								.filter((row) => profiles.some((profile) => profile.name === row.name))
								.map((row) => [row.name, row]),
						),
					);
			})
			.catch(reportHarnessFailure);
		return () => {
			current = false;
		};
	}, [profiles]);
	return (
		<section aria-labelledby="behavior-sandbox-title">
			<header className="mb-4 flex items-start justify-between gap-3">
				<div>
					<h2 id="behavior-sandbox-title" className="text-ui-14 font-semibold text-ink">
						{t("behavior.sandbox.title")}
					</h2>
					<p className="mt-1 text-ui-12 leading-relaxed text-ink-dim">{t("behavior.sandbox.caption")}</p>
				</div>
				<Button size="sm" onClick={() => setEditor("new")} className="flex shrink-0 items-center gap-1.5">
					<PlusIcon />
					{t("behavior.sandbox.add")}
				</Button>
			</header>
			<div className="flex flex-col gap-3">
				<BehaviorSettingRow title={t("behavior.sandbox.default")} hint={t("behavior.sandbox.defaultHint")}>
					<Select
						variant="ghost"
						ariaLabel={t("behavior.sandbox.default")}
						value={defaultSandbox ?? "local"}
						onChange={(name) => setDefaultSandbox(name === "local" ? null : name)}
						options={[
							{ value: "local", label: t("behavior.sandbox.local") },
							...profiles.map((profile) => ({
								value: profile.name,
								label: profile.name,
								disabled: isHarnessConnected() && !status[profile.name]?.available,
								description: status[profile.name]?.reason,
							})),
						]}
					/>
				</BehaviorSettingRow>
				{editor ? (
					<SandboxProfileEditor
						key={editor === "new" ? "new" : editor.name}
						profile={editor === "new" ? undefined : editor}
						onClose={() => setEditor(null)}
					/>
				) : profiles.length === 0 ? (
					<div className="flex items-start gap-3 rounded-xl bg-hover/30 p-4 text-ink-faint">
						<ShieldIcon size={18} />
						<p className="text-ui-12 leading-relaxed">{t("behavior.sandbox.empty")}</p>
					</div>
				) : (
					<ul className="flex flex-col gap-2">
						{profiles.map((profile) => (
							<li
								key={profile.name}
								className="flex flex-wrap items-center justify-between gap-3 rounded-xl bg-hover/30 px-4 py-3"
							>
								<div className="min-w-0">
									<p className="break-words text-ui-13 font-medium text-ink-2">{profile.name}</p>
									<p className="mt-1 text-ui-11 text-ink-dim">
										{profile.mode === "docker" ? "Docker" : "Bubblewrap / WSL"} ·{" "}
										{t(`behavior.sandbox.access.${profile.workspace_access}`)}
									</p>
									<p className="mt-1 text-ui-11 text-ink-faint">
										{status[profile.name]?.reason || t("behavior.sandbox.notChecked")}
									</p>
								</div>
								<div className="flex items-center gap-1">
									<Button
										size="sm"
										aria-label={t("behavior.sandbox.editNamed", { name: profile.name })}
										onClick={() => setEditor(profile)}
									>
										<EditIcon />
									</Button>
									<Button
										size="sm"
										aria-label={t("behavior.sandbox.removeNamed", { name: profile.name })}
										onClick={() => setDeleting(profile.name)}
									>
										<TrashIcon />
									</Button>
								</div>
							</li>
						))}
					</ul>
				)}
				<p className="text-ui-11 leading-relaxed text-ink-faint">{t("behavior.sandbox.workspaceHint")}</p>
			</div>
			{deleting && (
				<ConfirmDialog
					title={t("behavior.sandbox.remove")}
					description={t("behavior.sandbox.removeHint", { name: deleting })}
					confirmLabel={t("common.delete")}
					cancelLabel={t("common.cancel")}
					danger
					onCancel={() => setDeleting(null)}
					onConfirm={async () => {
						if (isHarnessConnected()) {
							try {
								await harness("saveSandboxProfiles", {
									profiles: profiles.filter((profile) => profile.name !== deleting),
								});
							} catch (error) {
								await reportHarnessFailure(error);
								return;
							}
						}
						removeSandbox(deleting);
						if (editor !== "new" && editor?.name === deleting) setEditor(null);
						setDeleting(null);
					}}
				/>
			)}
		</section>
	);
}
