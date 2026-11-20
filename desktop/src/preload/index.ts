import {
	CHANNEL_TABLE,
	type DesktopClientApi,
	type EnvironmentApi,
	type EnvironmentRef,
	SUBSCRIPTION_TABLE,
} from "@vera/contracts";
import { contextBridge, ipcRenderer, webUtils } from "electron";

/** 桌面能力通过固定方法表暴露；渲染层无法访问原始 IPC、Node 或文件系统。 */
function subscriptions(scope: "desktop" | "environment"): Record<string, unknown> {
	return Object.fromEntries(
		Object.entries(SUBSCRIPTION_TABLE)
			.filter(([, definition]) => definition.scope === scope)
			.map(([method]) => [
				method,
				(callback: (payload: unknown) => void) => {
					const listener = (_event: unknown, data: { method: string; payload: unknown }) => {
						if (data.method === method) callback(data.payload);
					};
					ipcRenderer.on("vera:event", listener);
					return () => ipcRenderer.removeListener("vera:event", listener);
				},
			]),
	);
}
function methods(scope: "desktop" | "environment"): Record<string, unknown> {
	return Object.fromEntries(
		Object.entries(CHANNEL_TABLE)
			.filter(([, definition]) => definition.scope === scope)
			.map(([method]) => [method, (args: unknown) => ipcRenderer.invoke("vera:invoke", { method, args })]),
	);
}
const api = {
	...methods("desktop"),
	...subscriptions("desktop"),
	platform: process.platform,
	getPathForFile: (file: File) => webUtils.getPathForFile(file),
	forEnvironment: (environment: EnvironmentRef) => {
		if (environment.kind !== "local") throw new Error("Unsupported execution environment");
		return { ...methods("environment"), ...subscriptions("environment") } as EnvironmentApi;
	},
} as unknown as DesktopClientApi;
contextBridge.exposeInMainWorld("vera", api);
