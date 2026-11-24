import { useT } from "../../i18n";
import { COMPOSER_FOCUS_EVENT } from "../../stores/drafts";
import { useSessionsStore } from "../../stores/sessions";
import { navigateWorkspacePage, useWorkspacePageStore } from "../../stores/workspace-page";
import { ClockIcon, EditIcon, PuzzleIcon } from "../icons";

/**
 * 左栏固定头区：新任务、插件和定时任务入口，位于会话列表滚动容器之外。
 * 顶部入口与顶栏「＋」同语义：从真实会话进入时复用当前项目/模型等配置；已在 draft 页则原样保留。
 */
export function SidebarHeader() {
	const t = useT();
	const page = useWorkspacePageStore((s) => s.page);
	const activateNewSessionDraft = useSessionsStore((s) => s.activateNewSessionDraft);

	const openNewSession = () => {
		activateNewSessionDraft();
		// 等新会话页 Composer 挂载后再聚焦；同步派发会被刚卸载的真实会话 Composer 接走。
		requestAnimationFrame(() => window.dispatchEvent(new CustomEvent(COMPOSER_FOCUS_EVENT)));
	};

	return (
		<div className="flex shrink-0 flex-col gap-1 px-2.5 pt-2.5 pb-2">
			<button
				type="button"
				className="flex h-9 w-full items-center gap-2 rounded-lg px-2 text-ui-14 font-medium text-ink-2 transition-colors hover:bg-hover hover:text-ink"
				onClick={openNewSession}
			>
				<EditIcon size={17} className="shrink-0" />
				<span>{t("sidebar.newSession")}</span>
			</button>
			{(
				[
					{ id: "plugins", Icon: PuzzleIcon },
					{ id: "taskboard", Icon: EditIcon },
					{ id: "scheduled", Icon: ClockIcon },
				] as const
			).map(({ id, Icon }) => (
				<button
					key={id}
					type="button"
					aria-current={page === id ? "page" : undefined}
					className={`flex h-9 w-full items-center gap-2 rounded-lg px-2 text-ui-14 outline-none transition-colors hover:bg-hover hover:text-ink focus-visible:ring-2 focus-visible:ring-ink-faint ${page === id ? "bg-hover font-medium text-ink" : "text-ink-dim"}`}
					onClick={() => navigateWorkspacePage(id)}
				>
					<Icon size={17} />
					<span>{t(`sidebar.${id}`)}</span>
				</button>
			))}
		</div>
	);
}
