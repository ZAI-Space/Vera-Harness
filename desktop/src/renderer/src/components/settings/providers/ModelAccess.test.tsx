// @vitest-environment happy-dom
import type { ModelPrefs, ProviderInfo } from "@vera/contracts";
import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, expect, it, vi } from "vitest";

const mock = vi.hoisted(() => ({
	providers: [] as ProviderInfo[],
	modelPrefs: { hiddenModels: {}, subagentModels: {} } as ModelPrefs,
	loading: false,
	refreshing: false,
	error: null,
	refreshProvidersFromNetwork: vi.fn().mockResolvedValue(undefined),
	listUpstreamModels: vi.fn(),
	addCustom: vi.fn(),
	updateCustom: vi.fn(),
	test: vi.fn(),
	setModelHidden: vi.fn(),
	setProviderModelsHidden: vi.fn(),
	testResults: {},
}));
vi.mock("../../../stores/settings", () => ({
	useSettingsStore: (select: (state: typeof mock) => unknown) => select(mock),
}));
vi.mock("../../../stores/provider-login", () => ({
	useProviderLoginStore: (select: (state: unknown) => unknown) =>
		select({ login: null, startProviderLogin: vi.fn() }),
}));
vi.mock("./LoginDialog", () => ({ LoginDialog: () => null }));

import { useI18nStore } from "../../../i18n";
import { MODEL_ADVANCED_STORAGE_KEY, readModelAdvanced } from "../../../stores/model-advanced-preferences";
import { ProvidersPanel } from "./ProvidersPanel";

let host: HTMLDivElement;
let root: Root;
beforeEach(() => {
	vi.stubGlobal("IS_REACT_ACT_ENVIRONMENT", true);
	vi.clearAllMocks();
	localStorage.clear();
	mock.providers = [];
	mock.addCustom.mockResolvedValue(undefined);
	mock.listUpstreamModels.mockResolvedValue({
		baseUrl: "https://fixture.invalid/v1",
		models: [
			{ id: "alpha", name: "Alpha", contextWindow: 64000 },
			{ id: "beta" },
			{ id: "gamma", reasoning: true },
		],
	});
	useI18nStore.setState({ language: "zh" });
	host = document.createElement("div");
	document.body.append(host);
	root = createRoot(host);
});
afterEach(async () => {
	await act(() => root.unmount());
	host.remove();
	vi.unstubAllGlobals();
});
function button(text: string): HTMLButtonElement {
	const item = [...host.querySelectorAll<HTMLButtonElement>("button")].find(
		(element) => element.textContent?.trim() === text,
	);
	if (!item) throw Error(`Missing button ${text}`);
	return item;
}
async function fill(selector: string, value: string) {
	const input = host.querySelector<HTMLInputElement>(selector);
	if (!input) throw Error(`Missing field ${selector}`);
	await act(() => {
		Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value")?.set?.call(input, value);
		input.dispatchEvent(new Event("input", { bubbles: true }));
	});
}
async function openConnection() {
	await act(() => root.render(<ProvidersPanel />));
	await act(() => button("添加连接").click());
	await fill('input[aria-label="连接名称"]', "DeepSeek");
	await fill('input[type="password"]', "fixture-only");
	await fill('input[aria-label="baseUrl，如 https://api.example.com/v1"]', "https://fixture.invalid/v1");
}

async function choose(label: string, option: string) {
	await act(() => host.querySelector<HTMLButtonElement>(`button[aria-label="${label}"]`)?.click());
	const target = [...document.querySelectorAll<HTMLButtonElement>('[role="option"]')].find(
		(item) => item.textContent?.trim() === option,
	);
	if (!target) throw Error(`Missing option ${option}`);
	await act(() => target.click());
}

