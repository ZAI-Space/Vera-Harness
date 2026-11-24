import { LOCAL_ENVIRONMENT, type TaskNotificationClick } from "@vera/contracts";
import { beforeEach, describe, expect, it, vi } from "vitest";

const fixture = vi.hoisted(() => ({
	listener: undefined as ((event: TaskNotificationClick) => void) | undefined,
	ready: vi.fn(async (_args: { ready: boolean }) => {}),
	off: vi.fn(),
	open: vi.fn(),
	switchSession: vi.fn(),
	toast: vi.fn(),
	sessions: [] as { sessionId: string }[],
}));
vi.mock("../../../../src/renderer/src/api", () => ({
	getDesktopApi: () => ({
		onTaskNotificationClick: (listener: (event: TaskNotificationClick) => void) => {
			fixture.listener = listener;
			return fixture.off;
		},
		setTaskNotificationNavigationReady: fixture.ready,
	}),
}));
vi.mock("../../../../src/renderer/src/stores/sessions", () => ({
	useSessionsStore: {
		getState: () => ({
			sessions: fixture.sessions,
			openFromHistory: fixture.open,
			switchSession: fixture.switchSession,
		}),
	},
}));
vi.mock("../../../../src/renderer/src/stores/toasts", () => ({ pushToast: fixture.toast }));

import { noteUserIntent } from "../../../../src/renderer/src/stores/session-navigation";
import { initTaskNotificationNavigation } from "../../../../src/renderer/src/stores/task-notification-navigation";

const target = { environment: LOCAL_ENVIRONMENT, sessionId: "s", sessionFile: "/fixture/s.jsonl" };
const flush = () => new Promise((resolve) => setTimeout(resolve, 0));
beforeEach(() => {
	vi.clearAllMocks();
	fixture.sessions = [];
	fixture.open.mockResolvedValue({ ok: true, meta: { sessionId: "s" } });
});
describe("notification click entry point", () => {
	it("does not connect or open local history for an unavailable remote target", async () => {
		const off = initTaskNotificationNavigation();
		fixture.listener?.({
			target: { ...target, environment: { kind: "ssh", connectionId: "fixture", environmentId: "one" } },
			queued: false,
		});
		await flush();
		expect(fixture.open).not.toHaveBeenCalled();
		expect(fixture.switchSession).not.toHaveBeenCalled();
		expect(fixture.toast).toHaveBeenCalledWith("warning", "notifications.targetUnavailable");
		off();
	});
	it("opens an unloaded target from an empty page after installing its listener", async () => {
		const off = initTaskNotificationNavigation();
		expect(fixture.listener).toBeTypeOf("function");
		expect(fixture.ready).toHaveBeenCalledWith({ ready: true });
		fixture.listener?.({ target, queued: true });
		await flush();
		expect(fixture.open).toHaveBeenCalledWith("/fixture/s.jsonl", expect.any(Function));
		off();
		expect(fixture.off).toHaveBeenCalledOnce();
		expect(fixture.ready).toHaveBeenLastCalledWith({ ready: false });
	});
	it("does not overwrite user navigation with a click queued before readiness", async () => {
		const off = initTaskNotificationNavigation();
		noteUserIntent();
		fixture.listener?.({ target, queued: true });
		await flush();
		expect(fixture.open).not.toHaveBeenCalled();
		off();
	});
	it("switches existing sessions without reopening and explains invalid targets", async () => {
		fixture.sessions = [{ sessionId: "s" }];
		const off = initTaskNotificationNavigation();
		fixture.listener?.({ target, queued: false });
		await flush();
		expect(fixture.switchSession).toHaveBeenCalledWith("s");
		fixture.listener?.({ target: null, queued: false });
		expect(fixture.toast).toHaveBeenCalledWith("warning", "notifications.targetUnavailable");
		off();
	});
	it("invalidates the commit guard after unmount without manufacturing history readiness", async () => {
		let guard: ((meta: { sessionId: string }) => boolean) | undefined;
		fixture.open.mockImplementation((_file, check) => {
			guard = check;
			return new Promise(() => {});
		});
		const off = initTaskNotificationNavigation();
		fixture.listener?.({ target, queued: false });
		await flush();
		expect(guard?.({ sessionId: "s" })).toBe(true);
		off();
		expect(guard?.({ sessionId: "s" })).toBe(false);
	});
});
