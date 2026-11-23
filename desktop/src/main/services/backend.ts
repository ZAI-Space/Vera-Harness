import { CHANNEL_TABLE } from "@vera/contracts";

/** 自有后端唯一接入点：适配业务方法和事件，不启动或导入任何智能体运行时。 */
export interface BackendTransport {
	invoke(method: string, args: unknown): Promise<unknown>;
	subscribe(listener: (method: string, payload: unknown) => void): () => void;
	close(): Promise<void>;
}

export class BackendUnavailableError extends Error {
	constructor() {
		super("尚未连接后端服务");
		this.name = "BackendUnavailableError";
	}
}

/** 未接入时仅提供界面预览所需的空快照，所有服务端写入均拒绝。 */
function disconnectedSnapshot(method: string): unknown {
	switch (method) {
		case "listModels":
		case "listProviders":
		case "listSubagents":
		case "listAllSessions":
		case "listSessions":
		case "getLoadedSessions":
		case "getChannelSubscriptionSessionIds":
		case "listSlashCommandsForCwd":
			return [];
		case "getContextUsage":
		case "getGitBranch":
			return null;
		case "listGitBranches":
			return { current: null, branches: [] };
		case "getModelPrefs":
			return { hiddenModels: {}, subagentModels: {}, subagentThinking: {}, subagentPreferBuiltin: true };
		case "getPermissionConfig":
			return { enabled: true };
		case "getPermissionMode":
			return "default";
		case "getChannelWatchConfig":
			return { enabled: false };
		case "getCodemodeConfig":
			return { enabled: false, only: false };
		case "querySessionCatalog":
			return { sessions: [], revision: "frontend-preview", complete: true, errors: 0, total: 0 };
		case "querySessionProjects":
			return { projects: [], revision: "frontend-preview", complete: true, errors: 0 };
		case "verifySessionCatalog":
			return [];
		case "getPendingInteractions":
			return { revision: 0, permissions: [], trust: [], dialogs: [] };
		case "getLoadedResources":
			return { skills: [], skillDiagnostics: [], extensions: [], extensionErrors: [] };
		case "mcpConfigList":
			return { global: [], project: [], errors: [], projectTrusted: false, globalPath: "" };
		case "lanGetStatus":
			return { enabled: false, remoteControl: false, urls: [], clients: 0, port: null };
		default:
			throw new BackendUnavailableError();
	}
}

/** 管理适配器生命周期；迟到的旧服务事件在替换后失效。 */
export class BackendBridge {
	private transport: BackendTransport | null = null;
	private unsubscribe: (() => void) | null = null;
	private generation = 0;
	private available = true;

	constructor(private readonly emit: (method: string, payload: unknown) => void) {}
	get isConnected(): boolean {
		return this.transport !== null && this.available;
	}

	async connect(transport: BackendTransport | null): Promise<void> {
		const previous = this.transport;
		if (transport === previous) return;
		const generation = ++this.generation;
		this.unsubscribe?.();
		this.unsubscribe = null;
		this.transport = transport;
		this.available = true;
		this.emit("onBackendStatusChanged", { connected: this.isConnected });
		if (transport) {
			this.unsubscribe = transport.subscribe((method, payload) => {
				if (generation !== this.generation) return;
				if (
					method === "onBackendStatusChanged" &&
					payload &&
					typeof payload === "object" &&
					"connected" in payload
				)
					this.available = payload.connected === true;
				this.emit(method, payload);
			});
		}
		await previous?.close();
	}

	async invoke(method: string, args: unknown): Promise<unknown> {
		if (!Object.hasOwn(CHANNEL_TABLE, method)) throw new Error("Unknown backend method");
		if (this.transport) return this.transport.invoke(method, args);
		return disconnectedSnapshot(method);
	}
}
