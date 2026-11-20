import { useEffect, useId, useRef, useState } from "react";
import { useT } from "../../i18n";
import { useProjectsStore } from "../../stores/projects";
import { useUiPreferencesStore } from "../../stores/ui-preferences";
import { CloseIcon, SearchIcon } from "../icons";
import { Tooltip } from "../ui/Tooltip";

/** 顶栏搜索入口：展开时聚焦输入并显示侧栏结果；收起保留筛选，Escape 清空并返回按钮。 */
export function SessionSearch() {
	const t = useT();
	const search = useProjectsStore((state) => state.search);
	const setSearch = useProjectsStore((state) => state.setSearch);
	const [isOpen, setIsOpen] = useState(false);
	const inputId = useId();
	const inputRef = useRef<HTMLInputElement>(null);
	const buttonRef = useRef<HTMLButtonElement>(null);

	useEffect(() => {
		if (isOpen) {
			inputRef.current?.focus();
			inputRef.current?.select();
		}
	}, [isOpen]);

	return (
		<search
			aria-label={t("sidebar.search")}
			className="no-drag flex shrink-0 items-center gap-1"
			onBlur={(event) => {
				if (!event.currentTarget.contains(event.relatedTarget)) setIsOpen(false);
			}}
		>
			<Tooltip label={t("sidebar.search")} align="start">
				<button
					ref={buttonRef}
					type="button"
					className={`shrink-0 rounded-lg p-1.5 transition-colors ${
						isOpen || search ? "bg-hover text-ink" : "text-ink-dim hover:bg-hover hover:text-ink"
					}`}
					onClick={() => {
						if (!isOpen) {
							const preferences = useUiPreferencesStore.getState();
							if (preferences.sidebarCollapsed) preferences.toggleSidebarCollapsed();
						}
						setIsOpen(!isOpen);
					}}
					aria-label={t("sidebar.search")}
					aria-expanded={isOpen}
					aria-controls={isOpen ? inputId : undefined}
				>
					<SearchIcon size={16} />
				</button>
			</Tooltip>
			{isOpen && (
				<div className="flex h-8 w-[min(220px,35vw)] min-w-0 items-center rounded-lg bg-hover px-2">
					<input
						ref={inputRef}
						id={inputId}
						type="search"
						value={search}
						onChange={(event) => setSearch(event.target.value)}
						onKeyDown={(event) => {
							if (event.key !== "Escape" || event.nativeEvent.isComposing) return;
							event.preventDefault();
							event.stopPropagation();
							setSearch("");
							setIsOpen(false);
							buttonRef.current?.focus();
						}}
						aria-label={t("sidebar.search")}
						placeholder={t("sidebar.search")}
						className="min-w-0 flex-1 bg-transparent text-ui-13 text-ink-2 outline-none placeholder:text-ink-faint [&::-webkit-search-cancel-button]:hidden"
					/>
					{search && (
						<button
							type="button"
							className="rounded p-1 text-ink-faint hover:text-ink"
							onClick={() => {
								setSearch("");
								inputRef.current?.focus();
							}}
							aria-label={t("sidebar.clearSearch")}
						>
							<CloseIcon size={12} />
						</button>
					)}
				</div>
			)}
		</search>
	);
}
