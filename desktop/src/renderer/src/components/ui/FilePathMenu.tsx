import { environmentEntityRef, LOCAL_ENVIRONMENT } from "@vera/contracts";
import { getDesktopApi } from "../../api";
import { getExecutionApi } from "../../environment-api";
import { type MessageKey, useT } from "../../i18n";
import { errText } from "../../lib/error-text";
import { useToastsStore } from "../../stores/toasts";
import { CopyIcon, FileTextIcon, FolderIcon } from "../icons";
import { ContextMenu, type ContextMenuItem } from "./ContextMenu";
import type { MenuAnchor } from "./place-menu";

/**
 * 文件路径右键菜单（轮末文件行 / 变更侧栏文件卡共用）：
 * 打开文件（系统默认应用）/ 在系统文件管理器中显示（文案按平台）/ 复制路径。
 * 本机路径解析保留原生规则，历史外部身份不执行本机文件操作。
 * 路径不存在时三个动作各自 toast 报错（不做禁用态 —— 禁用态说不清原因）。
 */
export function FilePathMenu({
	target,
	cwd,
	anchor,
	onClose,
}: {
	/** 模型给出的原始路径文本（可能是相对路径） */
	target: string;
	fileUrl?: boolean;
	/** 会话工作目录（相对路径基准） */
	cwd: string | null;
	anchor: MenuAnchor;
	onClose: () => void;
}) {
	const t = useT();
	const environment = cwd ? environmentEntityRef(cwd).environment : LOCAL_ENVIRONMENT;
	const reveal = revealCopy(getDesktopApi().platform);

	const run = async (action: "open" | "reveal" | "copy") => {
		try {
			if (environment.kind !== "local") throw new Error(t("environment.unavailable"));
			if (action === "copy") {
				// 复制的是解析后的绝对路径（原样复制相对路径对用户没用）
				const resolved = await getExecutionApi(environment).resolvePath({ target, cwd });
				await navigator.clipboard.writeText(resolved);
				// 剪贴板不可见，给一条 info 反馈（详情 = 绝对路径）
				useToastsStore.getState().push("info", "toast.pathCopied", resolved);
				return;
			}
			if (action === "open") await getDesktopApi().openPath({ target, cwd });
			else await getDesktopApi().revealPath({ target, cwd });
		} catch (error) {
			console.error("文件路径操作失败", { action, target, error });
			const key =
				action === "copy"
					? "toast.pathCopyFailed"
					: action === "reveal"
						? reveal.failed
						: "toast.pathOpenFailed";
			useToastsStore.getState().push("error", key, errText(error));
		}
	};

	const items: ContextMenuItem[] = [
		{
			key: "open",
			label: t("pathMenu.open"),
			icon: <FileTextIcon size={13} />,
			onSelect: () => void run("open"),
		},
		{
			key: "reveal",
			label: t(reveal.label),
			icon: <FolderIcon size={13} />,
			onSelect: () => void run("reveal"),
		},
		{
			key: "copy",
			label: t("pathMenu.copyPath"),
			icon: <CopyIcon size={13} />,
			onSelect: () => void run("copy"),
		},
	];

	return <ContextMenu anchor={anchor} items={items} onClose={onClose} />;
}

/** 「在系统文件管理器中显示」按平台取词：macOS 访达 / Windows 文件资源管理器 / 其他通用文件夹 */
export function revealCopy(platform: string): { label: MessageKey; failed: MessageKey } {
	if (platform === "darwin") return { label: "pathMenu.reveal", failed: "toast.pathRevealFailed" };
	if (platform === "win32")
		return { label: "pathMenu.revealExplorer", failed: "toast.pathRevealFailedExplorer" };
	return { label: "pathMenu.revealFolder", failed: "toast.pathRevealFailedFolder" };
}
