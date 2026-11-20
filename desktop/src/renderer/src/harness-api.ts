import { LOCAL_ENVIRONMENT } from "@vera/contracts";
import { getExecutionApi } from "./environment-api";

let connected = false;
export function setHarnessConnected(value: boolean): void {
	connected = value;
}
export function isHarnessConnected(): boolean {
	return connected;
}

/** 管理操作失败必须留在界面，不将本地意图误报为后端完成。 */
export async function reportHarnessFailure(error: unknown): Promise<void> {
	const { useToastsStore } = await import("./stores/toasts");
	useToastsStore
		.getState()
		.pushExtension("error", error instanceof Error ? error.message : String(error), "VERA");
}

/** VERA 模块管理接口；凭据不会通过本地草稿或事件返回。 */
export async function harness<T>(method: string, args?: Record<string, unknown>): Promise<T> {
	return (await getExecutionApi(LOCAL_ENVIRONMENT).harnessInvoke({ method, args })) as T;
}
