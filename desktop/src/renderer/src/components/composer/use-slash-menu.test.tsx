// @vitest-environment happy-dom
import { act } from "react";
import { createRoot } from "react-dom/client";
import { afterEach, expect, it, vi } from "vitest";
import { useSlashMenu } from "./use-slash-menu";

vi.mock("../../i18n", () => ({ useT: () => (key: string) => key }));
const fixture = vi.hoisted(() => ({ ensure: vi.fn(), run: vi.fn(), send: vi.fn(), setText: vi.fn() }));
let menu: ReturnType<typeof useSlashMenu>;
const host = document.createElement("div");
document.body.append(host);
let root = createRoot(host);

function Harness() {
	menu = useSlashMenu({
		activeSessionId: null,
		cwd: null,
		trustVersion: 0,
		text: "/",
		slashCommand: null,
		setText: fixture.setText,
		setSlashCommand: () => {},
		editorRef: { current: null },
		ensureSession: fixture.ensure,
		runSlashCommand: fixture.run,
		handleSend: fixture.send,
		showFeedback: () => {},
		setError: () => {},
	});
	return null;
}

afterEach(async () => {
	await act(() => root.unmount());
	root = createRoot(host);
	vi.clearAllMocks();
	vi.unstubAllGlobals();
});

it("无项目时仍可选 /new，禁用分类不能执行或发送，也不创建空会话", async () => {
	vi.stubGlobal("IS_REACT_ACT_ENVIRONMENT", true);
	await act(() => root.render(<Harness />));
	await act(() => menu.updateToken("/", 1));
	expect(menu.slashOpen).toBe(true);
	const sandbox = menu.slashCommands.find((command) => command.name === "sandbox");
	const createNew = menu.slashCommands.find((command) => command.name === "new");
	if (!sandbox || !createNew) throw new Error("缺少桌面命令");
	await act(async () => menu.handleSlashPick(sandbox));
	expect(fixture.run).not.toHaveBeenCalled();
	expect(fixture.send).not.toHaveBeenCalled();
	await act(async () => menu.handleSlashPick(createNew));
	expect(fixture.ensure).not.toHaveBeenCalled();
	expect(fixture.setText).toHaveBeenCalledWith("");
	expect(fixture.run).toHaveBeenCalledExactlyOnceWith("/new", null);
});
