/** Statistics are provider receipts and completed task observations; missing measurements remain null. */
export interface UsageDay {
	date: string;
	input: number;
	output: number;
	totalTokens: number;
	requests: number;
	cacheHitRate: number | null;
}

export interface PerformanceData {
	tasks: number;
	completed: number;
	failed: number;
	cancelled: number;
	completionRate: number | null;
	firstResponseMeanMs: number | null;
	firstResponseSamples: number;
	firstResponseExcluded: number;
	retryMean: number | null;
	retryRawMean: number | null;
	retrySamples: number;
	retryExcluded: number;
	tools: { name: string; calls: number; failures: number; meanMs: number | null }[];
	errors: { name: string; count: number }[];
}

export const EMPTY_PERFORMANCE: PerformanceData = {
	tasks: 0,
	completed: 0,
	failed: 0,
	cancelled: 0,
	completionRate: null,
	firstResponseMeanMs: null,
	firstResponseSamples: 0,
	firstResponseExcluded: 0,
	retryMean: null,
	retryRawMean: null,
	retrySamples: 0,
	retryExcluded: 0,
	tools: [],
	errors: [],
};

export interface UsageData {
	heatmap: UsageDay[];
	trend: UsageDay[];
	projects: string[];
	models: string[];
	modelLabels: Record<string, string>;
	performance?: PerformanceData;
	overviewTotals?: { input: number; output: number; totalTokens: number; requests: number };
	totals: {
		input: number;
		output: number;
		totalTokens: number;
		requests: number;
		cacheRead: number;
		cacheInput: number;
		cacheResponses: number;
		cacheHitRate: number | null;
	};
}

/** Stable decimal k/M units across interface languages, with the full value kept in tooltips. */
export function formatUsageCount(value: number): string {
	if (value < 1000) return String(Math.round(value));
	if (value >= 999_950) return `${Number((value / 1_000_000).toFixed(1))}M`;
	return `${Number((value / 1000).toFixed(1))}k`;
}

export function formatDuration(milliseconds: number | null): string {
	if (milliseconds === null) return "—";
	return milliseconds < 1000 ? `${Math.round(milliseconds)} ms` : `${(milliseconds / 1000).toFixed(1)} s`;
}

/** Null cache observations break the line rather than being rendered as a zero-percent hit. */
export function cacheLinePath(
	rows: UsageDay[],
	x: (index: number) => number,
	y: (rate: number) => number,
): string {
	let previousKnown = false;
	return rows
		.map((row, index) => {
			if (row.cacheHitRate == null) {
				previousKnown = false;
				return "";
			}
			const point = `${previousKnown ? "L" : "M"}${x(index)},${y(row.cacheHitRate)}`;
			previousKnown = true;
			return point;
		})
		.join(" ");
}
