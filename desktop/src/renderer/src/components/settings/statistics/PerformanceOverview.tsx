import { type ReactNode, useId, useState } from "react";
import { useT } from "../../../i18n";
import { Tooltip } from "../../ui/Tooltip";
import { EMPTY_PERFORMANCE, formatDuration, formatUsageCount, type UsageData } from "./usage-types";

/** Small overview values disclose their sample/exclusion policy on hover and keyboard focus. */
export function PerformanceOverview({ data }: { data: UsageData }) {
	const t = useT();
	const metrics = data.performance ?? EMPTY_PERFORMANCE;
	const totals = data.overviewTotals ?? data.totals;
	const items = [
		{
			label: t("usageStatistics.total"),
			value: formatUsageCount(totals.totalTokens),
			detail: t("usageStatistics.requestCount", { count: totals.requests }),
			hint: `${t("usageStatistics.input")} ${totals.input.toLocaleString()} · ${t("usageStatistics.output")} ${totals.output.toLocaleString()}`,
		},
		{
			label: t("usageStatistics.firstResponse"),
			value: formatDuration(metrics.firstResponseMeanMs),
			detail: t("usageStatistics.samples", { count: metrics.firstResponseSamples }),
			hint: t("usageStatistics.firstResponseHint", { excluded: metrics.firstResponseExcluded }),
		},
		{
			label: t("usageStatistics.averageRetries"),
			value: metrics.retryMean === null ? "—" : metrics.retryMean.toFixed(2),
			detail: t("usageStatistics.samples", { count: metrics.retrySamples }),
			hint: t("usageStatistics.retryHint", {
				excluded: metrics.retryExcluded,
				raw: metrics.retryRawMean === null ? "—" : metrics.retryRawMean.toFixed(2),
			}),
		},
		{
			label: t("usageStatistics.completionRate"),
			value: metrics.completionRate === null ? "—" : `${(metrics.completionRate * 100).toFixed(1)}%`,
			detail: t("usageStatistics.completedCount", { completed: metrics.completed, total: metrics.tasks }),
			hint: t("usageStatistics.completionHint", { failed: metrics.failed, cancelled: metrics.cancelled }),
		},
	];
	return (
		<div className="grid grid-cols-2 divide-x divide-border/70 rounded-xl border border-border bg-hover/25 sm:grid-cols-4">
			{items.map((item) => (
				<DetailsHint key={item.label} label={item.hint} className="px-4 py-4">
					<span className="block text-ui-11 text-ink-dim">{item.label}</span>
					<span className="my-1.5 block text-ui-23 leading-tight font-semibold tracking-tight tabular-nums text-ink">
						{item.value}
					</span>
					<span className="block text-ui-10 tabular-nums text-ink-faint">{item.detail}</span>
				</DetailsHint>
			))}
		</div>
	);
}

/** Tool call frequency and safe error categories share the performance filters, never the cache cohort. */
export function PerformanceRankings({ data }: { data: UsageData }) {
	const t = useT();
	const metrics = data.performance ?? EMPTY_PERFORMANCE;
	const maximum = Math.max(1, ...metrics.tools.map((row) => row.calls));
	return (
		<div className="grid gap-3 sm:grid-cols-2">
			<section className="rounded-xl border border-border p-4">
				<h3 className="text-ui-12 font-medium text-ink">{t("usageStatistics.toolsRanking")}</h3>
				{metrics.tools.length ? (
					<ol className="mt-4 space-y-3.5">
						{metrics.tools.map((row) => (
							<li key={row.name}>
								<DetailsHint
									label={t("usageStatistics.toolDetail", {
										failures: row.failures,
										duration: formatDuration(row.meanMs),
									})}
								>
									<span className="mb-1.5 flex items-center justify-between gap-3 text-ui-11">
										<span className="truncate text-ink-dim">{row.name}</span>
										<span className="tabular-nums text-ink">{row.calls}</span>
									</span>
									<span className="block h-1 rounded-full bg-hover">
										<span
											className="block h-1 rounded-full bg-violet-500/60"
											style={{ width: `${(row.calls / maximum) * 100}%` }}
										/>
									</span>
								</DetailsHint>
							</li>
						))}
					</ol>
				) : (
					<p className="py-8 text-center text-ui-11 text-ink-faint">{t("usageStatistics.noTools")}</p>
				)}
			</section>
			<section className="rounded-xl border border-border p-4">
				<h3 className="text-ui-12 font-medium text-ink">{t("usageStatistics.errorsRanking")}</h3>
				{metrics.errors.length ? (
					<ol className="mt-3 divide-y divide-border/50">
						{metrics.errors.map((row) => (
							<li key={row.name} className="flex items-center justify-between gap-3 py-2.5 text-ui-11">
								<span className="min-w-0 truncate text-ink-dim" title={row.name}>
									{errorLabel(row.name, t)}
								</span>
								<span className="rounded bg-red-500/8 px-2 py-0.5 tabular-nums text-err">{row.count}</span>
							</li>
						))}
					</ol>
				) : (
					<p className="py-8 text-center text-ui-11 text-ink-faint">{t("usageStatistics.noErrors")}</p>
				)}
			</section>
		</div>
	);
}

function errorLabel(name: string, t: ReturnType<typeof useT>): string {
	if (/Timeout/.test(name)) return t("usageStatistics.timeoutError");
	if (/RateLimit/.test(name)) return t("usageStatistics.rateLimitError");
	if (/Connection/.test(name)) return t("usageStatistics.connectionError");
	if (/Authentication|PermissionDenied/.test(name)) return t("usageStatistics.authError");
	if (/BadRequest|UnsupportedParams|ContextWindow/.test(name)) return t("usageStatistics.parameterError");
	if (name === "ToolError") return t("usageStatistics.toolError");
	if (name === "FormatRetry") return t("usageStatistics.formatRetry");
	if (name === "WorkerFailed") return t("usageStatistics.workerError");
	return name;
}

/** Reuse the portal tooltip so a focused/hovered metric cannot overflow the settings scroller. */
function DetailsHint({
	label,
	className = "",
	children,
}: {
	label: string;
	className?: string;
	children: ReactNode;
}) {
	const [open, setOpen] = useState(false);
	const id = useId();
	return (
		<Tooltip label={label} open={open} id={id} className="min-w-0 w-full">
			<button
				type="button"
				aria-describedby={open ? id : undefined}
				className={`w-full min-w-0 text-left outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-violet-400/60 ${className}`}
				onPointerEnter={() => setOpen(true)}
				onPointerLeave={() => setOpen(false)}
				onFocus={() => setOpen(true)}
				onBlur={() => setOpen(false)}
				onClick={() => setOpen(true)}
			>
				{children}
			</button>
		</Tooltip>
	);
}
