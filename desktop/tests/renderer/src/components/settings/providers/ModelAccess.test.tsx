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
vi.mock("../../../../../../src/renderer/src/stores/settings", () => ({
	useSettingsStore: (select: (state: typeof mock) => unknown) => select(mock),
}));

import { ProvidersPanel } from "../../../../../../src/renderer/src/components/settings/providers/ProvidersPanel";
import { useI18nStore } from "../../../../../../src/renderer/src/i18n";
import {
	MODEL_ADVANCED_STORAGE_KEY,
	readModelAdvanced,
} from "../../../../../../src/renderer/src/stores/model-advanced-preferences";

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
	const item = [...document.querySelectorAll<HTMLButtonElement>("button")].find(
		(element) => element.textContent?.trim() === text,
	);
	if (!item) throw Error(`Missing button ${text}`);
	return item;
}
async function fill(selector: string, value: string) {
	const input = document.querySelector<HTMLInputElement>(selector);
	if (!input) throw Error(`Missing field ${selector}`);
	await act(() => {
		Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value")?.set?.call(input, value);
		input.dispatchEvent(new Event("input", { bubbles: true }));
	});
}
async function openConnection() {
	await act(() => root.render(<ProvidersPanel />));
	await act(() => button("添加服务商").click());
	await act(() => button("自定义服务商").click());
	await fill('input[type="password"]', "fixture-only");
	await fill('input[aria-label="baseUrl，如 https://api.example.com/v1"]', "https://fixture.invalid/v1");
}

async function choose(label: string, option: string) {
	await act(() => document.querySelector<HTMLButtonElement>(`button[aria-label="${label}"]`)?.click());
	const target = [...document.querySelectorAll<HTMLButtonElement>('[role="option"]')].find(
		(item) => item.textContent?.trim() === option,
	);
	if (!target) throw Error(`Missing option ${option}`);
	await act(() => target.click());
}

it("shows only API configurations without authentication tabs or login controls", async () => {
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
			id: "direct",
			name: "Direct",
			custom: false,
			configured: true,
			authType: "api_key",
			models: [{ id: "api-model", name: "API model" }],
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
	expect(document.querySelectorAll("[role=tab], [role=tablist], [role=tabpanel]")).toHaveLength(0);
	expect(host.textContent).not.toMatch(/账号订阅|登录账号|设备码|Unused/);
	await act(() => document.querySelector<HTMLButtonElement>('[aria-label="展开 Relay 的模型"]')?.click());
	await act(() => document.querySelector<HTMLButtonElement>('[aria-label="展开 Direct 的模型"]')?.click());
	expect(
		[...document.querySelectorAll<HTMLElement>("[data-configured-model]")].map(
			(row) => row.dataset.configuredModel,
		),
	).toEqual(["chosen", "api-model"]);
	expect(mock.refreshProvidersFromNetwork).toHaveBeenCalledOnce();
});

it("a late save only closes its own editor, preserving another provider opened meanwhile", async () => {
	let finish!: () => void;
	mock.updateCustom.mockImplementationOnce(
		() =>
			new Promise<void>((resolve) => {
				finish = resolve;
			}),
	);
	mock.providers = ["First", "Second"].map((name) => ({
		id: name,
		name,
		custom: true,
		configured: true,
		baseUrl: `https://${name.toLowerCase()}.invalid/v1`,
		api: "openai-completions",
		models: [{ id: `${name}-model`, name }],
		customModels: [{ id: `${name}-model` }],
	}));
	await act(() => root.render(<ProvidersPanel />));
	await act(() => document.querySelector<HTMLButtonElement>('[aria-label="管理 First 的模型配置"]')?.click());
	await act(() => button("保存").click());
	await act(() =>
		document.querySelector<HTMLButtonElement>('[aria-label="管理 Second 的模型配置"]')?.click(),
	);
	expect(document.querySelector<HTMLInputElement>('[aria-label="模型 ID"]')?.value).toBe("Second-model");
	await act(() => finish());
	expect(document.querySelector<HTMLInputElement>('[aria-label="模型 ID"]')?.value).toBe("Second-model");
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
		template: "custom",
		fullUrl: undefined,
	});
	expect(mock.addCustom).not.toHaveBeenCalled();
	expect(button("保存").disabled).toBe(true);
	await act(() => document.querySelector<HTMLInputElement>('input[aria-label="alpha"]')?.click());
	await fill('input[aria-label="搜索模型名称或 ID"]', "gamma");
	await act(() => button("选择当前结果").click());
	await act(() => button("添加所选 · 2").click());
	expect(button("保存").disabled).toBe(false);
	expect(mock.addCustom).not.toHaveBeenCalled();
	await fill('input[aria-label="搜索模型名称或 ID"]', "alpha");
	expect(document.querySelector<HTMLInputElement>('input[aria-label="alpha"]')?.disabled).toBe(true);
	await act(async () => {
		button("保存").click();
	});
	expect(mock.addCustom).toHaveBeenCalledOnce();
	expect(mock.addCustom.mock.calls[0]?.[0]).toMatchObject({
		id: expect.stringMatching(/^connection-/),
		name: "fixture.invalid",
		apiKey: "fixture-only",
		models: [
			{ id: "alpha", contextWindow: 64000 },
			{ id: "gamma", reasoning: true },
		],
	});
	expect(document.querySelector('input[type="password"]')).toBeNull();
});

