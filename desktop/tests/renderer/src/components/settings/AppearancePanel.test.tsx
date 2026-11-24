// @vitest-environment happy-dom
import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, expect, it, vi } from "vitest";

const availability = vi.hoisted(() => ({ override: undefined as boolean | undefined }));
const api = vi.hoisted(() => ({
	saveUiState: vi.fn(async () => {}),
	testTaskNotification: vi.fn(async () => "submitted"),
}));
vi.mock("../../../../../src/renderer/src/lib/session-rail-availability", async (importOriginal) => {
	const actual =
		await importOriginal<typeof import("../../../../../src/renderer/src/lib/session-rail-availability")>();
	return {
		get SESSION_RAIL_AVAILABLE() {
			return availability.override ?? actual.SESSION_RAIL_AVAILABLE;
		},
	};
});
vi.mock("../../../../../src/renderer/src/api", () => ({ getDesktopApi: () => api }));
vi.mock("../../../../../src/renderer/src/i18n", async (importOriginal) => ({
	...(await importOriginal<typeof import("../../../../../src/renderer/src/i18n")>()),
	useT: () => (key: string) => key,
}));

import { AppearancePanel } from "../../../../../src/renderer/src/components/settings/AppearancePanel";
import { useI18nStore } from "../../../../../src/renderer/src/i18n";
import { useSessionWorkspaceStore } from "../../../../../src/renderer/src/stores/session-workspace";
import { useUiPreferencesStore } from "../../../../../src/renderer/src/stores/ui-preferences";

const members = [{ file: "/session.jsonl", sessionId: "session" }];
let host: HTMLDivElement;
let root: Root;

beforeEach(() => {
	vi.stubGlobal("IS_REACT_ACT_ENVIRONMENT", true);
	vi.clearAllMocks();
	availability.override = undefined;
	localStorage.clear();
	useI18nStore.setState({ language: "zh" });
	useUiPreferencesStore.setState({
		barSessionsVisible: false,
		sessionRailEnabled: true,
		taskNotificationsEnabled: true,
	});
	useSessionWorkspaceStore.setState({ members, activeFile: "/session.jsonl", recentFile: "/session.jsonl" });
	host = document.createElement("div");
	document.body.append(host);
	root = createRoot(host);
});

afterEach(async () => {
	await act(async () => root.unmount());
	host.remove();
	vi.unstubAllGlobals();
});

it("旧轨道偏好开启时仍隐藏入口，其他外观设置和工作区保持不变", async () => {
	const prefs = useUiPreferencesStore.getState();
	const workspace = useSessionWorkspaceStore.getState();
	await act(async () => root.render(<AppearancePanel />));

	expect(host.textContent).not.toContain("settings.sessionRail");
	expect(host.querySelectorAll('[role="switch"]')).toHaveLength(3);
	expect(host.textContent).toContain("settings.topBar");
	expect(host.textContent).toContain("settings.centerOrb");
	expect(host.querySelector('[aria-label="settings.theme"]')).not.toBeNull();
	for (const mode of ["Light", "Dark", "System"]) {
		expect(host.textContent).toContain(`settings.theme${mode}`);
	}
	expect(host.querySelector('[aria-label^="settings.fontSizeUi:"]')).not.toBeNull();
	expect(host.querySelector('[aria-label^="settings.fontSizeCode:"]')).not.toBeNull();
	expect(useUiPreferencesStore.getState()).toBe(prefs);
	expect(useUiPreferencesStore.getState().sessionRailEnabled).toBe(true);
	expect(useSessionWorkspaceStore.getState()).toBe(workspace);
	expect(api.saveUiState).not.toHaveBeenCalled();
});

it("恢复可用性后显示真实轨道开关并反映旧偏好", async () => {
	availability.override = true;
	await act(async () => root.render(<AppearancePanel />));
	const title = [...host.querySelectorAll("h3")].find(
		(element) => element.textContent === "settings.sessionRail",
	);
	const switchButton = title?.parentElement?.parentElement?.querySelector('[role="switch"]');
	expect(switchButton?.getAttribute("aria-checked")).toBe("true");
	expect(host.querySelectorAll('[role="switch"]')).toHaveLength(4);
	expect(useSessionWorkspaceStore.getState().members).toEqual(members);
	expect(api.saveUiState).not.toHaveBeenCalled();
});

it("通知并入外观后仍保存偏好并允许发送测试通知，移除旧功能入口", async () => {
	await act(async () => root.render(<AppearancePanel />));
	const notification = host.querySelector("section");
	const toggle = notification?.querySelector<HTMLButtonElement>('[role="switch"]');
	if (!toggle) throw new Error("Missing notification switch");
	await act(async () => toggle.click());
	expect(useUiPreferencesStore.getState().taskNotificationsEnabled).toBe(false);
	expect(api.saveUiState).toHaveBeenCalledWith({ state: { taskNotificationsEnabled: false } });
	const test = [...host.querySelectorAll("button")].find(
		(button) => button.textContent === "notifications.test",
	);
	if (!test) throw new Error("Missing test notification button");
	await act(async () => test.click());
	expect(api.testTaskNotification).toHaveBeenCalledOnce();
	expect(host.querySelector('[role="status"]')?.textContent).toBe("notifications.submitted");
	for (const removed of [
		"settings.appearance.tab",
		"settings.codemode",
		"settings.cacheWarming",
		"settings.channelWatch",
	])
		expect(host.textContent).not.toContain(removed);
});

it("语言选择通过真实菜单更新并保存，不写入外观或执行设置", async () => {
	await act(async () => root.render(<AppearancePanel />));
	const language = host.querySelector<HTMLButtonElement>('[aria-label="settings.language"]');
	if (!language) throw new Error("Missing language selector");
	expect(language.textContent).toContain("lang.zh");
	await act(async () => language.click());
	const english = [...document.querySelectorAll<HTMLButtonElement>('[role="option"]')].find((option) =>
		option.textContent?.includes("lang.en"),
	);
	if (!english) throw new Error("Missing English option");
	await act(async () => english.click());
	expect(useI18nStore.getState().language).toBe("en");
	expect(localStorage.getItem("vera.lang")).toBe("en");
	expect(language.textContent).toContain("lang.en");
	expect(api.saveUiState).not.toHaveBeenCalled();
});
