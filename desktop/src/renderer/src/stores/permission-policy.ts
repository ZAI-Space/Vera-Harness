import { create } from "zustand";
import { harness, isHarnessConnected, reportHarnessFailure } from "../harness-api";

/** Harness 权限策略的前端契约，值原样交给后续执行接口。 */
export type PermissionPolicy = "human" | "confirm" | "yolo";

interface PermissionPolicyStore {
	/** Existing sessions restore backend policy; drafts inherit behavior defaults. */
	byTarget: Record<string, PermissionPolicy>;
	selectPolicy: (target: string, policy: PermissionPolicy) => void;
	loadPolicy: (sessionId: string) => Promise<void>;
	savePolicy: (sessionId: string, policy: PermissionPolicy) => Promise<boolean>;
}

const revisions = new Map<string, number>();
const pending = new Map<string, Promise<boolean>>();
const confirmed = new Map<string, PermissionPolicy>();

/** Serialize session writes and reject stale reads without sharing draft policies. */
export const usePermissionPolicyStore = create<PermissionPolicyStore>((set, get) => ({
	byTarget: {},
	selectPolicy: (target, policy) => {
		revisions.set(target, (revisions.get(target) ?? 0) + 1);
		set((state) => ({ byTarget: { ...state.byTarget, [target]: policy } }));
	},
	loadPolicy: async (sessionId) => {
		if (!isHarnessConnected()) return;
		const revision = revisions.get(sessionId);
		try {
			const saved = await harness<{ permissionPolicy: PermissionPolicy }>("getSessionSelections", {
				sessionId,
			});
			if (revision === revisions.get(sessionId) && !pending.has(sessionId)) {
				confirmed.set(sessionId, saved.permissionPolicy);
				set((state) => ({ byTarget: { ...state.byTarget, [sessionId]: saved.permissionPolicy } }));
			}
		} catch (error) {
			await reportHarnessFailure(error);
		}
	},
	savePolicy: (sessionId, policy) => {
		get().selectPolicy(sessionId, policy);
		const revision = revisions.get(sessionId);
		const work = (pending.get(sessionId) ?? Promise.resolve()).then(async () => {
			try {
				await harness("setSessionSelections", { sessionId, permissionPolicy: policy });
				confirmed.set(sessionId, policy);
				if (revisions.get(sessionId) === revision)
					set((state) => ({ byTarget: { ...state.byTarget, [sessionId]: policy } }));
				return true;
			} catch (error) {
				if (revisions.get(sessionId) === revision) {
					let restored = confirmed.get(sessionId);
					try {
						restored = (
							await harness<{ permissionPolicy: PermissionPolicy }>("getSessionSelections", { sessionId })
						).permissionPolicy;
						confirmed.set(sessionId, restored);
					} catch {
						/* Only confirmed values can survive a failed write and read-back. */
					}
					if (revisions.get(sessionId) === revision) {
						if (restored) get().selectPolicy(sessionId, restored);
						else
							set((state) => {
								const byTarget = { ...state.byTarget };
								delete byTarget[sessionId];
								return { byTarget };
							});
					}
				}
				await reportHarnessFailure(error);
				return false;
			}
		});
		pending.set(sessionId, work);
		void work.finally(() => {
			if (pending.get(sessionId) === work) pending.delete(sessionId);
		});
		return work;
	},
}));