it("separates configured API models from subscription capabilities and never treats a stored API key as subscription login", async () => {
	mock.providers = [
		{
			id: "proxy",
			name: "Relay",
			custom: true,
			configured: true,
			authType: "api_key",
			models: [{ id: "unselected", name: "unselected" }],
			customModels: [{ id: "chosen", name: "Chosen" }],
		},
		{
			id: "dual",
			name: "Dual",
			custom: false,
			configured: true,
			authType: "api_key",
			oauth: { isSubscription: true },
			models: [{ id: "api-model", name: "API model" }],
		},
		{
			id: "subscription",
			name: "Account",
			custom: false,
			configured: true,
			authType: "oauth",
			oauth: { isSubscription: true },
			models: [{ id: "account-model", name: "Account model" }],
		},
		{
			id: "unconfigured",
			name: "Unused",
			custom: false,
			configured: false,
			models: [{ id: "unused", name: "Unused" }],
		},
	];
	await act(() => root.render(<ProvidersPanel />));
	expect([...host.querySelectorAll("[role=tab]")].map((tab) => tab.textContent)).toEqual([
		"API_KEY",
		"账号订阅",
	]);
	expect(host.querySelectorAll("[data-configured-model]")).toHaveLength(0);
	await act(() => host.querySelector<HTMLButtonElement>('[aria-label="展开 Relay 的模型"]')?.click());
	await act(() => host.querySelector<HTMLButtonElement>('[aria-label="展开 Dual 的模型"]')?.click());
	expect(
		[...host.querySelectorAll<HTMLElement>("[data-configured-model]")].map(
			(row) => row.dataset.configuredModel,
		),
	).toEqual(["chosen", "api-model"]);
	expect(host.textContent).not.toContain("Account model");
	await act(() => button("账号订阅").click());
	expect(host.textContent).toContain("Account");
	expect(host.textContent).not.toContain("Relay");
	const cards = [...host.querySelectorAll("li")];
	expect(cards.find((card) => card.textContent?.includes("Dual"))?.textContent).toContain("未登录");
	expect(cards.find((card) => card.textContent?.includes("Account"))?.textContent).toContain("已登录");
	expect(mock.refreshProvidersFromNetwork).toHaveBeenCalledOnce();
});

it("fetches candidates without auto-adding, preserves filtered selections and saves only explicitly added models", async () => {
	await openConnection();
	expect(button("保存").disabled).toBe(true);
	await act(async () => {
		button("自动获取").click();
	});
	expect(mock.listUpstreamModels).toHaveBeenCalledWith({
		providerId: undefined,
		baseUrl: "https://fixture.invalid/v1",
		api: "openai-completions",
		apiKey: "fixture-only",
	});
	expect(mock.addCustom).not.toHaveBeenCalled();
	expect(button("保存").disabled).toBe(true);
	await act(() => host.querySelector<HTMLInputElement>('input[aria-label="alpha"]')?.click());
	await fill('input[aria-label="搜索模型名称或 ID"]', "gamma");
	await act(() => button("选择当前结果").click());
	await act(() => button("添加所选 · 2").click());
	expect(button("保存").disabled).toBe(false);
	expect(mock.addCustom).not.toHaveBeenCalled();
	await fill('input[aria-label="搜索模型名称或 ID"]', "alpha");
	expect(host.querySelector<HTMLInputElement>('input[aria-label="alpha"]')?.disabled).toBe(true);
	await act(async () => {
		button("保存").click();
	});
	expect(mock.addCustom).toHaveBeenCalledOnce();
	expect(mock.addCustom.mock.calls[0]?.[0]).toMatchObject({
		id: expect.stringMatching(/^connection-/),
		name: "DeepSeek",
		apiKey: "fixture-only",
		models: [
			{ id: "alpha", contextWindow: 64000 },
			{ id: "gamma", reasoning: true },
		],
	});
	expect(host.querySelector('input[type="password"]')).toBeNull();
});

it("invalidates fetched candidates on connection changes and keeps a failed save editable for retry", async () => {
	await openConnection();
	await act(async () => {
		button("自动获取").click();
	});
	await fill('input[aria-label="baseUrl，如 https://api.example.com/v1"]', "https://changed.invalid/v1");
	expect(host.querySelector('input[aria-label="alpha"]')).toBeNull();
	await act(async () => {
		button("自动获取").click();
	});
	await act(() => host.querySelector<HTMLInputElement>('input[aria-label="beta"]')?.click());
	await act(() => button("添加所选 · 1").click());
	mock.addCustom.mockRejectedValueOnce(Error("save failed"));
	await act(async () => {
		button("保存").click();
	});
	expect(host.querySelector<HTMLInputElement>('input[type="password"]')?.value).toBe("fixture-only");
	await act(async () => {
		button("保存").click();
	});
	expect(mock.addCustom).toHaveBeenCalledTimes(2);
});

