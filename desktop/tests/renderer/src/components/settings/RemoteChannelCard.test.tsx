// @vitest-environment happy-dom
import type { SessionMeta } from "@vera/contracts";
import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import {
	type ChannelStatus,
	RemoteChannelCard,
} from "../../../../../src/renderer/src/components/settings/RemoteChannelCard";
import { useI18nStore } from "../../../../../src/renderer/src/i18n";

let host: HTMLDivElement;
let root: Root;
const session: SessionMeta = {
	sessionId: "linked-chat",
	cwd: "/workspace",
	name: "Linked chat",
	model: { provider: "configured-provider", modelId: "configured-model" },
	active: true,
	messageCount: 0,
	createdAt: 0,
};

beforeEach(() => {
	vi.stubGlobal("IS_REACT_ACT_ENVIRONMENT", true);
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

function button(label: string): HTMLButtonElement {
	const control = [...host.querySelectorAll("button")].find((entry) => entry.textContent === label);
	if (!control) throw new Error(`Missing button: ${label}`);
	return control;
}

it("uses English for unavailable models and the empty chat placeholder", async () => {
	useI18nStore.setState({ language: "en" });
	await act(() =>
		root.render(
			<RemoteChannelCard
				channel="weixin"
				status={undefined}
				sessions={[session]}
				models={[]}
				onStatus={() => {}}
			/>,
		),
	);
	expect(host.textContent).toContain("Choose a chat to continue");
	await act(() => (host.querySelector('[role="combobox"]') as HTMLButtonElement).click());
	expect(document.body.textContent).toContain("Linked chat · Model unavailable");
	expect(document.body.textContent).not.toContain("模型已失效");
});

it.each(["weixin", "feishu"] as const)(
	"%s keeps start/stop separate from unbinding through the connection lifecycle",
	async (channel) => {
		const status: ChannelStatus = {
			channel,
			bound: false,
			running: false,
			stopping: false,
			loginState: "idle",
			qrDataUrl: null,
			pairCode: null,
			error: null,
			sessionId: session.sessionId,
			executionSessionId: null,
			currentSessionId: null,
			journal: null,
		};
		const render = async (changes: Partial<ChannelStatus>, modelsAvailable = true) => {
			Object.assign(status, changes);
			await act(() =>
				root.render(
					<RemoteChannelCard
						channel={channel}
						status={{ ...status }}
						sessions={[session]}
						models={modelsAvailable ? [{ provider: "configured-provider", id: "configured-model" }] : []}
						onStatus={() => {}}
					/>,
				),
			);
		};
		await render({});
		expect(button("启动远程连接").disabled).toBe(true);
		expect(host.textContent).not.toContain("解除本机绑定");
		await render({ bound: true, loginState: "ready" });
		expect(button("启动远程连接").disabled).toBe(false);
		expect(button("解除本机绑定").disabled).toBe(false);
		expect(button(channel === "weixin" ? "微信扫码绑定" : "验证并配对飞书").disabled).toBe(true);
		await act(() => button("启动远程连接").click());
		expect(document.querySelector('[role="dialog"]')?.textContent).toContain("允许已配对账号继续此对话？");
		await act(() => window.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape" })));
		expect(document.querySelector('[role="dialog"]')).toBeNull();

		// Losing the model or running a task must never prevent stopping an existing connection.
		await render({ running: true, executionSessionId: session.sessionId }, false);
		expect(button("断开连接").disabled).toBe(false);
		expect(host.textContent).not.toContain("启动远程连接");
		expect(button("解除本机绑定").disabled).toBe(true);
		expect(button("解除本机绑定").className).toContain("disabled:opacity-40");
		await render({ running: false, stopping: true });
		expect(button("正在断开…").disabled).toBe(true);
		expect(button("解除本机绑定").disabled).toBe(true);
		await render({ stopping: false, executionSessionId: null });
		expect(button("启动远程连接").disabled).toBe(false);
		expect(button("解除本机绑定").disabled).toBe(false);
		await render({ bound: false });
		expect(button("启动远程连接").disabled).toBe(true);
		expect(host.textContent).not.toContain("解除本机绑定");
	},
);
