// @vitest-environment happy-dom
import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { useI18nStore } from "../../i18n";
import { useProjectsStore } from "../../stores/projects";
import { useUiPreferencesStore } from "../../stores/ui-preferences";
import { SessionSearch } from "./SessionSearch";

let host: HTMLDivElement;
let root: Root;

beforeEach(async () => {
	vi.stubGlobal("IS_REACT_ACT_ENVIRONMENT", true);
	useI18nStore.setState({ language: "zh" });
	useProjectsStore.setState({ search: "" });
	useUiPreferencesStore.setState({ sidebarCollapsed: true });
	host = document.createElement("div");
	document.body.append(host);
	root = createRoot(host);
	await act(() => root.render(<SessionSearch />));
});

afterEach(async () => {
	await act(() => root.unmount());
	host.remove();
	vi.unstubAllGlobals();
});

function trigger() {
	const button = host.querySelector<HTMLButtonElement>('button[aria-label="搜索会话"]');
	if (!button) throw new Error("缺少搜索入口");
	return button;
}

/** 使用原生 setter 模拟真实输入，确保 React onChange 写入原有筛选 store。 */
async function enterSearch(value: string) {
	const input = host.querySelector<HTMLInputElement>("input");
	if (!input) throw new Error("缺少搜索输入框");
	await act(() => {
		Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value")?.set?.call(input, value);
		input.dispatchEvent(new Event("input", { bubbles: true }));
	});
	return input;
}

describe("顶栏会话搜索", () => {
	it("默认只显示按钮，展开时聚焦并打开侧栏，输入沿用原有筛选", async () => {
		expect(host.querySelector("input")).toBeNull();
		await act(() => trigger().click());
		expect(document.activeElement).toBe(host.querySelector("input"));
		expect(useUiPreferencesStore.getState().sidebarCollapsed).toBe(false);
		await enterSearch("VERA");
		expect(useProjectsStore.getState().search).toBe("VERA");
	});

	it("离开后保留查询，重开可清空并继续输入", async () => {
		await act(() => trigger().click());
		const input = await enterSearch("VERA");
		const outside = document.createElement("button");
		host.append(outside);
		await act(() => outside.focus());
		expect(host.querySelector("input")).toBeNull();
		expect(useProjectsStore.getState().search).toBe("VERA");
		await act(() => trigger().click());
		expect(host.querySelector<HTMLInputElement>("input")?.value).toBe("VERA");
		await act(() => host.querySelector<HTMLButtonElement>('button[aria-label="清空搜索"]')?.click());
		expect(useProjectsStore.getState().search).toBe("");
		expect(document.activeElement).toBe(host.querySelector("input"));
		expect(input.isConnected).toBe(false);
	});

	it("Escape 取消筛选、收起输入并将焦点返回入口", async () => {
		await act(() => trigger().click());
		const input = await enterSearch("VERA");
		await act(() => {
			input.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", bubbles: true }));
		});
		expect(useProjectsStore.getState().search).toBe("");
		expect(host.querySelector("input")).toBeNull();
		expect(document.activeElement).toBe(trigger());
	});
});
