import type { ButtonHTMLAttributes, ReactNode } from "react";
import { useT } from "../../i18n";
import { SearchIcon } from "../icons";

/** 工作区页面共用结构：固定页头，内容独立滚动，沿用应用语义颜色与字号。 */
export function WorkspacePage({
	title,
	description,
	actions,
	children,
}: {
	title: string;
	description: string;
	actions?: ReactNode;
	children: ReactNode;
}) {
	const t = useT();
	return (
		<section className="min-w-0 flex-1 overflow-y-auto px-5 py-8 md:px-9" aria-label={title}>
			<div className="mx-auto flex max-w-[1040px] flex-col gap-7">
				<header className="flex flex-wrap items-start justify-between gap-4">
					<div>
						<h1 className="text-ui-28 font-semibold tracking-tight text-ink">{title}</h1>
						<p className="mt-2 text-ui-13 leading-relaxed text-ink-dim">{description}</p>
					</div>
					<div className="flex items-center gap-2">{actions}</div>
				</header>
				<p role="status" className="text-ui-12 leading-relaxed text-ink-faint">
					{t("workspace.preview")}
				</p>
				{children}
			</div>
		</section>
	);
}

/** 轻量操作按钮；所有异步提交的 busy/disabled 由调用方持有。 */
export function WorkspaceButton({
	children,
	className = "",
	...props
}: ButtonHTMLAttributes<HTMLButtonElement>) {
	return (
		<button
			type="button"
			className={`inline-flex min-h-8 items-center justify-center gap-2 rounded-lg px-3 py-2 text-ui-13 font-medium text-ink-2 outline-none transition-colors hover:bg-hover hover:text-ink focus-visible:ring-2 focus-visible:ring-ink-faint disabled:cursor-not-allowed disabled:opacity-40 ${className}`}
			{...props}
		>
			{children}
		</button>
	);
}

/** 受控搜索；清空会交回原始列表，搜索文本不参与任何执行请求。 */
export function WorkspaceSearch({
	value,
	onChange,
	label,
}: {
	value: string;
	onChange: (value: string) => void;
	label: string;
}) {
	return (
		<label className="flex min-w-0 items-center gap-2 rounded-lg bg-hover px-3 py-2 text-ink-dim">
			<SearchIcon size={14} />
			<input
				type="search"
				value={value}
				onChange={(event) => onChange(event.target.value)}
				placeholder={label}
				aria-label={label}
				className="w-full min-w-0 bg-transparent text-ui-13 text-ink outline-none placeholder:text-ink-faint"
			/>
		</label>
	);
}

/** 空列表和搜索无结果共用的内容容器，操作由所属页面提供。 */
export function WorkspaceEmpty({
	title,
	description,
	children,
}: {
	title: string;
	description?: string;
	children?: ReactNode;
}) {
	return (
		<div className="flex min-h-52 flex-col items-center justify-center gap-3 rounded-xl bg-surface px-6 py-10 text-center shadow-soft">
			<h2 className="text-ui-16 font-medium text-ink">{title}</h2>
			{description && <p className="max-w-md text-ui-13 leading-relaxed text-ink-dim">{description}</p>}
			{children && <div className="mt-2 flex flex-wrap justify-center gap-2">{children}</div>}
		</div>
	);
}

export const WORKSPACE_INPUT_CLASS =
	"w-full min-w-0 rounded-lg border border-border bg-transparent px-3 py-2 text-ui-13 text-ink outline-none placeholder:text-ink-faint focus:border-ink-faint";

/** 表单字段保持标签与控件关联，错误交由表单统一展示。 */
export function WorkspaceField({
	label,
	htmlFor,
	children,
}: {
	label: string;
	htmlFor: string;
	children: ReactNode;
}) {
	return (
		<div className="flex min-w-0 flex-col gap-2">
			<label htmlFor={htmlFor} className="text-ui-13 font-medium text-ink-2">
				{label}
			</label>
			{children}
		</div>
	);
}
