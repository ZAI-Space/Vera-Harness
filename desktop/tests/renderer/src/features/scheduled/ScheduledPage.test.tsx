// @vitest-environment happy-dom
import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, expect, it, vi } from "vitest";

vi.mock("../../../../../src/renderer/src/stores/sessions", () => ({
	useSessionsStore: (selector: (state: object) => unknown) =>
		selector({
			models: [],
			activeSessionId: null,
			newSessionDraft: { cwd: "/workspace" },
			sessions: [],
			cwd: "/workspace",
		}),
}));

import { ScheduledPage } from "../../../../../src/renderer/src/features/scheduled/ScheduledPage";
import { useScheduledPreviewStore } from "../../../../../src/renderer/src/features/scheduled/scheduled-preview-store";
import { useI18nStore } from "../../../../../src/renderer/src/i18n";

let host: HTMLDivElement;
let root: Root;
beforeEach(() => {
	vi.stubGlobal("IS_REACT_ACT_ENVIRONMENT", true);
	useI18nStore.setState({ language: "zh" });
	useScheduledPreviewStore.setState({ tasks: [], runs: [], selectedTaskId: null });
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
async function fill(id: string, value: string) {
	const field = host.querySelector<HTMLInputElement | HTMLTextAreaElement>(`#${id}`);
	if (!field) throw new Error(`Missing field: ${id}`);
	await act(() => {
		const prototype =
			field instanceof HTMLTextAreaElement ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype;
		Object.getOwnPropertyDescriptor(prototype, "value")?.set?.call(field, value);
		field.dispatchEvent(new Event("input", { bubbles: true }));
	});
}

it("create, edit, cancel and confirmed delete are local draft interactions; run remains unavailable", async () => {
	await act(() => root.render(<ScheduledPage />));
	await act(() => button("新建任务").click());
	expect(button("保存草稿").disabled).toBe(true);
	await fill("scheduled-title", "Daily review");
	await fill("scheduled-prompt", "Review project changes");
	expect((host.querySelector("#scheduled-workspace") as HTMLInputElement).value).toBe("/workspace");
	await act(() =>
		host.querySelector("form")?.dispatchEvent(new Event("submit", { bubbles: true, cancelable: true })),
	);
	const task = useScheduledPreviewStore.getState().tasks[0];
	expect(task?.title).toBe("Daily review");
	expect(task?.schedule?.hour).toBe(9);
	expect(host.textContent).toContain("草稿 · 未启用");
	expect(button("立即运行").disabled).toBe(true);
	expect(host.textContent).toContain("暂无运行记录");
	await act(() => button("编辑任务").click());
	await fill("scheduled-title", "Discarded edit");
	await act(() => button("取消").click());
	expect(useScheduledPreviewStore.getState().tasks[0]?.title).toBe("Daily review");
	await act(() => button("删除").click());
	const cancelDialog = document.querySelector('[role="dialog"]');
	if (!cancelDialog) throw new Error("Missing delete confirmation");
	await act(() => button("取消", cancelDialog).click());
	expect(useScheduledPreviewStore.getState().tasks).toHaveLength(1);
	await act(() => button("删除").click());
	const deleteDialog = document.querySelector('[role="dialog"]');
	if (!deleteDialog) throw new Error("Missing delete confirmation");
	await act(() => button("删除", deleteDialog).click());
	expect(useScheduledPreviewStore.getState().tasks).toEqual([]);
	expect(host.textContent).toContain("还没有定时任务");
});

it("weekly selection validates the actual form and survives saving and revisiting the page", async () => {
	await act(() => root.render(<ScheduledPage />));
	await act(() => button("新建任务").click());
	await fill("scheduled-title", "Weekly review");
	await fill("scheduled-prompt", "Check tests");
	const cadence = host.querySelector<HTMLButtonElement>('[aria-label="重复频率"]');
	await act(() => cadence?.click());
	const weekly = [...document.querySelectorAll<HTMLButtonElement>('[role="option"]')].find(
		(item) => item.textContent?.trim() === "每周",
	);
	if (!weekly) throw new Error("Missing weekly cadence");
	await act(() => weekly.click());
	await act(() => button("周一").click());
	expect(button("保存草稿").disabled).toBe(true);
	await act(() => button("周五").click());
	expect(button("保存草稿").disabled).toBe(false);
	await act(() =>
		host.querySelector("form")?.dispatchEvent(new Event("submit", { bubbles: true, cancelable: true })),
	);
	expect(useScheduledPreviewStore.getState().tasks[0]?.schedule?.weekdays).toEqual([4]);
	await act(() => root.render(null));
	await act(() => root.render(<ScheduledPage />));
	expect(host.textContent).toContain("Weekly review");
	expect(host.textContent).toContain("每周 · 周五 · 09:00");
});
