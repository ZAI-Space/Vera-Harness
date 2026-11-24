import { type ReactNode, useEffect, useRef } from "react";
import { createPortal } from "react-dom";
import { useT } from "../../i18n";
import { CloseIcon } from "../icons";

/** Viewport-bound dialog with an independent scroll area and keyboard focus containment. */
export function Modal({
	title,
	onClose,
	children,
	showHeader = true,
}: {
	title: string;
	onClose: () => void;
	children: ReactNode;
	showHeader?: boolean;
}) {
	const t = useT();
	const ref = useRef<HTMLDivElement>(null);
	useEffect(() => {
		const previous = document.activeElement as HTMLElement | null;
		ref.current?.focus();
		return () => previous?.focus();
	}, []);
	useEffect(() => {
		const onKeyDown = (event: KeyboardEvent) => {
			const dialog = ref.current;
			// Nested confirmations own the keyboard until they close, including when
			// their focused button unmounts and focus returns to the document body.
			if (!dialog || [...document.querySelectorAll('[role="dialog"]')].at(-1) !== dialog) return;
			if (event.key === "Escape" && !event.isComposing) {
				event.stopImmediatePropagation();
				onClose();
			}
			if (event.key !== "Tab") return;
			const controls = [
				...dialog.querySelectorAll<HTMLElement>(
					'a[href], button:not(:disabled), input:not(:disabled), textarea:not(:disabled), select:not(:disabled), [contenteditable="true"], [tabindex="0"]',
				),
			];
			const first = controls[0],
				last = controls.at(-1);
			const outside = !dialog.contains(document.activeElement) || document.activeElement === dialog;
			if (event.shiftKey && (outside || document.activeElement === first)) {
				event.preventDefault();
				last?.focus();
			} else if (!event.shiftKey && (outside || document.activeElement === last)) {
				event.preventDefault();
				first?.focus();
			}
		};
		window.addEventListener("keydown", onKeyDown, true);
		return () => window.removeEventListener("keydown", onKeyDown, true);
	}, [onClose]);
	const content = (
		<div
			className="fixed inset-0 z-50 flex items-center justify-center bg-ink/30 p-4"
			data-modal-overlay
			onPointerDown={(event) => {
				if (event.target === event.currentTarget) onClose();
			}}
		>
			<div
				ref={ref}
				tabIndex={-1}
				role="dialog"
				aria-modal="true"
				aria-label={title}
				className="flex max-h-[85vh] w-[680px] max-w-full flex-col overflow-hidden rounded-2xl bg-surface shadow-dialog outline-none"
			>
				{showHeader && (
					<header className="flex shrink-0 items-center justify-between border-b border-border px-5 py-4">
						<h2 className="text-ui-16 font-semibold text-ink">{title}</h2>
						<button
							type="button"
							aria-label={t("common.close")}
							className="rounded-lg p-2 text-ink-faint hover:bg-hover"
							onClick={onClose}
						>
							<CloseIcon size={14} />
						</button>
					</header>
				)}
				<div className={`min-h-0 overflow-y-auto ${showHeader ? "p-5" : ""}`}>{children}</div>
			</div>
		</div>
	);
	return createPortal(content, document.body);
}
