import { create } from "zustand";
import type { PermissionPolicy } from "./permission-policy";

/** 桌面配置草稿；不向借用的 Pi 后端发送执行模式、Shell 或沙箱设置。 */
export type BehaviorMode = "agent" | "plan" | "goal";
export type CommandShell =
	| "system"
	| "windows-powershell"
	| "pwsh"
	| "git-bash"
	| "bash"
	| "zsh"
	| `wsl:${string}`;

/** 字段对应 Harness SandboxConfig；可命名的配置只接受显式的 Docker 或 Bubblewrap。 */
export interface SandboxProfileDraft {
	name: string;
	mode: "docker" | "bubblewrap";
	workspace_access: "read-write" | "read-only";
	timeout: number;
	docker_image: string;
	allow_web_tools: boolean;
	host_mcp_servers: string[];
	remote_mcp_servers: string[];
}

interface BehaviorPreferences {
	defaultMode: BehaviorMode;
	permissionPolicy: PermissionPolicy;
	commandShell: CommandShell;
	sandboxProfiles: SandboxProfileDraft[];
	defaultSandbox: string | null;
}

export type SandboxDraftError =
	| "name"
	| "duplicate"
	| "timeout"
	| "image"
	| "servers"
	| "missing"
	| "storage";

/** 仅校验配置草稿，不检测引擎、不拉取镜像、不启动容器。 */
export function validateSandboxProfile(profile: SandboxProfileDraft): SandboxDraftError | null {
	if (!/^[a-z][a-z0-9-]{0,47}$/.test(profile.name) || ["none", "local", "all"].includes(profile.name))
		return "name";
	if (!Number.isInteger(profile.timeout) || profile.timeout < 1 || profile.timeout > 3600) return "timeout";
	if (profile.mode === "docker" && (!profile.docker_image.trim() || /\s/.test(profile.docker_image)))
		return "image";
	if (
		[...profile.host_mcp_servers, ...profile.remote_mcp_servers].some(
			(name) => !/^[A-Za-z0-9_.-]+$/.test(name),
		)
	)
		return "servers";
	return null;
}

interface BehaviorStore extends BehaviorPreferences {
	storageError: boolean;
	setDefaultMode: (mode: BehaviorMode) => void;
	setPermissionPolicy: (policy: PermissionPolicy) => void;
	setCommandShell: (shell: CommandShell) => void;
	saveSandbox: (profile: SandboxProfileDraft, originalName?: string) => SandboxDraftError | null;
	removeSandbox: (name: string) => void;
	setDefaultSandbox: (name: string | null) => void;
}

export const DEFAULT_BEHAVIOR: BehaviorPreferences = {
	defaultMode: "agent",
	permissionPolicy: "confirm",
	commandShell: "system",
	sandboxProfiles: [],
	defaultSandbox: null,
};

function isRecord(value: unknown): value is Record<string, unknown> {
	return !!value && typeof value === "object" && !Array.isArray(value);
}

