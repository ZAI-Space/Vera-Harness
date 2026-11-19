import type { Translate } from "../../i18n";
import type { ScheduledTask } from "./model";
import { formatScheduleClock, intervalAmount } from "./scheduled-format";

/** 只描述保存的调度意图，不计算或声称已经安排下一次执行。 */
export function scheduleLabel(task: ScheduledTask, t: Translate): string {
	if (task.cadence === "interval") {
		const amount = intervalAmount(task.schedule?.intervalMinutes);
		return amount
			? t("scheduled.everyInterval", { count: amount.value, unit: t(`scheduled.units.${amount.unit}`) })
			: t("scheduled.cadences.interval");
	}
	const cadence = t(`scheduled.cadences.${task.cadence}`);
	const clock = formatScheduleClock(task.schedule);
	if (task.cadence === "weekly") {
		const days = (task.schedule?.weekdays ?? [task.schedule?.weekday ?? 0]).map((day) =>
			t(`scheduled.days.${day as 0 | 1 | 2 | 3 | 4 | 5 | 6}`),
		);
		return `${cadence} · ${days.join(" / ")} · ${clock ?? ""}`;
	}
	return task.cadence === "daily" && clock ? `${cadence} · ${clock}` : cadence;
}