it("invalidates fetched candidates on connection changes and keeps a failed save editable for retry", async () => {
	await openConnection();
	await act(async () => {
		button("自动获取").click();
	});
	await fill('input[aria-label="baseUrl，如 https://api.example.com/v1"]', "https://changed.invalid/v1");
	expect(document.querySelector('input[aria-label="alpha"]')).toBeNull();
	await act(async () => {
		button("自动获取").click();
	});
	await act(() => document.querySelector<HTMLInputElement>('input[aria-label="beta"]')?.click());
	await act(() => button("添加所选 · 1").click());
	mock.addCustom.mockRejectedValueOnce(Error("save failed"));
	await act(async () => {
		button("保存").click();
	});
	expect(document.querySelector<HTMLInputElement>('input[type="password"]')?.value).toBe("fixture-only");
	await act(async () => {
		button("保存").click();
	});
	expect(mock.addCustom).toHaveBeenCalledTimes(2);
});

it("keeps per-model advanced values separate, saves supported metadata and restores persisted request preferences on edit", async () => {
	await openConnection();
	expect(document.querySelector('input[aria-label="连接标识"]')).toBeNull();
	expect(document.querySelector('input[aria-label="模型显示名称 1"]')).toBeNull();
	expect(document.querySelector('input[aria-label="连接名称"]')).toBeNull();
	expect(button("高级配置").getAttribute("aria-expanded")).toBe("false");
	await fill('input[aria-label="模型 ID"]', "alpha");
	await act(() => button("高级配置").click());
	await act(() => button("1M").click());
	await act(() => button("32k").click());
	await fill('input[aria-label="Temperature"]', "1.7");
	await act(() => document.querySelector<HTMLButtonElement>('[aria-label="思考模式"]')?.click());
	await fill('input[placeholder="reasoning_effort"]', "reasoning.effort");
	await fill('input[aria-label="可选值列表"]', "high");
	await act(() =>
		document
			.querySelector<HTMLInputElement>('input[aria-label="可选值列表"]')
			?.dispatchEvent(new KeyboardEvent("keydown", { key: "Enter", bubbles: true })),
	);
	await act(() => button("手动添加模型").click());
	const secondModel = document.querySelectorAll<HTMLInputElement>('input[aria-label="模型 ID"]')[1];
	if (!secondModel) throw Error("Missing second model");
	await act(() => {
		Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value")?.set?.call(secondModel, "beta");
		secondModel.dispatchEvent(new Event("input", { bubbles: true }));
	});
	await choose("配置模型", "beta");
	expect(document.querySelector<HTMLInputElement>('input[aria-label="Temperature"]')?.value).toBe("");
	await act(() => button("256k").click());
	await fill('input[aria-label="Temperature"]', "0.6");
	await choose("配置模型", "alpha");
	expect(document.querySelector<HTMLInputElement>('input[aria-label="输入"]')?.value).toBe("1M");
	expect(document.querySelector<HTMLInputElement>('input[aria-label="Temperature"]')?.value).toBe("1.7");
	expect(document.querySelector('[aria-label="保存前测试连接"]')).toBeNull();
	await act(async () => {
		button("保存").click();
	});
	const input = mock.addCustom.mock.calls[0]?.[0];
	expect(input.models).toMatchObject([
		{ id: "alpha", contextWindow: 1000000, maxTokens: 32000, reasoning: true },
		{ id: "beta", contextWindow: 256000 },
	]);
	expect(input.models[0].advanced).toMatchObject({
		temperature: 1.7,
		reasoningParameter: "reasoning.effort",
	});
	expect(readModelAdvanced(input.id)).toMatchObject({
		alpha: {
			temperature: "1.7",
			reasoningParameter: "reasoning.effort",
			reasoningValues: ["default", "off", "low", "medium", "high"],
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
		document.querySelector<HTMLButtonElement>('[aria-label="管理 DeepSeek 的模型配置"]')?.click(),
	);
	await act(() => button("高级配置").click());
	expect(document.querySelector<HTMLInputElement>('input[aria-label="Temperature"]')?.value).toBe("1.7");
	await act(async () => {
		button("保存").click();
	});
	expect(mock.updateCustom.mock.calls[0]?.[0]).toMatchObject({ id: input.id, name: "fixture.invalid" });
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
	expect(document.querySelectorAll("[data-configured-model]")).toHaveLength(0);
	await act(() =>
		document.querySelector<HTMLButtonElement>('[aria-label="展开 DeepSeek official 的模型"]')?.click(),
	);
	expect(document.querySelectorAll('[data-configured-model="shared-model"]')).toHaveLength(1);
	await act(() =>
		document.querySelector<HTMLButtonElement>('[aria-label="展开 DeepSeek relay 的模型"]')?.click(),
	);
	expect(document.querySelectorAll('[data-configured-model="shared-model"]')).toHaveLength(2);
	await act(() =>
		document.querySelector<HTMLButtonElement>('[aria-label="管理 DeepSeek official 的模型配置"]')?.click(),
	);
	await act(() => button("高级配置").click());
	await fill('input[aria-label="Temperature"]', "3");
	expect(button("保存").disabled).toBe(true);
	await act(() => button("取消").click());
	expect(mock.updateCustom).not.toHaveBeenCalled();
	expect(localStorage.getItem(MODEL_ADVANCED_STORAGE_KEY)).toBeNull();
});
