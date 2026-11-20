import type { UpdateState } from "@vera/contracts";
import { create } from "zustand";
import { getDesktopApi } from "../api";

/** 自动更新状态（main 事件驱动）。null = 尚未收到任何状态（无更新可见性） */
interface UpdateStore {
	state: UpdateState | null;
}

export const useUpdateStore = create<UpdateStore>()(() => ({ state: null }));

let subscribed = false;

/** 订阅 update:event → store（App 挂载时调用一次；StrictMode 双执行由模块级标志防重） */
export function initUpdateStore(): void {
	if (subscribed) return;
	subscribed = true;
	getDesktopApi().onUpdateEvent((state) => useUpdateStore.setState({ state }));
}
