import { useT } from "../../../i18n";
import type { UsageDay } from "./usage-types";

/** Calendar cells represent reported tokens, including genuine zero-use days. */
export function UsageHeatmap({
	rows,
	label,
	summary,
}: {
	rows: UsageDay[];
	label: string;
	summary: (row: UsageDay) => string;
}) {
	const t = useT();
	const padding = rows[0] ? (new Date(`${rows[0].date}T12:00:00Z`).getUTCDay() + 6) % 7 : 0;
	const columns = Math.ceil((rows.length + padding) / 7);
	const cell = 19;
	const width = 32 + columns * cell;
	const maximum = Math.max(1, ...rows.map((row) => row.totalTokens));
	return (
		<svg viewBox={`0 0 ${width} 166`} role="img" aria-label={label} className="w-full">
			<title>{label}</title>
			{([0, 2, 4, 6] as const).map((day) => (
				<text key={day} x={0} y={36 + day * cell} fontSize={9} fill="var(--color-ink-faint)">
					{t(`scheduled.days.${day}`)}
				</text>
			))}
			{rows.map((row, index) => {
				const column = Math.floor((index + padding) / 7),
					day = (index + padding) % 7;
				return (
					<g key={row.date}>
						{(index === 0 || row.date.endsWith("-01")) && (
							<text x={32 + column * cell} y={12} fontSize={9} fill="var(--color-ink-faint)">
								{row.date.slice(5, 7)}
							</text>
						)}
						<rect
							x={32 + column * cell}
							y={24 + day * cell}
							width={15}
							height={15}
							rx={3}
							fill={
								row.totalTokens
									? `rgba(139,92,246,${0.2 + Math.sqrt(row.totalTokens / maximum) * 0.8})`
									: "var(--color-hover)"
							}
						>
							<title>{summary(row)}</title>
						</rect>
					</g>
				);
			})}
		</svg>
	);
}
