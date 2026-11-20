// @vitest-environment happy-dom
import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, expect, it, vi } from "vitest";

vi.mock("../../api", () => ({ getDesktopApi: () => ({ platform: "win32" }) }));

import { useI18nStore } from "../../i18n";
import { DEFAULT_BEHAVIOR, useBehaviorPreferencesStore } from "../../stores/behavior-preferences";
import { BehaviorPanel } from "./BehaviorPanel";

let host: HTMLDivElement;
let root: Root;
beforeEach(() => {
	vi.stubGlobal("IS_REACT_ACT_ENVIRONMENT", true);
	localStorage.clear();
	useI18nStore.setState({ language: "zh" });
	useBehaviorPreferencesStore.setState({ ...DEFAULT_BEHAVIOR, sandboxProfiles: [], storageError: false });
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
	const item = [...parent.querySelectorAll<HTMLButtonElement>("button")].find(
		(element) => element.textContent?.trim() === text,
	);
	if (!item) throw new Error(`Missing button ${text}`);
	return item;
}
async function choose(label: string, option: string) {
	const selector = host.querySelector<HTMLButtonElement>(`[aria-label="${label}"]`);
	if (!selector) throw new Error(`Missing select ${label}`);
	await act(() => selector.click());
	const entry = [...document.querySelectorAll<HTMLButtonElement>('[role="option"]')].find(
		(element) => element.textContent?.trim() === option,
	);
	if (!entry) throw new Error(`Missing option ${option}`);
	await act(() => entry.click());
}
async function fill(id: string, value: string) {
	const field = host.querySelector<HTMLInputElement>(`#${id}`);
	if (!field) throw new Error(`Missing input ${id}`);
	await act(() => {
		Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value")?.set?.call(field, value);
		field.dispatchEvent(new Event("input", { bubbles: true }));
	});
}

it("shows only the requested defaults and updates controls in both languages", async () => {
	await act(() => root.render(<BehaviorPanel />));
	expect(host.textContent).toContain("会话默认");
	await act(() => button("规划").click());
	await choose("权限模式", "Yolo");
	await choose("命令 Shell", "Windows PowerShell");
	expect(useBehaviorPreferencesStore.getState()).toMatchObject({
		defaultMode: "plan",
		permissionPolicy: "yolo",
		commandShell: "windows-powershell",
	});
	for (const removed of ["无限重试", "桌面控制", "Code Mode", "缓存保温"])
		expect(host.textContent).not.toContain(removed);
	await act(() => useI18nStore.setState({ language: "en" }));
	expect(host.textContent).toContain("Session defaults");
	expect(host.textContent).toContain("Harness execution is not connected");
});

it("creates a sandbox draft, selects it as default, edits and confirms deletion", async () => {
	await act(() => root.render(<BehaviorPanel />));
	await act(() => button("添加配置").click());
	await fill("sandbox-name", "python-dev");
	await fill("sandbox-timeout", "45");
	await choose("工作目录权限", "只读");
	await act(() => button("保存配置草稿").click());
	expect(useBehaviorPreferencesStore.getState().sandboxProfiles[0]).toMatchObject({
		name: "python-dev",
		timeout: 45,
		workspace_access: "read-only",
	});
	expect(host.textContent).toContain("尚未检查可用性");
	await choose("默认环境", "python-dev");
	expect(useBehaviorPreferencesStore.getState().defaultSandbox).toBe("python-dev");
	await act(() => host.querySelector<HTMLButtonElement>('[aria-label="编辑 python-dev"]')?.click());
	await choose("隔离引擎", "Bubblewrap / WSL");
	expect(host.querySelector("#sandbox-image")).toBeNull();
	await act(() => button("取消").click());
	expect(useBehaviorPreferencesStore.getState().sandboxProfiles[0]?.mode).toBe("docker");
	await act(() => host.querySelector<HTMLButtonElement>('[aria-label="删除 python-dev"]')?.click());
	const dialog = document.querySelector('[role="dialog"]');
	if (!dialog) throw new Error("Missing delete confirmation");
	await act(() => button("删除", dialog).click());
	expect(useBehaviorPreferencesStore.getState().sandboxProfiles).toEqual([]);
	expect(useBehaviorPreferencesStore.getState().defaultSandbox).toBeNull();
});
