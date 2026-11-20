import { useT } from "../../i18n";
import { useSettingsStore } from "../../stores/settings";
import { GearIcon } from "../icons";

/**
 * 左栏底部：设置入口——左栏收起时整栏藏起，所以设置入口就只在侧栏，不另设临时图标。
 * v9：顶栏常驻，「本轮改动」开关永远在顶栏右侧，左栏不再补这个入口。
 */
export function SidebarFooter() {
	const t = useT();
	const setSettingsOpen = useSettingsStore((s) => s.setOpen);
	const [connected, setConnected] = useState(false);
	useEffect(() => {
		const api = getDesktopApi();
		let active = true;
		void api
			.getBackendStatus?.()
			.then((status) => {
				if (active) setConnected(status.connected);
			})
			.catch(() => {});
		const unsubscribe = api.onBackendStatusChanged?.((status) => setConnected(status.connected));
		return () => {
			active = false;
			unsubscribe?.();
		};
	}, []);
	return (
		<div className="flex shrink-0 flex-col gap-px p-2">
			<p
				role="status"
				data-backend-status={connected ? "connected" : "disconnected"}
				className="px-2 pb-1 text-ui-11 text-ink-faint"
			>
				{t(connected ? "settings.about.backendConnected" : "settings.about.backendDisconnected")}
			</p>
			<button
				type="button"
				className="flex h-8 w-full items-center gap-[9px] rounded-[7px] px-2 text-ui-135 text-ink-dim transition-colors hover:bg-hover hover:text-ink"
				onClick={() => setSettingsOpen(true)}
			>
				<GearIcon size={14} />
				<span>{t("sidebar.settings")}</span>
			</button>
		</div>
	);
}

import { useEffect, useState } from "react";
import { getDesktopApi } from "../../api";