/** 只恢复已识别的偏好，拒绝未知引擎和损坏的配置项，不恢复任何可执行回调。 */
function restorePreferences(saved: unknown): BehaviorPreferences {
	if (!isRecord(saved)) return { ...DEFAULT_BEHAVIOR };
	const sandboxProfiles: SandboxProfileDraft[] = [];
	if (Array.isArray(saved.sandboxProfiles))
		for (const item of saved.sandboxProfiles) {
			if (
				!isRecord(item) ||
				typeof item.name !== "string" ||
				!["docker", "bubblewrap"].includes(String(item.mode)) ||
				!["read-only", "read-write"].includes(String(item.workspace_access)) ||
				typeof item.timeout !== "number" ||
				typeof item.docker_image !== "string" ||
				typeof item.allow_web_tools !== "boolean" ||
				!Array.isArray(item.host_mcp_servers) ||
				!Array.isArray(item.remote_mcp_servers) ||
				[...item.host_mcp_servers, ...item.remote_mcp_servers].some((name) => typeof name !== "string")
			)
				continue;
			const profile = item as unknown as SandboxProfileDraft;
			if (!validateSandboxProfile(profile) && !sandboxProfiles.some((other) => other.name === profile.name))
				sandboxProfiles.push(profile);
		}
	return {
		defaultMode: ["agent", "plan", "goal"].includes(String(saved.defaultMode))
			? (saved.defaultMode as BehaviorMode)
			: "agent",
		permissionPolicy: ["human", "confirm", "yolo"].includes(String(saved.permissionPolicy))
			? (saved.permissionPolicy as PermissionPolicy)
			: "confirm",
		commandShell:
			["system", "windows-powershell", "pwsh", "git-bash", "bash", "zsh"].includes(
				String(saved.commandShell),
			) || /^wsl:.{1,128}$/.test(String(saved.commandShell))
				? (saved.commandShell as CommandShell)
				: "system",
		sandboxProfiles,
		defaultSandbox: sandboxProfiles.some((profile) => profile.name === saved.defaultSandbox)
			? String(saved.defaultSandbox)
			: null,
	};
}

export const BEHAVIOR_STORAGE_KEY = "vera.behavior-preferences.v1";

function loadPreferences(): BehaviorPreferences {
	try {
		return restorePreferences(JSON.parse(localStorage.getItem(BEHAVIOR_STORAGE_KEY) ?? "null"));
	} catch {
		return { ...DEFAULT_BEHAVIOR };
	}
}

/** 偏好按应用本地保存；写入失败保留内存选择并显示错误，不能声称已成功持久化。 */
export const useBehaviorPreferencesStore = create<BehaviorStore>((set, get) => {
	const update = (patch: Partial<BehaviorPreferences>, retainOnFailure = true) => {
		const { defaultMode, permissionPolicy, commandShell, sandboxProfiles, defaultSandbox } = {
			...get(),
			...patch,
		};
		try {
			localStorage.setItem(
				BEHAVIOR_STORAGE_KEY,
				JSON.stringify({ defaultMode, permissionPolicy, commandShell, sandboxProfiles, defaultSandbox }),
			);
			set({ ...patch, storageError: false });
		} catch {
			set({ ...(retainOnFailure ? patch : {}), storageError: true });
		}
	};
	return {
		...loadPreferences(),
		storageError: false,
		setDefaultMode: (defaultMode) => update({ defaultMode }),
		setPermissionPolicy: (permissionPolicy) => update({ permissionPolicy }),
		setCommandShell: (commandShell) => update({ commandShell }),
		saveSandbox: (profile, originalName) => {
			const normalized = {
				...profile,
				name: profile.name.trim(),
				docker_image: profile.docker_image.trim(),
				host_mcp_servers: [...new Set(profile.host_mcp_servers)],
				remote_mcp_servers: [...new Set(profile.remote_mcp_servers)],
			};
			const error = validateSandboxProfile(normalized);
			if (error) return error;
			const existing = get().sandboxProfiles;
			if (originalName && !existing.some((item) => item.name === originalName)) return "missing";
			if (existing.some((item) => item.name === normalized.name && item.name !== originalName))
				return "duplicate";
			update(
				{
					sandboxProfiles: originalName
						? existing.map((item) => (item.name === originalName ? normalized : item))
						: [...existing, normalized],
					defaultSandbox: get().defaultSandbox === originalName ? normalized.name : get().defaultSandbox,
				},
				false,
			);
			return get().storageError ? "storage" : null;
		},
		removeSandbox: (name) =>
			update(
				{
					sandboxProfiles: get().sandboxProfiles.filter((profile) => profile.name !== name),
					defaultSandbox: get().defaultSandbox === name ? null : get().defaultSandbox,
				},
				false,
			),
		setDefaultSandbox: (defaultSandbox) => {
			if (defaultSandbox === null || get().sandboxProfiles.some((profile) => profile.name === defaultSandbox))
				update({ defaultSandbox });
		},
	};
});
