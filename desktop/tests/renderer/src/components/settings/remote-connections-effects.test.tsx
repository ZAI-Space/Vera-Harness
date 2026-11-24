import React, { type EffectCallback } from "react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";

const fixture = vi.hoisted(() => ({
	effect: undefined as EffectCallback | undefined,
	invoke: vi.fn(),
	setState: vi.fn(),
}));
vi.mock("react", async (importOriginal) => ({
	...(await importOriginal<typeof import("react")>()),
	useEffect: (effect: EffectCallback) => {
		fixture.effect = effect;
	},
	useState: (value: unknown) => [value, fixture.setState],
}));
vi.mock("../../../../../src/renderer/src/harness-api", () => ({ harness: fixture.invoke }));
vi.mock("../../../../../src/renderer/src/i18n", () => ({ useI18nStore: () => false }));

import { RemoteConnectionsPanel } from "../../../../../src/renderer/src/components/settings/RemoteConnectionsPanel";

beforeEach(() => {
	vi.useFakeTimers();
	vi.stubGlobal("React", React);
	vi.clearAllMocks();
});
afterEach(() => {
	vi.useRealTimers();
	vi.unstubAllGlobals();
});

it.each([false, true])(
	"bounds requests and ignores late completion after cleanup (failure=%s)",
	async (failure) => {
		let resolveStatus: (value: unknown) => void = () => {};
		let rejectStatus: (reason: Error) => void = () => {};
		const pendingStatus = new Promise((resolve, reject) => {
			resolveStatus = resolve;
			rejectStatus = reject;
		});
		fixture.invoke.mockImplementation((method: string) =>
			method === "remoteGetStatus" ? pendingStatus : Promise.resolve([]),
		);
		RemoteConnectionsPanel();
		const cleanup = fixture.effect?.();
		vi.advanceTimersByTime(8000);
		expect(fixture.invoke).toHaveBeenCalledTimes(3);
		if (typeof cleanup !== "function") throw new Error("Missing polling cleanup");
		cleanup();
		if (failure) rejectStatus(new Error("late failure"));
		else resolveStatus({ channels: {} });
		await pendingStatus.catch(() => {});
		await Promise.resolve();
		vi.advanceTimersByTime(4000);
		expect(fixture.invoke).toHaveBeenCalledTimes(3);
		expect(fixture.setState).not.toHaveBeenCalled();
	},
);
