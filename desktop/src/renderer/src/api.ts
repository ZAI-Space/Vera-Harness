import type { DesktopClientApi } from "@vera/contracts";

declare global {
	interface Window {
		vera: DesktopClientApi;
	}
}

/** window.vera 类型化访问（未在 preload 注入时给出可读错误） */
export function getDesktopApi(): DesktopClientApi {
	if (!window.vera) {
		throw new Error("window.vera 未注入：preload 未加载或 contextBridge 失败");
	}
	return window.vera;
}
