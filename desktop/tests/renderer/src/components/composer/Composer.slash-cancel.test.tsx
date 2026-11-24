// @vitest-environment happy-dom
import { composerDocumentFromText, emptyTranscript } from "@vera/contracts";
import { $createParagraphNode, $createTextNode, $getRoot } from "lexical";
import { act } from "react";
import { createRoot } from "react-dom/client";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { Composer } from "../../../../../src/renderer/src/components/composer/Composer";
import {
	getComposerEditor,
	releaseComposerEditor,
} from "../../../../../src/renderer/src/components/composer/editor-host";
import { draftText, EMPTY_DRAFT, useDraftStore } from "../../../../../src/renderer/src/stores/drafts";
import { useSessionsStore } from "../../../../../src/renderer/src/stores/sessions";
import { useTranscriptStore } from "../../../../../src/renderer/src/stores/transcript";

const fixture = vi.hoisted(() => ({ prompt: vi.fn() }));
vi.mock("../../../../../src/renderer/src/i18n", () => ({ useT: () => (key: string) => key }));
vi.mock("../../../../../src/renderer/src/api", () => ({
	getDesktopApi: () => ({ showComposerEditMenu: async () => {}, cancelComposerEditMenu: async () => {} }),
}));
vi.mock("../../../../../src/renderer/src/harness-api", () => ({
	isHarnessConnected: () => true,
	harness: async () => ({ enabled: true }),
	reportHarnessFailure: async () => {},
}));
vi.mock("../../../../../src/renderer/src/environment-api", () => ({
	getExecutionApi: () => ({
		prompt: fixture.prompt,
		listSlashCommands: async () => [
			{
				name: "subagent:reader",
				invocationName: "subagent reader",
				description: "提炼内容",
				source: "builtin",
				supported: true,
			},
		],
	}),
}));
vi.mock("../../../../../src/renderer/src/hooks/use-session-state", () => ({
	useActiveModelInfo: () => undefined,
	useSessionReadOnly: () => false,
}));
vi.mock("../../../../../src/renderer/src/plugins/RegionHost", () => ({ RegionHost: () => null }));
vi.mock("../../../../../src/renderer/src/components/composer/ModelPicker", () => ({
	ModelPicker: () => null,
}));
vi.mock("../../../../../src/renderer/src/components/composer/PermissionPicker", () => ({
	PermissionPicker: () => null,
}));
vi.mock("../../../../../src/renderer/src/components/composer/ContextRing", () => ({
	ContextRing: () => null,
}));

let root: ReturnType<typeof createRoot>, container: HTMLDivElement;
beforeEach(() => {
	vi.stubGlobal("IS_REACT_ACT_ENVIRONMENT", true);
	vi.stubGlobal("requestAnimationFrame", (callback: () => void) => {
		callback();
		return 0;
	});
	vi.spyOn(useSessionsStore.getState(), "loadModels").mockResolvedValue(undefined);
	useSessionsStore.setState({ activeSessionId: "slash-fixture", sessions: [], newSessionDraft: null });
	useTranscriptStore.setState({
		bySession: { "slash-fixture": { ...emptyTranscript(), pendingPermissions: [], pendingDialogs: [] } },
	});
	useDraftStore.setState({ bySession: {}, pendingBySession: {}, errorsBySession: {}, failedBySession: {} });
	container = document.createElement("div");
	document.body.append(container);
	root = createRoot(container);
});
afterEach(async () => {
	await act(() => root.unmount());
	container.remove();
	releaseComposerEditor("slash-fixture");
	vi.restoreAllMocks();
	vi.unstubAllGlobals();
});

async function render(text: string, slashCommand: string | null) {
	useDraftStore.getState().updateDraft("slash-fixture", () => ({
		...EMPTY_DRAFT,
		slashCommand,
		document: composerDocumentFromText(text),
		quotes: ["保留引用"],
	}));
	await act(async () => root.render(<Composer />));
}

function currentDraft() {
	const draft = useDraftStore.getState().bySession["slash-fixture"];
	if (!draft) throw new Error("Missing composer draft");
	return draft;
}

it.each(["Escape", "Backspace", "Delete"])("%s 取消空命令标签，不会重新生成删不掉的命令", async (key) => {
	await render("", "subagent:reader");
	const editor = container.querySelector("[contenteditable]") as HTMLElement;
	await act(() =>
		editor.dispatchEvent(new KeyboardEvent("keydown", { key, bubbles: true, cancelable: true })),
	);
	const draft = currentDraft();
	expect(draft.slashCommand).toBeNull();
	expect(draftText(draft)).toBe("");
	expect(draft.quotes).toEqual(["保留引用"]);
	expect(container.querySelector('[aria-label="slash.cancelCommand"]')).toBeNull();
});

it.each(["click", "Escape"])("%s 取消标签时保留已经输入的任务正文和引用", async (action) => {
	await render("提炼这两篇文章", "subagent:reader");
	await act(() => {
		if (action === "click")
			(container.querySelector('[aria-label="slash.cancelCommand"]') as HTMLButtonElement).click();
		else
			container
				.querySelector("[contenteditable]")
				?.dispatchEvent(new KeyboardEvent("keydown", { key: action, bubbles: true, cancelable: true }));
	});
	const draft = currentDraft();
	expect(draft.slashCommand).toBeNull();
	expect(draftText(draft)).toBe("提炼这两篇文章");
	expect(draft.quotes).toEqual(["保留引用"]);
});

it("输入 /subagent 后可以直接选择角色，不会先发设置任务", async () => {
	await render("", null);
	const editor = getComposerEditor("slash-fixture", EMPTY_DRAFT.document).editor;
	await act(async () =>
		editor.update(
			() => {
				const paragraph = $createParagraphNode().append($createTextNode("/subagent"));
				$getRoot().clear().append(paragraph);
				paragraph.selectEnd();
			},
			{ discrete: true },
		),
	);
	const role = [...container.querySelectorAll("button")].find((button) =>
		button.textContent?.includes("/subagent:reader"),
	);
	expect(role).toBeDefined();
	await act(async () => role?.click());
	expect(currentDraft().slashCommand).toBe("subagent:reader");
	expect(draftText(currentDraft())).toBe("");
	expect(fixture.prompt).not.toHaveBeenCalled();
	expect(container.querySelector('[aria-label="slash.subagentTaskPlaceholder"]')).not.toBeNull();
});
