import { composerDocumentFromText, emptyTranscript } from "@vera/contracts";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { useComposerSend } from "../../../../../src/renderer/src/components/composer/use-composer-send";
import {
	COMPOSER_FOCUS_EVENT,
	EMPTY_DRAFT,
	newSessionDraftKey,
	useDraftStore,
} from "../../../../../src/renderer/src/stores/drafts";
import { useTranscriptStore } from "../../../../../src/renderer/src/stores/transcript";

const { prompt, clearQueue, activateDraft, createSession, openSettings } = vi.hoisted(() => ({
	prompt: vi.fn(),
	clearQueue: vi.fn(),
	activateDraft: vi.fn(),
	createSession: vi.fn(),
	openSettings: vi.fn(),
}));
const policyFixture = vi.hoisted(() => ({
	connected: false,
	save: vi.fn(),
	draft: undefined as { generation: number; cwd: string } | undefined,
}));
vi.mock("../../../../../src/renderer/src/harness-api", () => ({
	isHarnessConnected: () => policyFixture.connected,
}));
vi.mock("../../../../../src/renderer/src/harness-settings", () => ({ prepareHarnessTask: vi.fn() }));
vi.mock("../../../../../src/renderer/src/stores/permission-policy", () => ({
	usePermissionPolicyStore: { getState: () => ({ byTarget: {}, savePolicy: policyFixture.save }) },
}));
vi.mock("../../../../../src/renderer/src/environment-api", () => ({
	getExecutionApi: () => ({ prompt, clearQueue }),
}));
vi.mock("../../../../../src/renderer/src/i18n", () => ({ useT: () => (key: string) => key }));
vi.mock("../../../../../src/renderer/src/stores/session-event-boundary", () => ({
	isSessionSynchronizing: () => false,
}));
vi.mock("../../../../../src/renderer/src/stores/sessions", () => ({
	useSessionsStore: {
		getState: () => ({
			activeSessionId: "fixture",
			activateNewSessionDraft: activateDraft,
			createSession,
			newSessionDraft: policyFixture.draft,
		}),
	},
}));
vi.mock("../../../../../src/renderer/src/stores/settings", () => ({
	useSettingsStore: { getState: () => ({ openWith: openSettings }) },
}));

beforeEach(() => {
	policyFixture.connected = false;
	policyFixture.draft = undefined;
	policyFixture.save.mockReset();
	prompt.mockReset().mockResolvedValue(undefined);
	clearQueue.mockReset();
	activateDraft.mockReset();
	createSession.mockReset();
	openSettings.mockReset();
	vi.stubGlobal("window", { dispatchEvent: vi.fn() });
	vi.stubGlobal("requestAnimationFrame", (callback: () => void) => {
		callback();
		return 0;
	});
	useDraftStore.setState({ bySession: {}, pendingBySession: {}, errorsBySession: {} });
	useTranscriptStore.setState({ bySession: {} });
});

afterEach(() => vi.unstubAllGlobals());

function composer(
	activeSessionId: string | null = "fixture",
	resolveSlashCommand?: (name: string) => string,
	draftKey = "fixture",
) {
	let actions!: ReturnType<typeof useComposerSend>;
	function Probe() {
		actions = useComposerSend({
			draftKey,
			activeSessionId,
			imagesSupported: true,
			resolveSlashCommand,
		});
		return null;
	}
	renderToStaticMarkup(createElement(Probe));
	return actions;
}

