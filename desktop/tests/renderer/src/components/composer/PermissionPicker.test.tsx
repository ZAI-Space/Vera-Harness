// @vitest-environment happy-dom
import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { PermissionPicker } from "../../../../../src/renderer/src/components/composer/PermissionPicker";
import { useI18nStore } from "../../../../../src/renderer/src/i18n";
import { usePermissionPolicyStore } from "../../../../../src/renderer/src/stores/permission-policy";

let host: HTMLDivElement;
let root: Root;

/** 用真实前端 store 接收选择值，确保组件返回字段与显示名称分离。 */
function Harness({ target = "draft:1" }: { target?: string }) {
	const policy = usePermissionPolicyStore((state) => state.byTarget[target] ?? "confirm");
	const selectPolicy = usePermissionPolicyStore((state) => state.selectPolicy);
	return <PermissionPicker policy={policy} onPolicyChange={(value) => selectPolicy(target, value)} />;
}

beforeEach(async () => {
	vi.stubGlobal("IS_REACT_ACT_ENVIRONMENT", true);
	useI18nStore.setState({ language: "zh" });
	usePermissionPolicyStore.setState({ byTarget: {} });
	host = document.createElement("div");
	document.body.append(host);
	root = createRoot(host);
	await act(() => root.render(<Harness />));
});

afterEach(async () => {
	await act(() => root.unmount());
	host.remove();
	vi.unstubAllGlobals();
});

function trigger() {
	const button = host.querySelector<HTMLButtonElement>('[aria-haspopup="menu"]');
	if (!button) throw new Error("缺少权限策略入口");
	return button;
}

async function openMenu() {
	await act(() => trigger().click());
	return [...host.querySelectorAll<HTMLButtonElement>('[role="menuitemradio"]')];
}

it("显示指定的三个名称与简短说明，默认选中 Confirm", async () => {
	const items = await openMenu();
	expect(items.map((item) => item.textContent)).toEqual([
		"Human手动输入并执行命令",
		"Confirm执行操作前确认",
		"Yolo自动执行，无需确认",
	]);
	expect(items.map((item) => item.getAttribute("aria-checked"))).toEqual(["false", "true", "false"]);
	expect(host.querySelector('[role="menu"]')?.textContent).not.toMatch(/[。.]/);
	expect(items[2]?.querySelector("svg")?.classList.contains("text-warn")).toBe(true);
});

it.each([
	[0, "human", "Human"],
	[1, "confirm", "Confirm"],
	[2, "yolo", "Yolo"],
] as const)("第 %i 项选择值为 %s，入口显示 %s", async (index, value, label) => {
	const items = await openMenu();
	await act(() => items[index]?.click());
	if (value === "yolo")
		await act(() =>
			[...document.querySelectorAll<HTMLButtonElement>("button")]
				.find((item) => item.textContent?.includes("了解风险并开启"))
				?.click(),
		);
	expect(usePermissionPolicyStore.getState().byTarget["draft:1"]).toBe(value);
	expect(trigger().textContent).toBe(label);
	expect(host.querySelector('[role="menu"]')).toBeNull();
	expect(document.activeElement).toBe(trigger());
});

it("不同会话保留各自的前端选择，不把 Yolo 带给新目标", async () => {
	const items = await openMenu();
	await act(() => items[2]?.click());
	await act(() =>
		[...document.querySelectorAll<HTMLButtonElement>("button")]
			.find((item) => item.textContent?.includes("了解风险并开启"))
			?.click(),
	);
	await act(() => root.render(<Harness target="session:2" />));
	expect(trigger().textContent).toBe("Confirm");
	await act(() => root.render(<Harness />));
	expect(trigger().textContent).toBe("Yolo");
});

it("方向键切换焦点，Esc 与点击外部收起时保留策略", async () => {
	const items = await openMenu();
	expect(document.activeElement).toBe(items[1]);
	await act(() => items[1]?.dispatchEvent(new KeyboardEvent("keydown", { key: "ArrowUp", bubbles: true })));
	expect(document.activeElement).toBe(items[0]);
	await act(() => items[0]?.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", bubbles: true })));
	expect(host.querySelector('[role="menu"]')).toBeNull();
	expect(document.activeElement).toBe(trigger());
	await openMenu();
	await act(() => document.body.dispatchEvent(new PointerEvent("pointerdown", { bubbles: true })));
	expect(host.querySelector('[role="menu"]')).toBeNull();
	expect(usePermissionPolicyStore.getState().byTarget).toEqual({});
});
