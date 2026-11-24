// @vitest-environment happy-dom
import { act } from "react";
import { createRoot } from "react-dom/client";
import { afterEach, expect, it, vi } from "vitest";
import { TaskboardPage } from "../../../../../src/renderer/src/features/taskboard/TaskboardPage";
import { useI18nStore } from "../../../../../src/renderer/src/i18n";

const fixture = vi.hoisted(() => ({ invoke: vi.fn(), openExternal: vi.fn() }));
vi.mock("../../../../../src/renderer/src/harness-api", () => ({ harness: fixture.invoke }));
vi.mock("../../../../../src/renderer/src/api", () => ({ getDesktopApi: () => fixture }));
afterEach(() => vi.unstubAllGlobals());

it("opens the status repository and displays an external-open failure", async () => {
	vi.stubGlobal("IS_REACT_ACT_ENVIRONMENT", true);
	useI18nStore.setState({ language: "en" });
	fixture.invoke.mockResolvedValue({
		installed: false,
		running: false,
		repository: "https://example.com/board",
		nodeAvailable: true,
	});
	fixture.openExternal.mockRejectedValue(
		new Error("Error invoking remote method 'app:openExternal': Error: Browser unavailable"),
	);
	const host = document.createElement("div");
	const root = createRoot(host);
	try {
		await act(() => root.render(<TaskboardPage />));
		const documentation = [...host.querySelectorAll("button")].find(
			(button) => button.textContent === "Documentation",
		);
		if (!documentation) throw new Error("Missing documentation button");
		await act(() => documentation.click());
		expect(fixture.openExternal).toHaveBeenCalledWith({ url: "https://example.com/board" });
		expect(host.querySelector('[role="alert"]')?.textContent).toBe("Browser unavailable");
	} finally {
		await act(() => root.unmount());
	}
});
