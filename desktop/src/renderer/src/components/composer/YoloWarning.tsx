import { useT } from "../../i18n";
import { ConfirmDialog } from "../ui/ConfirmDialog";

/** Explicit acknowledgement before enabling automatic tool execution. */
export function YoloWarning({ onConfirm, onCancel }: { onConfirm: () => void; onCancel: () => void }) {
	const t = useT();
	return (
		<ConfirmDialog
			title={t("behavior.yoloTitle")}
			description={t("behavior.yoloWarning")}
			confirmLabel={t("behavior.yoloConfirm")}
			cancelLabel={t("common.cancel")}
			danger
			onCancel={onCancel}
			onConfirm={onConfirm}
		/>
	);
}
