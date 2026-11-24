import { environmentEntityKey, LOCAL_ENVIRONMENT, parseEnvironmentUiState } from "@vera/contracts";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { StoreApi } from "zustand";

const fixture = vi.hoisted(() => ({
	cleanup: [] as (() => void)[],
	reset: [] as (() => void)[],
	read: vi.fn(),
	save: vi.fn(),
	loaded: vi.fn(),
	open: vi.fn(),
	switch: vi.fn(),
	load: vi.fn(),
	verify: vi.fn(),
}));
function trackStore<T>(store: StoreApi<T>): StoreApi<T> {
	const subscribe = store.subscribe;
	store.subscribe = (listener) => {
		const off = subscribe(listener);
		fixture.cleanup.push(off);
		return off;
	};
	fixture.reset.push(() => store.setState(store.getInitialState(), true));
	return store;
}
vi.mock("../../../../src/renderer/src/api", () => ({
	getDesktopApi: () => ({ loadEnvironmentUiState: fixture.read, saveEnvironmentUiState: fixture.save }),
}));
vi.mock("../../../../src/renderer/src/environment-api", () => ({
	getExecutionApi: () => ({ getLoadedSessions: fixture.loaded, verifySessionCatalog: fixture.verify }),
}));
vi.mock("../../../../src/renderer/src/stores/projects", async () => {
	const { create } = await import("zustand");
	return {
		useProjectsStore: trackStore(
			create((set) => ({
				addedProjects: ["/legacy"],
				allSessions: [],
				load: fixture.load,
				mergeKnownSessions: (sessions: unknown[]) => set({ allSessions: sessions }),
			})),
		),
	};
});
vi.mock("../../../../src/renderer/src/stores/ui-preferences", async () => {
	const { create } = await import("zustand");
	return {
		useUiPreferencesStore: trackStore(
			create((set) => ({
				unpin: (id: string) =>
					set((state: { pinnedSessions: string[] }) => ({
						pinnedSessions: state.pinnedSessions.filter((item) => item !== id),
					})),
				pinnedSessions: ["legacy"],
				pinnedProjects: ["/legacy"],
				expandedGroups: ["/legacy"],
				expandedGroupsTouched: false,
				lastCwd: "/legacy",
			})),
		),
	};
});
vi.mock("../../../../src/renderer/src/stores/session-workspace", async () => {
	const { create } = await import("zustand");
	return {
		isWorkspaceRecording: () => true,
		useSessionWorkspaceStore: trackStore(
			create((set) => ({
				members: [] as { file: string; sessionId: string }[],
				activeFile: null,
				recentFile: null,
				epoch: 0,
				removeMember: (file: string) =>
					set((state: { members: { file: string; sessionId: string }[] }) => ({
						members: state.members.filter((item) => item.file !== file),
					})),
			})),
		),
	};
});
vi.mock("../../../../src/renderer/src/stores/sessions", async () => {
	const { create } = await import("zustand");
	return {
		useSessionsStore: trackStore(
			create(() => ({
				sessions: [],
				activeSessionId: null,
				openFromHistory: fixture.open,
				switchSession: fixture.switch,
			})),
		),
	};
});
const remote = { kind: "ssh", connectionId: "company", environmentId: "data" } as const;
const key = (value: string) => environmentEntityKey(remote, value);
const snapshot = () => ({
	version: 1,
	projects: ["/local", key("/remote")],
	pinnedSessions: [key("remote-id"), "local-id"],
	pinnedProjects: [key("/remote"), "/local"],
	expandedGroups: [],
	expandedGroupsTouched: true,
	lastCwd: key("/remote"),
	workspace: {
		members: [
			{ file: key("/remote/r.jsonl"), sessionId: key("remote-id") },
			{ file: "/local/l.jsonl", sessionId: "local-id" },
		],
		activeFile: key("/remote/r.jsonl"),
		recentFile: "/local/l.jsonl",
	},
	catalog: [
		{
			sessionId: key("remote-id"),
			sessionFile: key("/remote/r.jsonl"),
			cwd: key("/remote"),
			createdAt: 1,
			messageCount: 0,
			active: true,
			permissionMode: "fullAccess",
			secret: "must-not-persist",
		},
	],
});
beforeEach(() => {
	for (const off of fixture.cleanup.splice(0)) off();
	for (const reset of fixture.reset) reset();
	vi.resetModules();
	vi.clearAllMocks();
	fixture.read.mockResolvedValue(parseEnvironmentUiState(snapshot()));
	fixture.save.mockResolvedValue(undefined);
	fixture.load.mockResolvedValue(undefined);
	fixture.loaded.mockResolvedValue([]);
	fixture.verify.mockReset();
	fixture.verify.mockImplementation(async ({ references }) =>
		references.map((reference: unknown) => ({ reference, status: "unknown" })),
	);
});
async function stores() {
	return {
		projects: (await import("../../../../src/renderer/src/stores/projects")).useProjectsStore,
		prefs: (await import("../../../../src/renderer/src/stores/ui-preferences")).useUiPreferencesStore,
		workspace: (await import("../../../../src/renderer/src/stores/session-workspace"))
			.useSessionWorkspaceStore,
	};
}
describe("mixed navigation cold start", () => {
	it("逐项未知保留成员，归档成员和置顶被裁剪，等待期间新增成员保留", async () => {
		let release!: (results: unknown[]) => void;
		fixture.verify.mockImplementationOnce(
			() =>
				new Promise((resolve) => {
					release = resolve;
				}),
		);
		const api = await import("../../../../src/renderer/src/stores/environment-ui-restore");
		await api.initEnvironmentUiState();
		const s = await stores();
		const extra = { file: "/local/new.jsonl", sessionId: "new" };
		s.workspace.setState({ members: [...s.workspace.getState().members, extra] });
		const reference = { sessionFile: key("/remote/r.jsonl"), sessionId: key("remote-id") };
		release([{ reference, status: "archived", meta: snapshot().catalog[0] }]);
		await vi.waitFor(() =>
			expect(s.workspace.getState().members).toEqual([snapshot().workspace.members[1], extra]),
		);
		expect(s.prefs.getState().pinnedSessions).toEqual(["local-id"]);
		expect(fixture.verify).toHaveBeenCalledTimes(2);
	});
	it("restores the single mixed order and explicit empty expansion, retaining offline references", async () => {
		const api = await import("../../../../src/renderer/src/stores/environment-ui-restore");
		await api.initEnvironmentUiState();
		const s = await stores();
		expect(s.workspace.getState().members.map((item) => item.file)).toEqual(
			snapshot().workspace.members.map((item) => item.file),
		);
		expect(s.prefs.getState().expandedGroups).toEqual([]);
		expect(s.prefs.getState().expandedGroupsTouched).toBe(true);
		expect(s.workspace.getState().activeFile).toBeNull();
		await Promise.resolve();
		expect(fixture.loaded).not.toHaveBeenCalled();
		expect(s.projects.getState().addedProjects).toContain(key("/remote"));
		const saved = fixture.save.mock.calls.at(-1)?.[0].state;
		expect(JSON.stringify(saved)).not.toContain("must-not-persist");
		expect(saved.catalog[0].active).toBe(false);
	});
	it("混合工作区中上次查看的是本机对话时也从空白页开始", async () => {
		const value = snapshot();
		value.workspace.activeFile = "/local/l.jsonl";
		fixture.read.mockResolvedValue(parseEnvironmentUiState(value));
		const api = await import("../../../../src/renderer/src/stores/environment-ui-restore");
		await api.initEnvironmentUiState();
		const s = await stores();
		expect(s.workspace.getState().members).toEqual(value.workspace.members);
		expect(s.workspace.getState().activeFile).toBeNull();
		expect(fixture.open).not.toHaveBeenCalled();
		expect(fixture.switch).not.toHaveBeenCalled();
	});
	it("does not publish an empty mixed authority before legacy restoration finishes", async () => {
		fixture.read.mockResolvedValue(null);
		const api = await import("../../../../src/renderer/src/stores/environment-ui-restore");
		await api.initEnvironmentUiState();
		const s = await stores();
		s.prefs.setState({ lastCwd: "/local" });
		expect(fixture.save).not.toHaveBeenCalled();
		s.workspace.setState({
			members: [{ file: "/legacy/a.jsonl", sessionId: "a" }],
			activeFile: "/legacy/a.jsonl",
		});
		api.startEnvironmentUiPersistence();
		expect(fixture.save.mock.calls[0]?.[0].state.workspace.members[0].file).toBe("/legacy/a.jsonl");
	});
	it("serializes mixed order writes and keeps the last reorder while a save is pending", async () => {
		let release!: () => void;
		fixture.save.mockImplementationOnce(
			() =>
				new Promise<void>((resolve) => {
					release = resolve;
				}),
		);
		const api = await import("../../../../src/renderer/src/stores/environment-ui-restore");
		await api.initEnvironmentUiState();
		const s = await stores();
		const original = s.workspace.getState().members;
		s.workspace.setState({ members: [...original].reverse() });
		s.workspace.setState({ members: original });
		s.workspace.setState({ members: [...original].reverse() });
		expect(fixture.save).toHaveBeenCalledOnce();
		release();
		await vi.waitFor(() => expect(fixture.save).toHaveBeenCalledTimes(2));
		expect(
			fixture.save.mock.calls[1]?.[0].state.workspace.members.map((item: { file: string }) => item.file),
		).toEqual([...original].reverse().map((item) => item.file));
	});
	it("rejects corrupted and cross-environment references without treating them as local", () => {
		expect(
			parseEnvironmentUiState({
				...snapshot(),
				workspace: { ...snapshot().workspace, members: [{ file: "/local/a", sessionId: key("remote-id") }] },
			}),
		).toBeNull();
		expect(parseEnvironmentUiState({ version: 2 })).toBeNull();
		expect(parseEnvironmentUiState(null)).toBeNull();
		expect(
			parseEnvironmentUiState({
				...snapshot(),
				projects: [environmentEntityKey(LOCAL_ENVIRONMENT, "vera-env-v1:literal")],
			})?.projects,
		).toHaveLength(1);
	});
});
