import { useEffect, useRef, useState } from "react";
import { useT } from "../../i18n";
import type { PermissionPolicy } from "../../stores/permission-policy";
import { CheckIcon } from "../icons";
import { ConfirmPolicyIcon, HumanPolicyIcon, YoloPolicyIcon } from "./PermissionPolicyIcons";

const POLICIES = ["human", "confirm", "yolo"] as const satisfies readonly PermissionPolicy[];
const POLICY_ICONS = { human: HumanPolicyIcon, confirm: ConfirmPolicyIcon, yolo: YoloPolicyIcon };

/**
 * 受控权限策略选择器，onPolicyChange 原样返回 human/confirm/yolo。
 * 仅负责展示与交互，选择不会调用权限或执行接口。
 */
export function PermissionPicker({
	policy,
	onPolicyChange,
}: {
	policy: PermissionPolicy;
	onPolicyChange: (policy: PermissionPolicy) => void;
}) {
	const t = useT();
	const [open, setOpen] = useState(false);
	const ref = useRef<HTMLDivElement>(null);
	const triggerRef = useRef<HTMLButtonElement>(null);
	const PolicyIcon = POLICY_ICONS[policy];

	useEffect(() => {
		if (!open) return;
		ref.current?.querySelector<HTMLButtonElement>('[aria-checked="true"]')?.focus();
		const onPointerDown = (event: PointerEvent) => {
			if (ref.current && !ref.current.contains(event.target as Node)) setOpen(false);
		};
		const onKeyDown = (event: KeyboardEvent) => {
			if (event.key !== "Escape") return;
			setOpen(false);
			triggerRef.current?.focus();
		};
		window.addEventListener("pointerdown", onPointerDown);
		window.addEventListener("keydown", onKeyDown);
		return () => {
			window.removeEventListener("pointerdown", onPointerDown);
			window.removeEventListener("keydown", onKeyDown);
		};
	}, [open]);

	return (
		<div ref={ref} className="relative">
			<button
				ref={triggerRef}
				type="button"
				className="flex items-center gap-1 whitespace-nowrap rounded-full px-2.5 py-1 text-ui-14 leading-[calc(1_/_0.75)] text-ink-dim transition-colors hover:bg-hover hover:text-ink"
				aria-label={t("composer.permissionMode")}
				aria-haspopup="menu"
				aria-expanded={open}
				onClick={() => setOpen((value) => !value)}
			>
				<PolicyIcon size={14} className={policy === "yolo" ? "text-warn" : undefined} />
				<span>{t(`composer.permissionPolicies.${policy}.title`)}</span>
			</button>
			{open && (
				<div
					role="menu"
					aria-label={t("composer.permissionMode")}
					data-composer-overlay=""
					className="absolute bottom-full left-0 z-30 mb-1 w-64 rounded-xl bg-surface p-1 shadow-pop"
					onKeyDown={(event) => {
						if (!["ArrowDown", "ArrowUp", "Home", "End"].includes(event.key)) return;
						event.preventDefault();
						const items = [...event.currentTarget.querySelectorAll<HTMLButtonElement>("button")];
						const focused = document.activeElement;
						const current = focused instanceof HTMLButtonElement ? items.indexOf(focused) : 0;
						const next =
							event.key === "Home"
								? 0
								: event.key === "End"
									? items.length - 1
									: (current + (event.key === "ArrowDown" ? 1 : -1) + items.length) % items.length;
						items[next]?.focus();
					}}
				>
					{POLICIES.map((value) => {
						const Icon = POLICY_ICONS[value];
						return (
							<button
								key={value}
								type="button"
								role="menuitemradio"
								aria-checked={policy === value}
								className="flex w-full items-start gap-2 rounded-lg px-2 py-1.5 text-left text-ink-2 transition-colors hover:bg-hover"
								onClick={() => {
									onPolicyChange(value);
									setOpen(false);
									triggerRef.current?.focus();
								}}
							>
								<Icon
									size={14}
									className={`mt-0.5 shrink-0 ${value === "yolo" ? "text-warn" : "text-ink-dim"}`}
								/>
								<span className="min-w-0 flex-1">
									<span className="block text-ui-12 font-medium">
										{t(`composer.permissionPolicies.${value}.title`)}
									</span>
									<span className="mt-0.5 block text-ui-11 leading-relaxed text-ink-faint">
										{t(`composer.permissionPolicies.${value}.description`)}
									</span>
								</span>
								{policy === value && <CheckIcon size={12} className="mt-1 shrink-0" />}
							</button>
						);
					})}
				</div>
			)}
		</div>
	);
}