it("keeps per-model advanced values separate, saves supported metadata and restores frontend-only preferences on edit", async () => {
	await openConnection();
	expect(host.querySelector('input[aria-label="连接标识"]')).toBeNull();
	expect(host.querySelector('input[aria-label="显示名（可选）"]')).toBeNull();
	expect(button("高级配置").getAttribute("aria-expanded")).toBe("false");
	await fill('input[aria-label="模型 ID"]', "alpha");
	await act(() => button("高级配置").click());
	await act(() => button("1M").click());
	await act(() => button("32k").click());
	await fill('input[aria-label="Temperature"]', "1.7");
	await act(() => host.querySelector<HTMLButtonElement>('[aria-label="思考模式"]')?.click());
	await fill('input[placeholder="reasoning_effort"]', "reasoning.effort");
	await fill('input[aria-label="可选值列表"]', "high");
	await act(() =>
		host
			.querySelector<HTMLInputElement>('input[aria-label="可选值列表"]')
			?.dispatchEvent(new KeyboardEvent("keydown", { key: "Enter", bubbles: true })),
	);
	await act(() => button("手动添加模型").click());
	const secondModel = host.querySelectorAll<HTMLInputElement>('input[aria-label="模型 ID"]')[1];
	if (!secondModel) throw Error("Missing second model");
	await act(() => {
		Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value")?.set?.call(secondModel, "beta");
		secondModel.dispatchEvent(new Event("input", { bubbles: true }));
	});
	await choose("配置模型", "beta");
	expect(host.querySelector<HTMLInputElement>('input[aria-label="Temperature"]')?.value).toBe("");
	await act(() => button("256k").click());
	await fill('input[aria-label="Temperature"]', "0.6");
	await choose("配置模型", "alpha");
	expect(host.querySelector<HTMLInputElement>('input[aria-label="输入"]')?.value).toBe("1M");
	expect(host.querySelector<HTMLInputElement>('input[aria-label="Temperature"]')?.value).toBe("1.7");
	expect(host.querySelector<HTMLButtonElement>('[aria-label="保存前测试连接"]')?.disabled).toBe(true);
	await act(async () => {
		button("保存").click();
	});
	const input = mock.addCustom.mock.calls[0]?.[0];
	expect(input.models).toMatchObject([
		{ id: "alpha", contextWindow: 1000000, maxTokens: 32000, reasoning: true },
		{ id: "beta", contextWindow: 256000 },
	]);
	expect(input.models[0]).not.toHaveProperty("advanced");
	expect(readModelAdvanced(input.id)).toMatchObject({
		alpha: {
			temperature: "1.7",
			reasoningParameter: "reasoning.effort",
			reasoningValues: ["default", "off", "high"],
		},
		beta: { temperature: "0.6" },
	});
	expect(localStorage.getItem(MODEL_ADVANCED_STORAGE_KEY)).not.toContain("fixture-only");
	expect(mock.test).not.toHaveBeenCalled();
	mock.providers = [
		{
			id: input.id,
			name: "DeepSeek",
			custom: true,
			configured: true,
			authType: "api_key",
			baseUrl: input.baseUrl,
			api: input.api,
			customModels: input.models,
			models: input.models,
		},
	];
	await act(() => root.render(<ProvidersPanel />));
	await act(() =>
		host.querySelector<HTMLButtonElement>('[aria-label="管理 DeepSeek 的模型与连接"]')?.click(),
	);
	await fill('input[aria-label="连接名称"]', "DeepSeek 主用");
	await act(() => button("高级配置").click());
	expect(host.querySelector<HTMLInputElement>('input[aria-label="Temperature"]')?.value).toBe("1.7");
	await act(async () => {
		button("保存").click();
	});
	expect(mock.updateCustom.mock.calls[0]?.[0]).toMatchObject({ id: input.id, name: "DeepSeek 主用" });
});

it("keeps identical model IDs in separate connection cards and cancels advanced edits without saving", async () => {
	const model = { id: "shared-model", name: "Shared model" };
	mock.providers = ["official", "relay"].map((id) => ({
		id,
		name: `DeepSeek ${id}`,
		custom: true,
		configured: true,
		authType: "api_key",
		models: [model],
		customModels: [model],
	}));
	await act(() => root.render(<ProvidersPanel />));
	expect(host.querySelectorAll("[data-configured-model]")).toHaveLength(0);
	await act(() =>
		host.querySelector<HTMLButtonElement>('[aria-label="展开 DeepSeek official 的模型"]')?.click(),
	);
	expect(host.querySelectorAll('[data-configured-model="shared-model"]')).toHaveLength(1);
	await act(() =>
		host.querySelector<HTMLButtonElement>('[aria-label="展开 DeepSeek relay 的模型"]')?.click(),
	);
	expect(host.querySelectorAll('[data-configured-model="shared-model"]')).toHaveLength(2);
	await act(() =>
		host.querySelector<HTMLButtonElement>('[aria-label="管理 DeepSeek official 的模型与连接"]')?.click(),
	);
	await act(() => button("高级配置").click());
	await fill('input[aria-label="Temperature"]', "3");
	expect(button("保存").disabled).toBe(true);
	await act(() => button("取消").click());
	expect(mock.updateCustom).not.toHaveBeenCalled();
	expect(localStorage.getItem(MODEL_ADVANCED_STORAGE_KEY)).toBeNull();
});
