import { create } from "zustand";
import { harness, isHarnessConnected, reportHarnessFailure } from "../../harness-api";
import { errText } from "../../lib/error-text";
import type { WorkspacePlugin } from "./model";

interface PluginStore {
	plugins: WorkspacePlugin[];
	market: WorkspacePlugin[];
	marketSource: string;
	repositories: { id: string; name: string; source?: string }[];
	addRepository: (source: string) => Promise<boolean>;
	marketLoaded: boolean;
	marketLoading: boolean;
	marketError: string | null;
	error: string | null;
	busy: string | null;
	refresh: () => Promise<void>;
	loadMarket: (source: string, refresh?: boolean) => Promise<void>;
	add: (plugin: WorkspacePlugin) => Promise<boolean> | boolean;
	setEnabled: (id: string, enabled: boolean) => Promise<boolean> | boolean;
	remove: (id: string) => Promise<boolean> | boolean;
}

/** 安装与启用分开；仅后端成功返回后改变目录。 */
export const usePluginPreviewStore = create<PluginStore>((set, get) => {
	let marketRequest = 0;
	const catalogs = new Map<string, WorkspacePlugin[]>();
	const flights = new Map<string, Promise<WorkspacePlugin[]>>();
	const action = async (args: Record<string, unknown>): Promise<boolean> => {
		if (get().busy) return false;
		set({ busy: String(args.name), error: null });
		try {
			const plugins = await harness<WorkspacePlugin[]>("pluginAction", args);
			set({ plugins });
			return true;
		} catch (error) {
			set({ error: errText(error) ?? String(error) });
			await reportHarnessFailure(error);
			return false;
		} finally {
			set({ busy: null });
		}
	};
	return {
		plugins: [],
		market: [],
		marketSource: "anthropic",
		repositories: [
			{ id: "anthropic", name: "Anthropic 官方 · GitHub" },
			{ id: "github", name: "Codex 官方 · GitHub" },
			{ id: "gitee", name: "Claude Code · Gitee" },
		],
		addRepository: async (source) => {
			try {
				const repository = await harness<{ id: string; name: string; source: string }>(
					"addPluginRepository",
					{ source },
				);
				await get().refresh();
				await get().loadMarket(repository.id);
				return true;
			} catch (error) {
				set({ error: errText(error) ?? String(error) });
				return false;
			}
		},
		marketLoaded: false,
		marketLoading: false,
		marketError: null,
		error: null,
		busy: null,
		refresh: async () => {
			if (!isHarnessConnected()) return;
			try {
				const [plugins, repositories] = await Promise.all([
					harness<WorkspacePlugin[]>("getPlugins"),
					harness<PluginStore["repositories"]>("getPluginRepositories"),
				]);
				set({ plugins, repositories, error: null });
			} catch (error) {
				set({ error: errText(error) ?? String(error) });
			}
		},
		loadMarket: async (source, refresh = false) => {
			const request = ++marketRequest;
			const cached = catalogs.get(source);
			set({
				marketSource: source,
				marketLoading: !cached || refresh,
				marketLoaded: !!cached,
				marketError: null,
				market: cached ?? [],
			});
			if (cached && !refresh) return;
			try {
				let flight = flights.get(source);
				if (!flight) {
					flight = harness<WorkspacePlugin[]>("pluginMarket", { source, refresh }).finally(() =>
						flights.delete(source),
					);
					flights.set(source, flight);
				}
				const market = await flight;
				catalogs.set(source, market);
				if (request === marketRequest) set({ market, marketLoaded: true });
			} catch (error) {
				if (request === marketRequest) set({ marketError: errText(error) ?? String(error) });
			} finally {
				if (request === marketRequest) set({ marketLoading: false });
			}
		},
		add: (plugin) => {
			if (isHarnessConnected()) {
				return action({
					action: "install",
					name: plugin.id,
					source: plugin.source,
					marketplace: plugin.marketplace,
				});
			}
			set((state) => ({
				plugins: [
					...state.plugins.filter((item) => item.id !== plugin.id),
					{ ...plugin, capabilities: [...plugin.capabilities], status: "preview" },
				],
			}));
			return true;
		},
		setEnabled: (id, enabled) => {
			if (isHarnessConnected()) return action({ action: enabled ? "enable" : "disable", name: id });
			set((state) => ({ plugins: state.plugins.map((row) => (row.id === id ? { ...row, enabled } : row)) }));
			return true;
		},
		remove: (id) => {
			if (isHarnessConnected()) return action({ action: "remove", name: id });
			set((state) => ({ plugins: state.plugins.filter((row) => row.id !== id) }));
			return true;
		},
	};
});
