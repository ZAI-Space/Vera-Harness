import { describe, expect, it, vi } from "vitest";
import { BackendBridge, type BackendTransport, BackendUnavailableError } from "./backend";

describe("external backend boundary", () => {
	it("offers an empty preview while refusing business writes when disconnected", async () => {
		const bridge = new BackendBridge(vi.fn());
		expect(await bridge.invoke("listModels", undefined)).toEqual([]);
		await expect(bridge.invoke("prompt", { sessionId: "one", text: "run" })).rejects.toBeInstanceOf(
			BackendUnavailableError,
		);
		await expect(bridge.invoke("addCustomProvider", { input: {} })).rejects.toThrow("尚未连接");
		await expect(bridge.invoke("unknown", undefined)).rejects.toThrow("Unknown");
	});
	it("forwards calls and retires old events and listeners when switching adapters", async () => {
		const emit = vi.fn((method: string, _payload: unknown) => method);
		const bridge = new BackendBridge(emit);
		let firstEvent: (method: string, payload: unknown) => void = () => {};
		const remove = vi.fn();
		const first: BackendTransport = {
			invoke: vi.fn(async () => "first"),
			close: vi.fn(async () => {}),
			subscribe: (listener) => {
				firstEvent = listener;
				return remove;
			},
		};
		const second: BackendTransport = {
			invoke: vi.fn(async () => "second"),
			close: vi.fn(async () => {}),
			subscribe: () => () => {},
		};
		await bridge.connect(first);
		expect(await bridge.invoke("listModels", { options: {} })).toBe("first");
		firstEvent("onEvent", { sessionId: "one" });
		expect(emit.mock.calls.filter(([method]) => method === "onEvent")).toHaveLength(1);
		await bridge.connect(second);
		expect(remove).toHaveBeenCalledOnce();
		expect(first.close).toHaveBeenCalledOnce();
		firstEvent("onEvent", { sessionId: "stale" });
		expect(emit.mock.calls.filter(([method]) => method === "onEvent")).toHaveLength(1);
		expect(await bridge.invoke("listModels", undefined)).toBe("second");
		await bridge.connect(null);
		expect(second.close).toHaveBeenCalledOnce();
	});
});
