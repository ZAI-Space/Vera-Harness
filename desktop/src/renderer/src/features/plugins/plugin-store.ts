import { create } from "zustand";
import { harness, isHarnessConnected, reportHarnessFailure } from "../../harness-api";
import type { WorkspacePlugin } from "./model";

interface PluginStore {
	plugins: WorkspacePlugin[];
	market: WorkspacePlugin[];
	marketSource: "github" | "gitee";
	marketLoaded: boolean;
	marketLoading: boolean;
	marketError: string | null;
	error: string | null;
	busy: string | null;
	refresh: () => Promise<void>;
	loadMarket: (source: "github" | "gitee", refresh?: boolean) => Promise<void>;
	add: (plugin: WorkspacePlugin) => Promise<boolean> | boolean;
	setEnabled: (id: string, enabled: boolean) => Promise<boolean> | boolean;
	remove: (id: string) => Promise<boolean> | boolean;
}

/** 安装与启用分开；仅后端成功返回后改变目录。 */
export const usePluginPreviewStore = create<PluginStore>((set, get) => {
	let marketRequest = 0;
	const action = async (args: Record<string, unknown>): Promise<boolean> => {
		if (get().busy) return false;
		set({ busy: String(args.name), error: null });
		try {
			const plugins = await harness<WorkspacePlugin[]>("pluginAction", args);
			set({ plugins });
			return true;
		} catch (error) {
			set({ error: String(error) });
			await reportHarnessFailure(error);
			return false;
		} finally {
			set({ busy: null });
		}
	};
	return {
		plugins: [],
		market: [],
		marketSource: "github",
		marketLoaded: false,
		marketLoading: false,
		marketError: null,
		error: null,
		busy: null,
		refresh: async () => {
			if (!isHarnessConnected()) return;
			try {
				set({ plugins: await harness<WorkspacePlugin[]>("getPlugins"), error: null });
			} catch (error) {
				set({ error: String(error) });
			}
		},
		loadMarket: async (source, refresh = false) => {
			const request = ++marketRequest;
			set({ marketSource: source, marketLoading: true, marketLoaded: false, marketError: null, market: [] });
			try {
				const market = await harness<WorkspacePlugin[]>("pluginMarket", { source, refresh });
				if (request === marketRequest) set({ market, marketLoaded: true });
			} catch (error) {
				if (request === marketRequest) set({ marketError: String(error) });
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
