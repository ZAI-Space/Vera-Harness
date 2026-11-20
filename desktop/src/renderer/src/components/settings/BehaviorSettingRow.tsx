// Adapted layout from PI-Desktop settings/primitives.tsx, LGPL-3.0-only.
import type { ReactNode } from "react";
import { HintIcon } from "./HintIcon";

/** 行标题与胶囊控件在同一层级，解释通过问号展示，窄窗允许控件换行。 */
export function BehaviorSettingRow({
	title,
	hint,
	children,
}: {
	title: string;
	hint?: string;
	children: ReactNode;
}) {
	return (
		<div className="flex min-h-16 flex-wrap items-center justify-between gap-3 rounded-xl bg-hover/50 px-4 py-3">
			<div className="flex min-w-0 items-center gap-1.5">
				<h3 className="text-ui-13 font-medium text-ink-2">{title}</h3>
				{hint && <HintIcon label={hint} />}
			</div>
			<div className="max-w-full">{children}</div>
		</div>
	);
}