describe("本地命令与插件别名", () => {
	it.each([false, true])("选中子代理和任务一次发送，附件引用=%s 时仍还原为实际调用", async (withFile) => {
		useDraftStore.getState().updateDraft("fixture", () => ({
			...EMPTY_DRAFT,
			slashCommand: "subagent:reader",
			document: withFile
				? {
						version: 1,
						parts: [
							{ type: "text", text: "Summarize " },
							{ type: "file", path: "article.md", label: "article.md" },
						],
					}
				: composerDocumentFromText("Summarize article.md"),
		}));
		await composer("fixture", (name) => (name === "subagent:reader" ? "subagent reader" : name)).handleSend();
		expect(prompt).toHaveBeenCalledOnce();
		expect(prompt).toHaveBeenCalledWith(
			expect.objectContaining({ text: expect.stringMatching(/^\/subagent reader Summarize /) }),
		);
		if (withFile) {
			expect(prompt.mock.calls[0]?.[0].document.parts).toContainEqual({
				type: "file",
				path: "article.md",
				label: "article.md",
			});
		}
	});
	it("只有子代理标签没有任务时保留草稿，不创建会话或调用模型", async () => {
		useDraftStore
			.getState()
			.updateDraft("fixture", () => ({ ...EMPTY_DRAFT, slashCommand: "subagent:reader" }));
		await composer(null).handleSend();
		expect(prompt).not.toHaveBeenCalled();
		expect(createSession).not.toHaveBeenCalled();
		expect(useDraftStore.getState().bySession.fixture?.slashCommand).toBe("subagent:reader");
	});
	it("子代理命令位于引用之前，确保引用内容与任务在同一轮委派", async () => {
		useDraftStore.getState().updateDraft("fixture", () => ({
			...EMPTY_DRAFT,
			slashCommand: "subagent:reader",
			quotes: ["原文引用"],
			document: composerDocumentFromText("提炼核心观点"),
		}));
		await composer("fixture", () => "subagent reader").handleSend();
		const text = prompt.mock.calls[0]?.[0].text;
		expect(text).toMatch(/^\/subagent reader /);
		expect(text).toContain("原文引用");
		expect(text).toContain("提炼核心观点");
	});
	it.each(["fixture", null])("/new 从 %s 打开新草稿，不创建空会话也不调用模型", async (sessionId) => {
		useDraftStore.getState().updateDraft("fixture", () => ({
			...EMPTY_DRAFT,
			document: composerDocumentFromText("/new"),
		}));
		await composer(sessionId).handleSend();
		expect(activateDraft).toHaveBeenCalledOnce();
		expect(createSession).not.toHaveBeenCalled();
		expect(prompt).not.toHaveBeenCalled();
		expect(window.dispatchEvent).toHaveBeenCalledWith(
			expect.objectContaining({ type: COMPOSER_FOCUS_EVENT }),
		);
	});
	it("/settings 保持打开通用设置的行为", async () => {
		expect(await composer().runSlashCommand("/settings", "fixture")).toBe(true);
		expect(openSettings).toHaveBeenCalledWith();
	});
	it("插件展示别名在发送前还原，参数不变", async () => {
		useDraftStore.getState().updateDraft("fixture", () => ({
			...EMPTY_DRAFT,
			document: composerDocumentFromText("/plugin:review check this"),
		}));
		await composer("fixture", (name) => (name === "plugin:review" ? "review" : name)).handleSend();
		expect(prompt).toHaveBeenCalledWith(expect.objectContaining({ text: "/review check this" }));
	});
});

it("首发权限保存失败时，保留已创建会话中的输入且不启动任务", async () => {
	policyFixture.connected = true;
	policyFixture.draft = { generation: 7, cwd: "workspace" };
	const key = newSessionDraftKey(undefined, "workspace");
	useDraftStore
		.getState()
		.updateDraft(key, () => ({ ...EMPTY_DRAFT, document: composerDocumentFromText("retain input") }));
	createSession.mockImplementation(async () => {
		policyFixture.draft = undefined;
		return "created";
	});
	policyFixture.save.mockResolvedValue(false);
	await composer(null, undefined, key).handleSend();
	expect(prompt).not.toHaveBeenCalled();
	expect(useDraftStore.getState().bySession.created?.document).toEqual(
		composerDocumentFromText("retain input"),
	);
	expect(useDraftStore.getState().errorsBySession.created?.detail).toBe("composer.permissionSaveFailed");
	expect(useDraftStore.getState().pendingBySession).toEqual({});
});

describe("多附件输入不能被历史展示引用替换", () => {
	const images = [
		{ data: "AQID", mimeType: "image/png" },
		{ data: "BAUG", mimeType: "image/png" },
	];
	it.each([false, true])(
		"agentActive=%s的发送/排队保留两张原图，只有空闲发送做乐观回显",
		async (agentActive) => {
			useTranscriptStore.getState().loadHistory("fixture", []);
			useTranscriptStore.getState().markAgentActive("fixture", agentActive);
			useDraftStore.getState().updateDraft("fixture", () => ({
				...EMPTY_DRAFT,
				document: composerDocumentFromText("two images"),
				images,
			}));
			await composer().handleSend();
			expect(prompt).toHaveBeenCalledExactlyOnceWith({
				sessionId: "fixture",
				text: "two images",
				document: undefined,
				images,
			});
			const user = useTranscriptStore
				.getState()
				.bySession.fixture?.messages.find((message) => message.kind === "user");
			if (agentActive) expect(user).toBeUndefined();
			else expect(user).toMatchObject({ images });
			expect(useDraftStore.getState().bySession.fixture).toBeUndefined();
		},
	);
	it("发送失败恢复两张原图且移除乐观消息，不生成引用或丢附件", async () => {
		useTranscriptStore.getState().loadHistory("fixture", []);
		useDraftStore.getState().updateDraft("fixture", () => ({
			...EMPTY_DRAFT,
			document: composerDocumentFromText("failed"),
			images,
		}));
		prompt.mockRejectedValueOnce(new Error("synthetic failure"));
		await composer().handleSend();
		expect(useDraftStore.getState().bySession.fixture?.images).toEqual(images);
		expect(useTranscriptStore.getState().bySession.fixture?.messages).toEqual([]);
	});
	it("取回排队多附件追加到已有草稿，仍可按原图再次发送", async () => {
		useTranscriptStore.getState().loadHistory("fixture", []);
		useDraftStore.getState().updateDraft("fixture", () => ({
			...EMPTY_DRAFT,
			document: composerDocumentFromText("already editing"),
		}));
		clearQueue.mockResolvedValueOnce({
			followUp: ["queued"],
			followUpInputs: [{ document: composerDocumentFromText("queued"), images }],
		});
		const actions = composer();
		await actions.handleRestoreQueue(() => {});
		expect(useDraftStore.getState().bySession.fixture?.images).toEqual(images);
		await actions.handleSend();
		expect(prompt.mock.calls[0]?.[0]?.images).toEqual(images);
	});
});

