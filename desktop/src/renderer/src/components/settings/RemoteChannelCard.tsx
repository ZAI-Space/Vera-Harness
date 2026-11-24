import type { SessionMeta } from "@vera/contracts";
import { useEffect, useState } from "react";
import { harness } from "../../harness-api";
import { useI18nStore } from "../../i18n";
import { errText } from "../../lib/error-text";
import { CopyButton } from "../chat/message-actions";
import { Button } from "../ui/Button";
import { ConfirmDialog } from "../ui/ConfirmDialog";
import { Select } from "../ui/Select";

export interface ChannelStatus {
	bound: boolean;
	running: boolean;
	stopping: boolean;
	loginState: string;
	qrDataUrl: string | null;
	pairCode: string | null;
	error: string | null;
	sessionId: string | null;
	channel: string;
	executionSessionId: string | null;
	currentSessionId: string | null;
	journal: { connections: { account: string; status: string }[] } | null;
}

export interface ModelRef {
	provider: string;
	id: string;
}

/** One channel can be bound, started, stopped and rerouted independently of its sibling. */
export function RemoteChannelCard({
	channel,
	status,
	sessions,
	models,
	onStatus,
}: {
	channel: "weixin" | "feishu";
	status: ChannelStatus | undefined;
	sessions: SessionMeta[];
	models: ModelRef[];
	onStatus: (value: { channels: Record<string, ChannelStatus> }) => void;
}) {
	const zh = useI18nStore((state) => state.language === "zh");
	const [sessionId, setSessionId] = useState("");
	useEffect(() => {
		if (!sessionId && status?.sessionId) setSessionId(status.sessionId);
	}, [sessionId, status?.sessionId]);
	const [appId, setAppId] = useState("");
	const [appSecret, setAppSecret] = useState("");
	useEffect(() => {
		if (status?.loginState === "ready") setAppSecret("");
	}, [status?.loginState]);
	const [pin, setPin] = useState("");
	const [busy, setBusy] = useState(false);
	const [error, setError] = useState<string | null>(null);
	const [confirm, setConfirm] = useState(false);
	const modelAvailable = (session: SessionMeta) =>
		Boolean(
			session.model &&
				models.some(
					(model) => model.provider === session.model?.provider && model.id === session.model?.modelId,
				),
		);
	const isPairing = ["loading", "scan", "pin", "verifying", "pair"].includes(status?.loginState ?? "");
	const hasValidSession = sessions.some(
		(row) => row.sessionId === sessionId && !row.archivedAt && modelAvailable(row),
	);
	const canStart = Boolean(status?.bound && !isPairing && hasValidSession);
	const act = async (method: string, args: Record<string, unknown> = {}) => {
		setBusy(true);
		setError(null);
		try {
			onStatus(await harness<{ channels: Record<string, ChannelStatus> }>(method, { ...args, channel }));
			if (method === "remoteSubmitPin") setPin("");
		} catch (failure) {
			setError(errText(failure) ?? String(failure));
		} finally {
			setBusy(false);
		}
	};
	return (
		<section
			aria-label={
				channel === "weixin" ? (zh ? "微信连接" : "Weixin connection") : zh ? "飞书连接" : "Feishu connection"
			}
			className="flex flex-col gap-4 rounded-xl border border-border p-4"
		>
			<h3 className="text-ui-13 font-medium text-ink">
				{channel === "weixin" ? (zh ? "微信" : "Weixin") : zh ? "飞书" : "Feishu"}
			</h3>
			<Select
				ariaLabel={zh ? "连接对话" : "Linked chat"}
				value={sessionId}
				onChange={setSessionId}
				disabled={busy || status?.stopping || Boolean(status?.executionSessionId)}
				options={[
					{ value: "", label: zh ? "选择要继续的对话" : "Choose a chat to continue" },
					...sessions
						.filter((row) => !row.archivedAt && row.model)
						.map((row) => ({
							value: row.sessionId,
							label: modelAvailable(row)
								? row.name || row.sessionId
								: `${row.name || row.sessionId} · ${zh ? "模型已失效" : "Model unavailable"}`,
							disabled: !modelAvailable(row),
						})),
				]}
			/>
			{channel === "feishu" && (
				<>
					<p className="text-ui-11 text-ink-faint">
						{zh
							? "在飞书开放平台启用应用机器人、配置 im.message.receive_v1 事件并选择长连接接收，发布应用后填写凭据。配对时向机器人私聊发送页面显示的 /pair 验证码。"
							: "Enable and publish a Feishu bot, subscribe to im.message.receive_v1 over a persistent connection, then enter its app credentials and send the displayed /pair code privately to the bot."}
					</p>
					<label className="text-ui-12 text-ink-dim">
						App ID
						<input
							className="mt-1 w-full rounded-lg border border-border bg-canvas p-2"
							value={appId}
							onChange={(event) => setAppId(event.target.value)}
						/>
					</label>
					<label className="text-ui-12 text-ink-dim">
						App Secret
						<input
							type="password"
							autoComplete="off"
							className="mt-1 w-full rounded-lg border border-border bg-canvas p-2"
							value={appSecret}
							onChange={(event) => setAppSecret(event.target.value)}
						/>
					</label>
				</>
			)}
			<div className="flex flex-wrap gap-2">
				<Button
					className="disabled:cursor-not-allowed disabled:opacity-40"
					disabled={
						busy ||
						!status ||
						status.bound ||
						status?.running ||
						status?.stopping ||
						isPairing ||
						(channel === "feishu" && (!appId || !appSecret || !sessionId))
					}
					onClick={() => void act("remoteBeginLogin", { channel, sessionId, appId, appSecret })}
				>
					{channel === "weixin"
						? zh
							? "微信扫码绑定"
							: "Bind Weixin with QR"
						: zh
							? "验证并配对飞书"
							: "Verify and pair Feishu"}
				</Button>
				<Button
					variant="primary"
					className="disabled:cursor-not-allowed"
					disabled={busy || status?.stopping || (!status?.running && !canStart)}
					onClick={() => (status?.running ? void act("remoteStop") : setConfirm(true))}
				>
					{status?.stopping
						? zh
							? "正在断开…"
							: "Disconnecting…"
						: status?.running
							? zh
								? "断开连接"
								: "Disconnect"
							: zh
								? "启动远程连接"
								: "Start remote connection"}
				</Button>
				{status?.running && sessionId !== status.sessionId && (
					<Button
						disabled={busy || !hasValidSession || Boolean(status.executionSessionId)}
						onClick={() => setConfirm(true)}
					>
						{zh ? "切换连接对话" : "Switch linked chat"}
					</Button>
				)}
				{status?.bound && (
					<Button
						className="disabled:cursor-not-allowed disabled:opacity-40"
						disabled={busy || status.running || status.stopping || isPairing}
						onClick={() => void act("remoteLogout", { channel })}
					>
						{zh ? "解除本机绑定" : "Remove local binding"}
					</Button>
				)}
			</div>
			{status && (
				<p className="text-ui-12 text-ink-dim">
					{status.running
						? zh
							? "远程连接已启动"
							: "Remote connection started"
						: status.stopping
							? zh
								? "正在断开；等待消息长轮询结束…"
								: "Disconnecting; waiting for long polling to finish…"
							: status.bound
								? zh
									? "账号已绑定，连接尚未启动"
									: "Account paired; connection stopped"
								: zh
									? "尚未绑定账号"
									: "Account not paired"}
				</p>
			)}
			{status?.running && status.currentSessionId && (
				<p className="text-ui-11 text-ink-faint">
					{zh ? "远端当前对话：" : "Current remote chat: "}
					{sessions.find((row) => row.sessionId === status.currentSessionId)?.name || status.currentSessionId}
					{status.executionSessionId && (zh ? " · 执行中，结束后可切换" : " · Running; switch when settled")}
				</p>
			)}
			{status?.loginState === "loading" && (
				<p className="text-ui-12 text-ink-faint">
					{zh ? "正在连接官方服务…" : "Connecting to the official service…"}
				</p>
			)}
			{status?.qrDataUrl && (
				<div className="rounded-xl border border-border p-4 text-center">
					<img
						className="mx-auto h-56 w-56 bg-white p-2"
						src={status.qrDataUrl}
						alt={zh ? "微信官方绑定二维码" : "Weixin binding QR code"}
					/>
					<p className="mt-2 text-ui-12 text-ink-dim">
						{zh
							? "使用本人微信扫码，并在手机上确认绑定。"
							: "Scan with your own Weixin account and confirm on the phone."}
					</p>
				</div>
			)}
			{status?.pairCode && (
				<div className="flex items-center justify-between gap-3 rounded-lg border border-border p-3 text-ui-13 text-ink">
					<p className="min-w-0">
						{zh ? "向飞书机器人私聊发送：" : "Send privately to your Feishu bot: "}
						<code>/pair {status.pairCode}</code>
					</p>
					<CopyButton key={status.pairCode} text={`/pair ${status.pairCode}`} />
				</div>
			)}
			{status?.loginState === "pin" && (
				<div className="flex gap-2">
					<input
						aria-label={zh ? "手机验证码" : "Phone PIN"}
						type="password"
						inputMode="numeric"
						autoComplete="one-time-code"
						value={pin}
						onChange={(event) => setPin(event.target.value)}
						className="min-w-0 flex-1 rounded-lg border border-border p-2"
					/>
					<Button disabled={busy || !pin} onClick={() => void act("remoteSubmitPin", { pin })}>
						{zh ? "提交手机验证码" : "Submit phone PIN"}
					</Button>
				</div>
			)}
			{(error || status?.error) && (
				<p role="alert" className="text-ui-12 text-err">
					{error || status?.error}
				</p>
			)}
			{status?.journal?.connections.map((row) => (
				<p key={row.account} className="text-ui-11 text-ink-faint">
					{row.account} · {row.status}
				</p>
			))}
			<p className="text-ui-11 leading-relaxed text-ink-faint">
				{zh
					? "仅已配对用户可触发任务。确认模式的审批会发到聊天中，用 /allow 审批编号 或 /deny 审批编号 回答；只有一项待审批时可直接发 /allow 或 /deny。/sessions 列出对话、/switch 对话ID 切换、/new 新建上下文、/status 查询、/cancel 停止。断开连接会停止本通道发起的当前任务。"
					: "Only paired users can trigger tasks. Confirm-mode approvals are sent to chat; reply with /allow request-id or /deny request-id. Use /sessions, /switch chat-id, /new, /status and /cancel. Disconnecting stops the current remote turn."}
			</p>
			{confirm && (
				<ConfirmDialog
					title={
						status?.running
							? zh
								? "切换远程连接的对话？"
								: "Switch the remotely linked chat?"
							: zh
								? "允许已配对账号继续此对话？"
								: "Allow the paired account to continue this chat?"
					}
					description={
						zh
							? "微信或飞书消息将作为这个对话的用户指令执行，可以触发工具和文件修改。沿用对话当前权限：完全通过模式不会逐项确认，确认模式会发送审批请求。"
							: "Messages become user instructions in this chat and can trigger tools and file changes. Its existing permission policy applies: Yolo skips individual approval; confirm mode sends approval requests."
					}
					confirmLabel={
						status?.running ? (zh ? "确认切换" : "Confirm switch") : zh ? "启动连接" : "Start connection"
					}
					cancelLabel={zh ? "取消" : "Cancel"}
					onConfirm={() => {
						setConfirm(false);
						void act(status?.running ? "remoteSwitchSession" : "remoteStart", { sessionId });
					}}
					onCancel={() => setConfirm(false)}
				/>
			)}
		</section>
	);
}
