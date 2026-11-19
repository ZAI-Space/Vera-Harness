// Session-default layout adapted from PI-Desktop AgentBehaviorSettings.tsx, LGPL-3.0-only.
import { getDesktopApi } from "../../api";
import { isHarnessConnected } from "../../harness-api";
import { useT } from "../../i18n";
import { type CommandShell, useBehaviorPreferencesStore } from "../../stores/behavior-preferences";
import type { PermissionPolicy } from "../../stores/permission-policy";
import { Select } from "../ui/Select";
import { BehaviorSettingRow } from "./BehaviorSettingRow";
import { SandboxSettings } from "./sandbox/SandboxSettings";

/** 行为设置只保留会话默认项与沙箱；偏好是前端意图，不改写现有运行会话。 */
export function BehaviorPanel() {
	const t = useT();
	const mode = useBehaviorPreferencesStore((s) => s.defaultMode);
	const setMode = useBehaviorPreferencesStore((s) => s.setDefaultMode);
	const permission = useBehaviorPreferencesStore((s) => s.permissionPolicy);
	const setPermission = useBehaviorPreferencesStore((s) => s.setPermissionPolicy);
	const shell = useBehaviorPreferencesStore((s) => s.commandShell);
	const setShell = useBehaviorPreferencesStore((s) => s.setCommandShell);
	const storageError = useBehaviorPreferencesStore((s) => s.storageError);
	const platform = getDesktopApi().platform;
	const shells: CommandShell[] = isHarnessConnected()
		? platform === "win32"
			? ["system", "git-bash"]
			: ["system", "bash"]
		: platform === "win32"
			? ["system", "windows-powershell", "pwsh", "git-bash"]
			: ["system", "bash", "zsh"];
	if (!shells.includes(shell)) shells.push(shell);
	return (
		<div className="flex flex-col gap-7">
			<section aria-labelledby="behavior-session-defaults">
				<header className="mb-4">
					<h2 id="behavior-session-defaults" className="text-ui-14 font-semibold text-ink">
						{t("behavior.sessionDefaults")}
					</h2>
					<p className="mt-1 text-ui-12 text-ink-dim">{t("behavior.sessionDefaultsHint")}</p>
				</header>
				<div className="flex flex-col gap-2">
					<BehaviorSettingRow title={t("behavior.mode")} hint={t("behavior.modeHint")}>
						<fieldset className="inline-flex rounded-full bg-hover p-1" aria-label={t("behavior.mode")}>
							{(["agent", "plan", "goal"] as const).map((value) => (
								<button
									key={value}
									type="button"
									aria-pressed={mode === value}
									className={`rounded-full px-3 py-1.5 text-ui-12 outline-none transition-colors focus-visible:ring-2 focus-visible:ring-ink-faint ${mode === value ? "bg-surface font-medium text-ink shadow-soft" : "text-ink-dim hover:text-ink"}`}
									onClick={() => setMode(value)}
								>
									{t(`behavior.modes.${value}`)}
								</button>
							))}
						</fieldset>
					</BehaviorSettingRow>
					<BehaviorSettingRow title={t("behavior.permissions")} hint={t("behavior.permissionsHint")}>
						<Select
							variant="ghost"
							ariaLabel={t("behavior.permissions")}
							value={permission}
							onChange={(value) => setPermission(value as PermissionPolicy)}
							options={(["confirm", "yolo", "human"] as const).map((value) => ({
								value,
								label: t(`behavior.permissionModes.${value}`),
							}))}
						/>
					</BehaviorSettingRow>
					<BehaviorSettingRow title={t("behavior.shell")} hint={t("behavior.shellHint")}>
						<Select
							variant="ghost"
							ariaLabel={t("behavior.shell")}
							value={shell}
							onChange={(value) => setShell(value as CommandShell)}
							options={shells.map((value) => ({ value, label: t(`behavior.shells.${value}`) }))}
						/>
					</BehaviorSettingRow>
				</div>
			</section>
			<SandboxSettings />
			<p className="text-ui-11 leading-relaxed text-ink-faint">{t("behavior.frontendNotice")}</p>
			{storageError && (
				<p role="alert" className="text-ui-12 text-danger">
					{t("behavior.storageError")}
				</p>
			)}
		</div>
	);
}