describe("运行展示不放宽原发送资格", () => {
	it.each(["compacting", "full-queue"])("%s 拒绝普通草稿且保留正文和附件", async (reason) => {
		useTranscriptStore.getState().loadHistory("fixture", []);
		useTranscriptStore.setState((state) => ({
			bySession: {
				...state.bySession,
				fixture: {
					...emptyTranscript(),
					pendingPermissions: [],
					pendingDialogs: [],
					agentActive: true,
					phase: "idle",
					compacting: reason === "compacting",
					followUpQueue: reason === "full-queue" ? Array(20).fill("queued") : [],
				},
			},
		}));
		const draft = {
			...EMPTY_DRAFT,
			document: composerDocumentFromText("keep this"),
			images: [{ data: "AQID", mimeType: "image/png" }],
		};
		useDraftStore.getState().updateDraft("fixture", () => draft);
		await composer().handleSend();
		expect(prompt).not.toHaveBeenCalled();
		expect(useDraftStore.getState().bySession.fixture).toBe(draft);
	});
	it("工具轮结束的 idle 间隔仍按活跃任务排队，不插入空闲发送的乐观气泡", async () => {
		useTranscriptStore.getState().loadHistory("fixture", []);
		useTranscriptStore.getState().applyEvent("fixture", { type: "agent_start" });
		useTranscriptStore.getState().applyEvent("fixture", {
			type: "turn_end",
			toolResults: [],
			message: {
				role: "assistant",
				stopReason: "toolUse",
				content: [],
				api: "openai-completions",
				provider: "fixture",
				model: "fixture",
				timestamp: 0,
				usage: {
					input: 0,
					output: 0,
					cacheRead: 0,
					cacheWrite: 0,
					totalTokens: 0,
					cost: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0, total: 0 },
				},
			},
		});
		expect(useTranscriptStore.getState().bySession.fixture).toMatchObject({
			agentActive: true,
			phase: "idle",
		});
		useDraftStore
			.getState()
			.updateDraft("fixture", () => ({ ...EMPTY_DRAFT, document: composerDocumentFromText("follow up") }));
		await composer().handleSend();
		expect(prompt).toHaveBeenCalledOnce();
		expect(useTranscriptStore.getState().bySession.fixture?.messages.some((m) => m.kind === "user")).toBe(
			false,
		);
	});
});

describe("compaction recovery send", () => {
	it.each(["paused", "stopped"])(
		"accepts a human correction with a retained queue after %s",
		async (state) => {
			useTranscriptStore.getState().loadHistory("fixture", []);
			useTranscriptStore.setState({
				bySession: {
					fixture: {
						...emptyTranscript(),
						pendingPermissions: [],
						pendingDialogs: [],
						followUpQueue: ["modify config"],
						compactionPause: state === "paused" ? { reason: "failed" } : null,
					},
				},
			});
			useDraftStore.getState().updateDraft("fixture", () => ({
				...EMPTY_DRAFT,
				document: composerDocumentFromText("inspect only"),
			}));
			await composer().handleSend();
			expect(prompt).toHaveBeenCalledExactlyOnceWith({
				sessionId: "fixture",
				text: "inspect only",
				document: undefined,
				images: undefined,
			});
			expect(useTranscriptStore.getState().bySession.fixture?.followUpQueue).toEqual(["modify config"]);
			expect(useDraftStore.getState().bySession.fixture).toBeUndefined();
		},
	);
});
