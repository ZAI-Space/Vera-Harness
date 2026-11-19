import { useEffect, useRef } from "react";
import { useT } from "../../i18n";
import { SearchIcon } from "../icons";

/** @ 文件补全面板：顶部搜索常驻，列表独立滚动；筛选与引用回调由 Composer 驱动。 */
export function AtMenu({
	files,
	query,
	onQueryChange,
	onKeyDown,
	selectedIndex,
	onSelectedIndexChange,
	onPick,
}: {
	files: string[];
	/** 搜索词与正文 @ 后的输入同步；面板内编辑不会修改待发送正文。 */
	query: string;
	onQueryChange: (query: string) => void;
	onKeyDown: (event: React.KeyboardEvent<HTMLInputElement>) => boolean;
	/** 当前选中项下标 */
	selectedIndex: number;
	onSelectedIndexChange: (index: number) => void;
	onPick: (path: string) => void;
}) {
	const t = useT();
	const listRef = useRef<HTMLDivElement>(null);
	const active = Math.min(selectedIndex, Math.max(files.length - 1, 0));

	// 选中项超出可视区域时跟随滚动（键盘上下移动/鼠标悬停均生效）
	useEffect(() => {
		const container = listRef.current;
		if (!container) return;
		const item = container.querySelector<HTMLElement>(`[data-index="${active}"]`);
		if (!item) return;
		const cRect = container.getBoundingClientRect();
		const iRect = item.getBoundingClientRect();
		if (iRect.top < cRect.top) {
			container.scrollTop -= cRect.top - iRect.top;
		} else if (iRect.bottom > cRect.bottom) {
			container.scrollTop += iRect.bottom - cRect.bottom;
		}
	}, [active]);

	return (
		<div className="mb-1.5 flex max-h-64 flex-col overflow-hidden rounded-lg border border-border bg-surface shadow-pop">
			<div className="flex shrink-0 items-center gap-2 px-3 py-2">
				<SearchIcon size={14} className="shrink-0 text-ink-faint" />
				<input
					type="search"
					value={query}
					onChange={(event) => onQueryChange(event.target.value)}
					onKeyDown={onKeyDown}
					aria-label={t("at.search")}
					placeholder={t("at.search")}
					className="min-w-0 flex-1 bg-transparent text-ui-13 text-ink-2 outline-none placeholder:text-ink-faint"
				/>
			</div>
			<div ref={listRef} className="min-h-0 overflow-y-auto">
				{files.length === 0 && (
					<p className="py-2 text-center text-ui-12 text-ink-faint">{t("at.noMatch")}</p>
				)}
				{files.map((path, index) => {
					const isDir = path.endsWith("/");
					const slash = path.lastIndexOf("/", path.length - 2);
					const base = isDir ? path.slice(slash + 1, -1) : path.slice(slash + 1);
					const dir = isDir ? path.slice(0, slash + 1) : slash === -1 ? "" : path.slice(0, slash + 1);
					return (
						<button
							key={path}
							type="button"
							data-index={index}
							className={`flex w-full items-center gap-2 px-3 py-1.5 text-left text-ui-13 transition-colors ${
								index === active ? "bg-hover text-ink" : "text-ink-2 hover:bg-hover"
							}`}
							onMouseEnter={() => onSelectedIndexChange(index)}
							onClick={() => onPick(path)}
						>
							<span className="shrink-0 font-mono text-ink-faint">{isDir ? "▸" : "·"}</span>
							<span className="min-w-0 flex-1 truncate font-mono">
								<span className="text-ink-faint">{dir}</span>
								<span className="text-ink-2">{base}</span>
								{isDir && <span className="text-ink-faint">/</span>}
							</span>
						</button>
					);
				})}
			</div>
		</div>
	);
}
