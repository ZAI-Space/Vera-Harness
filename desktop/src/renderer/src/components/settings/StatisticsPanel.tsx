import { useCallback, useEffect, useRef, useState } from "react";
import { harness } from "../../harness-api";
import { useT } from "../../i18n";
import { errText } from "../../lib/error-text";
import { Button } from "../ui/Button";
import { Select } from "../ui/Select";
import { PerformanceOverview, PerformanceRankings } from "./statistics/PerformanceOverview";
import { UsageChart } from "./statistics/UsageChart";
import { UsageHeatmap } from "./statistics/UsageHeatmap";
import { formatUsageCount, type UsageData, type UsageDay } from "./statistics/usage-types";

/** One model/project/date scope, with a separate request cohort affecting the token/cache chart only. */
export function StatisticsPanel() {
	const t = useT();
	const [data, setData] = useState<UsageData | null>(null);
	const [model, setModel] = useState("");
	const [project, setProject] = useState("");
	const [cacheGroup, setCacheGroup] = useState("all");
	const [days, setDays] = useState(7);
	const [loading, setLoading] = useState(true);
	const [error, setError] = useState<string | null>(null);
	const generation = useRef(0);
	const load = useCallback(async () => {
		const request = ++generation.current;
		setLoading(true);
		try {
			const result = await harness<UsageData>("getUsageStatistics", {
				model,
				project,
				days,
				cacheGroup,
				timezone: Intl.DateTimeFormat().resolvedOptions().timeZone,
			});
			if (request === generation.current) {
				setData(result);
				setError(null);
			}
		} catch (failure) {
			if (request === generation.current) setError(errText(failure) ?? String(failure));
		} finally {
			if (request === generation.current) setLoading(false);
		}
	}, [model, project, days, cacheGroup]);
	useEffect(() => {
		void load();
		const timer = setInterval(() => void load(), 15000);
		return () => {
			clearInterval(timer);
			generation.current++;
		};
	}, [load]);
	const summary = (row: UsageDay) =>
		t("usageStatistics.daySummary", {
			date: row.date,
			tokens: row.totalTokens.toLocaleString(),
			requests: row.requests,
		});
	return (
		<section aria-label={t("usageStatistics.title")} className="flex flex-col gap-5">
			<div className="grid grid-cols-2 items-center gap-2 sm:grid-cols-[1fr_1fr_136px_auto]">
				<Select
					ariaLabel={t("usageStatistics.model")}
					value={model}
					onChange={setModel}
					options={[
						{ value: "", label: t("usageStatistics.allModels") },
						...(data?.models ?? []).map((value) => ({ value, label: data?.modelLabels[value] ?? value })),
					]}
				/>
				<Select
					ariaLabel={t("usageStatistics.project")}
					value={project}
					onChange={setProject}
					options={[
						{ value: "", label: t("usageStatistics.allProjects") },
						...(data?.projects ?? []).map((value) => ({
							value,
							label: value.split(/[\\/]/).filter(Boolean).at(-1) || value,
							description: value,
						})),
					]}
				/>
				<Select
					ariaLabel={t("usageStatistics.range")}
					value={String(days)}
					onChange={(value) => setDays(Number(value))}
					options={[7, 30, 90, 180].map((value) => ({
						value: String(value),
						label: t("usageStatistics.days", { days: value }),
					}))}
				/>
				<Button disabled={loading} onClick={() => void load()}>
					{t("usageStatistics.refresh")}
				</Button>
			</div>
			{error && (
				<p role="alert" className="text-ui-12 text-err">
					{error}
				</p>
			)}
			{!data && loading && (
				<p role="status" className="py-12 text-center text-ui-12 text-ink-faint">
					{t("usageStatistics.loading")}
				</p>
			)}
			{data && (
				<>
					<PerformanceOverview data={data} />
					<section
						className="rounded-2xl border border-border bg-surface p-4 sm:p-5"
						aria-label={t("usageStatistics.trend")}
					>
						<div className="flex flex-wrap items-center justify-between gap-3">
							<h3 className="text-ui-13 font-medium text-ink">{t("usageStatistics.trend")}</h3>
							<fieldset
								className="flex rounded-lg bg-hover p-0.5"
								aria-label={t("usageStatistics.cacheGroup")}
							>
								{(["all", "first", "continued"] as const).map((value) => (
									<button
										key={value}
										type="button"
										aria-pressed={cacheGroup === value}
										onClick={() => setCacheGroup(value)}
										className={`rounded-md px-2.5 py-1.5 text-ui-11 transition-colors focus-visible:outline-2 focus-visible:outline-violet-400 ${cacheGroup === value ? "bg-surface text-ink shadow-sm" : "text-ink-faint hover:text-ink-dim"}`}
									>
										{t(`usageStatistics.group_${value}`)}
									</button>
								))}
							</fieldset>
						</div>
						<div className="mt-3 flex flex-wrap items-center justify-between gap-x-4 gap-y-1 text-ui-11 text-ink-faint">
							<span>
								{t("usageStatistics.input")}{" "}
								<span className="tabular-nums text-ink-dim">{formatUsageCount(data.totals.input)}</span>{" "}
								<span className="mx-2 text-border-strong">/</span> {t("usageStatistics.output")}{" "}
								<span className="tabular-nums text-ink-dim">{formatUsageCount(data.totals.output)}</span>
							</span>
						</div>
						<UsageChart rows={data.trend} />
						<p className="mt-3 text-ui-10 leading-relaxed text-ink-faint">
							{t("usageStatistics.cacheColdHint")}
						</p>
						<div className="mt-2 flex flex-wrap justify-between gap-1 text-ui-10 text-ink-faint">
							<span>
								{t("usageStatistics.coverage", {
									reported: data.totals.cacheResponses,
									total: data.totals.requests,
								})}
							</span>
							{data.totals.cacheHitRate !== null && (
								<span title={t("usageStatistics.cacheHint")}>
									{t("usageStatistics.cacheBreakdown", {
										cached: formatUsageCount(data.totals.cacheRead),
										input: formatUsageCount(data.totals.cacheInput),
									})}
								</span>
							)}
						</div>
						{cacheGroup !== "all" && (
							<p className="mt-1 text-ui-10 text-ink-faint">{t("usageStatistics.cohortHint")}</p>
						)}
						{!data.totals.requests && (
							<p className="mt-3 text-center text-ui-11 text-ink-faint">{t("usageStatistics.noData")}</p>
						)}
					</section>
					<PerformanceRankings data={data} />
					<section className="rounded-xl border border-border p-4" aria-label={t("usageStatistics.heatmap")}>
						<div className="mb-3 flex items-center justify-between">
							<h3 className="text-ui-12 font-medium text-ink">{t("usageStatistics.heatmap")}</h3>
							<span className="text-ui-10 text-ink-faint">
								{t("usageStatistics.less")}{" "}
								<span className="mx-1.5 inline-block h-2 w-14 rounded-sm bg-gradient-to-r from-violet-100 to-violet-500" />{" "}
								{t("usageStatistics.more")}
							</span>
						</div>
						<UsageHeatmap rows={data.heatmap} label={t("usageStatistics.heatmap")} summary={summary} />
					</section>
					<p className="text-ui-10 leading-relaxed text-ink-faint">
						{t("usageStatistics.performanceHint")} {t("usageStatistics.hint")}
					</p>
				</>
			)}
		</section>
	);
}
