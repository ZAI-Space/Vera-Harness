// @vitest-environment happy-dom
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import {
	BEHAVIOR_STORAGE_KEY,
	DEFAULT_BEHAVIOR,
	type SandboxProfileDraft,
	useBehaviorPreferencesStore,
} from "./behavior-preferences";

const profile: SandboxProfileDraft = {
	name: "python-dev",
	mode: "docker",
	docker_image: "python:3.12-slim",
	workspace_access: "read-only",
	timeout: 30,
	allow_web_tools: false,
	host_mcp_servers: [],
	remote_mcp_servers: [],
};
beforeEach(() => {
	localStorage.clear();
	useBehaviorPreferencesStore.setState({ ...DEFAULT_BEHAVIOR, sandboxProfiles: [], storageError: false });
});
afterEach(() => {
	vi.restoreAllMocks();
	vi.unstubAllGlobals();
});

it("saves separate session defaults locally and restores them without storing executable actions", async () => {
	const store = useBehaviorPreferencesStore.getState();
	store.setDefaultMode("goal");
	store.setPermissionPolicy("human");
	store.setCommandShell("git-bash");
	const saved = JSON.parse(localStorage.getItem(BEHAVIOR_STORAGE_KEY) ?? "{}");
	expect(saved).toMatchObject({ defaultMode: "goal", permissionPolicy: "human", commandShell: "git-bash" });
	expect(saved.setDefaultMode).toBeUndefined();
	vi.resetModules();
	const restored = (await import("./behavior-preferences")).useBehaviorPreferencesStore.getState();
	expect(restored).toMatchObject({
		defaultMode: "goal",
		permissionPolicy: "human",
		commandShell: "git-bash",
	});
});

it.each([
	{ ...profile, name: "local" },
	{ ...profile, name: "Invalid Name" },
	{ ...profile, timeout: 0 },
	{ ...profile, timeout: 3601 },
	{ ...profile, timeout: 1.5 },
	{ ...profile, docker_image: "" },
	{ ...profile, docker_image: "image with spaces" },
	{ ...profile, host_mcp_servers: ["server; command"] },
])("invalid profile leaves the saved and default configuration unchanged: %j", (invalid) => {
	const store = useBehaviorPreferencesStore.getState();
	expect(store.saveSandbox(profile)).toBeNull();
	store.setDefaultSandbox(profile.name);
	const before = localStorage.getItem(BEHAVIOR_STORAGE_KEY);
	expect(store.saveSandbox(invalid)).not.toBeNull();
	expect(localStorage.getItem(BEHAVIOR_STORAGE_KEY)).toBe(before);
	expect(useBehaviorPreferencesStore.getState().defaultSandbox).toBe(profile.name);
});

it("checks duplicates, updates named profiles and clears a deleted default without changing other profiles", () => {
	const store = useBehaviorPreferencesStore.getState();
	expect(store.saveSandbox(profile)).toBeNull();
	expect(store.saveSandbox(profile)).toBe("duplicate");
	expect(store.saveSandbox({ ...profile, name: "bwrap", mode: "bubblewrap", docker_image: "" })).toBeNull();
	store.setDefaultSandbox(profile.name);
	expect(
		store.saveSandbox({ ...profile, name: "python-ro", host_mcp_servers: ["docs", "docs"] }, profile.name),
	).toBeNull();
	expect(useBehaviorPreferencesStore.getState().defaultSandbox).toBe("python-ro");
	expect(useBehaviorPreferencesStore.getState().sandboxProfiles[0]?.host_mcp_servers).toEqual(["docs"]);
	store.setDefaultSandbox("unknown");
	expect(useBehaviorPreferencesStore.getState().defaultSandbox).toBe("python-ro");
	store.removeSandbox("python-ro");
	expect(useBehaviorPreferencesStore.getState().defaultSandbox).toBeNull();
	expect(useBehaviorPreferencesStore.getState().sandboxProfiles.map((item) => item.name)).toEqual(["bwrap"]);
});

it("storage failure keeps the editor retryable and never reports a persisted profile", () => {
	const originalStorage = localStorage;
	vi.stubGlobal("localStorage", {
		getItem: originalStorage.getItem.bind(originalStorage),
		setItem: () => {
			throw new Error("disk quota");
		},
	});
	expect(useBehaviorPreferencesStore.getState().saveSandbox(profile)).toBe("storage");
	expect(useBehaviorPreferencesStore.getState().sandboxProfiles).toEqual([]);
	expect(useBehaviorPreferencesStore.getState().storageError).toBe(true);
	vi.unstubAllGlobals();
	expect(useBehaviorPreferencesStore.getState().saveSandbox(profile)).toBeNull();
	expect(useBehaviorPreferencesStore.getState().storageError).toBe(false);
});

it("rejects malformed saved profiles and unknown defaults on startup", async () => {
	localStorage.setItem(
		BEHAVIOR_STORAGE_KEY,
		JSON.stringify({
			defaultMode: "unknown",
			permissionPolicy: "unrestricted",
			commandShell: "exec",
			defaultSandbox: "remote",
			sandboxProfiles: [
				{ ...profile, mode: "ssh" },
				{ ...profile, timeout: -1 },
			],
		}),
	);
	vi.resetModules();
	const restored = (await import("./behavior-preferences")).useBehaviorPreferencesStore.getState();
	expect(restored).toMatchObject(DEFAULT_BEHAVIOR);
});
