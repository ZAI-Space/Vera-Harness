import { describe, expect, it } from "vitest";
import { validateDesktopRequest } from "./request";

describe("desktop request validation", () => {
	it("accepts desktop object payloads as well as zero-argument calls", () => {
		const value = { method: "saveUiState", args: { state: { theme: "dark" } } };
		expect(validateDesktopRequest(value)).toEqual(value);
		expect(validateDesktopRequest({ method: "getAppInfo" }).args).toBeUndefined();
	});
	it("validates business arguments before adapter dispatch", () => {
		expect(() => validateDesktopRequest({ method: "prompt", args: {} })).toThrow();
		expect(
			validateDesktopRequest({ method: "prompt", args: { sessionId: "one", text: "hello" } }).method,
		).toBe("prompt");
	});
	it.each([
		null,
		[],
		{ method: "unknown" },
		{ method: "__proto__" },
		{ method: "saveUiState", args: "text" },
	])("rejects malformed or unknown requests", (value) => {
		expect(() => validateDesktopRequest(value)).toThrow();
	});
});
