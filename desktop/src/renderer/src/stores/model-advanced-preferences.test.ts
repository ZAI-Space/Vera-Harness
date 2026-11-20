// @vitest-environment happy-dom
import { beforeEach, expect, it, vi } from "vitest";
import {
	DEFAULT_MODEL_ADVANCED,
	MODEL_ADVANCED_STORAGE_KEY,
	readModelAdvanced,
	saveModelAdvanced,
	validateModelAdvanced,
} from "./model-advanced-preferences";

beforeEach(() => {
	vi.unstubAllGlobals();
	localStorage.clear();
});
it.each([
	[{ toolCallLimit: "0" }, "toolCallLimit"],
	[{ toolCallLimit: "1.5" }, "toolCallLimit"],
	[{ reasoningParameter: "reasoning..effort" }, "reasoningParameter"],
	[{ temperature: "2.1" }, "temperature"],
	[{ temperature: "Infinity" }, "temperature"],
	[{ topP: "-1" }, "topP"],
	[{ topP: "1.1" }, "topP"],
	[{ topK: "0" }, "topK"],
	[{ topK: "1.5" }, "topK"],
	[{ topK: "101" }, "topK"],
] as const)("validates advanced ranges without sending model requests: %j", (patch, error) => {
	expect(validateModelAdvanced({ ...DEFAULT_MODEL_ADVANCED, ...patch })).toBe(error);
});
it("scopes settings by stable connection and model IDs and persists only known non-secret fields", () => {
	expect(
		saveModelAdvanced("official", [
			{
				id: "shared",
				advanced: {
					...DEFAULT_MODEL_ADVANCED,
					temperature: "0.5",
					apiKey: "must-not-store",
				} as typeof DEFAULT_MODEL_ADVANCED,
			},
		]),
	).toBe(true);
	expect(
		saveModelAdvanced("relay", [
			{ id: "shared", advanced: { ...DEFAULT_MODEL_ADVANCED, temperature: "1.5" } },
		]),
	).toBe(true);
	expect(readModelAdvanced("official").shared?.temperature).toBe("0.5");
	expect(readModelAdvanced("relay").shared?.temperature).toBe("1.5");
	expect(localStorage.getItem(MODEL_ADVANCED_STORAGE_KEY)).not.toContain("must-not-store");
});
it("rejects invalid data and reports local storage errors", () => {
	localStorage.setItem(
		MODEL_ADVANCED_STORAGE_KEY,
		JSON.stringify({ bad: { model: { ...DEFAULT_MODEL_ADVANCED, topK: "200" } } }),
	);
	expect(readModelAdvanced("bad")).toEqual({});
	expect(
		saveModelAdvanced("bad", [{ id: "model", advanced: { ...DEFAULT_MODEL_ADVANCED, topK: "0" } }]),
	).toBe(false);
	vi.stubGlobal("localStorage", {
		getItem: () => "{}",
		setItem: () => {
			throw Error("quota");
		},
	});
	expect(saveModelAdvanced("new", [{ id: "model", advanced: DEFAULT_MODEL_ADVANCED }])).toBe(false);
	vi.unstubAllGlobals();
});
