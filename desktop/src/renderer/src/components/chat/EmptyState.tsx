import { useEffect } from "react";
import { useT } from "../../i18n";
import { useProjectsStore } from "../../stores/projects";
import { Composer } from "../composer/Composer";
import { ProjectBranchPicker } from "../session/ProjectBranchPicker";

/** 空态：居中 slogan、输入框与项目/分支选择。 */
export function EmptyState() {
	const t = useT();
	const load = useProjectsStore((s) => s.load);

	useEffect(() => {
		void load();
	}, [load]);

	return (
		<div className="flex h-full flex-col items-center justify-center gap-8 px-8 pb-[8vh]">
			<div className="flex min-h-20 w-full max-w-[760px] items-center justify-center min-[721px]:mb-2 min-[721px]:min-h-24">
				<h1 className="empty-state-slogan text-center text-ui-28 min-[721px]:text-ui-32 leading-[1.15] tracking-[-0.035em] text-ink">
					<span>{t("emptyState.sloganLead")}</span>{" "}
					<span className="empty-state-slogan-brand">{t("emptyState.sloganBrand")}</span>
				</h1>
			</div>
			<Composer centered />
			<ProjectBranchPicker />
		</div>
	);
}
