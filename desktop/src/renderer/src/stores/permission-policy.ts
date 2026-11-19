import { create } from "zustand";

/** Harness 权限策略的前端契约，值原样交给后续执行接口。 */
export type PermissionPolicy = "human" | "confirm" | "yolo";

interface PermissionPolicyStore {
	/** 按会话或新任务草稿隔离，尚未接入后端持久化。 */
	byTarget: Record<string, PermissionPolicy>;
	selectPolicy: (target: string, policy: PermissionPolicy) => void;
}

/** 前端选择态：默认 confirm，不向借用的 VERA 后端发送权限更新。 */
export const usePermissionPolicyStore = create<PermissionPolicyStore>((set) => ({
	byTarget: {},
	selectPolicy: (target, policy) => set((state) => ({ byTarget: { ...state.byTarget, [target]: policy } })),
}));
