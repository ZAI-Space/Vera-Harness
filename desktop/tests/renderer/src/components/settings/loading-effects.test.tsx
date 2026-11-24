import React, { type EffectCallback } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

// Execute the actual panel effect callbacks in Node. Hook registration/scheduling is controlled;
// this is not an Electron DOM/visual test or a claim about StrictMode render counts.
const harness = vi.hoisted(() => ({
	effects: [] as Array<{ callback: EffectCallback; deps: unknown[] | undefined }>,
	state: {
		providers: [],
		loading: false,
		refreshing: false,
		error: null,
		lanStatus: null as null | { enabled: boolean; urls: string[] },
		lanSaving: false,
		refreshProvidersFromNetwork: vi.fn().mockResolvedValue(undefined),
		refreshLanStatus: vi.fn().mockResolvedValue(undefined),
		setLanEnabled: vi.fn(),
		setLanRemoteControl: vi.fn(),
		permissionGateOff: null,
		loadPermissionGate: vi.fn().mockResolvedValue(undefined),
	},
}));
vi.mock("react", async (importOriginal) => {
	const actual = await importOriginal<typeof import("react")>();
	return {
		...actual,
		useEffect: (callback: EffectCallback, deps?: unknown[]) => {
			harness.effects.push({ callback, deps });
		},
		useState: (value: unknown) => [value, vi.fn()],
		useRef: () => ({ current: null }),
	};
});
vi.mock("../../../../../src/renderer/src/stores/settings", () => ({
	useSettingsStore: Object.assign(
		(selector: (state: typeof harness.state) => unknown) => selector(harness.state),
		{ getState: () => harness.state },
	),
}));
vi.mock("../../../../../src/renderer/src/stores/sessions", () => ({
	useSessionsStore: (selector: (state: any) => unknown) =>
		selector({
			activeSessionId: null,
			newSessionDraft: { permissionMode: "default" },
			permissionModes: {},
			setDraftPermissionMode: vi.fn(),
			setSessionPermissionMode: vi.fn(),
		}),
}));
vi.mock("../../../../../src/renderer/src/i18n", () => ({ useT: () => (key: string) => key }));
vi.mock("../../../../../src/renderer/src/components/settings/providers/CustomProviderForm", () => ({
	CustomProviderForm: () => null,
}));

import { PermissionPicker } from "../../../../../src/renderer/src/components/composer/PermissionPicker";
import { LanObserverPanel } from "../../../../../src/renderer/src/components/settings/LanObserverPanel";
import { ProvidersPanel } from "../../../../../src/renderer/src/components/settings/providers/ProvidersPanel";

beforeEach(() => {
	vi.stubGlobal("React", React);
	vi.useFakeTimers();
	vi.clearAllMocks();
	harness.effects = [];
	harness.state.lanStatus = null;
});
afterEach(() => {
	vi.useRealTimers();
	vi.unstubAllGlobals();
});

describe("V03 panel effect callback ownership", () => {
	it("LAN cannot change an unknown listener state, including after failed initial load", () => {
		for (const error of [null, "status unavailable"]) {
			Object.assign(harness.state, { lanStatus: null, lanError: error });
			const html = renderToStaticMarkup(<LanObserverPanel />);
			expect(html).toMatch(/role="switch"[^>]* disabled=""/);
		}
		harness.state.lanStatus = { enabled: false, urls: [] };
		expect(renderToStaticMarkup(<LanObserverPanel />)).not.toMatch(/role="switch"[^>]* disabled=""/);
	});
	it("providers effect is mount-scoped and refreshes only the provider catalog", () => {
		ProvidersPanel();
		expect(harness.effects).toHaveLength(1);
		expect(harness.effects[0]?.deps).toEqual([harness.state.refreshProvidersFromNetwork]);
		harness.effects[0]?.callback();
		expect(harness.state.refreshProvidersFromNetwork).toHaveBeenCalledTimes(1);
		expect(harness.state.refreshLanStatus).not.toHaveBeenCalled();
		harness.effects = [];
		ProvidersPanel();
		expect(harness.effects[0]?.deps).toEqual([harness.state.refreshProvidersFromNetwork]); // The captured action stays stable on rerender.
	});
	it("frontend policy picker does not load the borrowed backend permission gate", () => {
		PermissionPicker({ policy: "confirm", onPolicyChange: vi.fn() });
		expect(harness.effects).toHaveLength(1);
		harness.effects[0]?.callback();
		expect(harness.state.loadPermissionGate).not.toHaveBeenCalled();
		expect(harness.state.refreshProvidersFromNetwork).not.toHaveBeenCalled();
		expect(harness.state.refreshLanStatus).not.toHaveBeenCalled();
	});
	it("LAN has no initial load callback; enabled-only polling retains 5s and cleanup", () => {
		LanObserverPanel();
		expect(harness.effects).toHaveLength(1);
		harness.effects[0]?.callback();
		vi.advanceTimersByTime(10000);
		expect(harness.state.refreshLanStatus).not.toHaveBeenCalled();
		expect(harness.state.refreshProvidersFromNetwork).not.toHaveBeenCalled();
		harness.effects = [];
		harness.state.lanStatus = { enabled: true, urls: [] };
		LanObserverPanel();
		const cleanup = harness.effects[0]?.callback();
		vi.advanceTimersByTime(5000);
		expect(harness.state.refreshLanStatus).toHaveBeenCalledTimes(1);
		if (typeof cleanup !== "function") throw Error("Expected enabled polling cleanup");
		cleanup();
		vi.advanceTimersByTime(10000);
		expect(harness.state.refreshLanStatus).toHaveBeenCalledTimes(1);
	});
});
