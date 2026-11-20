// @vitest-environment happy-dom
import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { useI18nStore } from "../../../i18n";
import { useSubagentDraftsStore } from "../../../stores/subagent-drafts";
import { SubagentsPanel } from "./SubagentsPanel";
import { SUBAGENT_PRESETS } from "./subagent-presets";

let host: HTMLDivElement;
let root: Root;
beforeEach(() => {
	vi.stubGlobal("IS_REACT_ACT_ENVIRONMENT", true);
	localStorage.clear();
	useI18nStore.setState({ language: "zh" });
	useSubagentDraftsStore.setState({ drafts: [], storageError: false });
	host = document.createElement("div");
	document.body.append(host);
	root = createRoot(host);
});
afterEach(async () => {
	await act(() => root.unmount());
	host.remove();
	vi.unstubAllGlobals();
});
function button(text: string, parent: ParentNode = host): HTMLButtonElement {
	const element = [...parent.querySelectorAll<HTMLButtonElement>("button")].find(
		(item) => item.textContent?.trim() === text || item.getAttribute("aria-label") === text,
	);
	if (!element) throw Error(`Missing button: ${text}`);
	return element;
}
async function fill(selector: string, value: string) {
	const element = host.querySelector<HTMLInputElement | HTMLTextAreaElement>(selector);
	if (!element) throw Error(`Missing field: ${selector}`);
	await act(() => {
		const prototype =
			element.tagName === "TEXTAREA" ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype;
		Object.getOwnPropertyDescriptor(prototype, "value")?.set?.call(element, value);
		element.dispatchEvent(new Event("input", { bubbles: true }));
	});
}

it("creates from a template, edits, copies, toggles, searches and confirms deletion", async () => {
	await act(() => root.render(<SubagentsPanel />));
	expect(useSubagentDraftsStore.getState().drafts).toEqual([]);
	await act(() => button("使用模板").click());
	expect(host.querySelector<HTMLInputElement>("#subagent-name")?.value).toBe("explorer");
	const description = "很长的角色简介，用于验证列表省略展示，但保存与编辑时必须保留完整文字。".repeat(4);
	await fill("#subagent-description", description);
	await act(() => button("保存角色草稿").click());
	expect(useSubagentDraftsStore.getState().drafts[0]?.description).toBe(description);
	expect(host.querySelector("[data-subagent-description]")?.textContent).toBe(description);
	await act(() => button("编辑 explorer").click());
	await fill("#subagent-description", "cancelled description");
	await act(() => button("取消").click());
	expect(useSubagentDraftsStore.getState().drafts[0]?.description).toBe(description);
	await act(() => button("复制 explorer").click());
	expect(host.querySelector<HTMLInputElement>("#subagent-name")?.value).toBe("explorer-2");
	await act(() => button("保存角色草稿").click());
	await act(() => button("启用 explorer-2 草稿").click());
	expect(useSubagentDraftsStore.getState().drafts[1]?.enabled).toBe(false);
	await fill('input[type="search"]', "explorer-2");
	expect(host.querySelectorAll("[data-subagent-row]")).toHaveLength(1);
	await act(() => button("删除 explorer-2").click());
	const dialog = document.querySelector('[role="dialog"]');
	if (!dialog) throw Error("Missing confirmation");
	await act(() => button("删除", dialog).click());
	expect(useSubagentDraftsStore.getState().drafts).toHaveLength(1);
	await act(() => useI18nStore.setState({ language: "en" }));
	expect(host.textContent).toContain("Harness execution is not connected yet");
});

it("preserves a failed creation form and succeeds on retry without duplicate entries", async () => {
	await act(() => root.render(<SubagentsPanel />));
	await act(() => button("创建 Subagent").click());
	await fill("#subagent-name", "my-agent");
	await fill("#subagent-description", "A focused helper");
	await fill("#subagent-instructions", "Report the requested result.");
	const originalStorage = localStorage;
	vi.stubGlobal("localStorage", {
		getItem: originalStorage.getItem.bind(originalStorage),
		setItem: () => {
			throw Error("quota");
		},
	});
	await act(() => button("保存角色草稿").click());
	expect(host.querySelector("form")).not.toBeNull();
	expect(useSubagentDraftsStore.getState().drafts).toEqual([]);
	vi.stubGlobal("localStorage", originalStorage);
	await act(() => button("保存角色草稿").click());
	expect(host.querySelector("form")).toBeNull();
	expect(useSubagentDraftsStore.getState().drafts).toHaveLength(1);
});

it("offers all five original templates and blank start inside creation, preserving full prompts and budgets", async () => {
	await act(() => root.render(<SubagentsPanel />));
	expect(host.querySelectorAll("#subagent-templates-title + ul > li")).toHaveLength(5);
	await fill('input[type="search"]', "修复者");
	expect(host.querySelector('[data-subagent-row="fixer"]')).not.toBeNull();
	await act(() => button("创建 Subagent").click());
	await fill("#subagent-step_limit", "24");
	for (const [index, label] of ["探索者", "代码审查员", "测试执行者", "修复者", "UI 设计师"].entries()) {
		const preset = SUBAGENT_PRESETS[index];
		if (!preset) throw Error("Missing upstream preset");
		await act(() => button(label).click());
		expect(host.querySelector<HTMLInputElement>("#subagent-name")?.value).toBe(preset.id);
		expect(host.querySelector<HTMLInputElement>("#subagent-description")?.value).toBe(preset.description);
		expect(host.querySelector<HTMLTextAreaElement>("#subagent-instructions")?.value).toBe(preset.body);
		expect(host.querySelector<HTMLInputElement>("#subagent-tools")?.value).toBe(preset.tools.join(", "));
		expect(host.querySelector<HTMLInputElement>("#subagent-step_limit")?.value).toBe("24");
	}
	await act(() => button("空白开始").click());
	for (const field of ["name", "description", "instructions", "tools"])
		expect(host.querySelector<HTMLInputElement>(`#subagent-${field}`)?.value).toBe("");
	await act(() => button("修复者").click());
	await act(() => button("保存角色草稿").click());
	expect(useSubagentDraftsStore.getState().drafts[0]).toMatchObject({ name: "fixer", step_limit: 24 });
	await fill('input[type="search"]', "");
	await act(() => button("编辑 fixer").click());
	expect(host.textContent).not.toContain("从模板开始");
	expect(host.querySelector<HTMLTextAreaElement>("#subagent-instructions")?.value).toBe(
		SUBAGENT_PRESETS.find((preset) => preset.id === "fixer")?.body.trim(),
	);
});
