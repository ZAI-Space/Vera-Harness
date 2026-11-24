// Session-default layout adapted from PI-Desktop AgentBehaviorSettings.tsx, LGPL-3.0-only.

import { useCallback, useEffect, useState } from "react";
import { getDesktopApi } from "../../api";
import { harness, isHarnessConnected } from "../../harness-api";
import { useT } from "../../i18n";
import { type CommandShell, useBehaviorPreferencesStore } from "../../stores/behavior-preferences";
import type { PermissionPolicy } from "../../stores/permission-policy";
import { YoloWarning } from "../composer/YoloWarning";
import { Select } from "../ui/Select";
import { BehaviorSettingRow } from "./BehaviorSettingRow";
import { SandboxSettings } from "./sandbox/SandboxSettings";

/** 行为设置只保留会话默认项与沙箱；偏好是前端意图，不改写现有运行会话。 */
export function BehaviorPanel() {
	const t = useT();
	const [warning, setWarning] = useState(false);
	const [detected, setDetected] = useState<Array<{ id: CommandShell; label: string }>>([]);
	const [detecting, setDetecting] = useState(false);
	const [shellError, setShellError] = useState(false);
	const detect = useCallback(async (refresh = false) => {
		setDetecting(true);
		setShellError(false);
		try {
			setDetected(await harness<Array<{ id: CommandShell; label: string }>>("getCommandShells", { refresh }));
		} catch {
			setShellError(true);
		} finally {
			setDetecting(false);
		}
	}, []);
	useEffect(() => {
		if (isHarnessConnected()) void detect();
	}, [detect]);
	const mode = useBehaviorPreferencesStore((s) => s.defaultMode);
	const setMode = useBehaviorPreferencesStore((s) => s.setDefaultMode);
	const permission = useBehaviorPreferencesStore((s) => s.permissionPolicy);
	const setPermission = useBehaviorPreferencesStore((s) => s.setPermissionPolicy);
	const shell = useBehaviorPreferencesStore((s) => s.commandShell);
	const setShell = useBehaviorPreferencesStore((s) => s.setCommandShell);
	const storageError = useBehaviorPreferencesStore((s) => s.storageError);
	const platform = getDesktopApi().platform;
	const connected = isHarnessConnected();
	let shells: CommandShell[] = platform === "win32" ? ["system", "git-bash"] : ["system", "bash"];
	if (!connected)
		shells =
			platform === "win32" ? ["system", "windows-powershell", "pwsh", "git-bash"] : ["system", "bash", "zsh"];
	if (detected.length) shells = detected.map((row) => row.id);
	if (!shells.includes(shell)) shells.push(shell);
	const shellOptions = shells.map((value) => ({
		value,
		label: value.startsWith("wsl:")
			? (detected.find((row) => row.id === value)?.label ?? value)
			: t(`behavior.shells.${value as Exclude<CommandShell, `wsl:${string}`>}`),
	}));
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
							onChange={(value) => {
								if (value === "yolo" && permission !== "yolo") setWarning(true);
								else setPermission(value as PermissionPolicy);
							}}
							options={(["confirm", "yolo", "human"] as const).map((value) => ({
								value,
								label: t(`behavior.permissionModes.${value}`),
							}))}
						/>
					</BehaviorSettingRow>
					<BehaviorSettingRow title={t("behavior.shell")} hint={t("behavior.shellHint")}>
						<div className="flex items-center gap-2">
							<Select
								variant="ghost"
								ariaLabel={t("behavior.shell")}
								value={shell}
								onChange={(value) => setShell(value as CommandShell)}
								options={shellOptions}
							/>
							{isHarnessConnected() && (
								<button
									type="button"
									className="text-ui-12 text-ink-dim"
									disabled={detecting}
									onClick={() => void detect(true)}
								>
									{detecting ? t("behavior.detecting") : t("behavior.detectShells")}
								</button>
							)}
						</div>
					</BehaviorSettingRow>
				</div>
			</section>
			<SandboxSettings />
			{shellError && (
				<p role="alert" className="text-ui-12 text-err">
					{t("behavior.detectShellsFailed")}
				</p>
			)}
			{warning && (
				<YoloWarning
					onCancel={() => setWarning(false)}
					onConfirm={() => {
						setPermission("yolo");
						setWarning(false);
					}}
				/>
			)}
			<p className="text-ui-11 leading-relaxed text-ink-faint">{t("behavior.frontendNotice")}</p>
			{storageError && (
				<p role="alert" className="text-ui-12 text-err">
					{t("behavior.storageError")}
				</p>
			)}
		</div>
	);
}
