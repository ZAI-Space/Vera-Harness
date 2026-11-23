// @vitest-environment happy-dom
import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { PluginsPage } from "../../../../../src/renderer/src/features/plugins/PluginsPage";
import { usePluginPreviewStore } from "../../../../../src/renderer/src/features/plugins/plugin-preview-store";
import { setHarnessConnected } from "../../../../../src/renderer/src/harness-api";
import { useI18nStore } from "../../../../../src/renderer/src/i18n";

let host: HTMLDivElement;
let root: Root;
beforeEach(() => {
	vi.stubGlobal("IS_REACT_ACT_ENVIRONMENT", true);
	useI18nStore.setState({ language: "zh" });
	setHarnessConnected(false);
	usePluginPreviewStore.setState({ plugins: [] });
	host = document.createElement("div");
	document.body.append(host);
	root = createRoot(host);
});
afterEach(async () => {
	await act(() => root.unmount());
	host.remove();
	vi.unstubAllGlobals();
});

function button(text: string, parent: ParentNode = document): HTMLButtonElement {
	const match = [...parent.querySelectorAll<HTMLButtonElement>("button")].find(
		(item) => item.textContent?.trim() === text,
	);
	if (!match) throw new Error(`Missing button: ${text}`);
	return match;
}

it("marketplace browsing, detail, explicit preview confirmation and removal work without claiming installation", async () => {
	await act(() => root.render(<PluginsPage />));
	expect(host.textContent).toContain("前端预览");
	expect(host.textContent).toContain("还没有添加插件");
	await act(() => button("浏览插件市场").click());
	expect(host.querySelectorAll("article")).toHaveLength(3);
	expect(host.querySelector('[aria-label="市场来源"]')).toBeNull();
	expect([...host.querySelectorAll("button")].some((item) => item.textContent?.trim() === "刷新市场")).toBe(
		false,
	);
	await act(() => button("查看详情").click());
	expect(host.querySelectorAll("article")).toHaveLength(3);
	expect(document.querySelector("[data-modal-overlay]")?.parentElement).toBe(document.body);
	expect(document.querySelectorAll("[data-modal-overlay] button[aria-label=关闭]")).toHaveLength(1);
	expect(document.querySelector('[aria-label="查看详情"]')?.textContent).toContain("Review Kit");
	await act(() => button("添加到预览").click());
	const confirm = [...document.querySelectorAll<HTMLElement>('[role="dialog"]')].at(-1);
	if (!confirm) throw new Error("Missing confirmation");
	expect(confirm.textContent).toContain("不会下载、安装或运行");
	await act(() => button("添加到预览", confirm).click());
	expect(usePluginPreviewStore.getState().plugins[0]?.status).toBe("preview");
	await act(() => window.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", bubbles: true })));
	expect(document.querySelector('[role="dialog"]')).toBeNull();
	await act(() => button("已添加 1").click());
	const toggle = host.querySelector<HTMLButtonElement>('[role="switch"]');
	await act(() => toggle?.click());
	expect(usePluginPreviewStore.getState().plugins[0]?.enabled).toBe(false);
	const remove = host.querySelector<HTMLButtonElement>('[aria-label="移除 Review Kit"]');
	await act(() => remove?.click());
	const dialog = [...document.querySelectorAll<HTMLElement>('[role="dialog"]')].at(-1);
	if (!dialog) throw new Error("Missing remove confirmation");
	await act(() => button("删除", dialog).click());
	expect(usePluginPreviewStore.getState().plugins).toEqual([]);
});

it("search filters examples and changing language updates workspace labels", async () => {
	await act(() => root.render(<PluginsPage />));
	await act(() =>
		host
			.querySelector('[role="tablist"]')
			?.dispatchEvent(new KeyboardEvent("keydown", { key: "ArrowRight", bubbles: true })),
	);
	expect(document.activeElement?.id).toBe("plugins-tab-market");
	const search = host.querySelector<HTMLInputElement>('input[type="search"]');
	if (!search) throw new Error("Missing search field");
	await act(() => {
		Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value")?.set?.call(search, "frontend");
		search.dispatchEvent(new Event("input", { bubbles: true }));
	});
	expect(host.querySelectorAll("article")).toHaveLength(1);
	expect(host.querySelector("article")?.textContent).toContain("Frontend Design");
	await act(() => useI18nStore.setState({ language: "en" }));
	expect(host.querySelector("h1")?.textContent).toBe("Plugins");
	expect(host.textContent).toContain("These are interface examples");
});

it("plugin sources remain drafts, reject embedded credentials and keep system descriptions localizable", async () => {
	await act(() => root.render(<PluginsPage />));
	await act(() => button("添加插件仓库").click());
	const fill = async (id: string, value: string) => {
		const field = document.querySelector<HTMLInputElement>(`#${id}`);
		if (!field) throw new Error(`Missing input: ${id}`);
		await act(() => {
			Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value")?.set?.call(field, value);
			field.dispatchEvent(new Event("input", { bubbles: true }));
		});
	};
	const submit = () =>
		document.querySelector("form")?.dispatchEvent(new Event("submit", { bubbles: true, cancelable: true }));
	await fill("plugin-name", "Local package");
	await fill("plugin-source", "https://user:secret@example.com/plugin");
	await act(async () => {
		submit();
		await Promise.resolve();
	});
	expect(document.querySelector('[role="alert"]')).not.toBeNull();
	expect(usePluginPreviewStore.getState().plugins).toEqual([]);
	await fill("plugin-source", "https://github.com/example/plugin");
	await act(async () => {
		submit();
		await Promise.resolve();
	});
	const source = usePluginPreviewStore.getState().plugins[0];
	expect(source?.enabled).toBe(false);
	expect(source?.status).toBe("preview");
	expect(source?.capabilities).toEqual([]);
	await act(() => useI18nStore.setState({ language: "en" }));
	expect(source?.description).toBe("");
	expect(source?.status).toBe("preview");
});
