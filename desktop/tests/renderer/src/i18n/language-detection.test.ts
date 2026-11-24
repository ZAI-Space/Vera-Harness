import { afterEach, expect, it, vi } from "vitest";

afterEach(() => {
	vi.unstubAllGlobals();
});

it.each([
	["invalid", "zh", "en-US", "zh"],
	["", "en", "zh-CN", "en"],
	["en", "zh", "zh-CN", "en"],
	[null, "zh", "en-US", "zh"],
	["invalid", "invalid", "zh-CN", "zh"],
])("detects saved language %s / %s before system %s", async (saved, legacy, system, expected) => {
	vi.resetModules();
	vi.stubGlobal("localStorage", {
		getItem: (key: string) => (key === "vera.lang" ? saved : legacy),
	});
	vi.stubGlobal("navigator", { language: system });
	const { useI18nStore } = await import("../../../../src/renderer/src/i18n");
	expect(useI18nStore.getState().language).toBe(expected);
});
