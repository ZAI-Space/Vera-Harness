import type { SessionMeta } from "@vera/contracts";
import { useCallback, useEffect, useState } from "react";
import { harness } from "../../harness-api";
import { useI18nStore } from "../../i18n";
import { errText } from "../../lib/error-text";
import { LanObserverPanel } from "./LanObserverPanel";
import { type ChannelStatus, type ModelRef, RemoteChannelCard } from "./RemoteChannelCard";

/** Independent cards share one catalog refresh; opening settings never starts a transport. */
export function RemoteConnectionsPanel() {
	const zh = useI18nStore((state) => state.language === "zh");
	const [channels, setChannels] = useState<Record<string, ChannelStatus>>({});
	const [sessions, setSessions] = useState<SessionMeta[]>([]);
	const [models, setModels] = useState<ModelRef[]>([]);
	const [error, setError] = useState<string | null>(null);
	const refresh = useCallback(async () => {
		try {
			const [status, rows, catalog] = await Promise.all([
				harness<{ channels: Record<string, ChannelStatus> }>("remoteGetStatus"),
				harness<SessionMeta[]>("listAllSessions"),
				harness<ModelRef[]>("listModels"),
			]);
			setChannels(status.channels);
			setSessions(rows);
			setModels(catalog);
			setError(null);
		} catch (failure) {
			setError(errText(failure) ?? String(failure));
		}
	}, []);
	useEffect(() => {
		void refresh();
		const timer = setInterval(() => void refresh(), 2000);
		return () => clearInterval(timer);
	}, [refresh]);
	return (
		<div className="flex flex-col gap-4">
			<p className="text-ui-12 leading-relaxed text-ink-dim">
				{zh
					? "微信和飞书可同时连接，无需同一局域网。分别绑定账号、选择对话并启动；空闲时可以切换对话，无需重新扫码。同一对话同时只执行一个任务，两个通道需要并行执行时请选择不同对话。"
					: "Weixin and Feishu can connect simultaneously without a shared LAN. Pair each account, choose a chat and start. Switch chats while idle without pairing again. For parallel execution, choose separate chats."}
			</p>
			{error && (
				<p role="alert" className="text-ui-12 text-err">
					{error}
				</p>
			)}
			{(["weixin", "feishu"] as const).map((channel) => (
				<RemoteChannelCard
					key={channel}
					channel={channel}
					status={channels[channel]}
					sessions={sessions}
					models={models}
					onStatus={(value) => setChannels(value.channels)}
				/>
			))}
			<details className="border-t border-border pt-3">
				<summary className="cursor-pointer text-ui-12 text-ink-faint">
					{zh ? "局域网观察（可选）" : "LAN observer (optional)"}
				</summary>
				<div className="pt-4">
					<LanObserverPanel />
				</div>
			</details>
		</div>
	);
}
