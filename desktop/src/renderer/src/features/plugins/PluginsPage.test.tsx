// @vitest-environment happy-dom
import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { useI18nStore } from "../../i18n";
import { PluginsPage } from "./PluginsPage";
import { usePluginPreviewStore } from "./plugin-preview-store";

let host: HTMLDivElement;
let root: Root;
beforeEach(() => {
	vi.stubGlobal("IS_REACT_ACT_ENVIRONMENT", true);
	useI18nStore.setState({ language: "zh" });
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

function button(text: string, parent: ParentNode = host): HTMLButtonElement {
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
	await act(() => button("查看详情").click());
	expect(host.querySelector('[aria-label="查看详情"]')?.textContent).toContain("Review Kit");
	await act(() => button("添加到预览").click());
	const confirm = document.querySelector('[role="dialog"]');
	if (!confirm) throw new Error("Missing confirmation");
	expect(confirm.textContent).toContain("不会下载、安装或运行");
	await act(() => button("添加到预览", confirm).click());
	expect(usePluginPreviewStore.getState().plugins[0]?.status).toBe("preview");
	await act(() => button("已添加 1").click());
	const toggle = host.querySelector<HTMLButtonElement>('[role="switch"]');
	await act(() => toggle?.click());
	expect(usePluginPreviewStore.getState().plugins[0]?.enabled).toBe(false);
	const remove = host.querySelector<HTMLButtonElement>('[aria-label="移除 Review Kit"]');
	await act(() => remove?.click());
	const dialog = document.querySelector('[role="dialog"]');
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
	await act(() => button("添加插件来源").click());
	const fill = async (id: string, value: string) => {
		const field = host.querySelector<HTMLInputElement>(`#${id}`);
		if (!field) throw new Error(`Missing input: ${id}`);
		await act(() => {
			Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value")?.set?.call(field, value);
			field.dispatchEvent(new Event("input", { bubbles: true }));
		});
	};
	const submit = () =>
		host.querySelector("form")?.dispatchEvent(new Event("submit", { bubbles: true, cancelable: true }));
	await fill("plugin-name", "Local package");
	await fill("plugin-source", "https://user:secret@example.com/plugin");
	await act(submit);
	expect(host.querySelector('[role="alert"]')).not.toBeNull();
	expect(usePluginPreviewStore.getState().plugins).toEqual([]);
	await fill("plugin-source", "https://github.com/example/plugin");
	await act(submit);
	const source = usePluginPreviewStore.getState().plugins[0];
	expect(source?.enabled).toBe(false);
	expect(source?.status).toBe("preview");
	expect(source?.capabilities).toEqual([]);
	await act(() => useI18nStore.setState({ language: "en" }));
	expect(host.textContent).toContain("Source draft; manifest not loaded");
});
