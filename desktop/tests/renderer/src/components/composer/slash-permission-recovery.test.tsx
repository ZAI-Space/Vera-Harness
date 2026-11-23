// @vitest-environment happy-dom
import { act } from "react";
import { createRoot } from "react-dom/client";
import { expect, it, vi } from "vitest";
import { useComposerSend } from "../../../../../src/renderer/src/components/composer/use-composer-send";
import { useSlashMenu } from "../../../../../src/renderer/src/components/composer/use-slash-menu";
import { useDraftStore } from "../../../../../src/renderer/src/stores/drafts";

const fixture = vi.hoisted(() => ({
	create: vi.fn(),
	save: vi.fn(),
	setText: vi.fn(),
	run: vi.fn(),
	draft: { generation: 12, cwd: "workspace" } as { generation: number; cwd: string } | undefined,
}));
vi.mock("../../../../../src/renderer/src/i18n", () => ({ useT: () => (key: string) => key }));
vi.mock("../../../../../src/renderer/src/environment-api", () => ({ getExecutionApi: () => ({}) }));
vi.mock("../../../../../src/renderer/src/harness-api", () => ({ isHarnessConnected: () => true }));
vi.mock("../../../../../src/renderer/src/harness-settings", () => ({ prepareHarnessTask: vi.fn() }));
vi.mock("../../../../../src/renderer/src/stores/sessions", () => ({
	useSessionsStore: { getState: () => ({ newSessionDraft: fixture.draft, createSession: fixture.create }) },
}));
vi.mock("../../../../../src/renderer/src/stores/session-event-boundary", () => ({
	isSessionSynchronizing: () => false,
}));
vi.mock("../../../../../src/renderer/src/stores/settings", () => ({
	useSettingsStore: { getState: () => ({}) },
}));
vi.mock("../../../../../src/renderer/src/stores/permission-policy", () => ({
	usePermissionPolicyStore: { getState: () => ({ byTarget: {}, savePolicy: fixture.save }) },
}));

it("/settings displays permission-save failure on the session that was actually created", async () => {
	vi.stubGlobal("IS_REACT_ACT_ENVIRONMENT", true);
	useDraftStore.setState({ errorsBySession: {}, pendingBySession: {}, bySession: {} });
	fixture.create.mockImplementation(async () => {
		fixture.draft = undefined;
		return "created-from-slash";
	});
	fixture.save.mockResolvedValue(false);
	const host = document.createElement("div");
	document.body.append(host);
	const root = createRoot(host);
	let menu!: ReturnType<typeof useSlashMenu>;
	function Harness() {
		const send = useComposerSend({ draftKey: "old-draft", activeSessionId: null, imagesSupported: true });
		menu = useSlashMenu({
			activeSessionId: null,
			cwd: null,
			trustVersion: 0,
			text: "/",
			slashCommand: null,
			setText: fixture.setText,
			setSlashCommand: () => {},
			editorRef: { current: null },
			ensureSession: send.ensureSession,
			runSlashCommand: fixture.run,
			handleSend: send.handleSend,
			showFeedback: () => {},
			setError: send.setError,
		});
		return null;
	}
	try {
		await act(() => root.render(<Harness />));
		await act(() => menu.updateToken("/", 1));
		const command = menu.slashCommands.find((item) => item.name === "settings");
		if (!command) throw new Error("Missing settings command");
		await act(async () => menu.handleSlashPick(command));
		expect(fixture.create).toHaveBeenCalledOnce();
		expect(fixture.save).toHaveBeenCalledWith("created-from-slash", expect.any(String));
		expect(fixture.run).not.toHaveBeenCalled();
		expect(fixture.setText).not.toHaveBeenCalled();
		expect(useDraftStore.getState().errorsBySession["created-from-slash"]?.detail).toBe(
			"composer.permissionSaveFailed",
		);
		expect(useDraftStore.getState().errorsBySession["old-draft"]).toBeUndefined();
	} finally {
		await act(() => root.unmount());
		host.remove();
		vi.unstubAllGlobals();
	}
});
