import { create } from "zustand";
import { claimActivation, noteUserIntent, onSessionNavigationIntent } from "./session-navigation";

/** 首页工作区导航；只切换视图，不关闭会话或清空输入草稿。 */
export type WorkspacePage = "chat" | "plugins" | "scheduled";

export const useWorkspacePageStore = create<{
	page: WorkspacePage;
	setPage: (page: WorkspacePage) => void;
}>((set) => ({ page: "chat", setPage: (page) => set({ page }) }));

/** 页面切换作废旧会话的在途激活；会话数据与输入草稿仍由原 store 持有。 */
export function navigateWorkspacePage(page: WorkspacePage): void {
	claimActivation();
	noteUserIntent();
	useWorkspacePageStore.getState().setPage(page);
}

/** 根组件挂载一次；显式点击会话或新任务时恢复聊天，卸载后解除订阅。 */
export function initWorkspaceNavigation(): () => void {
	return onSessionNavigationIntent(() => useWorkspacePageStore.getState().setPage("chat"));
}
