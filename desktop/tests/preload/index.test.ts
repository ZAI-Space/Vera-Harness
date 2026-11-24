import type { DesktopClientApi } from "@vera/contracts";
import { beforeEach, describe, expect, it, vi } from "vitest";

const fixture = vi.hoisted(() => ({
	name: "",
	api: null as DesktopClientApi | null,
	invoke: vi.fn(async () => undefined),
	on: vi.fn(),
	removeListener: vi.fn(),
}));
vi.mock("electron", () => ({
	contextBridge: {
		exposeInMainWorld: (name: string, api: DesktopClientApi) => {
			fixture.name = name;
			fixture.api = api;
		},
	},
	ipcRenderer: { invoke: fixture.invoke, on: fixture.on, removeListener: fixture.removeListener },
	webUtils: { getPathForFile: () => "/selected/file" },
}));

import "../../src/preload/index";

beforeEach(() => vi.clearAllMocks());

describe("standalone renderer bridge", () => {
	it("exposes VERA's fixed API without raw Electron access", () => {
		expect(fixture.name).toBe("vera");
		expect(fixture.api).not.toHaveProperty("ipcRenderer");
		expect(fixture.api).not.toHaveProperty("remoteConnect");
		const executionApi = fixture.api?.forEnvironment({ kind: "local" });
		for (const method of [
			"searchCatalog",
			"installPackage",
			"removePackage",
			"listConfiguredPackages",
			"checkPackageUpdates",
			"getCacheWarming",
			"setCacheWarming",
		]) {
			expect(fixture.api).not.toHaveProperty(method);
			expect(executionApi).not.toHaveProperty(method);
		}
	});
	it("forwards desktop object payloads through the new request channel", async () => {
		await fixture.api?.saveUiState({ state: { theme: "dark" } });
		expect(fixture.invoke).toHaveBeenCalledWith("vera:invoke", {
			method: "saveUiState",
			args: { state: { theme: "dark" } },
		});
	});
	it("rejects retired environments and keeps native capabilities outside the business API", () => {
		expect(() =>
			fixture.api?.forEnvironment({ kind: "ssh", connectionId: "old", environmentId: "old" }),
		).toThrow("Unsupported");
		expect(fixture.api?.forEnvironment({ kind: "local" })).not.toHaveProperty("openExternal");
	});
	it("filters event methods and removes the exact listener", () => {
		const callback = vi.fn();
		const off = fixture.api?.onBackendStatusChanged(callback);
		const listener = fixture.on.mock.calls[0]?.[1] as (event: unknown, data: unknown) => void;
		listener(undefined, { method: "onUpdateEvent", payload: {} });
		listener(undefined, { method: "onBackendStatusChanged", payload: { connected: true } });
		expect(callback).toHaveBeenCalledExactlyOnceWith({ connected: true });
		off?.();
		expect(fixture.removeListener).toHaveBeenCalledWith("vera:event", listener);
	});
});
