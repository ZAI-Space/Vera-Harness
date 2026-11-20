import { getDesktopApi } from "./api";
import { harness, setHarnessConnected } from "./harness-api";
import { setRuntimeCopy } from "./i18n";
import { useBehaviorPreferencesStore } from "./stores/behavior-preferences";
import { readModelAdvanced } from "./stores/model-advanced-preferences";
import { usePermissionPolicyStore } from "./stores/permission-policy";
import { useSessionsStore } from "./stores/sessions";
import { useSubagentDraftsStore } from "./stores/subagent-drafts";

/** 服务端配置是运行时真值；界面保留未连接时的草稿能力。 */
export async function initializeHarness(): Promise<void> {
	const status = await getDesktopApi().getBackendStatus();
	setHarnessConnected(status.connected);
	setRuntimeCopy(status.connected);
	if (!status.connected) return;
	const [behavior, roles, sandbox] = await Promise.all([
		harness<Record<string, unknown>>("getBehaviorSettings"),
		harness<ReturnType<typeof useSubagentDraftsStore.getState>["drafts"]>("getSubagentRoles"),
		harness<{ profiles: ReturnType<typeof useBehaviorPreferencesStore.getState>["sandboxProfiles"] }>(
			"getSandboxProfiles",
		),
	]);
	useBehaviorPreferencesStore.setState({ ...behavior, sandboxProfiles: sandbox.profiles });
	useSubagentDraftsStore.setState({ drafts: roles });
	useBehaviorPreferencesStore.subscribe((state, previous) => {
		if (state === previous) return;
		const settings = {
			defaultMode: state.defaultMode,
			permissionPolicy: state.permissionPolicy,
			commandShell: state.commandShell,
			defaultSandbox: state.defaultSandbox,
		};
		void harness("saveBehaviorSettings", { settings }).catch(async (error) => {
			const { reportHarnessFailure } = await import("./harness-api");
			await reportHarnessFailure(error);
		});
	});
}

/** 开始前显式提交选择；后端重新校验，任一失败都保留输入草稿并阻止任务启动。 */
export async function prepareHarnessTask(sessionId: string, policyTarget: string): Promise<void> {
	const behavior = useBehaviorPreferencesStore.getState();
	await harness("saveBehaviorSettings", {
		settings: {
			defaultMode: behavior.defaultMode,
			permissionPolicy: behavior.permissionPolicy,
			commandShell: behavior.commandShell,
			defaultSandbox: behavior.defaultSandbox,
		},
	});
	await harness("saveSubagentRoles", { roles: useSubagentDraftsStore.getState().drafts });
	await harness("saveSandboxProfiles", { profiles: behavior.sandboxProfiles });
	const policy =
		usePermissionPolicyStore.getState().byTarget[sessionId] ??
		usePermissionPolicyStore.getState().byTarget[policyTarget] ??
		behavior.permissionPolicy;
	const current = await harness<{ selections: Record<string, unknown> }>("getSessionSelections", {
		sessionId,
	});
	const model = useSessionsStore
		.getState()
		.sessions.find((session) => session.sessionId === sessionId)?.model;
	await harness("setSessionSelections", {
		sessionId,
		permissionPolicy: policy,
		modelOptions: model ? readModelAdvanced(model.provider)[model.modelId] : undefined,
		selections: {
			runMode: behavior.defaultMode === "agent" ? "normal" : behavior.defaultMode,
			sandbox: behavior.defaultSandbox,
			...current.selections,
		},
	});
}
