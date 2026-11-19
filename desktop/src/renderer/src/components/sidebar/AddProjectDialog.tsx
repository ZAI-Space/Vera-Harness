import { createPortal } from "react-dom";
import { useT } from "../../i18n";
import { useProjectsStore } from "../../stores/projects";
import { Button } from "../ui/Button";

export function AddProjectDialog({
	onClose,
	onLocalProject,
}: {
	onClose: () => void;
	onLocalProject?: () => Promise<void>;
}) {
	const t = useT();
	return createPortal(
		<div
			role="dialog"
			aria-modal
			aria-label={t("sidebar.addProject")}
			className="fixed inset-0 z-40 flex items-center justify-center bg-ink/20"
		>
			<div className="w-[360px] max-w-[calc(100vw-32px)] rounded-xl bg-surface p-5 shadow-dialog">
				<h2 className="text-ui-14 font-semibold text-ink">{t("sidebar.addProject")}</h2>
				<div className="mt-4 flex justify-end gap-2">
					<Button onClick={onClose}>{t("common.cancel")}</Button>
					<Button
						onClick={() => {
							onClose();
							void (onLocalProject ? onLocalProject() : useProjectsStore.getState().addProject());
						}}
					>
						{t("environment.localProject")}
					</Button>
				</div>
			</div>
		</div>,
		document.body,
	);
}
