// @vitest-environment happy-dom
import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import {
	PerformanceOverview,
	PerformanceRankings,
} from "../../../../../../src/renderer/src/components/settings/statistics/PerformanceOverview";
import { UsageChart } from "../../../../../../src/renderer/src/components/settings/statistics/UsageChart";
import type { UsageData } from "../../../../../../src/renderer/src/components/settings/statistics/usage-types";
import {
	cacheLinePath,
	formatUsageCount,
	type UsageDay,
} from "../../../../../../src/renderer/src/components/settings/statistics/usage-types";
import { useI18nStore } from "../../../../../../src/renderer/src/i18n";

let host: HTMLDivElement;
let root: Root;
const rows: UsageDay[] = [
	{ date: "2026-11-21", input: 80, output: 20, totalTokens: 100, requests: 2, cacheHitRate: 0 },
	{ date: "2026-11-22", input: 0, output: 0, totalTokens: 0, requests: 0, cacheHitRate: null },
	{ date: "2026-11-23", input: 800, output: 200, totalTokens: 1000, requests: 4, cacheHitRate: 0.75 },
];

beforeEach(() => {
	vi.stubGlobal("IS_REACT_ACT_ENVIRONMENT", true);
	useI18nStore.setState({ language: "zh" });
	host = document.createElement("div");
	document.body.append(host);
	root = createRoot(host);
});
afterEach(async () => {
	await act(() => root.unmount());
	host.remove();
	vi.unstubAllGlobals();
});

it("keeps missing cache observations distinct from zero and supports keyboard inspection and series toggles", async () => {
	await act(() => root.render(<UsageChart rows={rows} />));
	const chart = host.querySelector<HTMLElement>('[role="slider"]');
	if (!chart) throw new Error("Missing chart navigation");
	await act(() => chart.focus());
	expect(host.querySelector('[role="tooltip"]')?.textContent).toContain("75.0%");
	await act(() => chart.dispatchEvent(new KeyboardEvent("keydown", { key: "ArrowLeft", bubbles: true })));
	expect(host.querySelector('[role="tooltip"]')?.textContent).toContain("2026-11-22");
	expect(host.querySelector('[role="tooltip"]')?.textContent).toContain("—");
	await act(() => chart.dispatchEvent(new KeyboardEvent("keydown", { key: "Home", bubbles: true })));
	expect(host.querySelector('[role="tooltip"]')?.textContent).toContain("0.0%");
	const toggle = [...host.querySelectorAll("button")].find((button) =>
		button.textContent?.includes("缓存命中率"),
	);
	if (!toggle) throw new Error("Missing cache series toggle");
	await act(() => toggle.click());
	expect(toggle.getAttribute("aria-pressed")).toBe("false");
	expect(host.querySelector('path[stroke="var(--stats-cache)"]')).toBeNull();
	await act(() => chart.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", bubbles: true })));
	expect(host.querySelector('[role="tooltip"]')).toBeNull();
});

it("uses decimal k/M units and breaks the cache line across unreported days", () => {
	expect([999, 1000, 744936, 999999, 1234567].map(formatUsageCount)).toEqual([
		"999",
		"1k",
		"744.9k",
		"1M",
		"1.2M",
	]);
	expect(
		cacheLinePath(
			rows,
			(index) => index * 10,
			(rate) => rate * 100,
		),
	).toBe("M0,0  M20,75");
});

it("keeps legacy missing performance unknown and exposes sample cleaning details on focus", async () => {
	const data: UsageData = {
		heatmap: rows,
		trend: rows,
		projects: [],
		models: [],
		modelLabels: {},
		totals: {
			input: 880,
			output: 220,
			totalTokens: 1100,
			requests: 6,
			cacheRead: 600,
			cacheInput: 880,
			cacheResponses: 6,
			cacheHitRate: 600 / 880,
		},
	};
	await act(() => root.render(<PerformanceOverview data={data} />));
	expect(host.textContent?.match(/—/g)?.length).toBe(3);
	expect(host.textContent).not.toContain("NaN");
	await act(() => host.querySelectorAll("button")[1]?.focus());
	expect(document.querySelector('[role="tooltip"]')?.textContent).toContain("仅计正常完成");
	await act(() => root.render(<PerformanceRankings data={data} />));
	expect(host.textContent).toContain("暂无已记录工具调用");
	expect(host.textContent).toContain("暂无已记录错误");
});
