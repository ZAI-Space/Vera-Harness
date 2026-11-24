import { useId, useState } from "react";
import { useT } from "../../../i18n";
import { cacheLinePath, formatUsageCount, type UsageDay } from "./usage-types";

/** Dual-axis daily observations with pointer/touch inspection and arrow-key navigation. */
export function UsageChart({ rows }: { rows: UsageDay[] }) {
	const t = useT();
	const gradient = useId();
	const [active, setActive] = useState<number | null>(null);
	const [showTokens, setShowTokens] = useState(true);
	const [showCache, setShowCache] = useState(true);
	const width = 720,
		left = 54,
		right = 660,
		top = 24,
		bottom = 216;
	const maximum = Math.max(1, ...rows.map((row) => row.totalTokens));
	const x = (index: number) => left + (index * (right - left)) / Math.max(1, rows.length - 1);
	const tokenY = (value: number) => bottom - (value / maximum) * (bottom - top);
	const cacheY = (value: number) => bottom - Math.max(0, Math.min(1, value)) * (bottom - top);
	const tokenPath = rows
		.map((row, index) => `${index ? "L" : "M"}${x(index)},${tokenY(row.totalTokens)}`)
		.join(" ");
	const selected = active === null ? null : rows[active];
	const selectedX = active === null ? 0 : x(active);
	return (
		<div className="[--stats-token:#7c3aed] [--stats-cache:#0d9488] dark:[--stats-token:#a78bfa] dark:[--stats-cache:#2dd4bf]">
			<div className="mb-1 flex justify-end gap-4">
				{(
					[
						["tokens", t("usageStatistics.tokensLegend"), showTokens, setShowTokens, "var(--stats-token)"],
						["cache", t("usageStatistics.hitRate"), showCache, setShowCache, "var(--stats-cache)"],
					] as const
				).map(([key, label, visible, toggle, color]) => (
					<button
						key={key}
						type="button"
						aria-pressed={visible}
						onClick={() => toggle(!visible)}
						className={`flex items-center gap-1.5 rounded px-1 py-1 text-ui-11 focus-visible:outline-2 focus-visible:outline-offset-2 ${visible ? "text-ink-dim" : "text-ink-faint opacity-45"}`}
					>
						<span
							className={`h-0.5 w-4 ${key === "cache" ? "border-t-2 border-dashed" : "rounded"}`}
							style={key === "cache" ? { borderColor: color } : { backgroundColor: color }}
						/>
						{label}
					</button>
				))}
			</div>
			<div
				className="relative rounded-lg outline-none focus-visible:ring-2 focus-visible:ring-violet-400/50"
				role="slider"
				tabIndex={0}
				aria-valuemin={0}
				aria-valuemax={Math.max(0, rows.length - 1)}
				aria-valuenow={active ?? Math.max(0, rows.length - 1)}
				aria-valuetext={selected?.date ?? rows.at(-1)?.date ?? "—"}
				aria-label={t("usageStatistics.chartKeyboard")}
				onFocus={() => setActive((previous) => previous ?? Math.max(0, rows.length - 1))}
				onBlur={() => setActive(null)}
				onPointerLeave={() => setActive(null)}
				onKeyDown={(event) => {
					if (event.key === "ArrowLeft" || event.key === "ArrowRight") {
						event.preventDefault();
						setActive((previous) =>
							Math.max(0, Math.min(rows.length - 1, (previous ?? 0) + (event.key === "ArrowRight" ? 1 : -1))),
						);
					} else if (event.key === "Home" || event.key === "End") {
						event.preventDefault();
						setActive(event.key === "Home" ? 0 : Math.max(0, rows.length - 1));
					} else if (event.key === "Escape") setActive(null);
				}}
				onPointerMove={(event) => {
					const bounds = event.currentTarget.getBoundingClientRect();
					const position = ((event.clientX - bounds.left) / bounds.width) * width;
					setActive(
						Math.max(
							0,
							Math.min(rows.length - 1, Math.round(((position - left) / (right - left)) * (rows.length - 1))),
						),
					);
				}}
			>
				<svg
					viewBox={`0 0 ${width} 250`}
					className="w-full"
					role="img"
					aria-label={t("usageStatistics.trend")}
				>
					<title>{t("usageStatistics.trend")}</title>
					<defs>
						<linearGradient id={gradient} x1="0" y1="0" x2="0" y2="1">
							<stop offset="0%" stopColor="var(--stats-token)" stopOpacity="0.15" />
							<stop offset="100%" stopColor="var(--stats-token)" stopOpacity="0.015" />
						</linearGradient>
					</defs>
					{[0, 0.25, 0.5, 0.75, 1].map((fraction) => (
						<g key={fraction}>
							<line
								x1={left}
								x2={right}
								y1={cacheY(fraction)}
								y2={cacheY(fraction)}
								stroke="var(--color-border)"
								strokeDasharray={fraction === 0 ? undefined : "3 5"}
								strokeOpacity="0.65"
							/>
							<text
								x={left - 12}
								y={cacheY(fraction) + 4}
								textAnchor="end"
								fontSize="10"
								fill="var(--color-ink-faint)"
							>
								{formatUsageCount(maximum === 1 ? 0 : maximum * fraction)}
							</text>
							<text x={right + 12} y={cacheY(fraction) + 4} fontSize="10" fill="var(--color-ink-faint)">
								{fraction * 100}%
							</text>
						</g>
					))}
					{showTokens && rows.length > 0 && (
						<>
							<path
								d={`${tokenPath} L${x(rows.length - 1)},${bottom} L${left},${bottom} Z`}
								fill={`url(#${gradient})`}
							/>
							<path
								d={tokenPath}
								fill="none"
								stroke="var(--stats-token)"
								strokeWidth="2.4"
								strokeLinejoin="round"
								strokeLinecap="round"
							/>
						</>
					)}
					{showCache && (
						<path
							d={cacheLinePath(rows, x, cacheY)}
							fill="none"
							stroke="var(--stats-cache)"
							strokeWidth="2"
							strokeDasharray="5 4"
							strokeLinecap="round"
						/>
					)}
					{rows.map((row, index) => (
						<g key={row.date}>
							{showTokens && row.totalTokens > 0 && (
								<circle
									cx={x(index)}
									cy={tokenY(row.totalTokens)}
									r="2.5"
									fill="var(--color-surface)"
									stroke="var(--stats-token)"
									strokeWidth="1.5"
								/>
							)}
							{showCache && row.cacheHitRate != null && (
								<circle
									cx={x(index)}
									cy={cacheY(row.cacheHitRate)}
									r="2.5"
									fill="var(--color-surface)"
									stroke="var(--stats-cache)"
									strokeWidth="1.5"
								/>
							)}
							{[0, Math.floor(rows.length / 2), rows.length - 1].includes(index) && (
								<text x={x(index)} y="241" textAnchor="middle" fontSize="10" fill="var(--color-ink-faint)">
									{row.date.slice(5)}
								</text>
							)}
						</g>
					))}
					{selected && (
						<g>
							<line
								x1={selectedX}
								x2={selectedX}
								y1={top}
								y2={bottom}
								stroke="var(--color-ink-faint)"
								strokeDasharray="3 4"
								strokeOpacity="0.5"
							/>
							{showTokens && (
								<circle
									cx={selectedX}
									cy={tokenY(selected.totalTokens)}
									r="5"
									fill="var(--stats-token)"
									stroke="var(--color-surface)"
									strokeWidth="2"
								/>
							)}
							{showCache && selected.cacheHitRate != null && (
								<circle
									cx={selectedX}
									cy={cacheY(selected.cacheHitRate)}
									r="5"
									fill="var(--stats-cache)"
									stroke="var(--color-surface)"
									strokeWidth="2"
								/>
							)}
						</g>
					)}
				</svg>
				{selected && (
					<div
						role="tooltip"
						className="pointer-events-none absolute top-4 z-10 w-44 rounded-xl border border-border bg-surface px-3 py-2.5 shadow-pop"
						style={{ left: `clamp(8px, ${(selectedX / width) * 100 + 2}%, calc(100% - 184px))` }}
					>
						<p className="mb-2 text-ui-11 text-ink-faint">{selected.date}</p>
						<p className="flex justify-between gap-3 text-ui-12">
							<span className="text-ink-dim">Token</span>
							<strong className="tabular-nums text-ink">{selected.totalTokens.toLocaleString()}</strong>
						</p>
						<p className="mt-1 flex justify-between gap-3 text-ui-12">
							<span className="text-ink-dim">{t("usageStatistics.hitRate")}</span>
							<strong className="tabular-nums text-ink">
								{selected.cacheHitRate == null ? "—" : `${(selected.cacheHitRate * 100).toFixed(1)}%`}
							</strong>
						</p>
						<p className="mt-2 border-t border-border/60 pt-1.5 text-ui-10 text-ink-faint">
							{t("usageStatistics.requestCount", { count: selected.requests })}
						</p>
					</div>
				)}
			</div>
		</div>
	);
}
