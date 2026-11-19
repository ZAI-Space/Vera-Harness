import { create } from "zustand";
import { harness, isHarnessConnected, reportHarnessFailure } from "../../harness-api";
import type { WorkspacePlugin } from "./model";

interface PluginStore {
	plugins: WorkspacePlugin[];
	market: WorkspacePlugin[];
	refresh: () => Promise<void>;
	loadMarket: (source: "github" | "gitee") => Promise<void>;
	add: (plugin: WorkspacePlugin) => void;
	setEnabled: (id: string, enabled: boolean) => void;
	remove: (id: string) => void;
}

/** 安装与启用分开；仅后端成功返回后改变目录。 */
export const usePluginPreviewStore = create<PluginStore>((set) => {
	const action = (args: Record<string, unknown>) => {
		void harness<WorkspacePlugin[]>("pluginAction", args)
			.then((plugins) => set({ plugins }))
			.catch(reportHarnessFailure);
	};
	return {
		plugins: [],
		market: [],
		refresh: async () => {
			if (isHarnessConnected()) set({ plugins: await harness<WorkspacePlugin[]>("getPlugins") });
		},
		loadMarket: async (source) => {
			try {
				set({ market: await harness<WorkspacePlugin[]>("pluginMarket", { source }) });
			} catch (error) {
				await reportHarnessFailure(error);
			}
		},
		add: (plugin) => {
			if (isHarnessConnected()) {
				action({ action: "install", name: plugin.id, source: plugin.source });
				return;
			}
			set((state) => ({
				plugins: [
					...state.plugins.filter((item) => item.id !== plugin.id),
					{ ...plugin, capabilities: [...plugin.capabilities], status: "preview" },
				],
			}));
		},
		setEnabled: (id, enabled) =>
			isHarnessConnected()
				? action({ action: enabled ? "enable" : "disable", name: id })
				: set((state) => ({
						plugins: state.plugins.map((row) => (row.id === id ? { ...row, enabled } : row)),
					})),
		remove: (id) =>
			isHarnessConnected()
				? action({ action: "remove", name: id })
				: set((state) => ({ plugins: state.plugins.filter((row) => row.id !== id) })),
	};
});
