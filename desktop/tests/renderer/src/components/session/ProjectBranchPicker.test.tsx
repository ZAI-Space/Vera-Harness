// @vitest-environment happy-dom
import { act } from "react";
import { createRoot } from "react-dom/client";
import { afterEach, expect, it, vi } from "vitest";
import { ProjectBranchPicker } from "../../../../../src/renderer/src/components/session/ProjectBranchPicker";
import { useSessionsStore } from "../../../../../src/renderer/src/stores/sessions";

const fixture = vi.hoisted(() => ({
	listGitBranches: vi.fn(),
	checkoutBranch: vi.fn(),
	getDailyDir: vi.fn().mockResolvedValue(null),
	ensureProjectTrust: vi.fn().mockResolvedValue(undefined),
	listener: undefined as ((status: { connected: boolean }) => void) | undefined,
	unsubscribe: vi.fn(),
}));
vi.mock("../../../../../src/renderer/src/environment-api", () => ({ getExecutionApi: () => fixture }));
vi.mock("../../../../../src/renderer/src/api", () => ({
	getDesktopApi: () => ({
		saveUiState: vi.fn().mockResolvedValue(undefined),
		onBackendStatusChanged: (listener: typeof fixture.listener) => {
			fixture.listener = listener;
			return fixture.unsubscribe;
		},
	}),
}));
vi.mock("../../../../../src/renderer/src/i18n", () => ({ useT: () => (key: string) => key }));
afterEach(() => {
	vi.unstubAllGlobals();
});

it("cleans checkout IPC errors, refreshes on reconnect and unsubscribes", async () => {
	vi.stubGlobal("IS_REACT_ACT_ENVIRONMENT", true);
	fixture.listGitBranches.mockResolvedValue({ current: "main", branches: ["main", "feature"] });
	fixture.checkoutBranch.mockRejectedValue(
		new Error("Error invoking remote method 'project:checkoutBranch': Error: Checkout blocked"),
	);
	useSessionsStore.setState({ activeSessionId: null, sessions: [] });
	useSessionsStore.getState().setDraftCwd("/workspace");
	const host = document.createElement("div");
	const root = createRoot(host);
	try {
		await act(() => root.render(<ProjectBranchPicker />));
		const trigger = [...host.querySelectorAll("button")].find((button) =>
			button.textContent?.includes("main"),
		);
		if (!trigger) throw new Error("Missing branch trigger");
		await act(() => trigger.click());
		const feature = [...host.querySelectorAll("button")].find((button) =>
			button.textContent?.includes("feature"),
		);
		if (!feature) throw new Error("Missing feature branch");
		await act(() => feature.click());
		expect(fixture.checkoutBranch).toHaveBeenCalledWith({ cwd: "/workspace", branch: "feature" });
		expect(host.textContent).toContain("Checkout blocked");
		expect(host.textContent).not.toContain("Error invoking remote method");
		fixture.listGitBranches.mockResolvedValue({ current: "reconnected", branches: ["reconnected"] });
		await act(() => fixture.listener?.({ connected: true }));
		expect(host.textContent).toContain("reconnected");
	} finally {
		await act(() => root.unmount());
	}
	expect(fixture.unsubscribe).toHaveBeenCalledTimes(1);
});
